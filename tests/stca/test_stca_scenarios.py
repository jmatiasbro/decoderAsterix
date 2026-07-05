"""Escenarios STCA end-to-end a través del pipeline del RadarWidget.

A diferencia de `test_stca_engine.py` (unitario del motor), aquí se alimentan
plots por `on_new_plot_batch` y se ejerce toda la cadena del widget:
proyección → track en `self.tracks` → cálculo de velocidad → `evaluar_stca`
(builder de tracks_for_stca) → motor → `conflictos_activos`.

Cierra el hueco de trazabilidad "escenarios PCAP/end-to-end STCA" (matriz §3) y
documenta el hallazgo STCA-1 (doble marco de coordenadas): la fase VIOLATION usa
la posición cruda (lat_render, haversine), por lo que un conflicto real cercano
(<10 NM co-altitud) SIEMPRE dispara, con independencia del x/y suavizado.

REQ-SN-1 / HLR-STCA-01 / SSR-07 — ver 04_matriz_trazabilidad y 06_FHA.
"""
import math
import pytest

from tests.tracking.test_matching import app  # noqa: F401

LAT0, LON0 = -31.0, -64.0   # origen de proyección del escenario
NM_POR_GRADO_LAT = 60.0     # 1° de latitud ≈ 60 NM


@pytest.fixture
def w(app):
    from player.radar_widget import RadarWidget
    widget = RadarWidget()
    widget.sensores_visibles = None
    widget.limpiar_pantalla()
    widget.reset_origin_for_new_file(LAT0, LON0, 226, 210, "TEST")
    widget.modo_integrado = True
    widget.stca_habilitado = True
    # Desactivar el filtro DQF de pistas inmaduras: aquí se verifica el STCA, no el
    # DQF. Con un solo plot por aeronave, el DQF las marcaría inmaduras (<2 barridos)
    # y el builder de STCA las excluiría. El DQF tiene su propio banco de pruebas.
    widget.quality_manager.filtro_inmaduras_activo = False
    return widget


def _plot(mode_s, d_norte_nm, fl, speed=400.0, track_angle=90.0, mode3a=None, t=1000.0):
    """Plot ADS-B (CAT21) a `d_norte_nm` NM al norte del origen, a nivel `fl`.

    El squawk por defecto se deriva del Mode-S: distinto entre aeronaves distintas
    (evita la supresión por identidad del motor) e igual para el mismo Mode-S.
    """
    if mode3a is None:
        mode3a = "".join(str(ord(c) % 8) for c in mode_s[:4])  # p.ej. AAAAAA→1111
    lat = LAT0 + d_norte_nm / NM_POR_GRADO_LAT
    lon = LON0
    return {
        "sac_sic": "226/210", "category": 21, "time": t,
        "lat": lat, "lon": lon, "lat_render": lat, "lon_render": lon,
        "mode_s": mode_s, "mode3a": mode3a,
        "flight_level": int(fl), "ground_speed": speed, "track_angle": track_angle,
    }


def _pares_en_alerta(w):
    return {frozenset((c[0], c[1])) for c in getattr(w, 'conflictos_activos', [])}


def _hay_violacion(w):
    return any(c[2] == 'VIOLATION' for c in getattr(w, 'conflictos_activos', []))


# ── Escenario 1: conflicto real cercano → VIOLATION (verificación STCA-1) ──────

def test_conflicto_cercano_coaltitud_dispara_violacion(w):
    """Dos aeronaves a <10 NM y misma altitud (FL300) → VIOLATION.

    Núcleo del hallazgo STCA-1: la separación actual se resuelve con la posición
    cruda (lat_render), por lo que el conflicto se detecta sin depender del x/y.
    """
    w.on_new_plot_batch([
        _plot("AAAAAA", d_norte_nm=0.0, fl=300),
        _plot("BBBBBB", d_norte_nm=5.0, fl=300),
    ])
    w.evaluar_stca()
    assert _hay_violacion(w), "Conflicto real <10 NM co-altitud debe disparar VIOLATION"
    assert frozenset(("AAAAAA", "BBBBBB")) in _pares_en_alerta(w)


# ── Escenario 2: separación vertical suficiente → sin alerta ───────────────────

def test_separacion_vertical_no_alerta(w):
    """<10 NM horizontal pero ≥900 ft de separación vertical → sin conflicto."""
    w.on_new_plot_batch([
        _plot("AAAAAA", d_norte_nm=0.0, fl=300),
        _plot("BBBBBB", d_norte_nm=5.0, fl=320),   # 2000 ft de separación
    ])
    w.evaluar_stca()
    assert frozenset(("AAAAAA", "BBBBBB")) not in _pares_en_alerta(w)


# ── Escenario 3: separación horizontal amplia y rumbos paralelos → sin alerta ──

def test_separacion_horizontal_rumbos_paralelos_no_alerta(w):
    """>10 NM y velocidades paralelas (no convergen) → ni VIOLATION ni PREDICTION."""
    w.on_new_plot_batch([
        _plot("AAAAAA", d_norte_nm=0.0, fl=300, track_angle=90.0),
        _plot("BBBBBB", d_norte_nm=20.0, fl=300, track_angle=90.0),
    ])
    w.evaluar_stca()
    assert frozenset(("AAAAAA", "BBBBBB")) not in _pares_en_alerta(w)


# ── Escenario 4: misma aeronave (mismo Mode-S) → no se marca conflicto ─────────

def test_mismo_mode_s_no_es_conflicto(w):
    """Dos reportes con el mismo Mode-S son la misma aeronave → suprimido."""
    w.on_new_plot_batch([
        _plot("AAAAAA", d_norte_nm=0.0, fl=300, mode3a="1234"),
        _plot("AAAAAA", d_norte_nm=3.0, fl=300, mode3a="1234"),
    ])
    w.evaluar_stca()
    assert not _hay_violacion(w)


# ── Escenario 5: blancos estáticos (baja velocidad) → excluidos ────────────────

def test_blancos_estaticos_excluidos(w):
    """Velocidad <40 kt (obstáculos/calibración) → no entran al STCA."""
    w.on_new_plot_batch([
        _plot("AAAAAA", d_norte_nm=0.0, fl=300, speed=10.0),
        _plot("BBBBBB", d_norte_nm=5.0, fl=300, speed=10.0),
    ])
    w.evaluar_stca()
    assert frozenset(("AAAAAA", "BBBBBB")) not in _pares_en_alerta(w)


# ── Escenario 6: fuera de la banda de FL evaluada → sin alerta ─────────────────

def test_fuera_de_banda_fl_no_alerta(w):
    """Conflicto geométrico pero por debajo de FL245 → fuera de alcance STCA."""
    w.on_new_plot_batch([
        _plot("AAAAAA", d_norte_nm=0.0, fl=100),
        _plot("BBBBBB", d_norte_nm=5.0, fl=100),
    ])
    w.evaluar_stca()
    assert frozenset(("AAAAAA", "BBBBBB")) not in _pares_en_alerta(w)


# ── Escenario 7: STCA inhibido → no evalúa ─────────────────────────────────────

def test_stca_inhibido_no_evalua(w):
    """Con stca_habilitado=False no se generan conflictos aunque exista geometría."""
    w.stca_habilitado = False
    w.on_new_plot_batch([
        _plot("AAAAAA", d_norte_nm=0.0, fl=300),
        _plot("BBBBBB", d_norte_nm=5.0, fl=300),
    ])
    w.evaluar_stca()
    assert getattr(w, 'conflictos_activos', []) == []
