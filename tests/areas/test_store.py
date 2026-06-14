from datetime import time

from player.areas.model import Area, Vigencia
from player.areas import store


def _user(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "_BASE", str(tmp_path))
    return "TESTU"


def test_roundtrip_poligono_temporal(tmp_path, monkeypatch):
    u = _user(tmp_path, monkeypatch)
    a = Area("ZONA_X", "R", "poly", lower_fl=0, upper_fl=120,
             vertices=[(-31.0, -64.0), (-31.0, -63.5), (-30.5, -63.7)],
             vigencia=Vigencia(permanente=False, habilitada=False, dias={0, 2, 4},
                               desde=time(8, 0), hasta=time(20, 0)), origen="usuario")
    store.guardar(a, u)
    got = {x.name: x for x in store.cargar_todas(u)}["ZONA_X"]
    assert got.shape == "poly" and len(got.vertices) == 3
    assert got.lower_fl == 0 and got.upper_fl == 120
    assert got.vigencia.permanente is False
    assert got.vigencia.habilitada is False          # switch manual persiste
    assert got.vigencia.dias == {0, 2, 4}
    assert got.vigencia.desde == time(8, 0)
    assert got.vigencia.hasta == time(20, 0)


def test_roundtrip_circulo_permanente(tmp_path, monkeypatch):
    u = _user(tmp_path, monkeypatch)
    a = Area("CIRC", "P", "circle", lower_fl=10, upper_fl=999,
             center=(-34.0, -58.0), radius_nm=5.0,
             vigencia=Vigencia(permanente=True), origen="usuario")
    store.guardar(a, u)
    got = store.cargar_todas(u)[0]
    assert got.shape == "circle"
    assert got.center == (-34.0, -58.0) and got.radius_nm == 5.0
    assert got.vigencia.permanente is True


def test_borrar(tmp_path, monkeypatch):
    u = _user(tmp_path, monkeypatch)
    a = Area("DEL", "D", "poly", vertices=[(0, 0), (0, 1), (1, 1)])
    store.guardar(a, u)
    assert any(x.name == "DEL" for x in store.cargar_todas(u))
    assert store.borrar("DEL", u) is True
    assert store.cargar_todas(u) == []
    assert store.borrar("DEL", u) is False
