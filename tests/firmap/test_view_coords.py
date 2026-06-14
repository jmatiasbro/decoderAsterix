import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PyQt6.QtWidgets")
from PyQt6.QtWidgets import QApplication
from player.firmap.firmap_view import FirMapView


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def _view(app):
    v = FirMapView()
    v.resize(800, 600)
    v.set_center(-64.21, -31.31)  # (lon, lat) Córdoba
    v.set_zoom(8)
    return v


def test_track_en_centro_cae_en_centro(app):
    v = _view(app)
    sp = v._lonlat_to_screen(-31.31, -64.21)  # (lat, lon)
    assert abs(sp.x() - 400) < 1.0 and abs(sp.y() - 300) < 1.0


def test_track_al_noreste_va_arriba_derecha(app):
    v = _view(app)
    sp = v._lonlat_to_screen(-31.0, -64.0)  # más al norte y este
    assert sp.x() > 400 and sp.y() < 300
