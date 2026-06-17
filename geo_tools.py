"""
Herramientas de Geoespacial

Módulo para conversiones de coordenadas, cálculos trigonométricos y proyecciones.
"""

import math
import time
from typing import Tuple, Dict, Optional, List, Any
from collections import deque
try:
    from pyproj import Geod, Transformer
    HAS_PYPROJ = True
    WGS84_GEOD = Geod(ellps='WGS84')
except ImportError:
    HAS_PYPROJ = False

# CoordinateTransformer ha sido eliminado en favor de RadarProjectionSystem (PyProj LCC) y Vincenty directo en TargetProcessor.

class GeoTools:
    """Herramientas para conversiones geoespaciales."""

    # Constantes WGS-84 de respaldo (en caso de que pyproj no esté disponible)
    WGS84_A = 6378137.0
    WGS84_B = 6356752.314245
    WGS84_E2 = 0.00669437999014132
    
    @staticmethod
    def slant_to_ground_range(slant_range_nm: float, flight_level: Optional[float], 
                              radar_height_ft: float = 0) -> float:
        """
        Convierte Slant Range (distancia oblicua) a Ground Range (distancia sobre terreno).
        
        Args:
            slant_range_nm: Distancia oblicua en millas náuticas
            flight_level: Nivel de vuelo del target (1/4 FL o 25 pies por LSB)
            radar_height_ft: Altura del radar sobre el terreno en pies
        
        Returns:
            Ground range en millas náuticas
        """
        if flight_level is None or slant_range_nm == 0:
            return slant_range_nm
        
        # Convertir Flight Level a pies
        target_height_ft = flight_level * 100  # FL * 100 pies
        
        # Diferencia de altitud
        height_diff = target_height_ft - radar_height_ft
        
        # Convertir slant range de NM a pies (1 NM = 6076.118 pies)
        slant_range_ft = slant_range_nm * 6076.118
        
        # Aplicar Pitágoras: ground_range² + height² = slant_range²
        abs_height_diff = abs(height_diff)
        if slant_range_ft >= abs_height_diff:
            # Usar max(0, ...) para evitar errores de precisión de punto flotante
            ground_range_ft = math.sqrt(max(0.0, slant_range_ft**2 - abs_height_diff**2))
        else:
            # Si la altura es mayor que la distancia oblicua, el ground range es físicamente 0
            ground_range_ft = 0.0
        
        # Convertir de vuelta a NM
        ground_range_nm = ground_range_ft / 6076.118
        return ground_range_nm
    
    @staticmethod
    def polar_to_wgs84(radar_lat: float, radar_lon: float, 
                       azimuth_deg: float, ground_range_nm: float) -> Tuple[float, float]:
        """
        Convierte coordenadas polares (azimut, rango) desde la posición del radar
        a coordenadas WGS-84 (latitud, longitud) usando fórmulas de trigonometría esférica.
        
        Args:
            radar_lat: Latitud del radar en grados decimales
            radar_lon: Longitud del radar en grados decimales
            azimuth_deg: Azimut en grados (0=Norte, 90=Este, 180=Sur, 270=Oeste)
            ground_range_nm: Distancia horizontal en millas náuticas
        
        Returns:
            Tupla (latitud, longitud) en grados decimales
        """
        if ground_range_nm == 0:
            return radar_lat, radar_lon
        
        # Convertir a radianes
        lat1_rad = math.radians(radar_lat)
        lon1_rad = math.radians(radar_lon)
        az_rad = math.radians(azimuth_deg)
        
        # Convertir ground range de NM a metros (1 NM = 1852 metros)
        distance_m = ground_range_nm * 1852.0
        
        if HAS_PYPROJ:
            try:
                # Proyección elipsoidal de alta precisión usando Geod (Forward Problem)
                lon2, lat2, _ = WGS84_GEOD.fwd(radar_lon, radar_lat, azimuth_deg, distance_m)
                return lat2, lon2
            except Exception:
                pass
        
        # Fallback: Fórmulas de Haversine/Great Circle
        angular_distance = distance_m / GeoTools.WGS84_A
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
        """
        Convierte coordenadas cartesianas (X, Y en metros) a WGS84.
        Utiliza la proyección Azimuthal Equidistant centrada en el radar para CAT 062.
        """
        if HAS_PYPROJ:
            try:
                # AEQD centrada en el origen del radar (ARP)
                proj_str = (f"+proj=aeqd +lat_0={radar_lat} +lon_0={radar_lon} "
                            f"+x_0=0 +y_0=0 +ellps=WGS84 +datum=WGS84 +units=m +no_defs")
                transformer = Transformer.from_crs(proj_str, "EPSG:4326", always_xy=True)
                lon, lat = transformer.transform(x_m, y_m)
                return lat, lon
            except Exception:
                pass
        
        # Fallback: Aproximación lineal simple
        lat_offset = y_m / 111132.0
        lon_offset = x_m / (111320.0 * math.cos(math.radians(radar_lat)))
        return radar_lat + lat_offset, radar_lon + lon_offset

    @staticmethod
    def calculate_distance_and_azimuth(lat1: float, lon1: float, lat2: float, lon2: float) -> Tuple[float, float]:
        """
        Calcula la distancia (m) y el azimut (deg) entre dos puntos WGS-84.
        Utilizado para proyectar datos de trazas (CAT 62) en pantallas PPI.
        """
        if HAS_PYPROJ:
            try:
                # Problema inverso geodésico
                az, _, dist = WGS84_GEOD.inv(lon1, lat1, lon2, lat2)
                return dist, (az + 360) % 360
            except Exception:
                pass

        phi1, phi2 = math.radians(lat1), math.radians(lat2)
        dphi = math.radians(lat2 - lat1)
        dlambda = math.radians(lon2 - lon1)

        # Distancia usando Haversine (suficiente para visualización PPI)
        a = (math.sin(dphi / 2)**2 + 
             math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2)**2)
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        distance = GeoTools.WGS84_A * c

        # Azimut (Rumbo inicial)
        y = math.sin(dlambda) * math.cos(phi2)
        x = (math.cos(phi1) * math.sin(phi2) - 
             math.sin(phi1) * math.cos(phi2) * math.cos(dlambda))
        
        azimuth = (math.degrees(math.atan2(y, x)) + 360) % 360
        
        return distance, azimuth

    @staticmethod
    def vincenty_forward(lat: float, lon: float, azimuth_deg: float, 
                         distance_m: float) -> Tuple[float, float]:
        """
        Calcula punto destino usando la fórmula Vincenty directa (más precisa para distancias largas).
        
        Args:
            lat: Latitud inicial en grados
            lon: Longitud inicial en grados
            azimuth_deg: Azimut inicial en grados
            distance_m: Distancia en metros
        
        Returns:
            Tupla (latitud_final, longitud_final) en grados
        """
        lat1_rad = math.radians(lat)
        lon1_rad = math.radians(lon)
        az1_rad = math.radians(azimuth_deg)
        
        sin_az1 = math.sin(az1_rad)
        cos_az1 = math.cos(az1_rad)
        
        tan_u1 = (1 - GeoTools.WGS84_E2) * math.tan(lat1_rad)
        cos_u1 = 1 / math.sqrt(1 + tan_u1**2)
        sin_u1 = tan_u1 * cos_u1
        
        sigma1 = math.atan2(tan_u1, cos_az1)
        sin_alpha = cos_u1 * sin_az1
        
        u2 = (1 - GeoTools.WGS84_E2) * sin_alpha**2 / (1 - GeoTools.WGS84_E2 * sin_alpha**2)
        A = 1 + u2 / 16384 * (4096 + u2 * (-768 + u2 * (320 - 175 * u2)))
        B = u2 / 1024 * (256 + u2 * (-128 + u2 * (74 - 47 * u2)))
        
        sigma = distance_m / (GeoTools.WGS84_B * A)
        sigma_p = 2 * math.pi
        
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
            sigma = distance_m / (GeoTools.WGS84_B * A) + B_cos_sigma
        
        tmp = sin_u1 * sin_sigma - cos_u1 * cos_sigma * cos_az1
        lat2_rad = math.atan2(
            sin_u1 * cos_sigma + cos_u1 * sin_sigma * cos_az1,
            (1 - GeoTools.WGS84_E2) * math.sqrt(sin_alpha**2 + tmp**2)
        )
        
        lambda_val = math.atan2(sin_sigma * sin_az1, cos_u1 * cos_sigma - sin_u1 * sin_sigma * cos_az1)
        
        C = GeoTools.WGS84_E2 / 16 * sin_alpha**2 * (4 + GeoTools.WGS84_E2 * (4 - 3 * sin_alpha**2))
        
        lon2_rad = lon1_rad + (
            lambda_val - (1 - C) * GeoTools.WGS84_E2 * sin_alpha * (
                sigma + C * sin_sigma * (
                    cos_2_sigma_m + C * cos_sigma * (-1 + 2 * cos_2_sigma_m**2)
                )
            )
        )
        
        lat2 = math.degrees(lat2_rad)
        lon2 = math.degrees(lon2_rad)
        
        # Normalizar longitud
        if lon2 > 180:
            lon2 -= 360
        elif lon2 < -180:
            lon2 += 360
        
        return lat2, lon2
    
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
