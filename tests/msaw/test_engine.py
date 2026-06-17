from types import SimpleNamespace as S

from player.msaw.model import MsaZone, MsaSector, MsawParams
from player.msaw.engine import evaluar_msaw


def _zona():
    # Centro en el ecuador (decl 0): este=4100, oeste=8300, radio 25 NM.
    return MsaZone(icao="SACO", center=(0.0, 0.0), radius_nm=25.0, mag_decl_w=0.0,
                   sectors=[MsaSector(19, 199, 4100), MsaSector(199, 19, 8300)])


def _trk(**kw):
    base = dict(id="AR123", lat=0.0, lon=0.1, flight_level=30, vx=None, vy=None,
                vertical_rate=None)
    base.update(kw)
    return S(**base)


def test_violacion_por_debajo_de_msa():
    # FL030 = 3000 ft < 4100 (sector este) -> VIOLATION
    al = evaluar_msaw([_trk(flight_level=30)], [_zona()])
    assert len(al) == 1 and al[0].tipo == "VIOLATION"
    assert al[0].msa_ft == 4100 and al[0].alt_ft == 3000


def test_sin_alerta_por_encima():
    al = evaluar_msaw([_trk(flight_level=60)], [_zona()])   # 6000 > 4100
    assert al == []


def test_prediccion_de_descenso():
    # FL050=5000, desciende 2000 ft/min -> a 120s ~1000 ft < 4100 -> PREDICTED
    al = evaluar_msaw([_trk(flight_level=50, vertical_rate=-2000)], [_zona()])
    assert len(al) == 1 and al[0].tipo == "PREDICTED"
    assert 0 < al[0].eta_s <= 120


def test_descenso_que_no_cruza_no_alerta():
    al = evaluar_msaw([_trk(flight_level=60, vertical_rate=-100)], [_zona()])
    assert al == []


def test_fuera_de_tma_no_alerta():
    al = evaluar_msaw([_trk(lat=5.0, lon=5.0, flight_level=10)], [_zona()])
    assert al == []


def test_inhibicion_por_categoria():
    # Track sin categoría -> no exento -> alerta.
    assert len(evaluar_msaw([_trk(flight_level=30)], [_zona()], exentos=["SAR"])) == 1
    # Track con categoría exenta -> inhibido.
    t = _trk(flight_level=30)
    t.flight_category = "SAR"
    assert evaluar_msaw([t], [_zona()], exentos=["SAR"]) == []


def test_sector_oeste_usa_su_msa():
    # punto al oeste (lon negativo) -> sector 199-019 = 8300; FL070=7000 < 8300
    al = evaluar_msaw([_trk(lon=-0.1, flight_level=70)], [_zona()])
    assert len(al) == 1 and al[0].msa_ft == 8300 and al[0].tipo == "VIOLATION"


def test_params_lookahead_personalizado():
    p = MsawParams(time_to_prediction=30, rocd=1500, cfl_thold=5)
    # 5000 ft, -2000 ft/min: a 30s baja 1000 -> 4000 < 4100 -> PREDICTED dentro de 30s
    al = evaluar_msaw([_trk(flight_level=50, vertical_rate=-2000)], [_zona()], params=p)
    assert len(al) == 1 and al[0].eta_s <= 30


from player.msaw.model import MsaPolygon, ApmCorridor, SuppressionSet


def test_cascada_poligono_tiene_prioridad():
    # Polígono alrededor del origen con MSA 9000; el círculo daría 4100 al este.
    poly = MsaPolygon("SACO", 9000,
                      [(-0.05, -0.05), (-0.05, 0.05), (0.05, 0.05), (0.05, -0.05)])
    al = evaluar_msaw([_trk(lat=0.0, lon=0.01, flight_level=80)], [poly, _zona()])
    assert len(al) == 1 and al[0].msa_ft == 9000


def test_cascada_cae_a_circulo_fuera_del_poligono():
    poly = MsaPolygon("P", 9000,
                      [(0.40, 0.40), (0.40, 0.45), (0.45, 0.45), (0.45, 0.40)])
    al = evaluar_msaw([_trk(lat=0.0, lon=0.05, flight_level=30)], [poly, _zona()])
    assert len(al) == 1 and al[0].msa_ft == 4100


def test_supresion_inhibe_violacion():
    import math
    apm = ApmCorridor("T", "01", near=(0.0, 0.0), far=(0.2, 0.0),
                      half_wide_nm=1.0, min_dist=3.0, max_dist=12.0,
                      lower_slope=2.5, upper_slope=4.8, glide_slope=3.0,
                      thr_elev_ft=0)
    ss = SuppressionSet(apm=[apm], profiles=[], params={"tol_altitude_ft": 300})
    d = 6.0
    lat = d / 60.0
    alt = d * 6076.12 * math.tan(math.radians(3.0))
    fl = alt / 100.0
    poly = MsaPolygon("T", 9000,
                      [(-1.0, -1.0), (-1.0, 1.0), (1.0, 1.0), (1.0, -1.0)])
    sin_sup = evaluar_msaw([_trk(lat=lat, lon=0.0, flight_level=fl)], [poly])
    assert len(sin_sup) == 1                      # sin supresión: alerta
    con_sup = evaluar_msaw([_trk(lat=lat, lon=0.0, flight_level=fl)], [poly],
                           suppression=ss)
    assert con_sup == []                          # suprimida
