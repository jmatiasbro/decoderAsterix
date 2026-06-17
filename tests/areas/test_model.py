from datetime import datetime, time

from player.areas.model import (Area, Vigencia, haversine_nm, point_in_poly,
                                 UNLIMITED_FL)


def test_point_in_poly_dentro_fuera():
    sq = [(0.0, 0.0), (0.0, 2.0), (2.0, 2.0), (2.0, 0.0)]  # (lat,lon)
    assert point_in_poly(1.0, 1.0, sq) is True
    assert point_in_poly(3.0, 1.0, sq) is False
    assert point_in_poly(1.0, 3.0, sq) is False
    assert point_in_poly(1.0, 1.0, sq[:2]) is False         # < 3 vértices


def test_haversine_nm():
    # 1 minuto de latitud ~ 1 NM
    assert abs(haversine_nm(0.0, 0.0, 1.0 / 60.0, 0.0) - 1.0) < 0.02


def test_area_circulo_contiene_y_banda():
    a = Area("X", "P", "circle", lower_fl=0, upper_fl=100,
             center=(-31.0, -64.0), radius_nm=10.0)
    assert a.contiene(-31.0 + 5.0 / 60.0, -64.0) is True     # ~5 NM al norte
    assert a.contiene(-31.0 + 20.0 / 60.0, -64.0) is False   # ~20 NM
    assert a.banda(50) is True
    assert a.banda(150) is False
    assert a.banda(None) is False
    assert a.banda(105, margen=10) is True


def test_area_poligono_bbox_y_polilinea():
    a = Area("Y", "R", "poly", vertices=[(0.0, 0.0), (0.0, 2.0), (2.0, 1.0)])
    assert a.bbox() == (0.0, 0.0, 2.0, 2.0)
    pl = a.polilinea()
    assert pl[0] == pl[-1]                                   # cerrada


def test_vigencia_permanente_y_manual():
    lun = datetime(2026, 6, 15, 12, 0)                       # lunes
    assert Vigencia(permanente=True).activa(lun) is True
    assert Vigencia(permanente=True, habilitada=False).activa(lun) is False


def test_vigencia_temporal_dias_y_franja():
    lun = datetime(2026, 6, 15, 12, 0)                       # lunes 12:00
    mar = datetime(2026, 6, 16, 12, 0)                       # martes 12:00
    v = Vigencia(permanente=False, dias={0}, desde=time(8, 0), hasta=time(18, 0))
    assert v.activa(lun) is True
    assert v.activa(mar) is False                            # martes no
    assert v.activa(datetime(2026, 6, 15, 6, 0)) is False    # fuera de franja


def test_default_upper_unlimited():
    assert Area("Z", "D", "poly").upper_fl == UNLIMITED_FL
