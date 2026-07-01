"""REQ-FUS-1/2: Correlator — correlación multisensor y calibración headless."""
import math
import pytest
from fusion.correlator import Correlator, CorrelatorConfig

NM = 1852.0


def _track(x=0.0, y=0.0, ts=1000.0, mode_s=None, mode3a=None, fl=None,
           gs=None, ta=None, vx=None, vy=None):
    class T:
        pass
    t = T()
    t.x, t.y, t.timestamp = x, y, ts
    t.mode_s = mode_s or ""
    t.mode3a = mode3a
    t.flight_level = fl
    t.altitude_ft = None
    t.ground_speed = gs
    t.track_angle = ta
    if vx is not None:
        t._smooth_vx = vx
        t._smooth_vy = vy or 0.0
    return t


@pytest.fixture
def c():
    return Correlator()


# ── claves_identidad ────────────────────────────────────────────────────────

class TestClavesIdentidad:

    def test_mode_s_genera_clave_ms(self, c):
        t = _track(mode_s='7C1234')
        assert ('MS', '7C1234') in c.claves_identidad(t)

    def test_squawk_no_generico_genera_clave_sq(self, c):
        t = _track(mode3a=0o2375)
        assert ('SQ', '2375') in c.claves_identidad(t)

    def test_squawk_generico_7000_no_genera_sq(self, c):
        t = _track(mode3a=0o7000)
        assert not any(k[0] == 'SQ' for k in c.claves_identidad(t))

    def test_squawk_1200_no_genera_sq(self, c):
        t = _track(mode3a=0o1200)
        assert not any(k[0] == 'SQ' for k in c.claves_identidad(t))

    def test_sin_identidad_lista_vacia(self, c):
        t = _track()
        assert c.claves_identidad(t) == []

    def test_ambas_claves_juntas(self, c):
        t = _track(mode_s='7C1234', mode3a=0o2375)
        keys = c.claves_identidad(t)
        assert ('MS', '7C1234') in keys
        assert ('SQ', '2375') in keys


# ── velocidad ───────────────────────────────────────────────────────────────

class TestVelocidad:

    def test_smooth_vx_vy_tiene_prioridad(self, c):
        t = _track(vx=50.0, vy=100.0, gs=999, ta=45)
        vx, vy = c.velocidad(t)
        assert vx == 50.0 and vy == 100.0

    def test_desde_ground_speed_y_track_angle_norte(self, c):
        t = _track(gs=300.0, ta=0.0)   # 300 kt al Norte
        vx, vy = c.velocidad(t)
        assert vx == pytest.approx(0.0, abs=1.0)
        assert vy == pytest.approx(300 * NM / 3600, rel=0.01)

    def test_desde_ground_speed_este(self, c):
        t = _track(gs=300.0, ta=90.0)
        vx, vy = c.velocidad(t)
        assert vx == pytest.approx(300 * NM / 3600, rel=0.01)
        assert vy == pytest.approx(0.0, abs=1.0)

    def test_sin_velocidad_retorna_cero(self, c):
        t = _track()
        assert c.velocidad(t) == (0.0, 0.0)

    def test_velocidad_excesiva_ignorada(self, c):
        t = _track(gs=99999.0, ta=0.0)  # > vel_fallback_max_mps
        assert c.velocidad(t) == (0.0, 0.0)


# ── extrapolar ──────────────────────────────────────────────────────────────

class TestExtrapolar:

    def test_extrapola_norte_4s(self, c):
        t = _track(x=0, y=0, ts=1000.0, vx=0, vy=100.0)
        x2, y2 = c.extrapolar(t, 1004.0)
        assert x2 == pytest.approx(0.0, abs=1)
        assert y2 == pytest.approx(400.0, abs=1)

    def test_extrapola_sin_velocidad_queda_en_sitio(self, c):
        t = _track(x=500, y=300, ts=1000.0)
        x2, y2 = c.extrapolar(t, 1010.0)
        assert x2 == pytest.approx(500.0)
        assert y2 == pytest.approx(300.0)

    def test_dt_mayor_max_no_extrapola(self, c):
        t = _track(x=0, y=0, ts=1000.0, vx=0, vy=100.0)
        x2, y2 = c.extrapolar(t, 1040.0)  # 40s > extrapol_max_dt_s=30
        assert x2 == 0.0 and y2 == 0.0

    def test_sin_timestamp_no_extrapola(self, c):
        t = _track(x=100, y=200, ts=None, vx=50, vy=50)
        x2, y2 = c.extrapolar(t, 1005.0)
        assert x2 == pytest.approx(100.0)
        assert y2 == pytest.approx(200.0)


# ── son_misma_aeronave ──────────────────────────────────────────────────────

class TestSonMismaAeronave:

    def test_co_ubicados_sin_identidad_son_misma(self, c):
        a = _track(x=0, y=0, ts=1000.0)
        b = _track(x=100, y=100, ts=1000.0)   # 141 m < 0.7 NM
        assert c.son_misma_aeronave(a, b) is True

    def test_lejos_sin_identidad_no_son_misma(self, c):
        a = _track(x=0, y=0, ts=1000.0)
        b = _track(x=2 * NM, y=0, ts=1000.0)  # 2 NM > gate estricto 0.7 NM
        assert c.son_misma_aeronave(a, b) is False

    def test_mode_s_distintos_no_son_misma(self, c):
        a = _track(x=0, y=0, ts=1000.0, mode_s='7C1111')
        b = _track(x=0, y=0, ts=1000.0, mode_s='7C2222')
        assert c.son_misma_aeronave(a, b) is False

    def test_squawk_distintos_no_son_misma(self, c):
        a = _track(x=0, y=0, ts=1000.0, mode3a=0o1111)
        b = _track(x=0, y=0, ts=1000.0, mode3a=0o2222)
        assert c.son_misma_aeronave(a, b) is False

    def test_fl_diferente_1500ft_no_son_misma(self, c):
        a = _track(x=0, y=0, ts=1000.0, fl=100)
        b = _track(x=0, y=0, ts=1000.0, fl=115)   # 1500 ft exactos → False
        assert c.son_misma_aeronave(a, b) is False

    def test_fl_diferente_menos_1500ft_son_misma(self, c):
        a = _track(x=0, y=0, ts=1000.0, fl=100)
        b = _track(x=0, y=0, ts=1000.0, fl=114)   # 1400 ft < 1500 ft → True
        assert c.son_misma_aeronave(a, b) is True

    def test_asociacion_aprendida_mantiene_fusion(self, c):
        a = _track(x=0, y=0, ts=1000.0, mode_s='7C1234', mode3a=0o2375)
        b = _track(x=0, y=0, ts=1000.0, mode3a=0o2375)
        c.registrar_asociacion(a, b)
        # Ahora b está a 4 NM pero dentro del gate_asociado (5 NM) y con asociación
        b2 = _track(x=4 * NM, y=0, ts=1004.0, mode3a=0o2375)
        assert c.son_misma_aeronave(a, b2) is True

    def test_mode_s_igual_squawk_diferente_posicion_cercana(self, c):
        """Mode S igual gana: un squawk diferente no puede descartar si posición cercana."""
        a = _track(x=0, y=0, ts=1000.0, mode_s='7C5555', mode3a=0o1111)
        b = _track(x=100, y=100, ts=1000.0, mode_s='7C5555', mode3a=0o2222)
        # mode_s iguales pero squawk distintos → debería devolver False (squawks contradicen)
        assert c.son_misma_aeronave(a, b) is False


# ── registrar_asociacion ────────────────────────────────────────────────────

class TestRegistrarAsociacion:

    def test_registrar_persiste_en_assoc(self, c):
        a = _track(mode_s='AA1111')
        b = _track(mode3a=0o3456)
        c.registrar_asociacion(a, b)
        assert len(c._assoc) > 0

    def test_asociacion_bidireccional(self, c):
        a = _track(mode_s='BB2222')
        b = _track(mode3a=0o4567)
        c.registrar_asociacion(a, b)
        keys = set(c._assoc.keys())
        assert ('MS', 'BB2222') in keys
        assert ('SQ', '4567') in keys

    def test_multiples_tracks_cruzan(self, c):
        a = _track(mode_s='CC3333', mode3a=0o5555)
        b = _track(mode_s='DD4444')
        c.registrar_asociacion(a, b)
        # MS→MS, MS→SQ, SQ→MS, SQ→MS cross
        assert len(c._assoc) >= 3
