"""Banco de pruebas del motor STCA (analysis/stca_analyzer.py).

Verifica `STCA_Engine.evaluar_conflictos`, el motor real instanciado por
`radar_widget` (RadarWidget.stca_engine). Cada test aísla una regla de decisión:
filtros de entrada (banda FL, blancos estáticos, identidad/duplicados), fase de
VIOLATION (separación actual) y fase de PREDICTION (CPA cinemático).

Convenciones de unidades del motor:
- lat_render/lon_render en grados (separación actual vía haversine).
- x/y en metros, vx/vy en m/s (predicción de CPA).
- flight_level: string de dígitos (centenas de pies). speed_kt en nudos.

REQ-SN-1 — Matriz de trazabilidad ([documentacion/certificacion/04]).
"""
import math
import pytest

from analysis.stca_analyzer import STCA_Engine


def mk(**kw):
    """Track válido y conflicto-capaz por defecto: en banda FL, en movimiento,
    con identidad propia. Sobreescribir campos por test."""
    t = dict(
        speed_kt=400.0,
        flight_level="300",
        mode3a="1234",
        mode_s="AAAAAA",
        lat_render=0.0,
        lon_render=0.0,
        x=0.0,
        y=0.0,
        vx=100.0,
        vy=0.0,
    )
    t.update(kw)
    return t


def ids(conflictos):
    """Conjunto de pares (frozenset de ids) presentes en la lista de conflictos."""
    return {frozenset((c[0], c[1])) for c in conflictos}


@pytest.fixture
def eng():
    return STCA_Engine()


# --------------------------------------------------------------------------- #
# Geometría base
# --------------------------------------------------------------------------- #

def test_haversine_un_grado_latitud_es_60nm():
    # 1° de latitud ≈ 60 NM
    d = STCA_Engine.haversine_nm(0.0, 0.0, 1.0, 0.0)
    assert d == pytest.approx(60.0, abs=0.2)


def test_haversine_mismo_punto_es_cero():
    assert STCA_Engine.haversine_nm(-31.4, -64.2, -31.4, -64.2) == pytest.approx(0.0, abs=1e-6)


# --------------------------------------------------------------------------- #
# Fase de VIOLATION (separación actual)
# --------------------------------------------------------------------------- #

def test_violacion_horizontal_y_vertical(eng):
    # 0.1° lon ≈ 6 NM (<10) y co-altitud (<900 ft) → VIOLATION
    tracks = {
        "A": mk(lat_render=0.0, lon_render=0.0, mode3a="1111", mode_s="AAAAAA"),
        "B": mk(lat_render=0.0, lon_render=0.1, mode3a="2222", mode_s="BBBBBB"),
    }
    c = eng.evaluar_conflictos(tracks)
    assert len(c) == 1
    t1, t2, estado, tiempo, dist_h, dist_v = c[0]
    assert estado == "VIOLATION"
    assert tiempo == 0
    assert dist_h == pytest.approx(6.0, abs=0.3)
    assert dist_v == 0


def test_sin_violacion_si_separados_verticalmente(eng):
    # 1000 ft de separación (>=900) → sin conflicto pese a estar pegados
    tracks = {
        "A": mk(lat_render=0.0, lon_render=0.0, flight_level="300", mode3a="1111", mode_s="AAAAAA"),
        "B": mk(lat_render=0.0, lon_render=0.05, flight_level="310", mode3a="2222", mode_s="BBBBBB"),
    }
    assert eng.evaluar_conflictos(tracks) == []


def test_separacion_vertical_justo_bajo_umbral_es_violacion(eng):
    # 800 ft (<900) co-localizados horizontalmente → VIOLATION
    tracks = {
        "A": mk(lat_render=0.0, lon_render=0.0, flight_level="300", mode3a="1111", mode_s="AAAAAA"),
        "B": mk(lat_render=0.0, lon_render=0.05, flight_level="308", mode3a="2222", mode_s="BBBBBB"),
    }
    c = eng.evaluar_conflictos(tracks)
    assert len(c) == 1
    assert c[0][2] == "VIOLATION"
    assert c[0][5] == 800


# --------------------------------------------------------------------------- #
# Filtro de banda de niveles de vuelo (fl_min=245, fl_max=450)
# --------------------------------------------------------------------------- #

def test_fuera_de_banda_inferior_se_excluye(eng):
    tracks = {
        "A": mk(flight_level="200", lon_render=0.0, mode3a="1111", mode_s="AAAAAA"),
        "B": mk(flight_level="205", lon_render=0.05, mode3a="2222", mode_s="BBBBBB"),
    }
    assert eng.evaluar_conflictos(tracks) == []


def test_fuera_de_banda_superior_se_excluye(eng):
    tracks = {
        "A": mk(flight_level="460", lon_render=0.0, mode3a="1111", mode_s="AAAAAA"),
        "B": mk(flight_level="465", lon_render=0.05, mode3a="2222", mode_s="BBBBBB"),
    }
    assert eng.evaluar_conflictos(tracks) == []


def test_limite_inferior_de_banda_incluido(eng):
    # FL245 = fl_min → dentro de banda
    tracks = {
        "A": mk(flight_level="245", lon_render=0.0, mode3a="1111", mode_s="AAAAAA"),
        "B": mk(flight_level="245", lon_render=0.05, mode3a="2222", mode_s="BBBBBB"),
    }
    c = eng.evaluar_conflictos(tracks)
    assert len(c) == 1 and c[0][2] == "VIOLATION"


def test_flight_level_no_numerico_se_excluye(eng):
    tracks = {
        "A": mk(flight_level="", lon_render=0.0, mode3a="1111", mode_s="AAAAAA"),
        "B": mk(flight_level="300", lon_render=0.05, mode3a="2222", mode_s="BBBBBB"),
    }
    assert eng.evaluar_conflictos(tracks) == []


# --------------------------------------------------------------------------- #
# Filtro de blancos estáticos (speed_kt < 40)
# --------------------------------------------------------------------------- #

def test_blanco_estatico_se_excluye(eng):
    tracks = {
        "A": mk(speed_kt=10.0, lon_render=0.0, mode3a="1111", mode_s="AAAAAA"),
        "B": mk(speed_kt=400.0, lon_render=0.05, mode3a="2222", mode_s="BBBBBB"),
    }
    assert eng.evaluar_conflictos(tracks) == []


def test_speed_none_no_se_filtra(eng):
    # speed_kt None no debe filtrar (el filtro sólo aplica si hay velocidad)
    tracks = {
        "A": mk(speed_kt=None, lon_render=0.0, mode3a="1111", mode_s="AAAAAA"),
        "B": mk(speed_kt=None, lon_render=0.05, mode3a="2222", mode_s="BBBBBB"),
    }
    c = eng.evaluar_conflictos(tracks)
    assert len(c) == 1 and c[0][2] == "VIOLATION"


# --------------------------------------------------------------------------- #
# Supresión por identidad (misma aeronave) y por duplicado multi-radar
# --------------------------------------------------------------------------- #

def test_supresion_por_mismo_squawk(eng):
    tracks = {
        "A": mk(lon_render=0.0, mode3a="3017", mode_s="AAAAAA"),
        "B": mk(lon_render=0.05, mode3a="3017", mode_s="BBBBBB"),
    }
    assert eng.evaluar_conflictos(tracks) == []


def test_squawk_invalido_no_suprime(eng):
    # '----' y '0000' no son identidad válida → no deben suprimir
    for bad in ("----", "0000"):
        tracks = {
            "A": mk(lon_render=0.0, mode3a=bad, mode_s="AAAAAA"),
            "B": mk(lon_render=0.05, mode3a=bad, mode_s="BBBBBB"),
        }
        c = eng.evaluar_conflictos(tracks)
        assert len(c) == 1, f"squawk {bad} no debería suprimir"


def test_supresion_por_mismo_mode_s(eng):
    # mismo Mode S, distinto squawk → misma aeronave → suprimido
    tracks = {
        "A": mk(lon_render=0.0, mode3a="1111", mode_s="ABCDEF"),
        "B": mk(lon_render=0.05, mode3a="2222", mode_s="ABCDEF"),
    }
    assert eng.evaluar_conflictos(tracks) == []


def test_supresion_de_duplicado_multiradar(eng):
    # Mismo blanco visto por dos radares, no fusionado, sin identidad compartida:
    # superpuestos (<0.5 NM) y co-altitud (<200 ft) → no es conflicto real.
    tracks = {
        "A": mk(lat_render=0.0, lon_render=0.0, flight_level="300", mode3a="1111", mode_s="AAAAAA"),
        "B": mk(lat_render=0.0, lon_render=0.001, flight_level="300", mode3a="2222", mode_s="BBBBBB"),
    }
    assert eng.evaluar_conflictos(tracks) == []


def test_duplicado_no_suprime_si_hay_separacion_vertical(eng):
    # Superpuestos horizontalmente pero 300 ft (>=200) → es VIOLATION, no duplicado
    tracks = {
        "A": mk(lat_render=0.0, lon_render=0.0, flight_level="300", mode3a="1111", mode_s="AAAAAA"),
        "B": mk(lat_render=0.0, lon_render=0.001, flight_level="303", mode3a="2222", mode_s="BBBBBB"),
    }
    c = eng.evaluar_conflictos(tracks)
    assert len(c) == 1 and c[0][2] == "VIOLATION"


# --------------------------------------------------------------------------- #
# Fase de PREDICTION (CPA cinemático)
# --------------------------------------------------------------------------- #

def test_prediccion_convergente(eng):
    # Rumbos de colisión: actual >10 NM (sin violación) pero CPA ~2.7 NM a t≈100 s
    tracks = {
        "A": mk(lat_render=0.0, lon_render=0.0, x=0.0, y=0.0, vx=100.0, vy=0.0,
                mode3a="1111", mode_s="AAAAAA"),
        "B": mk(lat_render=0.0, lon_render=0.2, x=20000.0, y=5000.0, vx=-100.0, vy=0.0,
                mode3a="2222", mode_s="BBBBBB"),
    }
    c = eng.evaluar_conflictos(tracks)
    assert len(c) == 1
    t1, t2, estado, tiempo, dist_h, dist_v = c[0]
    assert estado == "PREDICTION"
    assert tiempo == pytest.approx(100, abs=2)
    assert dist_h == pytest.approx(2.7, abs=0.2)


def test_sin_prediccion_si_divergen(eng):
    # Mismas posiciones pero alejándose → t_cpa negativo → sin conflicto
    tracks = {
        "A": mk(lat_render=0.0, lon_render=0.0, x=0.0, y=0.0, vx=-100.0, vy=0.0,
                mode3a="1111", mode_s="AAAAAA"),
        "B": mk(lat_render=0.0, lon_render=0.2, x=20000.0, y=5000.0, vx=100.0, vy=0.0,
                mode3a="2222", mode_s="BBBBBB"),
    }
    assert eng.evaluar_conflictos(tracks) == []


def test_sin_prediccion_si_cpa_supera_minimo(eng):
    # Convergen en X pero quedan 40 km (~21.6 NM) separados en Y en el CPA
    tracks = {
        "A": mk(lat_render=0.0, lon_render=0.0, x=0.0, y=0.0, vx=100.0, vy=0.0,
                mode3a="1111", mode_s="AAAAAA"),
        "B": mk(lat_render=0.0, lon_render=0.2, x=20000.0, y=40000.0, vx=-100.0, vy=0.0,
                mode3a="2222", mode_s="BBBBBB"),
    }
    assert eng.evaluar_conflictos(tracks) == []


def test_sin_prediccion_si_cpa_mas_alla_de_120s(eng):
    # Convergencia lenta: CPA a ~2000 s (>120) → fuera de horizonte de alerta
    tracks = {
        "A": mk(lat_render=0.0, lon_render=0.0, x=0.0, y=0.0, vx=10.0, vy=0.0,
                mode3a="1111", mode_s="AAAAAA"),
        "B": mk(lat_render=0.0, lon_render=0.5, x=40000.0, y=0.0, vx=-10.0, vy=0.0,
                mode3a="2222", mode_s="BBBBBB"),
    }
    assert eng.evaluar_conflictos(tracks) == []


def test_sin_prediccion_si_rumbos_paralelos(eng):
    # Velocidad relativa nula (mismo vector) → v_sq < umbral → sin predicción
    tracks = {
        "A": mk(lat_render=0.0, lon_render=0.0, x=0.0, y=0.0, vx=100.0, vy=0.0,
                mode3a="1111", mode_s="AAAAAA"),
        "B": mk(lat_render=0.0, lon_render=0.2, x=20000.0, y=5000.0, vx=100.0, vy=0.0,
                mode3a="2222", mode_s="BBBBBB"),
    }
    assert eng.evaluar_conflictos(tracks) == []


def test_prediccion_sin_cinematica_se_omite(eng):
    # Sin x/y/vx/vy no puede predecirse → sin conflicto (y actual >10 NM)
    tracks = {
        "A": mk(x=None, y=None, vx=None, vy=None,
                lat_render=0.0, lon_render=0.0, mode3a="1111", mode_s="AAAAAA"),
        "B": mk(x=None, y=None, vx=None, vy=None,
                lat_render=0.0, lon_render=0.2, mode3a="2222", mode_s="BBBBBB"),
    }
    assert eng.evaluar_conflictos(tracks) == []


# --------------------------------------------------------------------------- #
# Robustez de entrada
# --------------------------------------------------------------------------- #

def test_coordenadas_faltantes_se_omiten(eng):
    tracks = {
        "A": mk(lat_render=None, lon_render=None, mode3a="1111", mode_s="AAAAAA"),
        "B": mk(lat_render=0.0, lon_render=0.05, mode3a="2222", mode_s="BBBBBB"),
    }
    assert eng.evaluar_conflictos(tracks) == []


def test_dict_vacio_y_single_track(eng):
    assert eng.evaluar_conflictos({}) == []
    assert eng.evaluar_conflictos({"A": mk()}) == []


def test_multiples_conflictos_independientes(eng):
    # Dos pares en violación, bien separados entre pares
    tracks = {
        "A": mk(lat_render=0.0, lon_render=0.0, mode3a="1111", mode_s="A1"),
        "B": mk(lat_render=0.0, lon_render=0.05, mode3a="2222", mode_s="A2"),
        "C": mk(lat_render=5.0, lon_render=5.0, mode3a="3333", mode_s="A3"),
        "D": mk(lat_render=5.0, lon_render=5.05, mode3a="4444", mode_s="A4"),
    }
    c = eng.evaluar_conflictos(tracks)
    assert ids(c) == {frozenset(("A", "B")), frozenset(("C", "D"))}
