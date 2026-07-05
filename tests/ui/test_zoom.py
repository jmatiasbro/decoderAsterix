"""Zoom anclado: los botones +/− y la rueda no deben 'perder el foco'.

El punto ancla (track enfocado, cursor o centro de vista) debe quedar fijo en
pantalla al cambiar el zoom. Regresión del ajuste de pan en `zoom_por_factor`.
"""
import pytest
from PyQt6.QtCore import QPointF

from tests.tracking.test_matching import app  # noqa: F401


@pytest.fixture
def w(app):
    import player.radar_widget as rw
    widget = rw.RadarWidget()
    widget.resize(800, 600)
    widget.projection_set = True
    widget.pan_x, widget.pan_y = 40.0, -25.0
    widget.zoom_factor = 0.001
    return widget


def _dist(a, b):
    return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5


def test_zoom_in_ancla_centro_de_vista(w):
    antes = w._screen_to_world(400, 300)
    w.zoom_in()
    despues = w._screen_to_world(400, 300)
    assert _dist(antes, despues) < 1.0  # el mundo en el centro no se movió


def test_zoom_out_ancla_centro_de_vista(w):
    antes = w._screen_to_world(400, 300)
    w.zoom_out()
    despues = w._screen_to_world(400, 300)
    assert _dist(antes, despues) < 1.0


def test_rueda_ancla_en_cursor(w):
    px, py = 620.0, 180.0
    antes = w._screen_to_world(px, py)
    w.zoom_por_factor(1.2, anchor_screen=QPointF(px, py))
    despues = w._screen_to_world(px, py)
    assert _dist(antes, despues) < 1.0  # el mundo bajo el cursor queda fijo


def test_zoom_ancla_en_track_enfocado(w):
    from player.radar_widget import RadarPlot
    p = RadarPlot(x=15000.0, y=8000.0, sac_sic="226/210", category=21,
                  timestamp=1000.0, mode3a=None, callsign="F1", flight_level=350,
                  is_track=True, mode_s="ABCDEF", track_angle=90.0, ground_speed=400.0)
    w.tracks["ABCDEF"] = p
    w.focused_target_id = "ABCDEF"
    sp_antes = w._world_to_screen(p.x, p.y)
    w.zoom_in()  # sin anchor explícito → usa el track enfocado
    sp_despues = w._world_to_screen(p.x, p.y)
    d = ((sp_antes.x() - sp_despues.x()) ** 2 + (sp_antes.y() - sp_despues.y()) ** 2) ** 0.5
    assert d < 1.0  # el track enfocado no se movió en pantalla


def test_zoom_respeta_limites(w):
    from player.radar_widget import MIN_ZOOM, MAX_ZOOM
    for _ in range(200):
        w.zoom_out()
    assert w.zoom_factor >= MIN_ZOOM
    for _ in range(400):
        w.zoom_in()
    assert w.zoom_factor <= MAX_ZOOM


def test_botones_zoom_existen(w):
    assert w._btn_zoom_in is not None
    assert w._btn_zoom_out is not None
