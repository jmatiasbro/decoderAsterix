"""RBL — CPA (`radar_widget._rbl_cpa` / `_anchor_velocity_nm_h`).

Verifica los campos predictivos de la Range & Bearing Line: E (tiempo a la
distancia mínima) y X (distancia mínima pronosticada). Cubre la velocidad desde
la trayectoria suavizada (evita el flip ~180° del track_angle crudo), el gateo
por convergencia/divergencia y el caso aeronave↔punto fijo.
"""
import pytest

from player.radar_widget import RadarWidget
from utils.geo import METERS_PER_NM


class FakeTrack:
    def __init__(self, gs=None, ta=None, svx=None, svy=None, alive=True):
        self.ground_speed = gs
        self.track_angle = ta
        self._smooth_vx = svx
        self._smooth_vy = svy
        self._alive = alive

    def is_alive(self):
        return self._alive


def _widget(tracks):
    # Sin __init__ (sin Qt): _rbl_cpa/_anchor_velocity_nm_h sólo usan self.tracks.
    w = RadarWidget.__new__(RadarWidget)
    w.tracks = tracks
    return w


def _ac(pid):
    return {"type": "aircraft", "plot_id": pid}


FIJO = {"type": "point"}


# ---- _anchor_velocity_nm_h -------------------------------------------------

def test_velocidad_desde_gs_y_rumbo():
    w = _widget({"O": FakeTrack(gs=300, ta=90)})
    ve, vn = w._anchor_velocity_nm_h(_ac("O"))
    assert ve == pytest.approx(300.0)          # este
    assert vn == pytest.approx(0.0, abs=1e-6)


def test_velocidad_suavizada_tiene_prioridad():
    # gs/ta dicen "este"; la trayectoria suavizada dice "norte" → gana la suavizada.
    vy_norte = 300.0 * METERS_PER_NM / 3600.0  # 300 NM/h expresado en m/s
    w = _widget({"O": FakeTrack(gs=300, ta=90, svx=0.0, svy=vy_norte)})
    ve, vn = w._anchor_velocity_nm_h(_ac("O"))
    assert ve == pytest.approx(0.0, abs=1e-3)
    assert vn == pytest.approx(300.0, rel=1e-3)


def test_velocidad_suavizada_ruidosa_cae_a_rumbo():
    # |v_suave| < ~5 kt (2.5 m/s) → se descarta y se usa gs/ta.
    w = _widget({"O": FakeTrack(gs=300, ta=90, svx=1.0, svy=1.0)})
    ve, vn = w._anchor_velocity_nm_h(_ac("O"))
    assert ve == pytest.approx(300.0)
    assert vn == pytest.approx(0.0, abs=1e-6)


def test_velocidad_punto_fijo_es_cero():
    assert _widget({})._anchor_velocity_nm_h(FIJO) == (0.0, 0.0)


def test_velocidad_track_muerto_es_cero():
    w = _widget({"O": FakeTrack(gs=300, ta=90, alive=False)})
    assert w._anchor_velocity_nm_h(_ac("O")) == (0.0, 0.0)


# ---- _rbl_cpa --------------------------------------------------------------

def test_cpa_convergentes():
    # O en (0,0) al este 300 kt; D 6 NM al este y 0.6 NM al norte, al oeste 300 kt.
    w = _widget({"O": FakeTrack(gs=300, ta=90), "D": FakeTrack(gs=300, ta=270)})
    t_cpa, sep = w._rbl_cpa(0.0, 0.0, _ac("O"), 0.01, 0.1, _ac("D"))
    assert t_cpa == pytest.approx(36.0, abs=0.5)   # ~36 s hasta la mínima
    assert sep == pytest.approx(0.6, abs=0.02)     # 0.6 NM de separación mínima


def test_cpa_divergentes_devuelve_none():
    # Velocidades invertidas → se alejan → sin CPA futuro (E/X no se muestran).
    w = _widget({"O": FakeTrack(gs=300, ta=270), "D": FakeTrack(gs=300, ta=90)})
    assert w._rbl_cpa(0.0, 0.0, _ac("O"), 0.01, 0.1, _ac("D")) == (None, None)


def test_cpa_sin_movimiento_relativo_none():
    # Mismo vector de velocidad → separación constante → None.
    w = _widget({"O": FakeTrack(gs=300, ta=90), "D": FakeTrack(gs=300, ta=90)})
    assert w._rbl_cpa(0.0, 0.0, _ac("O"), 0.01, 0.1, _ac("D")) == (None, None)


def test_cpa_aeronave_a_punto_fijo():
    # Sólo el origen se mueve (al este) contra un punto fijo → CPA válido.
    w = _widget({"O": FakeTrack(gs=300, ta=90)})
    t_cpa, sep = w._rbl_cpa(0.0, 0.0, _ac("O"), 0.01, 0.1, FIJO)
    assert t_cpa == pytest.approx(72.0, abs=0.5)   # ~72 s
    assert sep == pytest.approx(0.6, abs=0.02)
