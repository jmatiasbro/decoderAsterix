"""
Configuración de Sensores ASTERIX

Archivo para almacenar las configuraciones de sensores conocidos
y facilitar su reutilización en diferentes análisis.

Incluye funciones para conversión de coordenadas en diferentes formatos y metadatos ASTERIX:
- Grados Decimales (DD): 40.474635, -3.588860
- Grados Minutos Segundos (DMS): 40° 28' 28.686", -3° 35' 19.896"
"""

import json
import os
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from collections import defaultdict

# ============================================================================
# Mapeo de Categorías y Descripciones para los Desplegables (GUI)
# ============================================================================

CATEGORY_FIELD_DESCRIPTIONS = {
    1: { # CAT 01
        "name": "Monoradar Estándar",
        "fields": {
            "I001/010": "Data Source Identifier (SAC/SIC).",
            "I001/020": "Plot/Track Descriptor.",
            "I001/040": "Posición medida en coordenadas polares (RHO/THETA).",
            "I001/070": "Mode-3/A Code (Squawk)."
        }
    },
    2: { # CAT 02
        "name": "Monoradar Service Messages (Configuración)",
        "fields": {
            "I002/010": "Data Source Identifier (SAC/SIC).",
            "I002/020": "Configuración de la estación y estado de la antena.",
            "I002/150": "Antenna Rotation Speed (Velocidad de rotación de la antena)."
        }
    },
    21: { # CAT 21 v2.4 (ADS-B Target Reports)
        "name": "ADS-B Messages",
        "fields": {
            "I021/010": "Data Source Identifier (SAC/SIC).",
            "I021/040": "Target Report Descriptor.",
            "I021/161": "Track Number.",
            "I021/015": "Service Identification.",
            "I021/071": "Time of Message Reception for High Precision.",
            "I021/080": "Aircraft Address: Dirección única de 24 bits de la aeronave (Mode S).",
            "I021/130": "Position (WGS-84): Latitud y Longitud en WGS-84.",
            "I021/131": "High Resolution Position (WGS-84).",
            "I021/145": "Flight Level: Nivel de vuelo reportado por la aeronave.",
            "I021/150": "Air Speed.",
            "I021/151": "True Air Speed.",
            "I021/152": "Magnetic Heading.",
            "I021/155": "Barometric Vertical Rate.",
            "I021/157": "Geometric Vertical Rate.",
            "I021/160": "Ground Vector (Ground Speed, Track Angle).",
            "I021/165": "Rate of Turn.",
            "I021/070": "Mode 3/A Code (Squawk).",
            "I021/170": "Target Identification: Matrícula o Identificación de vuelo (Callsign).",
            "I021/210": "MOPS Version.",
            "I021/230": "Met Information.",
            "I021/260": "Selected Altitude.",
            "I021/400": "Receiver ID."
        }
    },
    34: { # CAT 34
        "name": "Service Messages (Posición Radar)",
        "fields": {
            "I034/010": "Data Source Identifier (SAC/SIC).",
            "I034/020": "Message Type: Norte, Sector, Estado, etc.",
            "I034/030": "Time of Day: Timestamp del mensaje de servicio.",
            "I034/041": "Antenna Characteristics: Azimut y velocidad.",
            "I034/050": "System Configuration and Status.",
            "I034/060": "System Processing Mode.",
            "I034/070": "Message Count.",
            "I034/120": "3D Radar Position: Posición geográfica WGS-84 de la antena."
        }
    },
    48: { # CAT 48
        "name": "Monoradar Mode S",
        "fields": {
            "I048/010": "Data Source Identifier (SAC/SIC).",
            "I048/020": "Target Report Descriptor.",
            "I048/040": "Measured Position Polar (Azimuth, Range).",
            "I048/070": "Mode-3/A Code (Squawk).",
            "I048/080": "Mode-C Code.",
            "I048/090": "Nivel de vuelo del blanco (Flight Level).",
            "I048/140": "Time of Day: Tiempo del reporte.",
            "I048/161": "Track Number: Número de pista asignado.",
            "I048/220": "Aircraft Address: Dirección Mode S (24 bits).",
            "I048/240": "Aircraft Identification: Callsign/Matrícula."
        }
    },
    62: { # CAT 62
        "name": "System Track Data",
        "fields": {
            "I062/010": "Data Source Identifier (SAC/SIC).",
            "I062/015": "Service Identification.",
            "I062/070": "Time of Track Information (Time of Day).",
            "I062/100": "Calculated Track Position (WGS-84).",
            "I062/185": "Calculated Track Velocity (Cartesian).",
            "I062/210": "Calculated Acceleration (Cartesian).",
            "I062/040": "Track Number: Identificador único de la traza del sistema.",
            "I062/380": "Aircraft Derived Data (Mode S/ADS-B data)."
        }
    }
}


# ============================================================================
# CARGA DE PARÁMETROS DE RADAR DESDE ARCHIVOS
# ============================================================================

# Directorio de parámetros de sitio por defecto
DEFAULT_SITE_PARAMS_DIR = Path(__file__).parent / "default-site-params"

# Cache de radares cargados
_LOADED_RADARS = {}
_RADAR_LIST = None

def parse_site_params_file(file_path: Path) -> Dict:
    """
    Parsea un archivo de parámetros de sitio.
    
    Args:
        file_path: Ruta al archivo de parámetros
    
    Returns:
        Dict con los parámetros parseados
    """
    params = {}
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                
                # Parsear asignaciones como VARIABLE=valor
                if '=' in line:
                    key, value = line.split('=', 1)
                    key = key.strip()
                    value = value.strip()
                    
                    # Intentar convertir a tipos apropiados
                    if value.startswith('"') and value.endswith('"'):
                        params[key] = value[1:-1]
                    else:
                        try:
                            if '.' in value:
                                params[key] = float(value)
                            else:
                                params[key] = int(value)
                        except ValueError:
                            params[key] = value
    
    except Exception as e:
        print(f"⚠️  Error al parsear {file_path}: {e}")
        return {}
    
    return params

def load_radar_list() -> Dict:
    """
    Carga la lista de radares desde archivos en default-site-params.
    
    Returns:
        Dict con información de la lista de radares
    """
    global _RADAR_LIST
    
    if _RADAR_LIST is not None:
        return _RADAR_LIST
    
    radars = []
    
    if DEFAULT_SITE_PARAMS_DIR.exists():
        for file_path in sorted(DEFAULT_SITE_PARAMS_DIR.iterdir()):
            if file_path.is_file() and not file_path.name.startswith('.'):
                # Intentar cargar como JSON primero (formato nuevo), o fallback a texto (formato antiguo)
                params = {}
                if file_path.suffix.lower() == '.json':
                    try:
                        with open(file_path, 'r', encoding='utf-8') as f:
                            params = json.load(f)
                    except:
                        pass
                
                if not params:
                    params = parse_site_params_file(file_path)
                
                if params:
                    # Normalizar extracción de datos (maneja anidamiento de JSON y planos)
                    loc = params.get('location', {}) if isinstance(params.get('location'), dict) else {}
                    
                    # Crear entrada de radar
                    radar = {
                        'radar_id': params.get('RADAR_ID') or params.get('radar_id') or file_path.stem.upper(),
                        'name': params.get('SITE_NAME') or params.get('name') or file_path.stem,
                        'file': file_path.name,
                        'sac': params.get('RADAR_SAC') or params.get('sac'),
                        'sic': params.get('RADAR_SIC') or params.get('sic'),
                        'latitude': params.get('RADAR_LAT') or loc.get('latitude'),
                        'longitude': params.get('RADAR_LON') or loc.get('longitude'),
                        'type': params.get('type', 'RADAR'),
                        'category': params.get('category', 'CAT048')
                    }
                    radars.append(radar)
    
    _RADAR_LIST = {"radars": radars}
    return _RADAR_LIST

def load_radar_parameters(radar_id: str) -> Optional[Dict]:
    """
    Carga los parámetros de un radar específico.
    
    Args:
        radar_id: ID del radar a cargar
    
    Returns:
        Dict con parámetros del radar o None si no se encuentra
    """
    if radar_id in _LOADED_RADARS:
        return _LOADED_RADARS[radar_id]
    
    radar_list = load_radar_list()
    
    # Buscar el archivo correspondiente al radar_id
    radar_file = None
    for radar in radar_list.get("radars", []):
        if radar.get("radar_id") == radar_id:
            radar_file = radar.get("file")
            break
    
    if not radar_file:
        return None
    
    radar_file_path = DEFAULT_SITE_PARAMS_DIR / radar_file
    
    try:
        with open(radar_file_path, 'r', encoding='utf-8') as f:
            radar_data = json.load(f)
            _LOADED_RADARS[radar_id] = radar_data
            return radar_data
    except FileNotFoundError:
        print(f"⚠️  Archivo de radar no encontrado: {radar_file_path}")
        return None
    except json.JSONDecodeError:
        # Fallback si el archivo no es JSON (formato texto KEY=valor)
        radar_data = parse_site_params_file(radar_file_path)
        if radar_data:
            radar_data['radar_id'] = radar_id
            _LOADED_RADARS[radar_id] = radar_data
            return radar_data
        else:
            print(f"⚠️  Error al parsear {radar_file}: Formato no reconocido")
            return None

def get_all_available_radars() -> List[Dict]:
    """
    Obtiene la lista de todos los radares disponibles.
    
    Returns:
        Lista de diccionarios con información básica de cada radar
    """
    radar_list = load_radar_list()
    return radar_list.get("radars", [])

def get_radar_info(radar_id: str) -> Optional[Dict]:
    """
    Obtiene información completa de un radar por su ID.
    
    Args:
        radar_id: ID del radar
    
    Returns:
        Dict con toda la información del radar o None
    """
    return load_radar_parameters(radar_id)

def get_sensors_from_radar_data(radar_data: Dict) -> List[Tuple[int, int]]:
    """
    Extrae identificadores de sensores (SAC, SIC) de los datos de radar.
    
    Args:
        radar_data: Datos del radar
    
    Returns:
        Lista de tuplas (SAC, SIC) disponibles en el radar
    """
    # Por ahora, asumimos que cada radar tiene un sensor principal
    # En el futuro esto podría expandirse para múltiples sensores por radar
    sensors = []
    
    # Intentar obtener SAC/SIC explícitamente (ej. de archivos texto plano)
    sac = radar_data.get('RADAR_SAC') or radar_data.get('sac')
    sic = radar_data.get('RADAR_SIC') or radar_data.get('sic')
    
    if sac is not None and sic is not None:
        try:
            sensors.append((int(sac), int(sic)))
            return sensors
        except ValueError:
            pass

    # Intentar extraer SAC/SIC del radar_id o de campos específicos
    radar_id = radar_data.get("radar_id", "")
    
    # Si el radar_id contiene información de SAC/SIC, extraerla
    # Formato esperado: "RADAR{SAC}{SIC}" o similar
    if radar_id.startswith("RADAR") and len(radar_id) >= 9:  # RADAR + 3 dígitos SAC + 3 dígitos SIC
        try:
            sac_str = radar_id[5:8]  # caracteres 6-8 (índices 5-7)
            sic_str = radar_id[8:11]  # caracteres 9-11 (índices 8-10)
            sac = int(sac_str)
            sic = int(sic_str)
            sensors.append((sac, sic))
        except (ValueError, IndexError):
            pass
    
    # Si no se pudo extraer del ID, usar valores por defecto basados en el tipo
    if not sensors:
        category = radar_data.get("category", "")
        if category == "CAT001":
            sensors.append((1, 1))  # PSR típico
        elif category == "CAT048":
            sensors.append((1, 2))  # SSR típico
        elif category == "CAT021":
            sensors.append((2, 1))  # MLAT típico
        else:
            sensors.append((0, 0))  # Desconocido
    
    return sensors

# ============================================================================
# LÓGICA DE IDENTIFICACIÓN Y ASOCIACIÓN DE SENSORES (Mendoza/Salta)
# ============================================================================

def identify_sensor_type_and_association(sac: int, sic: int) -> Dict[str, Any]:
    """
    Identifica el tipo de sensor y su posible asociación según reglas específicas.
    
    Args:
        sac: System Area Code
        sic: System Identification Code
        
    Returns:
        Dict con 'type', 'name', 'associated_sic' (si aplica), 'is_radar', 'is_adsb'
    """
    sensor_info = {
        'type': 'Generic',
        'name': f"Sensor Genérico {sac}/{sic}",
        'associated_sic': None,
        'is_radar': False,
        'is_adsb': False
    }

    if sac == 153 and sic == 6:
        sensor_info['type'] = 'Mendoza Radar'
        sensor_info['name'] = 'Sensor Mendoza (Radar)'
        sensor_info['is_radar'] = True
    elif sac == 226:
        if sic == 214:
            sensor_info['type'] = 'Salta Radar'
            sensor_info['name'] = 'Radar Salta (SIC 214)'
            sensor_info['is_radar'] = True
            sensor_info['associated_sic'] = 114 # Asociar con ADS-B (SIC 114)
        elif sic == 114:
            sensor_info['type'] = 'Salta ADS-B'
            sensor_info['name'] = 'ADS-B Salta (SIC 114)'
            sensor_info['is_adsb'] = True
            sensor_info['associated_sic'] = 214 # Asociar con Radar (SIC 214)
    
    # Complementar con KNOWN_SENSORS si existe
    known_key = (sac, sic)
    if known_key in KNOWN_SENSORS:
        sensor_info['name'] = KNOWN_SENSORS[known_key].get('name', sensor_info['name'])
        sensor_info['description'] = KNOWN_SENSORS[known_key].get('description', '')

    return sensor_info


# ============================================================================
# CONFIGURACIÓN DE SENSORES CONOCIDOS
# ============================================================================
# Formato: (SAC, SIC) -> {'name': nombre, 'latitude': latitud_decimal, 'longitude': longitud_decimal, 'elevation': elevación_pies}

KNOWN_SENSORS = {
    (1, 1): {
        'name': 'Madrid-Barajas Primary Radar',
        'latitude': 40.474635,
        'longitude': -3.588860,
        'elevation': 2000,
        'description': 'Primary radar at Madrid-Barajas Airport'
    },
    (1, 2): {
        'name': 'Madrid-Barajas Secondary Radar',
        'latitude': 40.474635,
        'longitude': -3.588860,
        'elevation': 2000,
        'description': 'Secondary radar at Madrid-Barajas Airport'
    },
    (2, 1): {
        'name': 'Córdoba Radar',
        'latitude': 37.846111,
        'longitude': -4.747500,
        'elevation': 1500,
        'description': 'Radar at Córdoba region'
    },
}

# Configuración de exportación
EXPORT_CONFIG = {
    'kml': {
        'enabled': True,
        'group_by_sensor': True,
        'icon_url': 'http://maps.google.com/mapfiles/kml/pushpin/blue-pushpin.png',
        'style_name': 'placemarkStyle'
    },
    'geojson': {
        'enabled': True,
        'pretty_print': True,
    },
    'csv': {
        'enabled': True,
        'delimiter': ',',
        'quoting': True,
    },
    'report': {
        'enabled': True,
        'include_statistics': True,
        'include_coverage_analysis': True,
    }
}

# Configuración de decodificación
DECODER_CONFIG = {
    'support_categories': [1, 2, 21, 34, 48],
    'skip_unknown_categories': True,
    'strict_fspec': False,  # Si True, lanza excepción en FSPEC inválido. CAT21 v2.4 usa hasta 7 bytes.
    'max_record_size': 65535,  # Máximo tamaño de registro en bytes
}

# Configuración geoespacial
GEO_CONFIG = {
    'use_vincenty': False,  # Usar fórmula Vincenty en lugar de Great Circle
    'default_elevation': 0,  # Elevación por defecto en pies
    'wgs84_a': 6378137.0,  # Radio ecuatorial WGS-84
    'wgs84_b': 6356752.314245,  # Radio polar WGS-84
}


def get_sensor_position(sac: int, sic: int):
    """
    Obtiene la posición de un sensor conocido.
    
    Primero busca en KNOWN_SENSORS, luego en los radares cargados.
    Si es un sensor ADS-B (SIC < 200), también busca la posición de su radar asociado (SIC + 100).
    
    Args:
        sac: System Area Code
        sic: System Identification Code
    
    Returns:
        Tupla (lat, lon, elev) o None si no es conocido
    """
    keys_to_try = [(sac, sic)]
    
    # Si es ADS-B (SIC < 200), intentar usar la posición de su radar físico (SIC + 100)
    if sic < 200:
        keys_to_try.append((sac, sic + 100))
        
    for key in keys_to_try:
        # Buscar en sensores conocidos
        if key in KNOWN_SENSORS:
            sensor = KNOWN_SENSORS[key]
            return (sensor['latitude'], sensor['longitude'], sensor['elevation'])
        
        # Buscar en radares cargados
        for radar_id, radar_data in _LOADED_RADARS.items():
            sensors = get_sensors_from_radar_data(radar_data)
            if key in sensors:
                location = radar_data.get('location', {})
                lat = location.get('latitude') or radar_data.get('RADAR_LAT') or 0
                lon = location.get('longitude') or radar_data.get('RADAR_LON') or 0
                alt = location.get('altitude') or radar_data.get('RADAR_ELEV') or radar_data.get('RADAR_ALT') or 0
                return (
                    float(lat),
                    float(lon),
                    float(alt)
                )
    
    return None


def add_sensor(sac: int, sic: int, name: str, latitude: float, 
               longitude: float, elevation: float = 0, description: str = ""):
    """Añade un nuevo sensor a la configuración."""
    KNOWN_SENSORS[(sac, sic)] = {
        'name': name,
        'latitude': latitude,
        'longitude': longitude,
        'elevation': elevation,
        'description': description
    }


def get_all_sensors():
    """Retorna todos los sensores conocidos."""
    return KNOWN_SENSORS


def display_sensors_in_data(decoded_data: List[Dict]) -> None:
    """
    Muestra qué sensores están presentes en los datos analizados.
    
    Args:
        decoded_data: Lista de registros decodificados
    """
    if not decoded_data:
        print("⚠️  No hay datos para analizar")
        return
    
    # Extraer SAC/SIC únicos de los datos
    sensors_found = set()
    category_count = {}
    
    for record in decoded_data:
        sac = record.get('sac')
        sic = record.get('sic')
        category = record.get('category')
        
        if sac is not None and sic is not None:
            sensors_found.add((sac, sic))
        
        if category is not None:
            category_count[category] = category_count.get(category, 0) + 1
    
    print("\n" + "=" * 80)
    print("SENSORES PRESENTES EN LOS DATOS ANALIZADOS")
    print("=" * 80)
    
    if not sensors_found:
        print("⚠️  No se encontraron identificadores de sensor (SAC/SIC) en los datos")
        print("   Esto puede indicar datos incompletos o formato no estándar")
    else:
        print(f"📡 Sensores detectados: {len(sensors_found)}")
        print()
        
        for sac, sic in sorted(sensors_found):
            sensor_info = get_sensor_position(sac, sic)
            sensor_name = f"Sensor {sac:03d}/{sic:03d}"
            
            # Buscar nombre en sensores conocidos
            key = (sac, sic)
            if key in KNOWN_SENSORS:
                sensor_name = KNOWN_SENSORS[key]['name']
            else:
                # Buscar en radares cargados
                for radar_id, radar_data in _LOADED_RADARS.items():
                    sensors = get_sensors_from_radar_data(radar_data)
                    if key in sensors:
                        sensor_name = radar_data.get('name', sensor_name)
                        break
            
            print(f"  🔹 {sensor_name} (SAC: {sac:03d}, SIC: {sic:03d})")
            
            if sensor_info:
                lat, lon, elev = sensor_info
                print(f"      📍 Posición: {dms_to_string(lat)}, {dms_to_string(lon)}")
                print(f"      🏔️  Elevación: {elev:.0f} pies")
            else:
                print("      📍 Posición: Desconocida")
    
    print()
    print(f"📊 Categorías ASTERIX encontradas: {len(category_count)}")
    for cat, count in sorted(category_count.items()):
        cat_name = get_category_name(cat)
        print(f"  • CAT{cat:03d} ({cat_name}): {count} registros")
    
    print("=" * 80 + "\n")


def get_category_name(category: int) -> str:
    """
    Obtiene el nombre descriptivo de una categoría ASTERIX.
    
    Args:
        category: Número de categoría
    
    Returns:
        Nombre descriptivo de la categoría
    """
    category_names = {
        1: "Monoradar Service Messages",
        2: "Monoradar Service Messages",
        21: "ADS-B Messages",
        34: "Service Messages (Monoradar)",
        48: "Monoradar Target Reports (Mode S)",
        62: "System Track Data"
    }
    
    return category_names.get(category, "Unknown Category")


def load_all_radar_sensors():
    """
    Carga todos los sensores de radares disponibles y los añade a KNOWN_SENSORS.
    """
    radars = get_all_available_radars()
    
    for radar_info in radars:
        radar_id = radar_info.get('radar_id')
        if not radar_id:
            continue
            
        radar_data = load_radar_parameters(radar_id)
        if not radar_data:
            continue
        
        sensors = get_sensors_from_radar_data(radar_data)
        location = radar_data.get('location', {})
        
        for sac, sic in sensors:
            key = (sac, sic)
            if key not in KNOWN_SENSORS:
                lat = location.get('latitude') or radar_data.get('RADAR_LAT') or 0
                lon = location.get('longitude') or radar_data.get('RADAR_LON') or 0
                
                # Prioritize altitude in feet. If not found, use 'altitude' (likely meters) and convert.
                elev_ft = location.get('altitude_ft')
                if elev_ft is None:
                    # Assume 'altitude' is in meters as per README and convert to feet
                    elev_m = location.get('altitude') or radar_data.get('RADAR_ELEV') or radar_data.get('RADAR_ALT') or 0
                    elev_ft = float(elev_m) * 3.28084

                KNOWN_SENSORS[key] = {
                    'name': radar_data.get('SITE_NAME') or radar_data.get('name', f'Radar {radar_id}'),
                    'latitude': float(lat),
                    'longitude': float(lon),
                    'elevation': float(elev_ft),
                    'description': f"{radar_data.get('type', 'Unknown')} - {radar_data.get('category', '')}"
                }

# Cargar automáticamente todos los sensores de radar al importar el módulo
load_all_radar_sensors()

# ============================================================================
# FUNCIONES DE CONVERSIÓN DE COORDENADAS
# ============================================================================

def dms_to_decimal(degrees: int, minutes: int, seconds: float, 
                   direction: str = 'N') -> float:
    """
    Convierte coordenadas DMS (Grados, Minutos, Segundos) a grados decimales.
    
    Args:
        degrees: Grados (0-180)
        minutes: Minutos (0-59)
        seconds: Segundos con decimales (0-59.999)
        direction: Dirección ('N'/'S' para latitud, 'E'/'W' para longitud)
    
    Returns:
        Coordenada en grados decimales (negativa si S o W)
    
    Ejemplo:
        dms_to_decimal(40, 28, 28.686, 'N') → 40.474635
    """
    decimal = degrees + minutes / 60 + seconds / 3600
    
    if direction.upper() in ['S', 'W']:
        decimal = -decimal
    
    return decimal


def decimal_to_dms(coordinate: float) -> dict:
    """
    Convierte coordenadas en grados decimales a DMS.
    
    Args:
        coordinate: Coordenada en grados decimales
    
    Returns:
        Dict con keys: 'degrees', 'minutes', 'seconds', 'direction'
    
    Ejemplo:
        decimal_to_dms(40.474635) → {
            'degrees': 40, 'minutes': 28, 'seconds': 28.686, 'direction': 'N'
        }
    """
    direction = 'N' if coordinate >= 0 else 'S'
    abs_coord = abs(coordinate)
    
    degrees = int(abs_coord)
    minutes_decimal = (abs_coord - degrees) * 60
    minutes = int(minutes_decimal)
    seconds = (minutes_decimal - minutes) * 60
    
    return {
        'degrees': degrees,
        'minutes': minutes,
        'seconds': round(seconds, 3),
        'direction': direction
    }


def dms_to_string(coordinate: float) -> str:
    """
    Convierte coordenada decimal a string en formato DMS legible.
    
    Args:
        coordinate: Coordenada en grados decimales
    
    Returns:
        String con formato: "40° 28' 28.686\" N"
    
    Ejemplo:
        dms_to_string(40.474635) → "40° 28' 28.686\" N"
    """
    dms = decimal_to_dms(coordinate)
    
    if coordinate >= 0:
        return f"{dms['degrees']}° {dms['minutes']}' {dms['seconds']}\" {dms['direction']}"
    else:
        return f"{dms['degrees']}° {dms['minutes']}' {dms['seconds']}\" {dms['direction']}"


def parse_dms_string(dms_string: str) -> float:
    """
    Parsea string en formato DMS y retorna grados decimales.
    
    Formatos soportados:
        "40 28 28.686 N"
        "40:28:28.686N"
        "40° 28' 28.686\" N"
        "40d 28m 28.686s N"
    
    Args:
        dms_string: String con coordenadas en DMS
    
    Returns:
        Coordenada en grados decimales
    
    Raises:
        ValueError: Si el formato no es válido
    """
    import re
    
    # Limpiar caracteres especiales
    dms_string = dms_string.upper().strip()
    
    # Reemplazar caracteres especiales con espacios
    dms_string = re.sub(r'[°d:′]', ' ', dms_string)
    dms_string = re.sub(r'[\'m]', ' ', dms_string)
    dms_string = re.sub(r'[\"s]', ' ', dms_string)
    
    # Extraer componentes
    parts = dms_string.split()
    
    if len(parts) < 3 or len(parts) > 4:
        raise ValueError(f"Formato DMS inválido: {dms_string}")
    
    try:
        degrees = int(parts[0])
        minutes = int(parts[1])
        seconds = float(parts[2])
        direction = parts[3] if len(parts) == 4 else 'N'
    except ValueError as e:
        raise ValueError(f"No se pudo parsear DMS: {dms_string}") from e
    
    if direction not in ['N', 'S', 'E', 'W']:
        raise ValueError(f"Dirección inválida: {direction}")
    
    return dms_to_decimal(degrees, minutes, seconds, direction)


def input_coordinate_interactive(coord_type: str = "Latitud") -> float:
    """
    Solicita coordenada interactivamente en formato grados decimales o DMS.
    
    Args:
        coord_type: Tipo de coordenada ("Latitud" o "Longitud")
    
    Returns:
        Coordenada en grados decimales
    
    Ejemplo de uso interactivo:
        >>> lat = input_coordinate_interactive("Latitud")
        Ingrese Latitud (formato: GD o DMS)
        Ejemplos: 40.474635 o "40 28 28.686 N"
        >>> 40.474635
    """
    print(f"\nIngrese {coord_type}:")
    print("Formatos aceptados:")
    print("  - Grados Decimales: 40.474635")
    print("  - GMS: 40 28 28.686 N")
    print("  - GMS alternativo: 40:28:28.686N")
    
    while True:
        try:
            user_input = input(f"{coord_type}: ").strip()
            is_lat = "Latitud" in coord_type
            
            # Intentar parsear como decimal primero
            if not any(c in user_input.upper() for c in ['N', 'S', 'E', 'W', "'", '°', 'd', 'm']):
                coord = float(user_input)
                print(f"✓ {coord_type}: {coord}° = {dms_to_string(coord, is_lat)}")
                return coord
            else:
                # Parsear como DMS
                coord = parse_dms_string(user_input)
                print(f"✓ {coord_type}: {dms_to_string(coord, is_lat)} = {coord}°")
                return coord
        
        except ValueError as e:
            print(f"✗ Error: {e}")
            print("Intente nuevamente.\n")


def input_sensor_interactive() -> dict:
    """
    Interfaz interactiva para añadir un nuevo sensor.
    
    Returns:
        Dict con parámetros del sensor ready para add_sensor()
    
    Ejemplo:
        >>> sensor = input_sensor_interactive()
        SAC: 3
        SIC: 1
        Nombre: Mi Radar
        ...
        {'sac': 3, 'sic': 1, 'name': 'Mi Radar', ...}
    """
    print("\n" + "=" * 70)
    print("CONFIGURAR NUEVO SENSOR")
    print("=" * 70)
    
    # SAC y SIC
    while True:
        try:
            sac = int(input("SAC (0-255): ").strip())
            sic = int(input("SIC (0-255): ").strip())
            
            if not (0 <= sac <= 255 and 0 <= sic <= 255):
                print("✗ SAC y SIC deben estar entre 0-255")
                continue
            break
        except ValueError:
            print("✗ Ingrese números válidos")
    
    # Nombre
    name = input("Nombre del sensor (ej: Madrid-Barajas): ").strip()
    if not name:
        name = f"Sensor {sac}/{sic}"
    
    # Coordenadas
    latitude = input_coordinate_interactive("Latitud")
    longitude = input_coordinate_interactive("Longitud")
    
    # Elevación
    while True:
        try:
            elev_input = input("Elevación (pies, opcional, enter para dejar en blanco): ").strip()
            elevation = float(elev_input) if elev_input else 0.0
            break
        except ValueError:
            print("✗ Ingrese un número válido")
    
    # Descripción
    description = input("Descripción (opcional): ").strip()
    
    return {
        'sac': sac,
        'sic': sic,
        'name': name,
        'latitude': latitude,
        'longitude': longitude,
        'elevation': elevation,
        'description': description
    }


def add_sensor_interactive():
    """
    Interfaz interactiva para añadir sensor y guardarlo.
    """
    sensor_data = input_sensor_interactive()
    
    add_sensor(
        sac=sensor_data['sac'],
        sic=sensor_data['sic'],
        name=sensor_data['name'],
        latitude=sensor_data['latitude'],
        longitude=sensor_data['longitude'],
        elevation=sensor_data['elevation'],
        description=sensor_data['description']
    )
    
    print("\n" + "=" * 70)
    print(f"✓ Sensor {sensor_data['sac']:03d}/{sensor_data['sic']:03d} configurado correctamente")
    print(f"  Nombre: {sensor_data['name']}")
    print(f"  Posición: {dms_to_string(sensor_data['latitude'], True)}")
    print(f"             {dms_to_string(sensor_data['longitude'], False)}")
    print(f"  Elevación: {sensor_data['elevation']:.0f} pies")
    print("=" * 70 + "\n")


def save_sensor_to_file(sensor_data: Dict) -> bool:
    """
    Guarda la configuración de un sensor en un archivo JSON
    dentro del directorio default-site-params.

    Args:
        sensor_data: Diccionario con los datos del sensor.
                     Debe contener 'sac', 'sic', 'name', 'latitude',
                     'longitude', 'elevation' (en pies), y 'description'.

    Returns:
        True si se guardó correctamente, False en caso contrario.
    """
    try:
        # Asegurarse que el directorio existe
        DEFAULT_SITE_PARAMS_DIR.mkdir(exist_ok=True)

        sac = sensor_data['sac']
        sic = sensor_data['sic']

        # Crear el nombre del archivo
        file_name = f"user_sensor_{sac}_{sic}.json"
        file_path = DEFAULT_SITE_PARAMS_DIR / file_name

        if file_path.exists():
            print(f"[!] El archivo {file_path} ya existe. Se sobrescribirá.")

        # La elevación se recibe y guarda en pies para consistencia interna
        elevation_ft = sensor_data.get('elevation', 0.0)

        # Construir el objeto JSON
        json_content = {
            "radar_id": f"USER_{sac}_{sic}",
            "name": sensor_data.get('name', f"User Sensor {sac}/{sic}"),
            "type": "USER_ADDED",
            "category": "UNKNOWN",
            "sac": sac,
            "sic": sic,
            "location": {
                "latitude": sensor_data['latitude'],
                "longitude": sensor_data['longitude'],
                "altitude_ft": elevation_ft,  # Guardado en pies
                "coordinates_dms_lat": dms_to_string(sensor_data['latitude'], True),
                "coordinates_dms_lon": dms_to_string(sensor_data['longitude'], False)
            },
            "description": sensor_data.get('description', "Sensor añadido por el usuario.")
        }

        # Escribir el archivo JSON
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(json_content, f, indent=4, ensure_ascii=False)

        print(f"\n[✓] Sensor guardado correctamente en: {file_path}")
        return True

    except Exception as e:
        print(f"\n[✗] Error al guardar el archivo del sensor: {e}")
        return False
