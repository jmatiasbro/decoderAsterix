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


# Métricas agregables. Criterio: que la magnitud sea real y la columna esté
# poblada con datos monoradar.
#   - Se eliminó "Azimut medio": el azimut es CIRCULAR, su media aritmética no
#     tiene sentido (promediar 350° y 10° da 180°). El azimut es coordenada, no
#     magnitud — para verlo usar Rosa de azimut / PPI.
#   - Se eliminó "Pd medio": el Pd no es un valor por-plot (ver pestaña PASS y el
#     preset "Pd vs Azimut", que lo computan obs/esperado).
#   - Vertical = flight_level (siempre poblado en CAT048/001 vía Mode C); se quitó
#     altitude_ft, que sólo se llena con altitud geométrica y suele venir NULL.
#   - No todo es promedio: count, máximos (alcance/techo/velocidad), p95 y tasa.
METRICS = [
    Metric("count",         "Nº detecciones",        "",            "count", ALL_DIMS),
    Metric("max_range",     "Alcance máx (NM)",      "raw_range",   "max",   ALL_DIMS),
    Metric("avg_range",     "Rango medio (NM)",      "raw_range",   "avg",   ALL_DIMS),
    Metric("p95_range",     "Rango p95 (NM)",        "raw_range",   "p95",   ALL_DIMS),
    Metric("max_fl",        "Techo (FL)",            "flight_level","max",   ALL_DIMS),
    Metric("avg_fl",        "Nivel medio (FL)",      "flight_level","avg",   ALL_DIMS),
    Metric("max_gs",        "Velocidad máx (kt)",    "ground_speed","max",   ALL_DIMS),
    Metric("avg_gs",        "Velocidad media (kt)",  "ground_speed","avg",   ALL_DIMS),
    Metric("garbled_rate",  "Tasa de garbling (%)",  "garbled",     "rate",  ALL_DIMS),
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
            # Coerción numérica robusta: flight_level llega como str ("100"),
            # garbled como bool. Se descartan los no convertibles.
            vals = []
            for g in group:
                x = g.get(metric.column)
                if x is None:
                    continue
                try:
                    vals.append(float(x))
                except (TypeError, ValueError):
                    continue
            if not vals:
                continue
            if metric.agg == "avg":
                v = float(np.mean(vals))
            elif metric.agg == "max":
                v = float(np.max(vals))
            elif metric.agg == "p95":
                v = float(np.percentile(vals, 95))
            elif metric.agg == "rate":      # fracción de True → porcentaje
                v = float(np.mean(vals)) * 100.0
            else:
                raise ValueError(metric.agg)
        out.append((k, v))
    out.sort(key=lambda kv: kv[1], reverse=True)
    return out
