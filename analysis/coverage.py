"""Cálculo de cobertura real de radar por nivel de vuelo (FL).

Lógica extraída de analysis/exporters.py::export_coverage_map_kmz para poder
reusarla en pantalla (polar + mapa) y en exportación, sin acoplarla al KMZ.
Python puro + numpy. Sin pandas.
"""
import math
from dataclasses import dataclass, field

FL_BANDS = (50, 100, 150, 200, 250, 300)


def classify_fl(fl_str):
    """Devuelve la banda FL (50..300) para un flight_level, o None si no aplica."""
    if fl_str is None or fl_str == "---":
        return None
    try:
        fl = float(fl_str)
    except (ValueError, TypeError):
        return None
    if fl > 450.0:        # viene en pies -> normalizar a FL
        fl = fl / 100.0
    if 25 <= fl < 75:
        return 50
    if 75 <= fl < 125:
        return 100
    if 125 <= fl < 175:
        return 150
    if 175 <= fl < 225:
        return 200
    if 225 <= fl < 275:
        return 250
    if fl >= 275:
        return 300
    return None


import numpy as np
from utils.geo import GeoTools


@dataclass
class CoverageResult:
    radar_lat: float
    radar_lon: float
    levels: dict = field(default_factory=dict)   # FL banda -> list[360] rangos NM
    plot_count: int = 0


def compute_coverage(plots, radar_lat, radar_lon, *, percentile=95, bands=FL_BANDS):
    """plots: iterable de (lat, lon, fl_str). Devuelve CoverageResult.

    Para cada banda FL agrupa los plots en 360 sectores de azimut (1°) y toma el
    percentil indicado del rango (NM) por sector. Bandas con <10 plots quedan en 0.
    """
    by_band = {b: [[] for _ in range(360)] for b in bands}
    count = 0
    for lat, lon, fl_str in plots:
        band = classify_fl(fl_str)
        if band is None or band not in by_band:
            continue
        count += 1
        dist_m, az = GeoTools.calculate_distance_and_azimuth(radar_lat, radar_lon, lat, lon)
        r_nm = GeoTools.meters_to_nm(dist_m)
        by_band[band][int(math.floor(az)) % 360].append(r_nm)

    levels = {}
    for band, sectores in by_band.items():
        total = sum(len(s) for s in sectores)
        ranges = [0.0] * 360
        if total >= 10:
            for i, s in enumerate(sectores):
                if s:
                    ranges[i] = float(np.percentile(s, percentile))
        levels[band] = ranges
    return CoverageResult(radar_lat=radar_lat, radar_lon=radar_lon,
                          levels=levels, plot_count=count)
