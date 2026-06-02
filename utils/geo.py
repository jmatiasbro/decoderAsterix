"""
geo.py — Utilidades Geoespaciales Unificadas para ASTERIX Radar Decoder
=======================================================================
Módulo fusionado de geo_tools.py + geo_utils.py

Contiene:
  - StereographicLocal: Proyección estereográfica local centrada en un radar
  - GeoTools: Conversiones de coordenadas (polar→WGS84, Vincenty, Haversine)
  - cargar_sensores: Carga parámetros de radar desde JSON
  - Constantes: METERS_PER_NM, WGS84_GEOD

Dependencias: pyproj, json, glob, math
Sin dependencias de Qt.
"""

import os
import json
import glob
import math
import time
from typing import Dict, Tuple, Optional, Any, List
from collections import deque

try:
    from pyproj import Proj, Geod, Transformer
    HAS_PYPROJ = True
    WGS84_GEOD = Geod(ellps='WGS84')
except ImportError:
    HAS_PYPROJ = False
    WGS84_GEOD = None

try:
    from numba import njit
    HAS_NUMBA = True
except ImportError:
    HAS_NUMBA = False
    # Decorador mock para cuando numba no está presente
    def njit(*args, **kwargs):
        def decorator(func):
            return func
        return decorator


# ============================================================
# CONSTANTES
# ============================================================
METERS_PER_NM = 1852.0          # 1 milla náutica = 1852 m


# ============================================================
# CARGA DE SENSORES (Radar Sites)
# ============================================================

def cargar_sensores(directorio: str = "default-site-params") -> Dict[Tuple[int, int], Dict[str, Any]]:
    """
    Escanea directorio de archivos JSON y extrae parámetros de cada sensor.

    Returns
    -------
    dict : {(sac, sic): {'lat': float, 'lon': float, 'elev': float, 'name': str}}
    """
    registro: Dict[Tuple[int, int], Dict[str, Any]] = {}
    if not os.path.isdir(directorio):
        return registro

    for fp in sorted(glob.glob(os.path.join(directorio, "*.json"))):
        try:
            with open(fp, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except Exception:
            continue

        sac = data.get('sac')
        sic = data.get('sic')
        if sac is None or sic is None:
            continue

        loc = data.get('location', {})
        lat = loc.get('latitude')
        lon = loc.get('longitude')
        if lat is None or lon is None:
            continue

        registro[(int(sac), int(sic))] = {
            'lat': float(lat),
            'lon': float(lon),
            'elev': float(loc.get('elevation', 0)),
            'name': str(data.get('name', f"Radar {sac}/{sic}")),
            'category': str(data.get('category', '')),
            'type': str(data.get('type', ''))
        }

    return registro


def obtener_sensor_por_id(
    sac: int,
    sic: int,
    sensores: Dict[Tuple[int, int], Dict[str, Any]]
) -> Optional[Dict[str, Any]]:
    """Obtiene datos de un sensor específico por SAC/SIC."""
    return sensores.get((sac, sic))


def obtener_centros_control_por_sac_sic(sac: int, sic: int) -> List[str]:
    """Retorna los ACCs asociados según la base del SIC (sic % 100)."""
    base_sic = sic % 100
    if base_sic == 6:  # Bahía Blanca (206/106) o Mendoza (153/6)
        return ["Córdoba", "Mendoza"] if sac == 153 else ["Comodoro", "Ezeiza"]
    elif base_sic == 3:  # Paraná (203/103)
        return ["Córdoba", "Ezeiza", "Resistencia"]
    elif base_sic == 4:  # Bariloche (204/104/4/304)
        return ["Comodoro", "Ezeiza"]
    elif base_sic == 40:  # Comodoro Rivadavia (240/140)
        return ["Comodoro"]
    elif base_sic == 10:  # Córdoba (210/110)
        return ["Córdoba", "Ezeiza", "Mendoza"]
    elif base_sic == 30:  # Corrientes (230/130)
        return ["Córdoba", "Resistencia"]
    elif base_sic == 42:  # Esquel (242/142)
        return ["Comodoro", "Ezeiza"]
    elif base_sic == 12:  # La Rioja (212/112)
        return ["Córdoba", "Mendoza"]
    elif base_sic == 22:  # Malargüe (222/122)
        return ["Ezeiza", "Mendoza"]
    elif base_sic == 13:  # Morteros (213/113)
        return ["Córdoba", "Ezeiza", "Resistencia"]
    elif base_sic == 7:  # Neuquén (207/107)
        return ["Comodoro", "Córdoba", "Ezeiza", "Mendoza"]
    elif base_sic == 9:  # Pehuajó (209/109)
        return ["Ezeiza", "Mendoza"]
    elif base_sic == 31:  # Posadas (231/131)
        return ["Resistencia"]
    elif base_sic == 43:  # Puerto Madryn (243/143)
        return ["Comodoro"]
    elif base_sic == 5:  # Quilmes (205/105)
        return ["Córdoba", "Ezeiza"]
    elif base_sic == 41:  # Río Gallegos (241/141)
        return ["Comodoro"]
    elif base_sic == 32:  # Roque Sáenz Peña (232/132)
        return ["Córdoba", "Ezeiza", "Resistencia"]
    elif base_sic == 14:  # Salta (214/114)
        return ["Córdoba", "Resistencia"]
    elif base_sic == 21:  # San Luis (221/121)
        return ["Córdoba", "Ezeiza", "Mendoza"]
    elif base_sic == 8:  # Santa Rosa (208/108)
        return ["Córdoba", "Ezeiza", "Mendoza"]
    elif base_sic == 11:  # Tucumán (211/111)
        return ["Córdoba", "Resistencia"]
    elif base_sic == 45:  # Ushuaia (245/145)
        return ["Comodoro"]
    elif base_sic == 44:  # San Julián (244/144)
        return ["Comodoro"]
    return []


def obtener_centros_control(nombre_sensor: str, sac: int = None, sic: int = None) -> List[str]:
    """Retorna la lista de ACCs asociados usando SAC/SIC con fallback a coincidencia de nombre."""
    if sac is not None and sic is not None:
        centros = obtener_centros_control_por_sac_sic(sac, sic)
        if centros:
            return centros
            
    # Fallback a nombre
    nombre_lower = nombre_sensor.lower()
    centros = []
    if any(k in nombre_lower for k in ["bahia blanca", "baha blanca", "bahiablanca", "bariloche", "comodoro", "esquel", "neuquen", "neuqun", "madryn", "gallegos", "san juan", "sanjuan", "ushuaia", "julian", "julián"]):
        centros.append("Comodoro")
    if any(k in nombre_lower for k in ["cordoba", "crdoba", "corrientes", "mamboreta", "mamboret", "rioja", "morteros", "neuquen", "neuqun", "quilmes", "saenz", "senz", "pea", "pena", "salta", "san luis", "sanluis", "santa rosa", "santarosa", "tucuman", "tucumn", "parana", "mendoza"]):
        centros.append("Córdoba")
    if any(k in nombre_lower for k in ["bahia blanca", "baha blanca", "bahiablanca", "bariloche", "cordoba", "crdoba", "esquel", "ezeiza", "mamboreta", "mamboret", "malargue", "malarge", "morteros", "neuquen", "neuqun", "pehuajo", "pehuaj", "quilmes", "saenz", "senz", "pea", "pena", "san luis", "sanluis", "santa rosa", "santarosa", "parana"]):
        centros.append("Ezeiza")
    if any(k in nombre_lower for k in ["cordoba", "crdoba", "rioja", "malargue", "malarge", "mendoza", "neuquen", "neuqun", "pehuajo", "pehuaj", "san luis", "sanluis", "santa rosa", "santarosa"]):
        centros.append("Mendoza")
    if any(k in nombre_lower for k in ["corrientes", "mamboreta", "mamboret", "morteros", "posadas", "saenz", "senz", "pea", "pena", "salta", "tucuman", "tucumn", "parana"]):
        centros.append("Resistencia")
        
    return centros if centros else ["Otros"]



def sensor_mas_cercano(
    lat: float,
    lon: float,
    sensores: Dict[Tuple[int, int], Dict[str, Any]]
) -> Optional[Tuple[Tuple[int, int], Dict[str, Any]]]:
    """
    Encuentra el sensor más cercano a una coordenada dada.
    Útil para auto-seleccionar el radar de referencia.
    """
    if not sensores:
        return None

    mejor_dist = float('inf')
    mejor_key = None
    mejor_info = None

    for (sac, sic), info in sensores.items():
        dlat = info['lat'] - lat
        dlon = info['lon'] - lon
        dist_aprox = (dlat * 111320) ** 2 + (dlon * 111320 * abs(math.cos(math.radians(lat)))) ** 2
        if dist_aprox < mejor_dist:
            mejor_dist = dist_aprox
            mejor_key = (sac, sic)
            mejor_info = info

    return (mejor_key, mejor_info) if mejor_key else None


# ============================================================
# PROYECCIÓN ESTEREOGRÁFICA LOCAL
# ============================================================

class StereographicLocal:
    """
    Proyección Estereográfica Local centrada en un radar (estándar IGN).

    Proyección conforme: +proj=stere +lat_0=<radar_lat> +lon_0=<radar_lon>
    +k=1 +datum=WGS84 +units=m +no_defs

    Conversiones:
        latlon_to_xy(lat, lon) -> (x_m, y_m)
        xy_to_latlon(x_m, y_m) -> (lat, lon)
        rho_theta_to_wgs84(rho_nm, theta_deg) -> (lat, lon)
        rho_theta_to_xy(rho_nm, theta_deg) -> (x_m, y_m)
    """

    def __init__(self, center_lat: float = None, center_lon: float = None):
        self.center_lat = center_lat
        self.center_lon = center_lon
        self._proj = None

        if center_lat is not None and center_lon is not None:
            self._build_proj()

    def _build_proj(self):
        """Construye internamente el objeto Proj de pyproj."""
        if self.center_lat is None or self.center_lon is None:
            raise ValueError("Se requiere center_lat y center_lon para construir la proyección.")
        proj_string = (
            f"+proj=stere +lat_0={self.center_lat} +lon_0={self.center_lon} "
            f"+k=1 +datum=WGS84 +units=m +no_defs"
        )
        self._proj = Proj(proj_string)

    def set_center(self, lat: float, lon: float):
        """Cambia el centro de la proyección (útil al seleccionar otro radar)."""
        self.center_lat = lat
        self.center_lon = lon
        self._build_proj()

    # --------------------------------------------------------
    # Conversiones directas WGS84 ↔ Cartesianas
    # --------------------------------------------------------

    def latlon_to_xy(self, lat: float, lon: float) -> Tuple[float, float]:
        """Convierte WGS84 a cartesianas locales (X, Y en metros)."""
        if self._proj is None or lat is None or lon is None:
            return 0.0, 0.0
        x, y = self._proj(lon, lat)
        return float(x), float(y)

    def xy_to_latlon(self, x: float, y: float) -> Tuple[float, float]:
        """Convierte cartesianas locales de vuelta a WGS84."""
        if self._proj is None:
            return 0.0, 0.0
        lon, lat = self._proj(x, y, inverse=True)
        return float(lat), float(lon)

    # --------------------------------------------------------
    # Conversión Polar (RHO/THETA) → WGS84 vía Vincenty
    # --------------------------------------------------------

    def rho_theta_to_wgs84(
        self,
        rho_nm: float,
        theta_deg: float,
        sensor_lat: float = None,
        sensor_lon: float = None
    ) -> Tuple[Optional[float], Optional[float]]:
        """
        Convierte coordenadas polares de radar (RHO en NM, THETA en grados)
        a WGS84 (lat, lon) usando Vincenty (pyproj.Geod.fwd).
        """
        if sensor_lat is None:
            sensor_lat = self.center_lat
        if sensor_lon is None:
            sensor_lon = self.center_lon

        if sensor_lat is None or sensor_lon is None:
            return None, None

        dist_m = float(rho_nm) * METERS_PER_NM
        azimuth = float(theta_deg)

        try:
            lon_dest, lat_dest, _ = WGS84_GEOD.fwd(sensor_lon, sensor_lat, azimuth, dist_m)
            return float(lat_dest), float(lon_dest)
        except Exception as e:
            print(f"[geo] Error en cálculo de Vincenty fwd: {e}")
            return None, None

    def rho_theta_to_xy(
        self,
        rho_nm: float,
        theta_deg: float,
        sensor_lat: float = None,
        sensor_lon: float = None
    ) -> Tuple[Optional[float], Optional[float]]:
        """Convierte coordenadas polares directamente a cartesianas locales."""
        lat, lon = self.rho_theta_to_wgs84(rho_nm, theta_deg, sensor_lat, sensor_lon)
        if lat is None or lon is None:
            return None, None
        return self.latlon_to_xy(lat, lon)

    # --------------------------------------------------------
    # Utilidades
    # --------------------------------------------------------

    def distancia_vincenty(self, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """Distancia entre dos puntos WGS84 usando Vincenty (metros)."""
        _, _, dist_m = WGS84_GEOD.inv(lon1, lat1, lon2, lat2)
        return dist_m

    def azimuth_vincenty(self, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """Azimut inicial (forward) entre dos puntos WGS84 (grados)."""
        az_fwd, _, _ = WGS84_GEOD.inv(lon1, lat1, lon2, lat2)
        return float(az_fwd)

    @property
    def activo(self) -> bool:
        """Indica si la proyección está configurada y lista para usar."""
        return self._proj is not None


# ============================================================
# CONSTANTES WGS-84 A NIVEL DE MÓDULO PARA NUMBA JIT
# ============================================================
WGS84_A = 6378137.0
WGS84_B = 6356752.314245
WGS84_E2 = 0.00669437999014132

@njit(fastmath=True)
def _slant_to_ground_range_jit(slant_range_nm: float, flight_level: float, radar_height_ft: float) -> float:
    """Implementación matemática pura JIT de slant range a ground range."""
    target_height_ft = flight_level * 100
    height_diff = target_height_ft - radar_height_ft
    slant_range_ft = slant_range_nm * 6076.118
    
    abs_height_diff = abs(height_diff)
    if slant_range_ft >= abs_height_diff:
        ground_range_ft = math.sqrt(max(0.0, slant_range_ft**2 - abs_height_diff**2))
    else:
        ground_range_ft = 0.0
    
    return ground_range_ft / 6076.118

@njit(fastmath=True)
def _calculate_distance_and_azimuth_jit(lat1: float, lon1: float, lat2: float, lon2: float) -> Tuple[float, float]:
    """Cálculo geodésico Haversine JIT."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)

    a = (math.sin(dphi / 2)**2 + 
         math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2)**2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    distance = WGS84_A * c

    y = math.sin(dlambda) * math.cos(phi2)
    x = (math.cos(phi1) * math.sin(phi2) - 
         math.sin(phi1) * math.cos(phi2) * math.cos(dlambda))
    
    azimuth = (math.degrees(math.atan2(y, x)) + 360) % 360
    
    return distance, azimuth

@njit(fastmath=True)
def _vincenty_forward_jit(lat: float, lon: float, azimuth_deg: float, distance_m: float) -> Tuple[float, float]:
    """Cálculo Vincenty directa JIT."""
    lat1_rad = math.radians(lat)
    lon1_rad = math.radians(lon)
    az1_rad = math.radians(azimuth_deg)
    
    sin_az1 = math.sin(az1_rad)
    cos_az1 = math.cos(az1_rad)
    
    tan_u1 = (1 - WGS84_E2) * math.tan(lat1_rad)
    cos_u1 = 1 / math.sqrt(1 + tan_u1**2)
    sin_u1 = tan_u1 * cos_u1
    
    sigma1 = math.atan2(tan_u1, cos_az1)
    sin_alpha = cos_u1 * sin_az1
    
    u2 = (1 - WGS84_E2) * sin_alpha**2 / (1 - WGS84_E2 * sin_alpha**2)
    A = 1 + u2 / 16384 * (4096 + u2 * (-768 + u2 * (320 - 175 * u2)))
    B = u2 / 1024 * (256 + u2 * (-128 + u2 * (74 - 47 * u2)))
    
    sigma = distance_m / (WGS84_B * A)
    sigma_p = 2 * math.pi
    
    cos_2_sigma_m = 0.0
    while abs(sigma - sigma_p) > 1e-12:
        cos_2_sigma_m = math.cos(2 * sigma1 + sigma)
        sin_sigma = math.sin(sigma)
        cos_sigma = math.cos(sigma)
        
        B_sin_sigma = B * sin_sigma
        B_cos_sigma = B * cos_sigma * (math.cos(2 * sigma1) + B / 4 * (
            cos_sigma * (-1 + 2 * cos_2_sigma_m**2) - 
            B / 6 * cos_2_sigma_m * (-3 + 4 * sin_sigma**2) * (-3 + 4 * cos_2_sigma_m**2)
        ))
        
        sigma_p = sigma
        sigma = distance_m / (WGS84_B * A) + B_cos_sigma
    
    sin_sigma = math.sin(sigma)
    cos_sigma = math.cos(sigma)
    tmp = sin_u1 * sin_sigma - cos_u1 * cos_sigma * cos_az1
    lat2_rad = math.atan2(
        sin_u1 * cos_sigma + cos_u1 * sin_sigma * cos_az1,
        (1 - WGS84_E2) * math.sqrt(sin_alpha**2 + tmp**2)
    )
    
    lambda_val = math.atan2(sin_sigma * sin_az1, cos_u1 * cos_sigma - sin_u1 * sin_sigma * cos_az1)
    
    C = WGS84_E2 / 16 * sin_alpha**2 * (4 + WGS84_E2 * (4 - 3 * sin_alpha**2))
    
    lon2_rad = lon1_rad + (
        lambda_val - (1 - C) * WGS84_E2 * sin_alpha * (
            sigma + C * sin_sigma * (
                cos_2_sigma_m + C * cos_sigma * (-1 + 2 * cos_2_sigma_m**2)
            )
        )
    )
    
    lat2 = math.degrees(lat2_rad)
    lon2 = math.degrees(lon2_rad)
    
    if lon2 > 180:
        lon2 -= 360
    elif lon2 < -180:
        lon2 += 360
    
    return lat2, lon2

# ============================================================
# GeoTools — Herramientas de conversión geoespacial
# ============================================================

class GeoTools:
    """Herramientas para conversiones geoespaciales."""

    # Constantes WGS-84 de respaldo (Mantenidas para compatibilidad externa)
    WGS84_A = 6378137.0
    WGS84_B = 6356752.314245
    WGS84_E2 = 0.00669437999014132
    
    @staticmethod
    def slant_to_ground_range(slant_range_nm: float, flight_level: Optional[float], 
                               radar_height_ft: float = 0) -> float:
        """
        Convierte Slant Range (distancia oblicua) a Ground Range.
        """
        if flight_level is None or slant_range_nm == 0:
            return slant_range_nm
        
        return _slant_to_ground_range_jit(slant_range_nm, float(flight_level), float(radar_height_ft))
    
    @staticmethod
    def polar_to_wgs84(radar_lat: float, radar_lon: float, 
                       azimuth_deg: float, ground_range_nm: float) -> Tuple[float, float]:
        """
        Convierte coordenadas polares (azimut, rango) a WGS-84.
        Usa pyproj Geod si disponible, con fallback Haversine.
        """
        if ground_range_nm == 0:
            return radar_lat, radar_lon
        
        if HAS_PYPROJ:
            try:
                distance_m = ground_range_nm * 1852.0
                lon2, lat2, _ = WGS84_GEOD.fwd(radar_lon, radar_lat, azimuth_deg, distance_m)
                return lat2, lon2
            except Exception:
                pass
        
        # Fallback Haversine: JIT compilado
        distance_m = ground_range_nm * 1852.0
        # Reutilizamos el cálculo directo de punto de destino de Vincenty JIT si es preciso,
        # o Haversine matemático rápido. En este caso mantenemos Haversine en JIT para coincidir:
        lat1_rad = math.radians(radar_lat)
        lon1_rad = math.radians(radar_lon)
        az_rad = math.radians(azimuth_deg)
        angular_distance = distance_m / WGS84_A
        sin_lat2 = (math.sin(lat1_rad) * math.cos(angular_distance) +
                    math.cos(lat1_rad) * math.sin(angular_distance) * math.cos(az_rad))
        sin_lat2 = max(-1.0, min(1.0, sin_lat2))
        lat2_rad = math.asin(sin_lat2)
        lon2_rad = lon1_rad + math.atan2(
            math.sin(az_rad) * math.sin(angular_distance) * math.cos(lat1_rad),
            math.cos(angular_distance) - math.sin(lat1_rad) * math.sin(lat2_rad)
        )
        lat2 = math.degrees(lat2_rad)
        lon2 = math.degrees(lon2_rad)
        if lon2 > 180: lon2 -= 360
        elif lon2 < -180: lon2 += 360
        return lat2, lon2

    @staticmethod
    def cartesian_to_wgs84(radar_lat: float, radar_lon: float, x_m: float, y_m: float) -> Tuple[float, float]:
        """Convierte cartesianas (X, Y metros) a WGS84 usando AEQD."""
        if HAS_PYPROJ:
            try:
                proj_str = (f"+proj=aeqd +lat_0={radar_lat} +lon_0={radar_lon} "
                            f"+x_0=0 +y_0=0 +ellps=WGS84 +datum=WGS84 +units=m +no_defs")
                transformer = Transformer.from_crs(proj_str, "EPSG:4326", always_xy=True)
                lon, lat = transformer.transform(x_m, y_m)
                return lat, lon
            except Exception:
                pass
        
        # Fallback: Aproximación lineal
        lat_offset = y_m / 111132.0
        lon_offset = x_m / (111320.0 * math.cos(math.radians(radar_lat)))
        return radar_lat + lat_offset, radar_lon + lon_offset

    @staticmethod
    def calculate_distance_and_azimuth(lat1: float, lon1: float, lat2: float, lon2: float) -> Tuple[float, float]:
        """Calcula distancia (m) y azimut (deg) entre dos puntos WGS-84."""
        if HAS_PYPROJ:
            try:
                az, _, dist = WGS84_GEOD.inv(lon1, lat1, lon2, lat2)
                return dist, (az + 360) % 360
            except Exception:
                pass

        # Haversine JIT fallback
        return _calculate_distance_and_azimuth_jit(lat1, lon1, lat2, lon2)

    @staticmethod
    def vincenty_forward(lat: float, lon: float, azimuth_deg: float, 
                         distance_m: float) -> Tuple[float, float]:
        """Calcula punto destino usando Vincenty directa."""
        return _vincenty_forward_jit(lat, lon, azimuth_deg, distance_m)
    
    @staticmethod
    def meters_to_nm(meters: float) -> float:
        """Convierte metros a millas náuticas."""
        return meters / 1852.0
    
    @staticmethod
    def nm_to_meters(nm: float) -> float:
        """Convierte millas náuticas a metros."""
        return nm * 1852.0
    
    @staticmethod
    def feet_to_meters(feet: float) -> float:
        """Convierte pies a metros."""
        return feet * 0.3048
    
    @staticmethod
    def meters_to_feet(meters: float) -> float:
        """Convierte metros a pies."""
        return meters / 0.3048
