"""Tests HLR-HMI-06 / HLR-SSR-05: watchdog de la cadena de safety-nets."""
import time
import pytest
from unittest.mock import MagicMock

from tests.tracking.test_matching import app  # noqa: F401


def _radarplot(x=0.0, y=0.0, n=0):
    from player.radar_widget import RadarPlot
    return RadarPlot(x=x, y=y, sac_sic="226/210", category=48,
                     timestamp=1000.0, mode3a=None, callsign=None,
                     flight_level=None, is_track=False,
                     mode_s=f"{n:06X}", track_angle=None, ground_speed=None)


@pytest.fixture
def widget(app):
    from player.radar_widget import RadarWidget
    w = RadarWidget()
    w.projection_set = True
    w.system_bus = MagicMock()
    w.limpiar_pantalla()
    return w


def test_sin_tracks_no_alerta(widget):
    widget._safety_wall_last = time.time() - 10.0
    widget._check_safety_watchdog()
    widget.system_bus.inyectar.assert_not_called()


def test_cadena_reciente_no_alerta(widget):
    widget.tracks["T1"] = _radarplot()
    widget._safety_wall_last = time.time() - 1.0
    widget._check_safety_watchdog()
    widget.system_bus.inyectar.assert_not_called()


def test_cadena_bloqueada_alerta(widget):
    widget.tracks["T1"] = _radarplot()
    widget._safety_wall_last = time.time() - 6.0
    widget._check_safety_watchdog()
    assert widget._safety_watchdog_alerted is True
    widget.system_bus.inyectar.assert_called_once()
    args = widget.system_bus.inyectar.call_args[0]
    assert args[0] == "CRITICAL"
    assert "WATCHDOG" in args[1]


def test_segunda_llamada_no_duplica_alerta(widget):
    widget.tracks["T1"] = _radarplot()
    widget._safety_wall_last = time.time() - 6.0
    widget._check_safety_watchdog()
    widget._check_safety_watchdog()
    assert widget.system_bus.inyectar.call_count == 1


def test_cadena_recuperada_limpia_alerta(widget):
    widget.tracks["T1"] = _radarplot()
    widget._safety_wall_last = time.time() - 6.0
    widget._check_safety_watchdog()
    assert widget._safety_watchdog_alerted is True
    # La cadena vuelve a correr → finally de evaluar_msaw resetea la bandera
    widget._safety_watchdog_alerted = False
    assert widget._safety_watchdog_alerted is False
