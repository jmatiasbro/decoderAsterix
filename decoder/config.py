import re
import os
import json
from typing import Tuple, Optional, Dict

# Configuración global para la decodificación y geolocalización
DECODER_CONFIG = {'skip_unknown_categories': True}
GEO_CONFIG = {'use_vincenty': False}

# Registro base de sensores conocidos
KNOWN_SENSORS = {
    (1, 1): {'name': 'Radar Central', 'latitude': 40.4167, 'longitude': -3.7038, 'elevation': 2000},
    (226, 2): {'name': 'Radar Test', 'latitude': 40.474635, 'longitude': -3.588860, 'elevation': 650}
}

def load_sensors_from_directory(directory: str = None):
    """Carga los parámetros de sensores ASTERIX registrados en el directorio local."""
    if directory is None:
        base_dir = os.path.dirname(os.path.abspath(__file__))
        directory = os.path.join(base_dir, "default-site-params")
        
    if not os.path.exists(directory):
        return
    for filename in os.listdir(directory):
        if filename.endswith(".json") and filename != "radar_list.json":
            try:
                with open(os.path.join(directory, filename), 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    
                    sac_raw = data.get('sac')
                    sic_raw = data.get('sic')
                    
                    # Fallback para extraer SAC/SIC del nombre de archivo si no existen explícitamente
                    if sac_raw is None or sic_raw is None:
                        match = re.search(r'(?:sac_)?(\d+)[_-](?:sic_)?(\d+)', filename.lower())
                        if match:
                            sac_raw, sic_raw = match.groups()
                            
                    loc = data.get('location', {})
                    lat_raw = loc.get('latitude')
                    lon_raw = loc.get('longitude')
                    elev_raw = loc.get('altitude', 0)
                    
                    if sac_raw is not None and sic_raw is not None and lat_raw is not None and lon_raw is not None:
                        sac, sic = int(sac_raw), int(sic_raw)
                        KNOWN_SENSORS[(sac, sic)] = {
                            'name': data.get('name', filename),
                            'latitude': float(lat_raw),
                            'longitude': float(lon_raw),
                            'elevation': float(elev_raw)
                        }
            except Exception:
                pass

# Cargar sensores al inicializar el módulo
load_sensors_from_directory()

def get_sensor_position(sac: int, sic: int) -> Optional[Tuple[float, float, float]]:
    """Obtiene la posición geográfica de un sensor registrado."""
    if sac is None or sic is None:
        return None
        
    sensor = KNOWN_SENSORS.get((sac, sic))
    if sensor:
        return sensor['latitude'], sensor['longitude'], sensor['elevation']
        
    # Comprobación de fallback para sensores ADS-B coubicados (ej. CAT 21 donde SIC < 200)
    if sic < 200:
        sensor = KNOWN_SENSORS.get((sac, sic + 100))
        if sensor:
            return sensor['latitude'], sensor['longitude'], sensor['elevation']
        
    return None

def add_sensor(sac: int, sic: int, name: str, latitude: float, longitude: float, elevation: float, description: str = ''):
    """Registra manualmente la posición de un nuevo sensor."""
    KNOWN_SENSORS[(sac, sic)] = {
        'name': name,
        'latitude': latitude,
        'longitude': longitude,
        'elevation': elevation,
        'description': description
    }

def dms_to_decimal(degrees: int, minutes: int, seconds: float, direction: str) -> float:
    """Convierte formato Grados-Minutos-Segundos a grados decimales."""
    decimal = degrees + minutes / 60.0 + seconds / 3600.0
    if direction.upper() in ['S', 'W']:
        decimal = -decimal
    return decimal

def parse_dms_string(dms_str: str) -> float:
    """Parsea una cadena de texto en formato DMS y retorna grados decimales."""
    clean_str = re.sub(r'[°\'"dms]', ' ', dms_str)
    parts = clean_str.split()
    if len(parts) >= 4:
        return dms_to_decimal(float(parts[0]), float(parts[1]), float(parts[2]), parts[3])
    return 0.0

def decimal_to_dms(decimal: float) -> dict:
    """Convierte grados decimales a un diccionario Grados-Minutos-Segundos."""
    is_positive = decimal >= 0
    abs_dec = abs(decimal)
    degrees = int(abs_dec)
    minutes_float = (abs_dec - degrees) * 60
    minutes = int(minutes_float)
    seconds = (minutes_float - minutes) * 60
    return {
        'degrees': degrees,
        'minutes': minutes,
        'seconds': seconds,
        'direction': 'N' if is_positive else 'S'
    }

def dms_to_string(decimal: float, is_latitude: bool = True) -> str:
    """Retorna una coordenada decimal formateada amigablemente como string DMS."""
    dms = decimal_to_dms(decimal)
    if is_latitude:
        dir_ = 'N' if decimal >= 0 else 'S'
    else:
        dir_ = 'E' if decimal >= 0 else 'W'
    return f"{dms['degrees']}° {dms['minutes']}' {dms['seconds']:.3f}\" {dir_}"

def input_coordinate_interactive(label: str) -> float:
    val = input(f"{label} (decimal): ")
    return float(val) if val else 0.0

import configparser

def load_projection_center(filepath="system.conf"):
    """Extrae el centro de proyección del mapa desde la configuración."""
    config = configparser.ConfigParser()
    
    # Valores por defecto (Centro de Argentina aprox)
    proj_lat = -38.0
    proj_lon = -66.0
    
    if os.path.exists(filepath):
        config.read(filepath, encoding='utf-8')
        if config.has_section('proyeccion'):
            proj_lat = config.getfloat('proyeccion', 'CentroLat', fallback=proj_lat)
            proj_lon = config.getfloat('proyeccion', 'CentroLon', fallback=proj_lon)
            
    return proj_lat, proj_lon