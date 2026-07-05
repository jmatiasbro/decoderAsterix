"""Verifica AltimetryManager (LLR-GEO-04): nivel de transición ENR 1.7 y toggle A/F."""
from decoder.altimetry import AltimetryManager


def _mgr(ta=10000):
    return AltimetryManager({"transition_altitude": ta})


def test_transition_level_por_banda_qnh():
    """TL = TA/100 + capa(QNH) según las bandas de presión de ENR 1.7."""
    m = _mgr(ta=10000)          # TA/100 = FL100
    m.qnh_local = 1035.0
    assert m.transition_level == 100          # capa 0
    m.qnh_local = 1020.0
    assert m.transition_level == 105          # capa 5
    m.qnh_local = 1000.0
    assert m.transition_level == 110          # capa 10
    m.qnh_local = 985.0
    assert m.transition_level == 115          # capa 15
    m.qnh_local = 900.0
    assert m.transition_level == 130          # capa 30 (fuera de bandas altas)


def test_transition_level_escala_con_ta():
    m = _mgr(ta=18000)          # TA/100 = FL180
    m.qnh_local = 1020.0
    assert m.transition_level == 185          # 180 + 5


def test_formatear_altitud_fl_nulo():
    assert _mgr().formatear_altitud(None) == "F---"


def test_formatear_altitud_toggle_a_bajo_ta():
    """Por debajo de la TA → etiqueta A (altitud); por encima → F (FL)."""
    m = _mgr(ta=10000)
    m.qnh_local = 1013.25       # sin corrección QNH
    assert m.formatear_altitud(50) == "A050"      # 5000 ft <= 10000
    assert m.formatear_altitud(150) == "F150"     # 15000 ft > 10000


def test_formatear_altitud_correccion_qnh():
    """La corrección por QNH desplaza la altitud mostrada (~30 ft/hPa)."""
    m = _mgr(ta=10000)
    m.qnh_local = 1013.25 + 10   # +300 ft aprox
    # FL90 = 9000 ft std + 300 = 9300 ft <= 10000 → A093
    assert m.formatear_altitud(90) == "A093"
