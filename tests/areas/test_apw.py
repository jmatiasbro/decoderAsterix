from datetime import datetime, time
import pytest

from player.areas.model import Area, Vigencia
from player.areas.apw import evaluar_apw, AlertaAPW

# Helper datetimes
AHORA = datetime(2026, 6, 15, 12, 0) # Lunes 12:00


def test_apw_penetration_dentro_y_fuera():
    # Área circular de 10 NM de radio
    area = Area(
        name="ZONA_P1",
        kind="P",
        shape="circle",
        lower_fl=0,
        upper_fl=100,
        center=(-31.0, -64.0),
        radius_nm=10.0,
        vigencia=Vigencia(permanente=True)
    )
    
    # Track 1: Dentro del círculo a FL 50
    # 5 NM al norte (-31.0 + 5/60) -> Dentro
    track_inside = {
        "id": "T1",
        "flight_level": 50,
        "lat": -31.0 + 5.0 / 60.0,
        "lon": -64.0,
        "is_alive": True
    }
    
    # Track 2: Fuera del círculo a FL 50
    # 15 NM al norte (-31.0 + 15/60) -> Fuera
    track_outside = {
        "id": "T2",
        "flight_level": 50,
        "lat": -31.0 + 15.0 / 60.0,
        "lon": -64.0,
        "is_alive": True
    }
    
    # Evaluar track 1 (dentro) -> Debe generar VIOLATION
    alertas1 = evaluar_apw([track_inside], [area], AHORA)
    assert len(alertas1) == 1
    assert alertas1[0].track_id == "T1"
    assert alertas1[0].area_name == "ZONA_P1"
    assert alertas1[0].tipo == "VIOLATION"
    assert alertas1[0].eta_s == 0.0

    # Evaluar track 2 (fuera, sin velocidad) -> Sin alertas
    alertas2 = evaluar_apw([track_outside], [area], AHORA)
    assert len(alertas2) == 0


def test_apw_prediccion_entra_y_no_entra():
    # Área circular de 10 NM de radio centrada en (-31.0, -64.0)
    area = Area(
        name="ZONA_P1",
        kind="P",
        shape="circle",
        lower_fl=0,
        upper_fl=100,
        center=(-31.0, -64.0),
        radius_nm=10.0,
        vigencia=Vigencia(permanente=True)
    )
    
    # 1 grado de latitud = 111120 metros.
    # 15 NM al norte es: -31.0 + 15/60 = -30.75
    # El borde norte del círculo está a 10 NM al norte: -31.0 + 10/60 = -30.8333
    # Ponemos la traza a 12 NM al norte (-31.0 + 12/60 = -30.8)
    # Su distancia al borde es 2 NM (~3704 metros).
    # Si viaja al Sur a 100 m/s:
    # Tardará 3704 / 100 ~ 37 segundos en entrar.
    track_heading_south = {
        "id": "T1",
        "flight_level": 50,
        "lat": -31.0 + 12.0 / 60.0,
        "lon": -64.0,
        "vx": 0.0,
        "vy": -100.0, # Hacia el Sur (latitud decreciente)
        "is_alive": True
    }
    
    # Si viaja al Norte (alejándose del círculo):
    track_heading_north = {
        "id": "T2",
        "flight_level": 50,
        "lat": -31.0 + 12.0 / 60.0,
        "lon": -64.0,
        "vx": 0.0,
        "vy": 100.0, # Hacia el Norte (alejándose)
        "is_alive": True
    }

    # Evaluar track 1 (hacia el Sur) -> Debe generar PREDICTED
    alertas1 = evaluar_apw([track_heading_south], [area], AHORA, lead_s=120)
    assert len(alertas1) == 1
    assert alertas1[0].track_id == "T1"
    assert alertas1[0].tipo == "PREDICTED"
    assert 30 <= alertas1[0].eta_s <= 45

    # Evaluar track 2 (hacia el Norte) -> Sin alertas
    alertas2 = evaluar_apw([track_heading_north], [area], AHORA, lead_s=120)
    assert len(alertas2) == 0


def test_apw_fuera_de_banda():
    area = Area(
        name="ZONA_P1",
        kind="P",
        shape="circle",
        lower_fl=100, # Desde FL 100
        upper_fl=200, # Hasta FL 200
        center=(-31.0, -64.0),
        radius_nm=10.0,
        vigencia=Vigencia(permanente=True)
    )
    
    # Track dentro del círculo pero a FL 50 (por debajo de la banda)
    track_below = {
        "id": "T1",
        "flight_level": 50,
        "lat": -31.0 + 5.0 / 60.0,
        "lon": -64.0,
        "is_alive": True
    }
    
    # Track dentro a FL 150 (en la banda)
    track_in_band = {
        "id": "T2",
        "flight_level": 150,
        "lat": -31.0 + 5.0 / 60.0,
        "lon": -64.0,
        "is_alive": True
    }

    # Evaluar por debajo de la banda -> Sin alertas
    assert len(evaluar_apw([track_below], [area], AHORA)) == 0

    # Evaluar en la banda -> VIOLATION
    alertas = evaluar_apw([track_in_band], [area], AHORA)
    assert len(alertas) == 1
    assert alertas[0].track_id == "T2"


def test_apw_vigencia_inactiva_y_deshabilitada():
    # Área temporal inactiva (sólo activa martes, hoy es lunes)
    area_inactiva_dia = Area(
        name="TEMP_DIA",
        kind="R",
        shape="circle",
        lower_fl=0,
        upper_fl=100,
        center=(-31.0, -64.0),
        radius_nm=10.0,
        vigencia=Vigencia(permanente=False, dias={1}) # Martes
    )
    
    # Área temporal deshabilitada manualmente
    area_deshabilitada = Area(
        name="TEMP_DESH",
        kind="R",
        shape="circle",
        lower_fl=0,
        upper_fl=100,
        center=(-31.0, -64.0),
        radius_nm=10.0,
        vigencia=Vigencia(permanente=False, habilitada=False, dias={0}) # Lunes pero deshabilitada
    )

    track = {
        "id": "T1",
        "flight_level": 50,
        "lat": -31.0 + 5.0 / 60.0,
        "lon": -64.0,
        "is_alive": True
    }

    # Evaluar con área inactiva por día -> Sin alertas
    assert len(evaluar_apw([track], [area_inactiva_dia], AHORA)) == 0

    # Evaluar con área deshabilitada manualmente -> Sin alertas
    assert len(evaluar_apw([track], [area_deshabilitada], AHORA)) == 0


def test_apw_prefiltro_bbox():
    # Área rectangular pequeña (polígono) en lat: [0, 1], lon: [0, 1]
    area = Area(
        name="RECT",
        kind="D",
        shape="poly",
        lower_fl=0,
        upper_fl=100,
        vertices=[(0, 0), (0, 1), (1, 1), (1, 0)],
        vigencia=Vigencia(permanente=True)
    )

    # Track muy lejos (lat: 10, lon: 10), moviéndose en dirección opuesta
    track_far = {
        "id": "T_FAR",
        "flight_level": 50,
        "lat": 10.0,
        "lon": 10.0,
        "vx": 10.0,
        "vy": 10.0,
        "is_alive": True
    }

    # Evaluamos y verificamos que no genera alerta
    assert len(evaluar_apw([track_far], [area], AHORA)) == 0
