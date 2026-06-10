"""
fusion/calib_collector.py — Fase 2: colector de muestras de registración (offline).

Corre sobre los plots de DataEngine.scan_pcap y genera, por sensor, residuales de
azimut y rango respecto de una "verdad" co-temporal del mismo avión:
  - verdad ABSOLUTA   = ADS-B (CAT21) del mismo Mode S, si está disponible.
  - verdad RELATIVA   = consenso (mediana) de los OTROS radares que ven el avión,
                        cuando no hay ADS-B. Alinea cada radar al grupo (reduce el
                        desacuerdo inter-sensor, que es lo que rompe la fusión).

No modifica el motor ni aplica nada: solo mide y reporta. La estimación/veredicto
robusto y la propuesta del bloque `registration` son de la Fase 3.

Uso:  python fusion/calib_collector.py <pcap> [--bucket 1.0] [--out reporte.json]
"""
import os
import sys
import math
import json
import argparse
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from decoder.data_engine import DataEngine
from utils.geo import cargar_sensores, WGS84_GEOD, METERS_PER_NM

FT_A_M = 0.3048
N_SECTORES = 36                  # bins de azimut de 10°
DT_TOL = 0.5                     # tolerancia de bucket temporal (s)


def _key_aeronave(p):
    """Clave de agrupación: Mode S si hay, si no squawk discreto."""
    ms = (p.mode_s or "").strip().upper()
    if ms and ms != "----":
        return ("MS", ms)
    m = p.mode3a
    s = f"{m:04o}" if isinstance(m, int) else str(m or "").strip()
    if s and s not in ("----", "0000", "1200", "2000", "7000"):
        return ("SQ", s)
    return None


def _alt_m(p):
    if p.altitude_ft is not None:
        return p.altitude_ft * FT_A_M
    if p.flight_level is not None:
        return p.flight_level * 100.0 * FT_A_M
    return None


def _mediana(vals):
    v = sorted(vals)
    n = len(v)
    if n == 0:
        return None
    return v[n // 2] if n % 2 else 0.5 * (v[n // 2 - 1] + v[n // 2])


def _mad(vals, centro):
    """Desviación absoluta mediana (robusta) escalada a sigma."""
    if not vals:
        return None
    desv = [abs(x - centro) for x in vals]
    return 1.4826 * _mediana(desv)


def _wrap180(a):
    return (a + 180.0) % 360.0 - 180.0


def recolectar(pcap, sensores, bucket=1.0):
    eng = DataEngine(sensores=sensores)
    plots, dur, _ = eng.scan_pcap(pcap)

    # 1. Agrupar reportes por (avión, bucket temporal)
    grupos = defaultdict(list)
    for p in plots:
        if p.lat is None or p.lon is None:
            continue
        if p.category not in (21, 48):
            continue
        k = _key_aeronave(p)
        if k is None:
            continue
        tb = round(p.time / bucket)
        grupos[(k, tb)].append(p)

    # 2. Por bucket con ≥2 reportes: definir verdad y medir residual de cada radar
    # acumulador[sac_sic] = { 'sectores': {sec: {'daz':[], 'drng':[]}}, 'ref': {'adsb':n,'consenso':n} }
    acc = defaultdict(lambda: {'sectores': defaultdict(lambda: {'daz': [], 'drng': []}),
                               'ref': {'adsb': 0, 'consenso': 0}})

    for (k, tb), reps in grupos.items():
        radares = [p for p in reps if p.category == 48 and p.raw_range and p.raw_azimuth]
        adsb = [p for p in reps if p.category == 21]
        if not radares:
            continue

        # Verdad absoluta (ADS-B) o relativa (consenso de radares)
        if adsb:
            tlat = _mediana([p.lat for p in adsb])
            tlon = _mediana([p.lon for p in adsb])
            ref_tipo = 'adsb'
        elif len(radares) >= 2:
            tlat = _mediana([p.lat for p in radares])
            tlon = _mediana([p.lon for p in radares])
            ref_tipo = 'consenso'
        else:
            continue

        for p in radares:
            sac_sic = p.sac_sic
            info = sensores.get(_sac_sic_tuple(sac_sic))
            if not info or info.get('lat') is None:
                continue
            slat, slon = info['lat'], info['lon']

            # Verdad: si es consenso, excluir el propio sensor para no auto-sesgar
            if ref_tipo == 'consenso':
                otros = [q for q in radares if q.sac_sic != sac_sic]
                if not otros:
                    continue
                vlat = _mediana([q.lat for q in otros])
                vlon = _mediana([q.lon for q in otros])
            else:
                vlat, vlon = tlat, tlon

            # Polar de la verdad desde el sensor
            az_t, _, d_t = WGS84_GEOD.inv(slon, slat, vlon, vlat)
            az_t %= 360.0

            # Polar medido por el radar (raw), corregido slant->ground con la altitud
            theta_m = p.raw_azimuth % 360.0
            rho_slant_m = p.raw_range * METERS_PER_NM
            alt = _alt_m(p)
            if alt is not None and rho_slant_m > alt:
                rho_ground_m = math.sqrt(rho_slant_m ** 2 - alt ** 2)
            else:
                rho_ground_m = rho_slant_m

            daz = _wrap180(theta_m - az_t)            # grados
            drng = (rho_ground_m - d_t) / METERS_PER_NM  # NM

            # Filtro grueso de outliers brutos (correlación dudosa)
            if abs(daz) > 10.0 or abs(drng) > 10.0:
                continue

            sec = int(theta_m // (360.0 / N_SECTORES)) % N_SECTORES
            a = acc[sac_sic]
            a['sectores'][sec]['daz'].append(daz)
            a['sectores'][sec]['drng'].append(drng)
            a['ref'][ref_tipo] += 1

    return _resumir(acc, pcap, dur)


def _sac_sic_tuple(sac_sic):
    try:
        a, b = sac_sic.split('/')
        return (int(a), int(b))
    except (ValueError, AttributeError):
        return None


def _resumir(acc, pcap, dur):
    sensores_out = []
    for sac_sic, a in sorted(acc.items()):
        daz_all, drng_all, per_sector = [], [], []
        sectores_con_dato = 0
        for sec in range(N_SECTORES):
            s = a['sectores'].get(sec)
            if not s or not s['daz']:
                continue
            sectores_con_dato += 1
            md_az = _mediana(s['daz'])
            md_rng = _mediana(s['drng'])
            daz_all.extend(s['daz'])
            drng_all.extend(s['drng'])
            per_sector.append({'az': sec * (360 // N_SECTORES), 'n': len(s['daz']),
                               'd_az': round(md_az, 3), 'd_rng': round(md_rng, 3)})
        n = len(daz_all)
        if n == 0:
            continue
        c_az = _mediana(daz_all)
        c_rng = _mediana(drng_all)
        sensores_out.append({
            'sac_sic': sac_sic,
            'n': n,
            'coverage_az_pct': round(100.0 * sectores_con_dato / N_SECTORES, 1),
            'd_az_deg': round(c_az, 3),
            'd_rng_nm': round(c_rng, 3),
            'sigma_az_deg': round(_mad(daz_all, c_az) or 0.0, 3),
            'sigma_rng_nm': round(_mad(drng_all, c_rng) or 0.0, 3),
            'ref': a['ref'],
            'per_sector': per_sector,
        })
    return {'run': {'pcap': os.path.basename(pcap), 'duration_s': round(dur, 1)},
            'sensors': sensores_out}


def _imprimir(rep):
    print(f"\nCOLECTOR DE REGISTRACION - {rep['run']['pcap']} ({rep['run']['duration_s']} s)")
    print(f"{'SENSOR':9} {'N':>5} {'COBAZ':>6} {'dAZ_deg':>8} {'dRNG_NM':>8} {'sAZ':>6} {'sRNG':>6}  REF")
    for s in rep['sensors']:
        ref = s['ref']
        print(f"{s['sac_sic']:9} {s['n']:>5} {s['coverage_az_pct']:>5.0f}% "
              f"{s['d_az_deg']:>+8.2f} {s['d_rng_nm']:>+8.2f} "
              f"{s['sigma_az_deg']:>6.2f} {s['sigma_rng_nm']:>6.2f}  "
              f"adsb:{ref['adsb']} cons:{ref['consenso']}")
    print(f"\nTotal sensores con muestra: {len(rep['sensors'])}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('pcap')
    ap.add_argument('--bucket', type=float, default=1.0, help='tamaño de bucket temporal (s)')
    ap.add_argument('--out', default=None, help='ruta JSON de salida')
    args = ap.parse_args()

    sensores = cargar_sensores('default-site-params')
    rep = recolectar(args.pcap, sensores, bucket=args.bucket)
    _imprimir(rep)
    if args.out:
        with open(args.out, 'w', encoding='utf-8') as f:
            json.dump(rep, f, indent=2, ensure_ascii=False)
        print(f"Reporte JSON: {args.out}")


if __name__ == '__main__':
    main()
