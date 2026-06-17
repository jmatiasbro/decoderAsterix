from player.msaw.model import enu_nm, cross_along_nm


def test_enu_nm_norte_este():
    # 1 minuto de lat ~ 1 NM al norte
    x, y = enu_nm(0.0, 0.0, 1.0 / 60, 0.0)
    assert abs(y - 1.0) < 0.02
    assert abs(x) < 0.001


def test_cross_along_sobre_eje():
    # segmento de (0,0) a (0, 0.1) (hacia el este); punto sobre el eje a mitad
    cross, along = cross_along_nm(0.0, 0.05, 0.0, 0.0, 0.0, 0.1)
    assert abs(cross) < 0.05
    assert along > 0


def test_cross_lateral():
    # punto desplazado al norte del eje este-oeste -> cross != 0
    cross, along = cross_along_nm(0.02, 0.05, 0.0, 0.0, 0.0, 0.1)
    assert abs(cross) > 0.5
