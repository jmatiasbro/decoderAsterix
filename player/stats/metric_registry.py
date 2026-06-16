"""Catálogo declarativo de métricas/dimensiones y agregación en Python puro.

aggregate(rows, metric, dimension) -> list[(label, value)] ordenado desc por valor.
"""
from dataclasses import dataclass
import time as _time

import numpy as np


@dataclass(frozen=True)
class Metric:
    id: str
    label: str
    column: str          # campo fuente; "" para count
    agg: str             # "count" | "avg" | "p95"
    dims: tuple           # ids de dimensión admitidos


ALL_DIMS = ("radar", "hour", "mode3a", "fl_band", "category", "callsign", "mode_s", "garbled")


METRICS = [
    Metric("count",     "Nº detecciones",   "",          "count", ALL_DIMS),
    Metric("avg_range", "Rango medio (NM)", "raw_range", "avg",   ALL_DIMS),
    Metric("p95_range", "Rango p95 (NM)",   "raw_range", "p95",   ALL_DIMS),
    Metric("raw_azimuth", "Azimut (°)", "raw_azimuth", "avg", ALL_DIMS),
    Metric("raw_range", "Rango (NM)", "raw_range", "avg", ALL_DIMS),
    Metric("timestamp", "Tiempo (s)", "timestamp", "avg", ALL_DIMS),
    Metric("altitude_ft", "Modo C / Altitud (ft)", "altitude_ft", "avg", ALL_DIMS),
    Metric("mode3a", "Modo A / SSR (Código)", "mode3a", "count", ALL_DIMS),
    Metric("pd", "Probabilidad de Detección (Pd, %)", "pd", "avg", ALL_DIMS),
    Metric("garbled", "Garbling", "garbled", "avg", ALL_DIMS),
    Metric("sac_sic", "SIC/SAC", "sac_sic", "count", ALL_DIMS),
    Metric("mode_s", "Aircraft Address (Mode S)", "mode_s", "count", ALL_DIMS),
    Metric("callsign", "Callsign", "callsign", "count", ALL_DIMS),
    Metric("lat", "Latitud (°)", "lat", "avg", ALL_DIMS),
    Metric("lon", "Longitud (°)", "lon", "avg", ALL_DIMS),
    Metric("frequency", "Frecuencia (MHz)", "frequency", "avg", ALL_DIMS),
]


def metric_by_id(mid):
    for m in METRICS:
        if m.id == mid:
            return m
    raise KeyError(mid)


def _hour_bucket(row):
    ts = row.get("timestamp")
    if ts is None:
        return "—"
    return _time.strftime("%H:00", _time.gmtime(ts))


def _fl_band(row):
    from analysis.coverage import classify_fl
    b = classify_fl(row.get("flight_level"))
    return f"FL{b}" if b is not None else "—"


DIMENSIONS = {
    "radar":  lambda r: r.get("sac_sic") or "—",
    "hour":   _hour_bucket,
    "mode3a": lambda r: r.get("mode3a") or "—",
    "fl_band": _fl_band,
    "category": lambda r: str(r.get("category")) if r.get("category") is not None else "—",
    "callsign": lambda r: r.get("callsign") or "—",
    "mode_s": lambda r: r.get("mode_s") or "—",
    "garbled": lambda r: "Garbled" if r.get("garbled") else "Normal",
}


def aggregate(rows, metric, dimension):
    keyfn = DIMENSIONS[dimension]
    buckets = {}
    for r in rows:
        k = keyfn(r)
        buckets.setdefault(k, []).append(r)
    out = []
    for k, group in buckets.items():
        if metric.agg == "count":
            v = float(len(group))
        else:
            vals = [g.get(metric.column) for g in group if g.get(metric.column) is not None]
            if not vals:
                continue
            if metric.agg == "avg":
                v = float(np.mean(vals))
            elif metric.agg == "p95":
                v = float(np.percentile(vals, 95))
            else:
                raise ValueError(metric.agg)
        out.append((k, v))
    out.sort(key=lambda kv: kv[1], reverse=True)
    return out
