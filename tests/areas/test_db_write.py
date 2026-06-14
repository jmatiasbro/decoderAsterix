import shutil

import pytest

from player import atm_db
from player.areas.model import Area, Vigencia

pytestmark = pytest.mark.skipif(not atm_db.available(),
                                reason="atm.duckdb no disponible")


@pytest.fixture
def db_copia(tmp_path, monkeypatch):
    dst = tmp_path / "atm_copia.duckdb"
    shutil.copy(atm_db.DB_PATH, dst)
    atm_db._close()                                   # soltar RO sobre la base real
    monkeypatch.setattr(atm_db, "DB_PATH", str(dst))
    yield
    atm_db._close()


def _por_nombre(nombre):
    return next((a for a in atm_db.restricted_airspaces() if a.name.strip() == nombre), None)


def test_write_read_poligono(db_copia):
    a = Area("TEST_POLY", "R", "poly", lower_fl=20, upper_fl=120,
             vertices=[(-31.5, -64.5), (-31.5, -64.0), (-31.0, -64.25)],
             vigencia=Vigencia(permanente=True))
    atm_db.write_area(a)
    got = _por_nombre("TEST_POLY")
    assert got is not None and got.shape == "poly" and got.kind == "R"
    assert got.lower_fl == 20 and got.upper_fl == 120
    assert len(got.vertices) == 3
    # round-trip DMS (segundos enteros -> tolerancia ~1")
    assert abs(got.vertices[0][0] - (-31.5)) < 0.0006
    assert abs(got.vertices[0][1] - (-64.5)) < 0.0006


def test_write_read_circulo(db_copia):
    a = Area("TEST_CIRC", "P", "circle", lower_fl=0, upper_fl=50,
             center=(-34.6, -58.4), radius_nm=3.0, vigencia=Vigencia(permanente=True))
    atm_db.write_area(a)
    got = _por_nombre("TEST_CIRC")
    assert got is not None and got.shape == "circle"
    assert got.radius_nm == pytest.approx(3.0)
    assert abs(got.center[0] - (-34.6)) < 0.0006
    assert abs(got.center[1] - (-58.4)) < 0.0006


def test_update_y_delete(db_copia):
    a = Area("TEST_UPD", "D", "poly", lower_fl=0, upper_fl=100,
             vertices=[(0.0, 0.0), (0.0, 1.0), (1.0, 1.0)], vigencia=Vigencia(permanente=True))
    atm_db.write_area(a)
    # upsert: cambia niveles sin duplicar la fila (PK por nombre)
    a.upper_fl = 200
    atm_db.update_area(a)
    got = _por_nombre("TEST_UPD")
    assert got.upper_fl == 200
    assert sum(1 for x in atm_db.restricted_airspaces() if x.name.strip() == "TEST_UPD") == 1
    atm_db.delete_area("TEST_UPD")
    assert _por_nombre("TEST_UPD") is None
