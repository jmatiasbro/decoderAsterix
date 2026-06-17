import pytest

from player import atm_db

pytestmark = pytest.mark.skipif(not atm_db.available(),
                                reason="atm.duckdb no disponible")


def test_dms_to_dd_lat_lon():
    assert atm_db.dms_to_dd("311836S") == pytest.approx(-31.31, abs=0.01)
    assert atm_db.dms_to_dd("0641230W") == pytest.approx(-64.208, abs=0.01)
    assert atm_db.dms_to_dd("bad") is None


def test_minimums_zones():
    zs = {z["identifier"]: z for z in atm_db.minimums_zones()}
    assert "80E" in zs
    z = zs["80E"]
    assert z["msa_ft"] == 8000          # 80 -> x100
    assert len(z["coords"]) >= 4
    assert all(isinstance(c, tuple) and len(c) == 2 for c in z["coords"])


def test_apm_corridors_saco():
    cs = atm_db.apm_corridors("SACO")
    runways = {c["runway"] for c in cs}
    assert {"01", "05", "19", "23"} <= runways
    c = next(c for c in cs if c["runway"] == "01")
    assert c["near"] and c["far"]
    assert c["half_wide_nm"] == 1.0
    assert c["lower_slope"] == pytest.approx(2.5) and c["upper_slope"] == pytest.approx(4.8)
    assert c["thr_elev_ft"] == 1604


def test_profile_corridors_saco():
    ps = {p["profile"]: p for p in atm_db.profile_corridors("SACO")}
    assert "RWY01A" in ps
    p = ps["RWY01A"]
    assert p["kind"] == "A"
    assert len(p["points"]) == 3
    lat, lon, min_ft, dlat, az = p["points"][0]
    assert min_ft == 4500              # altitude 45 -> x100


def test_profile_parameters():
    pr = atm_db.profile_parameters()
    assert pr["tol_heading"] == 18
    assert pr["tol_altitude_ft"] == 300     # 3 -> x100
    assert pr["tol_distance_nm"] == 0.5
    assert pr["entorno_aerodrome_nm"] == 3
