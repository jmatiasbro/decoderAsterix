"""Tests HLR-HMI-01..03: completitud de presentación, fidelidad de etiqueta y simbología ODS.

HLR-HMI-01 — Todo track activo DEBE estar en pantalla (no omisión silenciosa).
HLR-HMI-02 — Callsign, Mode 3/A y FL mostrados exactamente como se decodificaron.
HLR-HMI-03 — Simbología EUROCONTROL ODS: forma y dashing correctos por estado.
"""
import pytest
from unittest.mock import patch

from tests.tracking.test_matching import app  # noqa: F401


@pytest.fixture
def w(app):
    from player.radar_widget import RadarWidget
    widget = RadarWidget()
    widget.projection_set = True
    widget.sensores_visibles = None
    widget.limpiar_pantalla()
    return widget


def _pdict(n, cat=21):
    return {
        "sac_sic": "226/210", "category": cat, "time": 1000.0,
        "x_meters": float(n) * 5000.0, "y_meters": 0.0,
        "mode_s": f"{n:06X}",
    }


def _rplot(cat=48, mode_s="", mode3a=None, raw_dict=None):
    from player.radar_widget import RadarPlot
    return RadarPlot(
        x=0.0, y=0.0, sac_sic="226/210", category=cat,
        timestamp=1000.0, mode3a=mode3a, callsign=None,
        flight_level=None, is_track=False,
        mode_s=mode_s, track_angle=None, ground_speed=None,
        raw_dict=raw_dict or {},
    )


# ── HLR-HMI-01: completitud de tracks activos ────────────────────────────────

class TestCompletitudTracks:

    def test_n_plots_generan_n_tracks(self, w):
        N = 10
        with patch("player.radar_widget.SimulationTime.time", return_value=1000.0):
            for i in range(N):
                w._process_plot_data(_pdict(i))
        total = len(w.tracks) + len(w.pending_tracks)
        assert total == N, f"Esperados {N} tracks, encontrados {total}"

    def test_ningún_track_activo_omitido(self, w):
        IDS = [f"{i:06X}" for i in range(20)]
        with patch("player.radar_widget.SimulationTime.time", return_value=1000.0):
            for i, mid in enumerate(IDS):
                w._process_plot_data({
                    "sac_sic": "226/210", "category": 21, "time": 1000.0,
                    "x_meters": float(i) * 5000.0, "y_meters": 0.0,
                    "mode_s": mid,
                })
        presentes = set(w.tracks) | set(w.pending_tracks)
        omitidos = [mid for mid in IDS if mid not in presentes]
        assert not omitidos, f"Tracks omitidos de pantalla: {omitidos}"

    def test_track_caducado_marcado_is_alive_false(self, w):
        """HLR-HMI-01: track caducado → is_alive() False → pintado lo omite.

        age() usa widget_ref.get_sensor_time() que lee sensor_times[(sac,sic)].
        Hay que avanzar también ese reloj para simular correctamente el paso del tiempo.
        """
        from player.radar_widget import MAX_AGE_TRACK
        with patch("player.radar_widget.SimulationTime.time", return_value=1000.0):
            w._process_plot_data(_pdict(0))
        tid = next(iter(w.tracks))
        track = w.tracks[tid]
        future_t = 1000.0 + MAX_AGE_TRACK + 1.0
        w.sensor_times[(226, 210)] = future_t  # avanza reloj del sensor
        with patch("player.radar_widget.SimulationTime.time", return_value=future_t):
            assert track.is_alive() is False, "Track caducado debe reportar is_alive()=False"


# ── HLR-HMI-02: fidelidad de etiqueta ────────────────────────────────────────

class TestFidelidadEtiqueta:

    def _full_plot(self, callsign, mode3a, flight_level):
        from player.radar_widget import RadarPlot
        return RadarPlot(
            x=1000.0, y=2000.0, sac_sic="226/210", category=21,
            timestamp=5000.0, mode3a=mode3a, callsign=callsign,
            flight_level=flight_level, is_track=True,
            mode_s="C0FFEE", track_angle=270.0, ground_speed=450.0,
        )

    def test_callsign_sin_modificacion(self):
        p = self._full_plot("AFR001", None, None)
        assert p.callsign == "AFR001"

    def test_mode3a_sin_modificacion(self):
        p = self._full_plot(None, 0o7200, None)
        assert p.mode3a == 0o7200

    def test_flight_level_sin_modificacion(self):
        p = self._full_plot(None, None, 350)
        assert p.flight_level == 350

    def test_todos_los_campos_etiqueta_juntos(self):
        p = self._full_plot("IBE3456", 0o5277, 310)
        assert p.callsign == "IBE3456"
        assert p.mode3a == 0o5277
        assert p.flight_level == 310
        assert p.mode_s == "C0FFEE"


# ── HLR-HMI-03: simbología EUROCONTROL ODS ────────────────────────────────────

class TestSimboloPorEstado:

    def test_cat21_clasifica_adsb(self):
        from player.ods.track_state import classify, ADSB
        assert classify(_rplot(cat=21, mode_s="ABCDEF"), False) == ADSB

    def test_cat48_sin_identidad_clasifica_psr_only(self):
        from player.ods.track_state import classify, PSR_ONLY
        assert classify(_rplot(cat=48, mode_s="", mode3a=None), False) == PSR_ONLY

    def test_cat48_con_mode_s_clasifica_ssr(self):
        from player.ods.track_state import classify, SSR
        assert classify(_rplot(cat=48, mode_s="A1B2C3"), False) == SSR

    def test_cat48_det_type_3_clasifica_combined(self):
        from player.ods.track_state import classify, COMBINED
        p = _rplot(cat=48, raw_dict={"det_type": 3})
        assert classify(p, False) == COMBINED

    def test_cat62_clasifica_system_track(self):
        from player.ods.track_state import classify, SYSTEM_TRACK
        assert classify(_rplot(cat=62), False) == SYSTEM_TRACK

    def test_coasting_override_cualquier_cat(self):
        from player.ods.track_state import classify, COASTING
        assert classify(_rplot(cat=21, mode_s="ABCDEF"), True) == COASTING

    def test_spec_diamond_para_adsb(self):
        from player.ods.track_state import ADSB
        from player.ods.symbology import symbol_spec
        assert symbol_spec(ADSB).shape == "diamond"

    def test_spec_dashed_para_coasting(self):
        from player.ods.track_state import COASTING
        from player.ods.symbology import symbol_spec
        assert symbol_spec(COASTING).dashed is True

    def test_spec_plus_para_psr_only(self):
        from player.ods.track_state import PSR_ONLY
        from player.ods.symbology import symbol_spec
        assert symbol_spec(PSR_ONLY).shape == "plus"

    def test_spec_filled_square_para_combined(self):
        from player.ods.track_state import COMBINED
        from player.ods.symbology import symbol_spec
        assert symbol_spec(COMBINED).shape == "filled_square"
