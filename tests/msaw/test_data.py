import pytest

from player import atm_db
from player.msaw import data as msaw_data

pytestmark = pytest.mark.skipif(not atm_db.available(),
                                reason="atm.duckdb no disponible")


def test_carga_8_zonas():
    zs = {z.icao: z for z in msaw_data.msa_zones()}
    assert set(zs) == {"SACO", "SANT", "SASA", "SASJ", "SANL", "SANC", "SANE", "SAOC"}
    for z in zs.values():
        assert z.center and z.radius_nm == 25.0
        assert z.sectors


def test_salta_tres_sectores():
    z = {x.icao: x for x in msaw_data.msa_zones()}["SASA"]
    assert len(z.sectors) == 3
    assert {s.msa_ft for s in z.sectors} == {6000, 9500, 16500}


def test_cordoba_este_4100_oeste_8300():
    z = {x.icao: x for x in msaw_data.msa_zones()}["SACO"]
    clat, clon = z.center
    # ~10 NM al este (lon +) y al oeste (lon -)
    dlon = 10.0 / (60.0 * 0.85)
    assert z.msa_en(clat, clon + dlon) == 4100
    assert z.msa_en(clat, clon - dlon) == 8300


def test_msaw_params():
    p = atm_db.msaw_params()
    assert p.time_to_prediction == 120
    assert p.rocd == 1500
    assert p.cfl_thold == 5
