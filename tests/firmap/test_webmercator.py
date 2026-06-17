import math

from player.firmap import webmercator as wm

ARG = (-73.6, -55.1, -53.6, -21.8)  # lon_min, lat_min, lon_max, lat_max


def approx(a, b, tol=1e-6):
    return abs(a - b) <= tol


def test_centro_mundo_en_z1():
    x, y = wm.lonlat_to_tile_xy(0.0, 0.0, 1)
    assert approx(x, 1.0) and approx(y, 1.0)


def test_esquina_nw_en_z0():
    x, y = wm.lonlat_to_tile_xy(-180.0, wm.MAX_LAT, 0)
    assert approx(x, 0.0, 1e-6) and approx(y, 0.0, 1e-3)


def test_pixel_centro_tile_unico():
    px, py = wm.lonlat_to_pixel(0.0, 0.0, 0)
    assert approx(px, 128.0) and approx(py, 128.0)


def test_roundtrip_lonlat():
    for lon, lat, z in [(-65.0, -25.0, 10), (-58.38, -34.60, 12), (10.0, 50.0, 8)]:
        tx, ty = wm.lonlat_to_tile_xy(lon, lat, z)
        lon2, lat2 = wm.tile_xy_to_lonlat(tx, ty, z)
        assert approx(lon, lon2, 1e-6) and approx(lat, lat2, 1e-6)


def test_clamp_latitud():
    assert wm.clamp_lat(89.0) == wm.MAX_LAT
    assert wm.clamp_lat(-89.0) == -wm.MAX_LAT


def test_rango_tiles_argentina_creciente_por_zoom():
    c5 = wm.count_tiles_for_bbox(*ARG, 5)
    c6 = wm.count_tiles_for_bbox(*ARG, 6)
    assert c5 > 0
    assert c6 > c5  # más zoom => más tiles


def test_buenos_aires_dentro_del_rango_nacional():
    z = 7
    x0, y0, x1, y1 = wm.tile_range_for_bbox(*ARG, z)
    bx, by = wm.lonlat_to_tile_xy(-58.38, -34.60, z)
    bx, by = int(math.floor(bx)), int(math.floor(by))
    assert x0 <= bx <= x1 and y0 <= by <= y1
