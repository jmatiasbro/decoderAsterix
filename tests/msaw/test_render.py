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
