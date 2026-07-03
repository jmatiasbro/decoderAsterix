"""Tests HLR-HMI-04: calidad de track reflejada en propiedades de RadarPlot."""
import pytest
from unittest.mock import patch

from player.radar_widget import RadarPlot, MAX_AGE_TRACK, MAX_AGE_PLOT


def _plot(cat=48, mode_s=None, mode3a=None, sim_time=0.0, is_track=False):
    """Crea un RadarPlot con _last_seen fijado a sim_time."""
    p = RadarPlot(x=0.0, y=0.0, sac_sic="226/210", category=cat,
                  timestamp=sim_time, mode3a=mode3a, callsign=None,
                  flight_level=None, is_track=is_track,
                  mode_s=mode_s or "", track_angle=None, ground_speed=None)
    p._last_seen = sim_time  # sobreescribe el que pone __init__ con SimulationTime
    return p


# ── HLR-HMI-04: is_alive ────────────────────────────────────────────────────

class TestIsAlive:

    def test_recien_creado_esta_vivo(self):
        p = _plot(sim_time=0.0)
        with patch("player.radar_widget.SimulationTime.time", return_value=1.0):
            assert p.is_alive() is True

    def test_plot_supera_MAX_AGE_PLOT_muere(self):
        p = _plot(cat=48, sim_time=0.0, is_track=False)
        with patch("player.radar_widget.SimulationTime.time",
                   return_value=MAX_AGE_PLOT + 1.0):
            assert p.is_alive() is False

    def test_track_supera_MAX_AGE_TRACK_muere(self):
        p = _plot(cat=48, sim_time=0.0, is_track=True)
        with patch("player.radar_widget.SimulationTime.time",
                   return_value=MAX_AGE_TRACK + 1.0):
            assert p.is_alive() is False

    def test_track_dentro_de_max_age_sigue_vivo(self):
        p = _plot(sim_time=0.0, is_track=True)
        with patch("player.radar_widget.SimulationTime.time",
                   return_value=MAX_AGE_TRACK - 1.0):
            assert p.is_alive() is True


# ── HLR-HMI-04: is_coasting ─────────────────────────────────────────────────

class TestIsCoasting:

    def test_fresco_no_esta_en_coasting(self):
        p = _plot(sim_time=0.0, is_track=True)
        with patch("player.radar_widget.SimulationTime.time", return_value=1.0):
            assert p.is_coasting is False

    def test_supera_mitad_max_age_entra_en_coasting(self):
        p = _plot(sim_time=0.0, is_track=True)
        with patch("player.radar_widget.SimulationTime.time",
                   return_value=MAX_AGE_TRACK / 2 + 1.0):
            assert p.is_coasting is True

    def test_plot_no_track_umbral_MAX_AGE_PLOT(self):
        p = _plot(sim_time=0.0, is_track=False)
        with patch("player.radar_widget.SimulationTime.time",
                   return_value=MAX_AGE_PLOT / 2 + 1.0):
            assert p.is_coasting is True

    def test_plot_no_track_fresco_no_coasting(self):
        p = _plot(sim_time=0.0, is_track=False)
        with patch("player.radar_widget.SimulationTime.time",
                   return_value=MAX_AGE_PLOT / 2 - 1.0):
            assert p.is_coasting is False


# ── HLR-HMI-04: tipo de track ───────────────────────────────────────────────

class TestTipoTrack:

    def test_cat21_es_adsb(self):
        p = _plot(cat=21, mode_s="ABCDEF")
        assert p.category == 21

    def test_mode_s_poblado_identifica_mode_s(self):
        p = _plot(cat=48, mode_s="A1B2C3")
        assert p.mode_s == "A1B2C3"
        assert bool(p.mode_s)

    def test_sin_mode_s_es_primario(self):
        p = _plot(cat=48, mode_s="")
        assert not p.mode_s

    def test_mode3a_identifica_squawk(self):
        p = _plot(cat=48, mode3a=0o7700)
        assert p.mode3a == 0o7700
