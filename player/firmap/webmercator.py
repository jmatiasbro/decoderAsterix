"""Conversiones WebMercator (EPSG:3857) / slippy-map. Puro y testeable.

Convención XYZ estándar (no TMS): y crece hacia el sur. La escritura/lectura
MBTiles (que usa TMS) se maneja en mbtiles.py, no acá.
"""
import math

TILE_SIZE = 256
# Límite de latitud de WebMercator.
MAX_LAT = 85.05112877980659


def clamp_lat(lat: float) -> float:
    return max(-MAX_LAT, min(MAX_LAT, lat))


def lonlat_to_tile_xy(lon: float, lat: float, z: float):
    """(lon, lat) -> (xtile, ytile) en coordenadas fraccionarias de tile."""
    lat = clamp_lat(lat)
    n = 2.0 ** z
    x = (lon + 180.0) / 360.0 * n
    lat_rad = math.radians(lat)
    y = (1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0 * n
    return x, y


def tile_xy_to_lonlat(x: float, y: float, z: float):
    """(xtile, ytile) -> (lon, lat) de la ESQUINA NW del tile."""
    n = 2.0 ** z
    lon = x / n * 360.0 - 180.0
    lat = math.degrees(math.atan(math.sinh(math.pi * (1.0 - 2.0 * y / n))))
    return lon, lat


def lonlat_to_pixel(lon: float, lat: float, z: int):
    """(lon, lat) -> pixel global (px, py) en el nivel de zoom z (256 px/tile)."""
    x, y = lonlat_to_tile_xy(lon, lat, z)
    return x * TILE_SIZE, y * TILE_SIZE


def pixel_to_lonlat(px: float, py: float, z: int):
    return tile_xy_to_lonlat(px / TILE_SIZE, py / TILE_SIZE, z)


def tile_range_for_bbox(lon_min, lat_min, lon_max, lat_max, z: int):
    """Rango inclusivo de tiles (x0, y0, x1, y1) que cubren el bbox en zoom z."""
    x0f, y_top = lonlat_to_tile_xy(lon_min, lat_max, z)  # NW
    x1f, y_bot = lonlat_to_tile_xy(lon_max, lat_min, z)  # SE
    n = int(2 ** z)
    x0 = max(0, min(n - 1, int(math.floor(x0f))))
    x1 = max(0, min(n - 1, int(math.floor(x1f))))
    y0 = max(0, min(n - 1, int(math.floor(y_top))))
    y1 = max(0, min(n - 1, int(math.floor(y_bot))))
    return x0, y0, x1, y1


def count_tiles_for_bbox(lon_min, lat_min, lon_max, lat_max, z: int) -> int:
    x0, y0, x1, y1 = tile_range_for_bbox(lon_min, lat_min, lon_max, lat_max, z)
    return (x1 - x0 + 1) * (y1 - y0 + 1)
