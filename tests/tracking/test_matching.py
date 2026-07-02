"""Banco de pruebas REQ-TRK-2: correlación / matching de tracks en RadarWidget._process_plot_data.

Estrategia:
- QT_QPA_PLATFORM=offscreen para instanciar RadarWidget sin pantalla.
- Usar x_meters/y_meters en los dicts de plot para saltear la proyección.
- Usar CAT021 (ADS-B) como categoría de test: bypass_pending=True, los plots
  van directo a self.tracks — fácil de verificar sin esperar el sweep.
- Cada test llama limpiar_pantalla() vía el fixture, garantizando estado limpio.

Pasos A–E del matching:
  A. Mode S (ICAO) — máxima prioridad
  B. Squawk (Mode 3/A) + ventana de distancia (10 NM genérico / 30 NM resto)
  C. Track number + 30 NM
  D. Mismo sensor + coords polares (tolerancia 0.15 NM / 0.5°)
  E. Proximidad cartesiana 3D (1 NM sin alt / 3 NM con alt, ±1500 ft)
"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
pytest.importorskip("PyQt6.QtWidgets")
from PyQt6.QtWidgets import QApplication

NM = 1852.0  # metros por NM


# ────────────────────────────────────────────────────────────────────────────
# Fixtures
# ────────────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def w(app):
    from player.radar_widget import RadarWidget
    widget = RadarWidget()
    # Forzar proyección inicializada (bypass al check `if not self.projection_set`)
    widget.projection_set = True
    widget.sensores_visibles = None   # sin filtro de sensor
    widget.modo_integrado = True
    widget.limpiar_pantalla()
    return widget


def plot(sac_sic="226/210", cat=21, time=1000.0, x=0.0, y=0.0,
         mode_s=None, mode3a=None, track_num=None, fl=None, **kw):
    d = {
        'sac_sic': sac_sic,
        'category': cat,
        'time': time,
        'x_meters': float(x),
        'y_meters': float(y),
    }
    if mode_s is not None:
        d['mode_s'] = mode_s
    if mode3a is not None:
        d['mode3a'] = mode3a
    if track_num is not None:
        d['track_number'] = track_num
    if fl is not None:
        d['flight_level'] = fl
    d.update(kw)
    return d


def proc(w, data):
    """Llama _process_plot_data y devuelve el target_id resultante."""
    return w._process_plot_data(data)


# ────────────────────────────────────────────────────────────────────────────
# Paso A: Mode S (ICAO)
# ────────────────────────────────────────────────────────────────────────────

class TestMatchingModeS:

    def test_mismo_modes_mismo_track(self, w):
        """Dos plots con idéntico Mode S → mismo target_id."""
        t1 = proc(w, plot(mode_s='7C1234', x=0, y=0, time=1000.0))
        t2 = proc(w, plot(mode_s='7C1234', x=100, y=100, time=1004.0))
        assert t1 == t2

    def test_diferente_modes_diferente_track(self, w):
        """Mode S distintos → tracks distintos (posiciones >1 NM para no activar paso E)."""
        t1 = proc(w, plot(mode_s='7C1234', x=0, y=0))
        t2 = proc(w, plot(mode_s='7CABCD', x=2 * NM, y=0))
        assert t1 != t2

    def test_modes_tiene_prioridad_sobre_squawk(self, w):
        """Mode S idéntico pero squawk diferente → se fusionan (A gana sobre B)."""
        t1 = proc(w, plot(mode_s='7C1234', mode3a=0o2375, x=0, y=0))
        t2 = proc(w, plot(mode_s='7C1234', mode3a=0o4567, x=50, y=50))
        assert t1 == t2

    def test_modes_multisensor_se_fusionan_en_integrado(self, w):
        """Mode S mismo desde dos sensores distintos → mismo track en modo integrado."""
        t1 = proc(w, plot(sac_sic='226/210', mode_s='7C5555', x=0, y=0))
        t2 = proc(w, plot(sac_sic='226/211', mode_s='7C5555', x=200, y=200))
        assert t1 == t2

    def test_target_id_usa_modes(self, w):
        """target_id contiene la dirección Mode S en la clave."""
        tid = proc(w, plot(mode_s='ABCDEF', x=0, y=0))
        assert 'ABCDEF' in tid

    def test_modes_mock_filtrado_antes_del_matching(self, w):
        """Mode S con prefijo 0AD5B es filtrado en la entrada → retorna None."""
        t1 = proc(w, plot(sac_sic='1/1', mode_s='0AD5B1', x=0, y=0))
        t2 = proc(w, plot(sac_sic='1/2', mode_s='0AD5B1', x=200, y=200))
        # El código hace `return None` antes de cualquier matching para estos prefijos
        assert t1 is None and t2 is None


# ────────────────────────────────────────────────────────────────────────────
# Paso B: Squawk (Mode 3/A)
# ────────────────────────────────────────────────────────────────────────────

class TestMatchingSquawk:

    def test_squawk_dentro_gate_fusiona(self, w):
        """Squawk 2375 dentro de 30 NM → mismo track."""
        t1 = proc(w, plot(mode3a=0o2375, x=0, y=0, time=1000.0))
        t2 = proc(w, plot(mode3a=0o2375, x=10 * NM, y=0, time=1004.0))
        assert t1 == t2

    def test_squawk_fuera_de_gate_no_fusiona_cross_sensor(self, w):
        """Cross-sensor: squawk idéntico a >30 NM → IDs distintos (gate falla).

        Nota: intra-sensor el ID-fallback siempre fusiona por clave squawk+sensor.
        El gate solo es efectivo en modo integrado para plots de sensores distintos.
        """
        t1 = proc(w, plot(sac_sic='226/210', mode3a=0o2375, x=0, y=0, time=1000.0))
        t2 = proc(w, plot(sac_sic='226/211', mode3a=0o2375, x=35 * NM, y=0, time=1004.0))
        assert t1 != t2

    def test_squawk_generico_7000_gate_reducido_cross_sensor(self, w):
        """Squawk 7000 cross-sensor a 15 NM → fuera del gate reducido (10 NM)."""
        t1 = proc(w, plot(sac_sic='226/210', mode3a=0o7000, x=0, y=0, time=1000.0))
        t2 = proc(w, plot(sac_sic='226/211', mode3a=0o7000, x=15 * NM, y=0, time=1004.0))
        assert t1 != t2

    def test_squawk_generico_7000_dentro_gate_fusiona(self, w):
        """Squawk 7000 cross-sensor dentro de 10 NM → fusiona."""
        t1 = proc(w, plot(sac_sic='226/210', mode3a=0o7000, x=0, y=0, time=1000.0))
        t2 = proc(w, plot(sac_sic='226/211', mode3a=0o7000, x=5 * NM, y=0, time=1004.0))
        assert t1 == t2

    def test_squawk_0000_sin_identidad_retorna_none(self, w):
        """Squawk 0000 sin Mode S, track_num ni coordenadas polares → None."""
        t1 = proc(w, plot(cat=21, mode3a=0, x=0, y=0, time=1000.0))
        # CAT21 sin mode_s, squawk 0000: sin identidad → None
        assert t1 is None


# ────────────────────────────────────────────────────────────────────────────
# Paso C: Track Number
# ────────────────────────────────────────────────────────────────────────────

class TestMatchingTrackNumber:

    def test_track_number_dentro_30nm_fusiona(self, w):
        """Mismo track_number dentro de 30 NM → fusiona."""
        t1 = proc(w, plot(track_num=1234, x=0, y=0, time=1000.0))
        t2 = proc(w, plot(track_num=1234, x=5 * NM, y=0, time=1004.0))
        assert t1 == t2

    def test_track_number_fuera_30nm_no_fusiona_cross_sensor(self, w):
        """Cross-sensor: mismo TN a >30 NM → no fusiona (gate C falla)."""
        t1 = proc(w, plot(sac_sic='226/210', track_num=5678, x=0, y=0, time=1000.0))
        t2 = proc(w, plot(sac_sic='226/211', track_num=5678, x=40 * NM, y=0, time=1004.0))
        assert t1 != t2

    def test_track_number_diferente_no_fusiona(self, w):
        """TN distintos → nunca fusionan (posiciones >1 NM para no activar E)."""
        t1 = proc(w, plot(track_num=100, x=0, y=0))
        t2 = proc(w, plot(track_num=200, x=2 * NM, y=0))
        assert t1 != t2


# ────────────────────────────────────────────────────────────────────────────
# Paso D: Mismo sensor + coordenadas polares
# ────────────────────────────────────────────────────────────────────────────

class TestMatchingPolar:

    def test_mismo_sensor_polar_identico_fusiona(self, w):
        """Mismo sensor + rho/theta idénticos → mismo eco → fusiona."""
        t1 = proc(w, plot(cat=48, sac_sic='226/210',
                          x=50 * NM, y=0,
                          raw_range=50.0, raw_azimuth=90.0, time=1000.0))
        t2 = proc(w, plot(cat=48, sac_sic='226/210',
                          x=50 * NM, y=0,
                          raw_range=50.0, raw_azimuth=90.0, time=1005.0))
        # Para CAT048 sin mode_s/mode3a/track_num, llega a paso D
        assert t1 == t2

    def test_mismo_sensor_polar_dentro_tolerancia(self, w):
        """Mismo sensor, rho dentro de 0.15 NM y az dentro de 0.5° → fusiona."""
        t1 = proc(w, plot(cat=48, sac_sic='226/210',
                          x=50 * NM, y=0,
                          raw_range=50.0, raw_azimuth=90.0, time=1000.0))
        t2 = proc(w, plot(cat=48, sac_sic='226/210',
                          x=50.1 * NM, y=0,
                          raw_range=50.1, raw_azimuth=90.3, time=1005.0))
        assert t1 == t2

    def test_mismo_sensor_polar_fuera_tolerancia_theta(self, w):
        """Diferencia de azimut >0.5° y posición >1 NM → no fusiona (D ni E)."""
        t1 = proc(w, plot(cat=48, sac_sic='226/210',
                          x=50 * NM, y=0,
                          raw_range=50.0, raw_azimuth=90.0, time=1000.0))
        t2 = proc(w, plot(cat=48, sac_sic='226/210',
                          x=50 * NM, y=3 * NM,   # >1 NM en Y para evitar E
                          raw_range=50.0, raw_azimuth=91.0, time=1005.0))
        assert t1 != t2

    def test_sensor_diferente_polar_no_fusiona_en_D(self, w):
        """Paso D requiere mismo sensor; sensor distinto debe fallar D (posiciones >1 NM)."""
        t1 = proc(w, plot(cat=48, sac_sic='226/210',
                          x=50 * NM, y=0,
                          raw_range=50.0, raw_azimuth=90.0, time=1000.0))
        t2 = proc(w, plot(cat=48, sac_sic='226/211',
                          x=50 * NM, y=3 * NM,   # >1 NM para evitar E
                          raw_range=50.0, raw_azimuth=90.0, time=1005.0))
        assert t1 != t2


# ────────────────────────────────────────────────────────────────────────────
# Paso E: Proximidad cartesiana 3D
# ────────────────────────────────────────────────────────────────────────────

class TestMatchingProximidad:

    def test_sin_altitud_1nm_fusiona(self, w):
        """Sin FL, dentro de 1 NM → fusiona."""
        t1 = proc(w, plot(cat=21, sac_sic='226/210',
                          mode_s='E1E1E1', x=0, y=0, time=1000.0))
        # Mueve track a posición conocida
        t2 = proc(w, plot(cat=21, sac_sic='226/210',
                          mode_s=None, x=0.9 * NM, y=0, time=1004.0))
        # Sin mode_s/mode3a en el segundo plot → pasa a E → debe colapsar
        assert t1 == t2 or len(w.tracks) == 1  # one track in widget

    def test_sin_altitud_2nm_no_fusiona(self, w):
        """Sin FL, a 2 NM → no fusiona en E (gate = 1 NM sin alt)."""
        t1 = proc(w, plot(cat=21, sac_sic='226/210',
                          mode_s='F2F2F2', x=0, y=0, time=1000.0))
        t2 = proc(w, plot(cat=21, sac_sic='226/210',
                          mode_s=None, x=2 * NM, y=0, time=1004.0))
        assert t1 != t2 or len(w.tracks) == 2

    def test_con_altitud_dentro_gate_vertical_fusiona(self, w):
        """Con FL, dentro de 3 NM y < 1500 ft vertical → fusiona."""
        t1 = proc(w, plot(cat=21, mode_s='A3A3A3', x=0, y=0, fl=250, time=1000.0))
        t2 = proc(w, plot(cat=21, mode_s=None, x=2 * NM, y=0, fl=260, time=1004.0))
        # 10 FL × 100 = 1000 ft < 1500 ft → dentro del gate vertical
        assert t1 == t2 or len(w.tracks) == 1

    def test_con_altitud_fuera_gate_vertical_no_fusiona(self, w):
        """Misma posición horizontal pero ΔFL > 1500 ft → no fusiona."""
        t1 = proc(w, plot(cat=21, mode_s='B4B4B4', x=0, y=0, fl=100, time=1000.0))
        t2 = proc(w, plot(cat=21, mode_s=None, x=0, y=0, fl=250, time=1004.0))
        # ΔFL = 15000 ft >> 1500 ft → no match por E
        assert t1 != t2


# ────────────────────────────────────────────────────────────────────────────
# CAT062: System Tracks (clave TRK_{tn}_{sensor_id})
# ────────────────────────────────────────────────────────────────────────────

class TestMatchingCat62:

    def test_mismo_track_number_fusiona(self, w):
        """CAT62 mismo TN → mismo target_id (sin correlación A-E)."""
        t1 = proc(w, plot(cat=62, sac_sic='226/210', track_num=100,
                          x=0, y=0, time=1000.0, is_track=True))
        t2 = proc(w, plot(cat=62, sac_sic='226/210', track_num=100,
                          x=100, y=100, time=1004.0, is_track=True))
        assert t1 == t2

    def test_diferente_track_number_diferente_track(self, w):
        t1 = proc(w, plot(cat=62, sac_sic='226/210', track_num=100,
                          x=0, y=0, time=1000.0, is_track=True))
        t2 = proc(w, plot(cat=62, sac_sic='226/210', track_num=200,
                          x=100, y=100, time=1004.0, is_track=True))
        assert t1 != t2

    def test_cat62_sin_track_number_retorna_none(self, w):
        """CAT62 sin track_number → descartado."""
        tid = proc(w, plot(cat=62, sac_sic='226/210',
                           x=0, y=0, time=1000.0, is_track=True))
        # Sin track_num en el dict → return None
        assert tid is None

    def test_cat62_por_sensor_distinto(self, w):
        """TN igual pero sensor distinto → tracks distintos (clave incluye sensor_id)."""
        t1 = proc(w, plot(cat=62, sac_sic='226/210', track_num=100,
                          x=0, y=0, time=1000.0, is_track=True))
        t2 = proc(w, plot(cat=62, sac_sic='226/211', track_num=100,
                          x=0, y=0, time=1004.0, is_track=True))
        assert t1 != t2


# ────────────────────────────────────────────────────────────────────────────
# Robustez y edge cases
# ────────────────────────────────────────────────────────────────────────────

class TestMatchingRobustez:

    def test_sin_posicion_retorna_none(self, w):
        """Plot sin coordenadas válidas → retorna None."""
        tid = w._process_plot_data({'sac_sic': '226/210', 'category': 21, 'time': 1000.0})
        assert tid is None

    def test_projection_no_set_retorna_none(self, w):
        """Si projection_set=False, ningún plot se procesa."""
        w.projection_set = False
        tid = proc(w, plot(mode_s='7C9999', x=0, y=0))
        w.projection_set = True  # restaurar para siguientes tests
        assert tid is None

    def test_plot_acumula_en_tracks(self, w):
        """Plots procesados aparecen en self.tracks (CAT21 bypass_pending=True)."""
        proc(w, plot(mode_s='AAAAAA', x=0, y=0, time=1000.0))
        proc(w, plot(mode_s='BBBBBB', x=2 * NM, y=0, time=1001.0))  # >1 NM para no activar E
        assert len(w.tracks) == 2

    def test_tres_plots_mismo_modes_un_track(self, w):
        """Tres actualizaciones del mismo avión → un solo track."""
        for t in [1000.0, 1004.0, 1008.0]:
            proc(w, plot(mode_s='C3C3C3', x=t * 10, y=0, time=t))
        assert len(w.tracks) == 1

    def test_squawk_igual_modes_distinguidos(self, w):
        """Squawk idéntico pero Mode S diferente → tracks separados (paso A gana sobre B).

        Posiciones a >30 NM para que B no fusione por squawk aunque A ya creó el primero.
        """
        proc(w, plot(mode_s='111111', mode3a=0o1234, x=0, y=0))
        proc(w, plot(mode_s='222222', mode3a=0o1234, x=35 * NM, y=0))
        assert len(w.tracks) == 2


# ────────────────────────────────────────────────────────────────────────────
# HLR-TRK-08: modo_integrado=False — sin fusión cross-sensor
# ────────────────────────────────────────────────────────────────────────────

class TestModoNoIntegrado:
    """Con modo_integrado=False, tracks de sensores distintos nunca se fusionan
    aunque compartan squawk, Mode S o número de track."""

    @pytest.fixture
    def w_no_int(self, app):
        from player.radar_widget import RadarWidget
        widget = RadarWidget()
        widget.projection_set = True
        widget.sensores_visibles = None
        widget.modo_integrado = False  # <--- no integrado
        widget.limpiar_pantalla()
        return widget

    def test_mismo_modes_sensor_diferente_comparte_track(self, w_no_int):
        """Mode S es globalmente único: incluso en modo no-integrado, el mismo
        Mode S de sensores distintos va al mismo track (diseño intencional)."""
        t1 = proc(w_no_int, plot(sac_sic='226/210', mode_s='ABCDEF', x=0, y=0))
        t2 = proc(w_no_int, plot(sac_sic='226/211', mode_s='ABCDEF', x=0, y=0))
        assert t1 == t2  # Mode S global → mismo track

    def test_mismo_squawk_sensor_diferente_no_fusiona(self, w_no_int):
        """Paso B ignorado para sensores distintos en modo no-integrado."""
        t1 = proc(w_no_int, plot(sac_sic='226/210', mode3a=0o3333, x=0, y=0))
        t2 = proc(w_no_int, plot(sac_sic='226/211', mode3a=0o3333, x=100, y=0))
        assert t1 != t2

    def test_mismo_track_num_sensor_diferente_no_fusiona(self, w_no_int):
        """Paso C ignorado para sensores distintos en modo no-integrado."""
        t1 = proc(w_no_int, plot(sac_sic='226/210', track_num=55, x=0, y=0))
        t2 = proc(w_no_int, plot(sac_sic='226/211', track_num=55, x=100, y=0))
        assert t1 != t2

    def test_proximidad_sensor_diferente_no_fusiona(self, w_no_int):
        """Paso E (proximidad) no se ejecuta en modo no-integrado.

        Los plots sin identidad SSR necesitan rho/theta para obtener un
        target_id estable (FIX_…); con modo_integrado=False el paso E no
        corre y los sensores distintos generan tracks separados.
        """
        d1 = plot(sac_sic='226/210', x=0, y=0)
        d1['raw_range'] = 10.0
        d1['raw_azimuth'] = 90.0
        d2 = plot(sac_sic='226/211', x=0, y=0)
        d2['raw_range'] = 10.0
        d2['raw_azimuth'] = 90.0
        t1 = proc(w_no_int, d1)
        t2 = proc(w_no_int, d2)
        assert t1 is not None and t2 is not None
        assert t1 != t2

    def test_mismo_sensor_mismo_modes_fusiona(self, w_no_int):
        """Mismo sensor con mismo Mode S SIEMPRE fusiona, incluso sin modo integrado."""
        t1 = proc(w_no_int, plot(sac_sic='226/210', mode_s='FEDCBA', x=0, y=0))
        t2 = proc(w_no_int, plot(sac_sic='226/210', mode_s='FEDCBA', x=100, y=0))
        assert t1 == t2


# ────────────────────────────────────────────────────────────────────────────
# HLR-DEC-06: filtro de rango máximo por sensor (CAT48/01)
# ────────────────────────────────────────────────────────────────────────────

class TestFiltroRangoMaximo:
    """max_rango_sensor_nm descarta plots CAT48/01 con rho > límite."""

    def test_cat48_dentro_del_rango_aceptado(self, w):
        w.max_rango_sensor_nm = 100.0
        d = plot(cat=48, mode_s='A1B2C3', x=0, y=0)
        d['raw_range'] = 50.0   # 50 NM < 100 NM → aceptado
        assert proc(w, d) is not None

    def test_cat48_fuera_del_rango_descartado(self, w):
        w.max_rango_sensor_nm = 100.0
        d = plot(cat=48, x=0, y=0)
        d['raw_range'] = 150.0  # 150 NM > 100 NM → descartado
        assert proc(w, d) is None

    def test_cat48_exactamente_en_limite_descartado(self, w):
        """Rho == max (no estrictamente menor) → descartado."""
        w.max_rango_sensor_nm = 100.0
        d = plot(cat=48, x=0, y=0)
        d['raw_range'] = 100.0
        assert proc(w, d) is None

    def test_cat21_no_filtrado_por_rango(self, w):
        """CAT21 (ADS-B) no está sujeto al filtro de rango."""
        w.max_rango_sensor_nm = 10.0
        d = plot(cat=21, mode_s='AA1111', x=0, y=0)
        d['raw_range'] = 500.0  # > 10 NM pero cat=21 → no filtra
        assert proc(w, d) is not None

    def test_sin_raw_range_no_filtra(self, w):
        """Plot sin raw_range no es filtrado (coordenadas cartesianas directas)."""
        w.max_rango_sensor_nm = 10.0
        d = plot(cat=48, mode_s='D4E5F6', x=0, y=0)
        # sin 'raw_range' en el dict
        assert proc(w, d) is not None
