import pytest

from player import atm_db

pytestmark = pytest.mark.skipif(not atm_db.available(),
                                reason="atm.duckdb no disponible")


def test_restricted_airspaces_carga():
    areas = atm_db.restricted_airspaces()
    assert len(areas) > 0
    kinds = {a.kind for a in areas}
    assert kinds <= {"R", "P", "D"}
    # toda área tiene geometría válida
    for a in areas:
        if a.shape == "circle":
            assert a.center is not None and a.radius_nm > 0
        else:
            assert len(a.vertices) >= 3


def test_filtro_por_kind():
    rest = atm_db.restricted_airspaces(kinds=["R"])
    assert rest and all(a.kind == "R" for a in rest)


def test_circulo_conocido_sap116():
    a = next((x for x in atm_db.restricted_airspaces() if x.name.strip() == "SAP116"), None)
    if a is None:
        pytest.skip("SAP116 no está en esta base")
    assert a.shape == "circle"
    assert a.radius_nm == pytest.approx(1.0)
    assert a.center is not None


def test_poligono_conocido_sar102():
    a = next((x for x in atm_db.restricted_airspaces() if x.name.strip() == "SAR102"), None)
    if a is None:
        pytest.skip("SAR102 no está en esta base")
    assert a.shape == "poly"
    assert len(a.vertices) >= 3
    # vértice 1 esperado ~ 334258S 0652003W
    lat0, lon0 = a.vertices[0]
    assert -34.0 < lat0 < -33.0
    assert -66.0 < lon0 < -65.0
