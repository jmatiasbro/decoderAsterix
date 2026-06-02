import os
import json
from typing import Dict, Optional, Tuple, Any
from pyproj import Geod

class SensorRegistry:
    """Caché en memoria para los parámetros de los sensores ASTERIX."""
    def __init__(self, config_dir="default-site-params"):
        # Resolve path relative to CWD or use absolute path for robustness
        # Assuming we run from decode_asterix root
        self.config_dir = config_dir
        if not os.path.isabs(self.config_dir):
            base_dir = os.getcwd()
            self.config_dir = os.path.join(base_dir, config_dir)
        self.sensors = {}  # Caché en memoria
        self._load_all_sensors()

    def _load_all_sensors(self):
        """Carga todos los archivos .json de la carpeta en la memoria RAM al arrancar."""
        if not os.path.exists(self.config_dir):
            print(f"⚠️ [AVISO] No se encontró la carpeta de radares: '{self.config_dir}'. Las coordenadas fallarán.")
            return
            
        archivos_cargados = 0
        for filename in os.listdir(self.config_dir):
            if filename.endswith(".json"):
                filepath = os.path.join(self.config_dir, filename)
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        # Usamos el nombre del archivo (ej. "226_214") como llave infalible
                        key = filename.replace('.json', '') 
                        self.sensors[key] = data
                        archivos_cargados += 1
                except Exception as e:
                    print(f"❌ Error cargando el radar {filename}: {e}")
                    
        print(f"📡 SensorRegistry: Se cargaron {archivos_cargados} radares exitosamente desde {self.config_dir}.")

    def get_sensor_coordinates(self, sac, sic) -> Tuple[Optional[float], Optional[float]]:
        """Busca el radar en la caché usando la llave formato 'sac_sic'."""
        try:
            key = f"{int(sac)}_{int(sic)}"
        except (TypeError, ValueError):
            return None, None
            
        sensor_data = self.sensors.get(key)
        if sensor_data:
            loc = sensor_data.get('location', {})
            return loc.get('latitude'), loc.get('longitude')
            
        return None, None

class TargetProcessor:
    """Procesa targets y convierte coordenadas."""
    
    def __init__(self, projection_system):
        self.projection_system = projection_system
        self.geod = Geod(ellps='WGS84')
        self._warned_sensors = set()
    
    def process_record(self, record: Any, sensor_registry: SensorRegistry) -> Dict:
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
            'is_garbled': record.extra_data.get('is_garbled', False),
            'extra_data': record.extra_data
        }

        # --- Motor de Validación de Calidad de Datos (Quality Flags) ---
        processed['invalid_a'] = processed.get('mode_3a') is None
        processed['invalid_c'] = processed.get('flight_level') is None
        processed['x_lcc_m'] = None
        processed['y_lcc_m'] = None
        processed['valid_position'] = False

        proj_sic = record.extra_data.get('service_id', record.sic) if hasattr(record, 'extra_data') and record.extra_data else record.sic
        
        # FASE 2: INMUNIDAD PARA CAT 62 (no requiere configuración de sensor local)
        if record.category != 62:
            # Obtener coordenadas del sensor desde el nuevo registro
            if record.sac is not None and proj_sic is not None:
                sensor_lat, sensor_lon = sensor_registry.get_sensor_coordinates(record.sac, proj_sic)
                
                if sensor_lat is not None and sensor_lon is not None:
                    # ¡CRÍTICO! Esto convierte al primer radar detectado en el centro X=0, Y=0
                    if getattr(self.projection_system, 'center_lat', None) is None:
                        if hasattr(self.projection_system, 'set_radar_center'):
                            self.projection_system.set_radar_center(sensor_lat, sensor_lon)
                        elif hasattr(self.projection_system, 'set_center'):
                            self.projection_system.set_center(sensor_lat, sensor_lon)
                        print(f"📡 Proyección centrada dinámicamente en el Radar {record.sac}/{proj_sic} ({sensor_lat}, {sensor_lon})")
                else:
                    sensor_key = (record.sac, proj_sic)
                    if sensor_key not in self._warned_sensors:
                        print(f"⚠️ [AVISO] Sensor {record.sac}/{proj_sic} no tiene posición configurada. No se podrán realizar proyecciones.")
                        self._warned_sensors.add(sensor_key)
        
        # CASO A: CAT 21/62 (Tienen Lat/Lon WGS-84 directas)
        if record.latitude is not None and record.longitude is not None:
            if hasattr(self.projection_system, 'latlon_to_lcc'):
                x, y = self.projection_system.latlon_to_lcc(record.latitude, record.longitude)
            elif hasattr(self.projection_system, 'latlon_to_xy'):
                x, y = self.projection_system.latlon_to_xy(record.latitude, record.longitude)
            else:
                x, y = None, None
            if x is not None and y is not None:
                processed['x_lcc_m'] = x
                processed['y_lcc_m'] = y
                processed['valid_position'] = True
            return processed
            
        # CASO B: CAT 48/01 (Coordenadas Polares RHO/THETA)
        if record.range_slant is not None and record.azimuth is not None:
            processed['valid_position'] = True
            
            sensor_lat, sensor_lon = sensor_registry.get_sensor_coordinates(record.sac, proj_sic)
            if sensor_lat is not None and sensor_lon is not None:
                distancia_metros = record.range_slant * 1852.0
                
                # 1. Vincenty: Polar a WGS-84
                lon_dest, lat_dest, _ = self.geod.fwd(
                    sensor_lon, sensor_lat, record.azimuth, distancia_metros
                )
                
                processed['latitude'] = lat_dest
                processed['longitude'] = lon_dest
                
                # 2. Lambert: WGS-84 a X,Y
                if hasattr(self.projection_system, 'latlon_to_lcc'):
                    x, y = self.projection_system.latlon_to_lcc(processed['latitude'], processed['longitude'])
                elif hasattr(self.projection_system, 'latlon_to_xy'):
                    x, y = self.projection_system.latlon_to_xy(processed['latitude'], processed['longitude'])
                else:
                    x, y = None, None
                if x is not None and y is not None:
                    processed['x_lcc_m'] = x
                    processed['y_lcc_m'] = y
                    processed['ground_range'] = record.range_slant
                    processed['radar_position'] = (sensor_lat, sensor_lon)
            return processed
            
        return processed
