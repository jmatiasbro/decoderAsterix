import pytest

from player import atm_db, atm_maps


# --- parse_dms: puro, siempre testeable ---
def test_parse_dms_lat_sur():
    assert atm_db.parse_dms("325755S") == pytest.approx(-(32 + 57 / 60 + 55 / 3600), abs=1e-6)


def test_parse_dms_lon_oeste():
    assert atm_db.parse_dms("0640721W") == pytest.approx(-(64 + 7 / 60 + 21 / 3600), abs=1e-6)


def test_parse_dms_norte_este_positivos():
    assert atm_db.parse_dms("0100000N") > 0   # lat
    assert atm_db.parse_dms("00100000E") > 0  # lon


def test_parse_dms_invalido():
    assert atm_db.parse_dms("") is None
    assert atm_db.parse_dms(None) is None
    assert atm_db.parse_dms("123X") is None


# --- DB: se saltan si no está construida ---
needs_db = pytest.mark.skipif(not atm_db.available(), reason="atm.duckdb no construido")


@needs_db
def test_airports_coords_reales():
    ap = atm_db.airports()
    assert len(ap) > 50
    saez = ap["SAEZ"]
    assert saez["lat"] == pytest.approx(-34.82, abs=0.05)
    assert saez["lon"] == pytest.approx(-58.54, abs=0.05)


@needs_db
def test_airways_clasificacion_excluyente():
    sup = {w["name"] for w in atm_db.airways("SUP")}
    rnav = {w["name"] for w in atm_db.airways("RNAV")}
    assert sup and rnav
    assert sup.isdisjoint(rnav)  # RNAV separada de superiores


@needs_db
def test_segmentos_aerovia_empiezan_con_move():
    segs = atm_maps.airway_segments("RNAV")
    assert segs and segs[0][0] == "M"
    assert all(len(s) == 4 for s in segs)


@needs_db
def test_fix_segments_simbolo_y_label():
    segs = atm_maps.fix_segments(["VO"], symbols=True, names=True)
    kinds = {s[0] for s in segs}
    assert kinds == {"S", "T"}
