from player.msaw.model import MsaZone, MsaSector
from player.msaw.render import zone_segments, MSA_LAYER


def _zona_2sec():
    return MsaZone(icao="SACO", center=(-31.31, -64.21), radius_nm=25.0,
                   mag_decl_w=6.0,
                   sectors=[MsaSector(19, 199, 4100), MsaSector(199, 19, 8300)])


def test_zone_segments_anillo_radiales_y_labels():
    segs = zone_segments(_zona_2sec())
    labels = [s for s in segs if s[0] == "T"]
    radial_moves = sum(1 for s in segs if s[0] == "M")
    # 1 M del anillo + 1 M por radial (2 sectores)
    assert radial_moves == 3
    assert {s[4] for s in labels} == {"MSA 4100", "MSA 8300"}
    assert all(s[1] == MSA_LAYER for s in segs)


def test_omni_sin_radiales():
    z = MsaZone(icao="SANE", center=(-27.76, -64.31), radius_nm=25.0,
                sectors=[MsaSector(0, 360, 2500)])
    segs = zone_segments(z)
    # solo el anillo (1 M) y una etiqueta en el centro, sin radiales extra
    assert sum(1 for s in segs if s[0] == "M") == 1
    labels = [s for s in segs if s[0] == "T"]
    assert len(labels) == 1 and labels[0][4] == "MSA 2500"


def test_centro_o_sectores_vacios_devuelve_vacio():
    assert zone_segments(MsaZone(icao="X", center=None, radius_nm=25.0)) == []


# ── Fase 2: polígonos MSA + corredores de aproximación ──────────────────────
from player.msaw.render import (polygon_segments, apm_corridor_segments,
                                 profile_corridor_segments,
                                 MSA_POLY_LAYER, APM_LAYER, PROFILE_LAYER)


def test_polygon_segments_cierra_y_etiqueta():
    zonas = [{"identifier": "80E", "msa_ft": 8000,
              "coords": [(-31.0, -64.0), (-31.0, -64.1), (-31.1, -64.1)]}]
    segs = polygon_segments(zonas)
    assert sum(1 for s in segs if s[0] == "M") == 1          # un solo Move (inicio)
    assert all(s[1] == MSA_POLY_LAYER for s in segs)
    # cierra el polígono: último L coincide con el primer vértice
    ls = [s for s in segs if s[0] == "L"]
    assert (ls[-1][2], ls[-1][3]) == (-31.0, -64.0)
    assert any(s[0] == "T" and "8000" in s[4] for s in segs)


def test_apm_corridor_segments_trapecio():
    cs = [{"airport": "SACO", "runway": "01", "near": (-31.37, -64.20),
           "far": (-31.24, -64.21), "half_wide_nm": 1.0, "min_dist": 3.0,
           "max_dist": 12.0, "lower_slope": 2.5, "upper_slope": 4.8,
           "glide_slope": 3.0, "thr_elev_ft": 1604}]
    segs = apm_corridor_segments(cs)
    assert sum(1 for s in segs if s[0] == "M") == 1
    assert all(s[1] == APM_LAYER for s in segs)
    # trapecio cerrado: 1 M + 4 L (4 esquinas, vuelve al inicio)
    assert sum(1 for s in segs if s[0] == "L") == 4
    assert any(s[0] == "T" and "01" in s[4] for s in segs)


def test_profile_corridor_segments_polilinea():
    ps = [{"profile": "RWY01A", "kind": "A",
           "points": [(-31.43, -64.04, 4500, 0.5, 0),
                      (-31.43, -64.16, 3600, 0.5, 0),
                      (-31.37, -64.20, 2500, 0.5, 0)]}]
    segs = profile_corridor_segments(ps)
    assert sum(1 for s in segs if s[0] == "M") == 1
    assert sum(1 for s in segs if s[0] == "L") == 2          # 3 puntos -> 2 tramos
    assert all(s[1] == PROFILE_LAYER for s in segs)
    assert any(s[0] == "T" and "4500" in s[4] for s in segs)


def test_render_vacio_si_no_hay_datos():
    assert polygon_segments([]) == []
    assert apm_corridor_segments([]) == []
    assert profile_corridor_segments([]) == []
