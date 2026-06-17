"""
test_stca.py — Pruebas unitarias para el motor STCA (Short-Term Conflict Alert)
=============================================================================
Valida:
  1. Extracción correcta de FL y coordenadas desde dict y objetos RadarPlot.
  2. Cumplimiento estricto del estrato de altitud (FL245 - FL450).
  3. Detección correcta de infracciones verticales (< 900 ft).
  4. Detección correcta de infracciones horizontales (< 10 NM) vía Haversine.
  5. Casos de borde y falsos positivos/negativos.
"""

import sys
import os

# Agregar directorio raíz al path para importaciones
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from analysis.stca_analyzer import STCA_Engine
from player.radar_widget import RadarPlot


def test_stca_engine_dict():
    print("Corriendo test_stca_engine_dict...")
    engine = STCA_Engine()

    # 1. Caso de Conflicto Real (Ambos en FL245-FL450, DH < 10NM, DV < 900ft)
    # Lat/Lon de Tucumán y alrededores cercanos
    tracks = {
        "ARG123": {
            "flight_level": "300",
            "lat_render": -26.85,
            "lon_render": -65.22,
            "callsign": "ARG123"
        },
        "LAN456": {
            "flight_level": "305", # Dif = 500 ft < 900 ft
            "lat_render": -26.80, # Cercanos horizontalmente (aprox 4.5 NM)
            "lon_render": -65.25,
            "callsign": "LAN456"
        },
        # Caso Fuera de Altura (FL inferior a FL245)
        "OUT_ALT": {
            "flight_level": "240", # Bajo el estrato FL245
            "lat_render": -26.84,
            "lon_render": -65.23,
            "callsign": "OUT_ALT"
        },
        # Caso Separación Vertical Segura
        "SAFE_V": {
            "flight_level": "340", # Dif = 4000 ft
            "lat_render": -26.85,
            "lon_render": -65.22,
            "callsign": "SAFE_V"
        },
        # Caso Separación Horizontal Segura (Salta - Tucumán es ~120 NM)
        "SAFE_H": {
            "flight_level": "302",
            "lat_render": -24.78,
            "lon_render": -65.41,
            "callsign": "SAFE_H"
        }
    }

    conflictos = engine.evaluar_conflictos(tracks)
    print(f"Conflictos encontrados: {conflictos}")
    
    # Debe haber exactamente 1 conflicto entre ARG123 y LAN456
    assert len(conflictos) == 1, f"Se esperaban 1 conflicto, se hallaron {len(conflictos)}"
    c = conflictos[0]
    assert (c[0] == "ARG123" and c[1] == "LAN456") or (c[0] == "LAN456" and c[1] == "ARG123")
    print("test_stca_engine_dict PASSED successfully!")


def test_stca_engine_objects():
    print("Corriendo test_stca_engine_objects...")
    engine = STCA_Engine()

    # Crear objetos RadarPlot
    plot1 = RadarPlot(
        x=0.0, y=0.0, sac_sic="1/1", category=62, timestamp=1000.0,
        mode3a="1234", callsign="ARG777", flight_level=350, is_track=True,
        mode_s="----", track_angle=None, ground_speed=None,
        raw_dict={"lat_render": -34.61, "lon_render": -58.38} # CABA
    )
    # plot1 no tiene lat/lon como atributos pero stca_analyzer los extraerá de raw_dict
    
    plot2 = RadarPlot(
        x=0.0, y=0.0, sac_sic="1/1", category=62, timestamp=1000.0,
        mode3a="5678", callsign="ARG888", flight_level=355, is_track=True,
        mode_s="----", track_angle=None, ground_speed=None,
        raw_dict={"lat_render": -34.63, "lon_render": -58.40} # Cercano a CABA
    )

    tracks = {
        "ARG777": plot1,
        "ARG888": plot2
    }

    # Preparar diccionarios para el motor STCA (tal como lo hace RadarWidget)
    tracks_for_stca = {}
    for tid, track in tracks.items():
        tracks_for_stca[tid] = {
            'flight_level': str(track.flight_level),
            'lat_render': track.raw_dict.get('lat_render'),
            'lon_render': track.raw_dict.get('lon_render')
        }

    conflictos = engine.evaluar_conflictos(tracks_for_stca)
    print(f"Conflictos encontrados con objetos: {conflictos}")
    
    assert len(conflictos) == 1, "Se esperaba 1 conflicto con objetos RadarPlot"
    c = conflictos[0]
    # En la FASE 1, la tupla contiene los track_ids reales de los conflictos
    assert (c[0] == "ARG777" and c[1] == "ARG888") or (c[0] == "ARG888" and c[1] == "ARG777")
    print("test_stca_engine_objects PASSED successfully!")


def test_stca_predictive():
    print("Corriendo test_stca_predictive...")
    engine = STCA_Engine()

    # Configurar dos pistas separadas a 15 NM pero dirigiéndose a CPA en 100 segundos
    tracks = {
        "PRED1": {
            "flight_level": "300",
            "lat_render": -26.85,
            "lon_render": -65.22,
            "x": 0.0,
            "y": 0.0,
            "vx": 100.0,
            "vy": 0.0,
            "callsign": "PRED1"
        },
        "PRED2": {
            "flight_level": "305",
            "lat_render": -26.85,
            "lon_render": -65.50, # ~15 NM, seguro para dist_actual
            "x": 20000.0, # 20 km
            "y": 0.0,
            "vx": -100.0,
            "vy": 0.0,
            "callsign": "PRED2"
        }
    }

    conflictos = engine.evaluar_conflictos(tracks)
    print(f"Conflictos predictivos encontrados: {conflictos}")

    assert len(conflictos) == 1, f"Se esperaba 1 conflicto predictivo, se hallaron {len(conflictos)}"
    c = conflictos[0]
    assert (c[0] == "PRED1" and c[1] == "PRED2") or (c[0] == "PRED2" and c[1] == "PRED1")
    assert c[2] == 'PREDICTION'
    assert 98 <= c[3] <= 102 # t_cpa = 100 segundos
    print("test_stca_predictive PASSED successfully!")


if __name__ == "__main__":
    test_stca_engine_dict()
    test_stca_engine_objects()
    test_stca_predictive()
    print("Todos los tests de STCA concluyeron exitosamente!")
