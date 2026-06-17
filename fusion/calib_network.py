"""
fusion/calib_network.py — Fase 5: ajuste de registración por red, anclado en ADS-B.

Resuelve simultáneamente el sesgo de azimut (Δθ) y rango (Δρ) de TODOS los
sensores a partir de aviones vistos por varios a la vez. Modelo de observación
(posición medida = verdad + J·sesgo), con la verdad por cluster como incógnita
nuisance: donde hay ADS-B, ancla absoluta; donde no, queda relativa al grupo.

Producto: un reporte con el MISMO formato que el colector (Fase 2), para reusar
el veredicto (Fase 3) y la aplicación opt-in (Fase 4). Los offsets de red son de
mejor calidad y absolutos donde la red alcanza un ancla ADS-B.

Uso:
  python fusion/calib_network.py <pcap> [--bucket 1.0] [--iter 8] [--out prop.json]
"""
import os
import sys
import math
import argparse
from collections import defaultdict

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from decoder.data_engine import DataEngine
from utils.geo import cargar_sensores, StereographicLocal, METERS_PER_NM
from fusion.calib_collector import construir_clusters, N_SECTORES
from fusion.calib_solver import evaluar, _imprimir as _imprimir_prop

MAX_RES_M = 15.0 * METERS_PER_NM   # descarte grueso de reportes mal correlacionados


def _mediana(v):
    v = sorted(v); n = len(v)
    return None if n == 0 else (v[n // 2] if n % 2 else 0.5 * (v[n // 2 - 1] + v[n // 2]))


def resolver_red(pcap, sensores, bucket=1.0, iteraciones=8, progress_cb=None):
    eng = DataEngine(sensores=sensores)
    if progress_cb is not None:
        eng.on_progress = progress_cb
    pcap_label = (os.path.basename(pcap) if isinstance(pcap, str)
                  else ", ".join(os.path.basename(p) for p in pcap))
    plots, dur, _ = eng.scan_pcap(pcap)
    clusters = construir_clusters(plots, sensores, bucket=bucket)
    if not clusters:
        return {'run': {'pcap': pcap_label, 'duration_s': round(dur, 1)}, 'sensors': []}

    # Marco común conforme centrado en el centroide de los reportes
    lats = [r['lat'] for c in clusters for r in c['reports']]
    lons = [r['lon'] for c in clusters for r in c['reports']]
    proy = StereographicLocal(); proy.set_center(_mediana(lats), _mediana(lons))

    # Precomputar geometría de cada reporte
    cl = []  # lista de clusters: {'T_adsb': np2|None, 'reps':[{sensor,p,J,theta,rho}]}
    for c in clusters:
        reps = []
        for r in c['reports']:
            px, py = proy.latlon_to_xy(r['lat'], r['lon'])
            th = math.radians(r['theta']); rho = r['rho_g']
            # Sesgo = [Δρ0 (bias a rango cero), Δθ (azimut), g (ganancia de rango)].
            # La ganancia aporta un desplazamiento radial proporcional al rango:
            # g·ρ en la dirección [sinθ, cosθ] (ICAO §3.2.32 b).
            J = np.array([[math.sin(th), rho * math.cos(th), rho * math.sin(th)],
                          [math.cos(th), -rho * math.sin(th), rho * math.cos(th)]])
            reps.append({'s': r['sac_sic'], 'p': np.array([px, py]), 'J': J,
                         'theta': r['theta'], 'rho': rho})
        T_adsb = None
        if c['adsb']:
            ax, ay = proy.latlon_to_xy(c['adsb'][0], c['adsb'][1])
            T_adsb = np.array([ax, ay])
        cl.append({'T_adsb': T_adsb, 'reps': reps})

    sensores_set = {rp['s'] for c in cl for rp in c['reps']}
    b = {s: np.zeros(3) for s in sensores_set}   # [Δρ0_m, Δθ_rad, g_adim]

    # Iteración: (1) estimar verdad T_k por cluster; (2) resolver sesgo por sensor
    for _ in range(iteraciones):
        T = []
        for c in cl:
            if c['T_adsb'] is not None:
                T.append(c['T_adsb'])
            else:
                corr = [rp['p'] - rp['J'] @ b[rp['s']] for rp in c['reps']]
                T.append(np.mean(corr, axis=0))
        AT = {s: np.zeros((3, 3)) for s in sensores_set}
        rhs = {s: np.zeros(3) for s in sensores_set}
        for c, Tk in zip(cl, T):
            for rp in c['reps']:
                d = rp['p'] - Tk
                if np.hypot(*d) > MAX_RES_M:
                    continue
                AT[rp['s']] += rp['J'].T @ rp['J']
                rhs[rp['s']] += rp['J'].T @ d
        for s in sensores_set:
            try:
                b[s] = np.linalg.solve(AT[s] + 1e-6 * np.eye(3), rhs[s])
            except np.linalg.LinAlgError:
                pass

    # Residuales finales + estadística por sensor (descomponer en rango/azimut)
    T = []
    for c in cl:
        if c['T_adsb'] is not None:
            T.append(c['T_adsb'])
        else:
            T.append(np.mean([rp['p'] - rp['J'] @ b[rp['s']] for rp in c['reps']], axis=0))

    acc = defaultdict(lambda: {'rng': [], 'az': [], 'sec': set(), 'anchor': 0, 'rel': 0})
    for c, Tk in zip(cl, T):
        anchored = c['T_adsb'] is not None
        for rp in c['reps']:
            resid = rp['p'] - Tk - rp['J'] @ b[rp['s']]
            if np.hypot(*resid) > MAX_RES_M:
                continue
            th = math.radians(rp['theta'])
            radial = resid[0] * math.sin(th) + resid[1] * math.cos(th)        # m
            tang = resid[0] * math.cos(th) - resid[1] * math.sin(th)          # m
            a = acc[rp['s']]
            a['rng'].append(radial / METERS_PER_NM)
            a['az'].append(math.degrees(tang / rp['rho']) if rp['rho'] > 1 else 0.0)
            a['sec'].add(int(rp['theta'] // (360.0 / N_SECTORES)) % N_SECTORES)
            a['anchor' if anchored else 'rel'] += 1

    sensors_out = []
    for s in sorted(b.keys()):
        a = acc[s]
        n = len(a['rng'])
        if n == 0:
            continue
        d_rng = b[s][0] / METERS_PER_NM            # NM (bias de rango a rango cero)
        d_az = math.degrees(b[s][1])               # grados (bias de azimut)
        range_gain = b[s][2]                       # adimensional (m/m), ICAO §3.2.32 b
        sg_rng = _mediana([abs(x) for x in a['rng']]) or 0.0
        sg_az = _mediana([abs(x) for x in a['az']]) or 0.0
        sensors_out.append({
            'sac_sic': s, 'n': n,
            'coverage_az_pct': round(100.0 * len(a['sec']) / N_SECTORES, 1),
            'd_az_deg': round(d_az, 3), 'd_rng_nm': round(d_rng, 3),
            'range_gain': round(range_gain, 6),
            'sigma_az_deg': round(1.4826 * sg_az, 3),
            'sigma_rng_nm': round(1.4826 * sg_rng, 3),
            'ref': {'adsb': a['anchor'], 'consenso': a['rel']},
            'per_sector': [],
        })
    return {'run': {'pcap': pcap_label, 'duration_s': round(dur, 1),
                    'method': 'network_lsq', 'iter': iteraciones}, 'sensors': sensors_out}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('pcap')
    ap.add_argument('--bucket', type=float, default=1.0)
    ap.add_argument('--iter', type=int, default=8)
    ap.add_argument('--out', default=None)
    args = ap.parse_args()

    sensores = cargar_sensores('default-site-params')
    report = resolver_red(args.pcap, sensores, bucket=args.bucket, iteraciones=args.iter)
    prop = evaluar(report)
    print(f"(LSQ de red, {args.iter} iteraciones)")
    _imprimir_prop(prop)
    if args.out:
        import json
        with open(args.out, 'w', encoding='utf-8') as f:
            json.dump(prop, f, indent=2, ensure_ascii=False)
        print(f"Propuestas JSON: {args.out}")


if __name__ == '__main__':
    main()
