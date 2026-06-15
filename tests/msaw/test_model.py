import math

from player.msaw.model import MsaZone, MsaSector, bearing_true, in_arc


def test_bearing_true_cardinales():
    # desde (0,0): norte ~0, este ~90, sur ~180, oeste ~270
    assert abs(bearing_true(0, 0, 1, 0) - 0) < 0.5
    assert abs(bearing_true(0, 0, 0, 1) - 90) < 0.5
    assert abs(bearing_true(0, 0, -1, 0) - 180) < 0.5
    assert abs(bearing_true(0, 0, 0, -1) - 270) < 0.5


def test_in_arc_normal_y_cruce_de_cero():
    assert in_arc(100, 19, 199) is True       # dentro
    assert in_arc(0, 19, 199) is False        # fuera
    # arco que cruza 0: 199 -> 019 (horario, pasa por 360/0)
    assert in_arc(300, 199, 19) is True
    assert in_arc(0, 199, 19) is True
    assert in_arc(100, 199, 19) is False
    # omnidireccional (span 0)
    assert in_arc(123, 0, 360) is True


def _zona_cordoba():
    # Centro en ecuador para que el bearing magnético ~ verdadero (decl 0 en test)
    return MsaZone(icao="X", center=(0.0, 0.0), radius_nm=25.0, mag_decl_w=0.0,
                   sectors=[MsaSector(19, 199, 4100), MsaSector(199, 19, 8300)])


def test_msa_por_sector_este_oeste():
    z = _zona_cordoba()
    # punto al este (~90°) dentro del radio -> sector 019-199 = 4100
    assert z.msa_en(0.0, 0.1) == 4100
    # punto al oeste (~270°) -> sector 199-019 = 8300
    assert z.msa_en(0.0, -0.1) == 8300


def test_fuera_de_radio_devuelve_none():
    z = _zona_cordoba()
    assert z.msa_en(5.0, 5.0) is None         # lejos (>25 NM)


def test_omnidireccional():
    z = MsaZone(icao="SANE", center=(0.0, 0.0), radius_nm=25.0,
                sectors=[MsaSector(0, 360, 2500)])
    assert z.msa_en(0.0, 0.05) == 2500
    assert z.msa_en(0.05, 0.0) == 2500


def test_declinacion_rota_el_limite():
    # Con declinación oeste, el rumbo magnético = verdadero + decl_w.
    z = MsaZone(icao="X", center=(0.0, 0.0), radius_nm=25.0, mag_decl_w=10.0,
                sectors=[MsaSector(19, 199, 4100), MsaSector(199, 19, 8300)])
    # un punto a rumbo verdadero ~12° -> magnético ~22° -> cae en 019-199 (este)
    # 12° desde el centro: dlat>0, dlon pequeño este
    lat = math.cos(math.radians(12)) * 0.1
    lon = math.sin(math.radians(12)) * 0.1
    assert z.msa_en(lat, lon) == 4100
