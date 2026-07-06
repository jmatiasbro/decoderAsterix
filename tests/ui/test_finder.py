"""Finder táctico: búsqueda por SSR normalizada + tracks tentativos.

Regresión del fix: un mode3a entero (según sensor) debe encontrarse igual que uno
string, y un blanco en pending_tracks (no confirmado) también debe localizarse.
"""
import pytest

from tests.tracking.test_matching import app  # noqa: F401


class _FakeTrack:
    def __init__(self, tid, mode3a=None, callsign=None, lat=-31.0, lon=-64.0):
        self.id = tid
        self.mode3a = mode3a
        self.callsign = callsign
        self.raw_dict = {"lat": lat, "lon": lon}


class _FakeRadar:
    def __init__(self):
        self.tracks = {}
        self.pending_tracks = {}


@pytest.fixture(autouse=True)
def _no_modal(monkeypatch):
    """Evita que QMessageBox.information (modal) bloquee la suite headless."""
    from PyQt6.QtWidgets import QMessageBox
    monkeypatch.setattr(QMessageBox, "information",
                        staticmethod(lambda *a, **k: None))


@pytest.fixture
def finder(app):
    from player.radar_finder_dialog import RadarFinderDialog
    return RadarFinderDialog(_FakeRadar())


def _buscar(finder, query):
    """Ejecuta la búsqueda y devuelve el identificador emitido, o None."""
    capturado = {}
    finder.target_located.connect(
        lambda lat, lon, tipo, ident: capturado.update(ident=ident, tipo=tipo))
    finder.txt_search.setText(query)
    finder.ejecutar_busqueda_finder()
    return capturado.get("ident")


def test_ssr_entero_se_encuentra(finder):
    """mode3a int 0o0062 → la etiqueta muestra '0062' → buscar '0062' lo halla."""
    finder.radar.tracks["T1"] = _FakeTrack("T1", mode3a=0o62)
    assert _buscar(finder, "0062") is not None


def test_ssr_string_se_encuentra(finder):
    finder.radar.tracks["T2"] = _FakeTrack("T2", mode3a="2013")
    assert _buscar(finder, "2013") is not None


def test_callsign_se_encuentra(finder):
    finder.radar.tracks["T3"] = _FakeTrack("T3", callsign="ARG1340")
    assert _buscar(finder, "arg1340") == "ARG1340"


def test_track_tentativo_se_encuentra(finder):
    """Un blanco en pending_tracks (no confirmado) también se localiza."""
    finder.radar.pending_tracks["P1"] = _FakeTrack("P1", mode3a=0o1234)
    assert _buscar(finder, "1234") is not None


def test_normalizacion_ssr():
    from player.radar_finder_dialog import RadarFinderDialog
    assert RadarFinderDialog._norm_ssr(0o62) == "0062"
    assert RadarFinderDialog._norm_ssr(0o7700) == "7700"
    assert RadarFinderDialog._norm_ssr("2013") == "2013"
    assert RadarFinderDialog._norm_ssr(None) == ""
    assert RadarFinderDialog._norm_ssr("") == ""


def test_inexistente_no_encuentra(finder):
    finder.radar.tracks["T4"] = _FakeTrack("T4", mode3a=0o62)
    assert _buscar(finder, "9999") is None
