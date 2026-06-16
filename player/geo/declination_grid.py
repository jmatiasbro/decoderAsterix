"""Loader + interpolación bilineal de la grilla offline de declinación magnética.

Python puro (stdlib). Fuente de respaldo del WMM: ver player/magnetic_compensator.py.
"""
import json
import os

DEFAULT_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "data", "magnetic", "declination_grid.json")

_CACHE = {}   # path -> grid dict | None


def G_NODE(grid, i, j):
    return grid["values"][i][j]


def _clamp(v, lo, hi):
    return lo if v < lo else hi if v > hi else v


def interpolate(grid, lat, lon):
    """Declinación interpolada (bilineal). Clampa al bbox de la grilla."""
    step = grid["step"]
    lat = _clamp(lat, grid["lat_min"], grid["lat_max"])
    lon = _clamp(lon, grid["lon_min"], grid["lon_max"])
    fi = (lat - grid["lat_min"]) / step
    fj = (lon - grid["lon_min"]) / step
    i0 = min(int(fi), grid["n_lat"] - 2) if grid["n_lat"] > 1 else 0
    j0 = min(int(fj), grid["n_lon"] - 2) if grid["n_lon"] > 1 else 0
    di, dj = fi - i0, fj - j0
    v = grid["values"]
    v00, v01 = v[i0][j0], v[i0][j0 + 1]
    v10, v11 = v[i0 + 1][j0], v[i0 + 1][j0 + 1]
    top = v00 + (v01 - v00) * dj
    bot = v10 + (v11 - v10) * dj
    return top + (bot - top) * di


def load(path=None):
    path = path or DEFAULT_PATH
    if path in _CACHE:
        return _CACHE[path]
    grid = None
    try:
        with open(path, "r", encoding="utf-8") as f:
            grid = json.load(f)
    except (OSError, ValueError):
        grid = None
    _CACHE[path] = grid
    return grid


def declinacion(lat, lon):
    """Declinación en (lat, lon) o None si la grilla no está disponible."""
    if lat is None or lon is None:
        return None
    grid = load(DEFAULT_PATH)
    if not grid:
        return None
    return interpolate(grid, lat, lon)
