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


class CoordinateTransformer:
    """Motor Geodésico optimizado con caché de transformaciones de proyección."""
    def __init__(self):
        self._aeqd_transformers: Dict[Tuple[float, float], Any] = {}
        if HAS_PYPROJ:
            self.geod = Geod(ellps='WGS84')

    def get_transformer(self, radar_lat: float, radar_lon: float):
        """Recupera o crea un transformador PROJ para el sensor específico (Evita cuello de botella)."""
        key = (radar_lat, radar_lon)
        if key not in self._aeqd_transformers:
            proj_str = (f"+proj=aeqd +lat_0={radar_lat} +lon_0={radar_lon} "
                        f"+x_0=0 +y_0=0 +ellps=WGS84 +datum=WGS84 +units=m +no_defs")
            self._aeqd_transformers[key] = Transformer.from_crs(proj_str, "EPSG:4326", always_xy=True)
        return self._aeqd_transformers[key]

    def cartesian_to_wgs84(self, radar_lat: float, radar_lon: float, x_m: float, y_m: float) -> Tuple[float, float]:
        if HAS_PYPROJ:
            transformer = self.get_transformer(radar_lat, radar_lon)
            lon, lat = transformer.transform(x_m, y_m)
            return lat, lon
        else:
            # Fallback matemático simple
            lat_offset = y_m / 111132.0
            lon_offset = x_m / (111320.0 * math.cos(math.radians(radar_lat)))
            return radar_lat + lat_offset, radar_lon + lon_offset

    def polar_to_wgs84(self, radar_lat: float, radar_lon: float, azimuth_deg: float, ground_range_nm: float) -> Tuple[float, float]:
        if ground_range_nm == 0:
            return radar_lat, radar_lon
        distance_m = ground_range_nm * 1852.0
        if HAS_PYPROJ:
            lon2, lat2, _ = self.geod.fwd(radar_lon, radar_lat, azimuth_deg, distance_m)
            return lat2, lon2
        # Fallback manejado estáticamente en la clase GeoTools.
        return GeoTools.polar_to_wgs84(radar_lat, radar_lon, azimuth_deg, ground_range_nm)

class GeoTools:
    """Herramientas para conversiones geoespaciales."""

    # Constantes WGS-84 de respaldo (en caso de que pyproj no esté disponible)
    WGS84_A = 6378137.0
    WGS84_B = 6356752.314245
    WGS84_E2 = 0.00669437999014132
    
    @staticmethod
    def slant_to_ground_range(slant_range_nm: float, flight_level: Optional[int], 
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
            # Proyección elipsoidal de alta precisión usando Geod (Forward Problem)
            lon2, lat2, _ = WGS84_GEOD.fwd(radar_lon, radar_lat, azimuth_deg, distance_m)
            return lat2, lon2
        else:
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
            # AEQD centrada en el origen del radar (ARP)
            proj_str = (f"+proj=aeqd +lat_0={radar_lat} +lon_0={radar_lon} "
                        f"+x_0=0 +y_0=0 +ellps=WGS84 +datum=WGS84 +units=m +no_defs")
            transformer = Transformer.from_crs(proj_str, "EPSG:4326", always_xy=True)
            lon, lat = transformer.transform(x_m, y_m)
            return lat, lon
        else:
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
            # Problema inverso geodésico
            az, _, dist = WGS84_GEOD.inv(lon1, lat1, lon2, lat2)
            return dist, (az + 360) % 360

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

class TrackManager:
    """
    Gestor de Estado de Traza (Memoria Circular).
    Mantiene los últimos N minutos de historia para evitar desbordamiento de RAM.
    """
    def __init__(self, history_minutes: int = 10, timeout_seconds: int = 60):
        self.tracks: Dict[str, deque] = {}  # Indexado por TargetAddress o Squawk
        self.last_update: Dict[str, float] = {}
        self.history_limit_seconds = history_minutes * 60
        self.timeout = timeout_seconds
        self.max_plots_per_track = 2000  # Límite de seguridad estricto para RAM

    def update_track(self, track_id: str, data: Dict):
        """Añade un plot a la historia de la traza y purga los que superan el límite de tiempo."""
        if track_id not in self.tracks:
            self.tracks[track_id] = deque(maxlen=self.max_plots_per_track)
        
        now = time.time()
        data['wall_clock'] = now
        self.tracks[track_id].append(data)
        self.last_update[track_id] = now

        # Purga plots de este track que superen el límite de historial.
        # Esto mantiene la memoria acotada por tiempo en lugar de por un número fijo de plots.
        while self.tracks[track_id]:
            # Usamos .get() para seguridad, aunque siempre debería estar presente.
            if now - self.tracks[track_id][0].get('wall_clock', now) > self.history_limit_seconds:
                self.tracks[track_id].popleft()
            else:
                # El resto de plots en el deque son suficientemente recientes.
                break

    def purge_stale_tracks(self):
        """Rutina de Garbage Collection para blancos inactivos."""
        now = time.time()
        stale_ids = [tid for tid, last_t in self.last_update.items() 
                     if (now - last_t) > self.timeout]
        for tid in stale_ids:
            del self.tracks[tid]
            del self.last_update[tid]
        return len(stale_ids)

    def clear_all(self):
        self.tracks.clear()
        self.last_update.clear()

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


class SensorRegistry:
    """Registro de sensores (combinaciones SAC/SIC) y sus propiedades."""
    
    def __init__(self):
        self.sensors: Dict[Tuple[int, int], Dict] = {}
    
    def register_sensor(self, sac: int, sic: int, lat: Optional[float] = None, 
                        lon: Optional[float] = None, elevation: Optional[float] = None):
        """Registra o actualiza un sensor con su posición."""
        key = (sac, sic)
        if key not in self.sensors:
            self.sensors[key] = {
                'sac': sac,
                'sic': sic,
                'latitude': lat,
                'longitude': lon,
                'elevation': elevation or 0,
                'records_count': 0
            }
        else:
            # Actualizar si tenemos nuevos datos
            if lat is not None:
                self.sensors[key]['latitude'] = lat
            if lon is not None:
                self.sensors[key]['longitude'] = lon
            if elevation is not None:
                self.sensors[key]['elevation'] = elevation
        
        self.sensors[key]['records_count'] += 1
    
    def get_sensor(self, sac: int, sic: int) -> Optional[Dict]:
        """Obtiene información de un sensor."""
        return self.sensors.get((sac, sic))
    
    def get_all_sensors(self) -> Dict[Tuple[int, int], Dict]:
        """Obtiene todos los sensores registrados."""
        return self.sensors
    
    def has_position(self, sac: int, sic: int) -> bool:
        """Verifica si un sensor tiene posición registrada."""
        sensor = self.get_sensor(sac, sic)
        return sensor is not None and sensor['latitude'] is not None and sensor['longitude'] is not None


class TargetProcessor:
    """Procesa targets y convierte coordenadas."""
    
    def __init__(self, sensor_registry: SensorRegistry):
        self.sensor_registry = sensor_registry
        self.transformer = CoordinateTransformer()
    
    def process_record(self, record) -> Dict:
        """
        Procesa un registro ASTERIX y convierte coordenadas si es posible.
        """
        processed = {
            'category': record.category,
            'sac': record.sac,
            'sic': record.sic,
            'timestamp': record.timestamp,
            'mode_3a': record.mode_3a,
            'flight_level': record.flight_level,
            'latitude': record.latitude,
            'longitude': record.longitude,
            'altitude': record.altitude,
            'raw_range': record.range_slant,
            'raw_azimuth': record.azimuth,
            'callsign': record.target_id,
            'mode_s': record.target_address,
            'track_number': record.track_number,
            'is_garbled': record.extra_data.get('is_garbled', False)
        }
        
        # CASO 1: Tenemos polares (CAT 048/001), calculamos WGS-84 para el Mapa
        if record.azimuth is not None and record.range_slant is not None:
            # Validación de "cordura" física: Ignorar rangos imposibles para un radar
            if record.range_slant > 1500 or record.range_slant < 0:
                return processed

            sensor = self.sensor_registry.get_sensor(record.sac, record.sic)
            
            if sensor and sensor['latitude'] is not None and sensor['longitude'] is not None:
                # Convertir slant range a ground range si hay flight level
                ground_range = GeoTools.slant_to_ground_range(
                    record.range_slant,
                    record.flight_level,
                    sensor['elevation']
                )
                
                # Convertir polares a WGS-84
                lat, lon = self.transformer.polar_to_wgs84(
                    sensor['latitude'],
                    sensor['longitude'],
                    record.azimuth,
                    ground_range
                )
                
                processed['latitude'] = lat
                processed['longitude'] = lon
                processed['ground_range'] = ground_range
                processed['radar_position'] = (sensor['latitude'], sensor['longitude'])

        # CASO 1.5: Tenemos Cartesianas (X, Y de CAT 062), calculamos WGS-84
        elif record.extra_data.get('x_m') is not None and record.extra_data.get('y_m') is not None:
            sensor = self.sensor_registry.get_sensor(record.sac, record.sic)
            if sensor and sensor['latitude'] is not None and sensor['longitude'] is not None:
                lat, lon = self.transformer.cartesian_to_wgs84(
                    sensor['latitude'],
                    sensor['longitude'],
                    record.extra_data['x_m'],
                    record.extra_data['y_m']
                )
                processed['latitude'] = lat
                processed['longitude'] = lon
                processed['radar_position'] = (sensor['latitude'], sensor['longitude'])

        # CASO 2: Ya tenemos WGS-84 (CAT 062/021) pero NO polares, las calculamos para el PPI
        elif processed['latitude'] is not None and processed['longitude'] is not None:
            if processed['raw_range'] is None or processed['raw_azimuth'] is None:
                sensor = self.sensor_registry.get_sensor(record.sac, record.sic)
                
                if sensor and sensor['latitude'] is not None and sensor['longitude'] is not None:
                    # Calcular polares inversas desde la posición del sensor
                    dist_m, az = GeoTools.calculate_distance_and_azimuth(
                        sensor['latitude'], 
                        sensor['longitude'],
                        processed['latitude'], 
                        processed['longitude']
                    )
                    
                    # Convertir a unidades ASTERIX (NM)
                    processed['raw_range'] = GeoTools.meters_to_nm(dist_m)
                    processed['raw_azimuth'] = az
                    processed['ground_range'] = processed['raw_range']
                    processed['radar_position'] = (sensor['latitude'], sensor['longitude'])
                
        return processed
