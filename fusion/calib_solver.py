"""
fusion/calib_solver.py — Fase 3: solver de registración + veredictos.

Toma las estadísticas del colector (Fase 2), aplica reglas de validez y emite,
por sensor, el bloque `registration` PROPUESTO con su veredicto. No aplica nada:
el offset queda con enabled=false hasta que el operador lo habilite (Fase 4/6).

Uso:
  python fusion/calib_solver.py <pcap>                 # corre colector + solver
  python fusion/calib_solver.py --json reporte.json    # solver sobre JSON ya hecho
  [--out propuestas.json] [--bucket 1.0]
"""
import os
import sys
import math
import json
import argparse
from dataclasses import dataclass

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from fusion.calib_collector import recolectar
from utils.geo import cargar_sensores


@dataclass
class SolverConfig:
    n_min: int = 100               # muestras mínimas
    cov_min_pct: float = 50.0      # cobertura de azimut mínima
    sigma_az_max: float = 0.5      # dispersión máxima aceptable (grados)
    sigma_rng_max: float = 0.5     # dispersión máxima aceptable (NM)
    z_signif: float = 3.0          # nº de sigmas para considerar el sesgo real
    min_off_az: float = 0.05       # offset por debajo del cual se considera alineado (deg)
    min_off_rng: float = 0.05      # idem en rango (NM)


def _significativo(bias, sigma, n, z):
    """El sesgo es real si supera z veces la incertidumbre de la mediana (sigma/sqrt(n))."""
    if n <= 0:
        return False
    err = (sigma or 0.0) / math.sqrt(n)
    return abs(bias) > z * err


def proponer(s, cfg: SolverConfig) -> dict:
    n = s['n']
    cov = s['coverage_az_pct']
    d_az, d_rng = s['d_az_deg'], s['d_rng_nm']
    sg_az, sg_rng = s['sigma_az_deg'], s['sigma_rng_nm']

    # Veredicto
    if n < cfg.n_min:
        verdict = 'insufficient_samples'
    elif cov < cfg.cov_min_pct:
        verdict = 'low_coverage'
    elif sg_az > cfg.sigma_az_max or sg_rng > cfg.sigma_rng_max:
        verdict = 'high_residual'
    else:
        sig_az = _significativo(d_az, sg_az, n, cfg.z_signif) and abs(d_az) >= cfg.min_off_az
        sig_rng = _significativo(d_rng, sg_rng, n, cfg.z_signif) and abs(d_rng) >= cfg.min_off_rng
        verdict = 'applicable' if (sig_az or sig_rng) else 'aligned'

    # Fuente y si la corrección es absoluta (ADS-B) o relativa (consenso/inter-radar)
    ref = s['ref']
    es_adsb = ref.get('adsb', 0) >= ref.get('consenso', 0) and ref.get('adsb', 0) > 0
    source = 'adsb' if es_adsb else 'interradar'

    # Residual antes/después por componente (después = sigma; antes = sqrt(bias^2+sigma^2))
    res_az_before = round(math.hypot(d_az, sg_az), 3)
    res_rng_before = round(math.hypot(d_rng, sg_rng), 3)

    aplica = verdict == 'applicable'
    return {
        'sac_sic': s['sac_sic'],
        'registration': {
            'azimuth_offset_deg': round(d_az, 3) if aplica else 0.0,
            'range_offset_nm': round(d_rng, 3) if aplica else 0.0,
            'range_scale': 1.0,
            'enabled': False,
            'source': source,
            'absolute': es_adsb,
            'stats': {
                'n': n,
                'coverage_az_pct': cov,
                'sigma_az_deg': sg_az,
                'sigma_rng_nm': sg_rng,
                'residual_az_before': res_az_before, 'residual_az_after': sg_az,
                'residual_rng_before': res_rng_before, 'residual_rng_after': sg_rng,
            },
            'verdict': verdict,
        }
    }


def evaluar(report, cfg: SolverConfig = None):
    cfg = cfg or SolverConfig()
    return {'run': report['run'],
            'proposals': [proponer(s, cfg) for s in report['sensors']]}


def _imprimir(prop):
    print(f"\nPROPUESTAS DE REGISTRACION - {prop['run']['pcap']} ({prop['run']['duration_s']} s)")
    print(f"{'SENSOR':9} {'N':>5} {'COB':>5} {'dAZ_deg':>8} {'dRNG_NM':>8} {'ABS':>4}  VEREDICTO")
    cont = {}
    for p in prop['proposals']:
        r = p['registration']; st = r['stats']; v = r['verdict']
        cont[v] = cont.get(v, 0) + 1
        print(f"{p['sac_sic']:9} {st['n']:>5} {st['coverage_az_pct']:>4.0f}% "
              f"{r['azimuth_offset_deg']:>+8.2f} {r['range_offset_nm']:>+8.2f} "
              f"{'si' if r['absolute'] else 'rel':>4}  {v}")
    print("\nRESUMEN: " + " | ".join(f"{k}:{n}" for k, n in sorted(cont.items())))
    print("NOTA: source=interradar es RELATIVO (alinea al grupo); el ajuste absoluto")
    print("      requiere anclar con ADS-B en la Fase 5 (LSQ de red).")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('pcap', nargs='?', help='archivo pcap (corre colector+solver)')
    ap.add_argument('--json', help='reporte JSON del colector (en vez de pcap)')
    ap.add_argument('--bucket', type=float, default=1.0)
    ap.add_argument('--out', default=None)
    args = ap.parse_args()

    if args.json:
        with open(args.json, encoding='utf-8') as f:
            report = json.load(f)
    elif args.pcap:
        report = recolectar(args.pcap, cargar_sensores('default-site-params'), bucket=args.bucket)
    else:
        ap.error('indicar <pcap> o --json')

    prop = evaluar(report)
    _imprimir(prop)
    if args.out:
        with open(args.out, 'w', encoding='utf-8') as f:
            json.dump(prop, f, indent=2, ensure_ascii=False)
        print(f"Propuestas JSON: {args.out}")


if __name__ == '__main__':
    main()
