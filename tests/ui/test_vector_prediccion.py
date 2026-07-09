"""Predictor del vector de velocidad (`radar_widget._puntos_prediccion_mundo`).

Verifica que el vector proyecte la posición real futura de la pista a 1/2/3 min
(HMI — vector velocidad a escala real): dirección, una marca por minuto, distancia
real proporcional a la velocidad y tope anti-inflación de 600 kt.
"""
import math
import pytest

from player.radar_widget import RadarWidget
from utils.geo import METERS_PER_NM

pred = RadarWidget._puntos_prediccion_mundo


def test_una_marca_por_minuto():
    assert len(pred(0.0, 0.0, 300.0, 0.0, 1)) == 1
    assert len(pred(0.0, 0.0, 300.0, 0.0, 2)) == 2
    assert len(pred(0.0, 0.0, 300.0, 0.0, 3)) == 3


def test_minutos_minimo_uno():
    assert len(pred(0.0, 0.0, 300.0, 0.0, 0)) == 1


def test_rumbo_norte_avanza_en_y():
    # 0° = Norte → sólo crece la coordenada norte (y); x queda constante.
    pts = pred(1000.0, 2000.0, 360.0, 0.0, 2)
    assert pts[0][0] == pytest.approx(1000.0)
    assert pts[1][0] == pytest.approx(1000.0)
    assert pts[0][1] > 2000.0 and pts[1][1] > pts[0][1]


def test_rumbo_este_avanza_en_x():
    pts = pred(0.0, 0.0, 300.0, 90.0, 1)
    assert pts[0][0] > 0.0                            # este
    assert pts[0][1] == pytest.approx(0.0, abs=1e-6)  # sin componente norte


def test_distancia_real_a_escala():
    # 600 kt = 10 NM/min → la punta a 1 min está a 10 NM reales del origen.
    (px, py), = pred(0.0, 0.0, 600.0, 0.0, 1)
    assert math.hypot(px, py) == pytest.approx(10.0 * METERS_PER_NM, rel=1e-6)


def test_marcas_equiespaciadas():
    pts = pred(0.0, 0.0, 480.0, 0.0, 3)
    d1, d2, d3 = (math.hypot(*p) for p in pts)
    assert d2 == pytest.approx(2 * d1, rel=1e-6)
    assert d3 == pytest.approx(3 * d1, rel=1e-6)


def test_tope_600kt():
    # gs=900 se topa en 600 → misma punta que gs=600.
    p900, = pred(0.0, 0.0, 900.0, 45.0, 1)
    p600, = pred(0.0, 0.0, 600.0, 45.0, 1)
    assert p900 == pytest.approx(p600)
