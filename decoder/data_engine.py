import os
import time
import json
import pickle
import hashlib
import tempfile
import socket
from typing import Dict, Tuple, List, Optional, Set, Any, Callable
from dataclasses import dataclass, field

import dpkt
from decoder.asterix_router import AsterixRouter
from utils.geo import METERS_PER_NM, WGS84_GEOD, StereographicLocal
from decoder.sensor_registry import SensorRegistry

# ============================================================
# CONSTANTES
# ============================================================
SECONDS_PER_DAY = 86400.0
CATEGORIAS_SOPORTADAS = {1, 2, 21, 23, 34, 48, 62}

# FASE 1: Resolución de cuantización para agrupar squitters sin dirección
QUANTIZE_LAT = 0.01
QUANTIZE_LON = 0.01


class SystemTrack:
    """Pista ASTERIX con ciclo de vida binario (ACTIVE / borrada)."""
    def __init__(self, category=None):
        self.category = category
        self.sac_sic = ""
        self.reporting_sensors = set()
        self.last_asterix_time = 0.0
        self.is_dropped_by_system = False
        self.status = "ACTIVE"

    def refrescar_estado(self):
        self.status = "ACTIVE"

    def actualizar_tiempo(self, asterix_timestamp: float):
        if self.last_asterix_time == 0.0:
            self.last_asterix_time = asterix_timestamp
            return
        if asterix_timestamp < self.last_asterix_time - 43200:
            asterix_timestamp += 86400
        self.last_asterix_time = asterix_timestamp


@dataclass
class AsterixPlot:
    """Estructura de un plot ASTERIX decodificado."""
    id: str               # ID único: "SAC_SIC_TOD_LAT_LON"
    sac_sic: str          # "{sac}/{sic}"
    category: int         # Categoría ASTERIX (1, 2, 21, 34, 48, 62)
    time: float           # Time of Day en segundos
    lat: float            # WGS84 Latitud (grados)
    lon: float            # WGS84 Longitud (grados)
    mode3a: str           # Código Squawk (Mode 3/A)
    callsign: str         # Identificador de vuelo (CAT 21)
    flight_level: float   # Nivel de vuelo (FL) o None
    altitude_ft: float    # Altitud en pies o None
    is_track: bool        # True si es CAT 62/21 (system track / ADS-B)
    bds_data: Dict[str, Any] = field(default_factory=dict)
    mode_s: Optional[str] = None
    track_angle: Optional[float] = None
    ground_speed: Optional[float] = None
    track_number: Optional[int] = None
    raw_range: Optional[float] = None
    raw_azimuth: Optional[float] = None
    pcap_time: Optional[float] = None  # PCAP packet arrival timestamp (epoch seconds)
    garbled: bool = False
    vertical_rate_ftmin: Optional[float] = None
    raw_bytes: Optional[bytes] = None  # bloque ASTERIX crudo (inspector de bajo nivel)

    def to_dict(self) -> Dict[str, Any]:
        """Retorna el diccionario para la señal new_plot_batch."""
        return {
            'id': self.id,
            'sac_sic': self.sac_sic,
            'category': self.category,
            'time': self.time,
            'lat': self.lat,
            'lon': self.lon,
            'mode3a': self.mode3a,
            'callsign': self.callsign,
            'flight_level': self.flight_level,
            'altitude_ft': self.altitude_ft,
            'is_track': self.is_track,
            'bds_data': self.bds_data,
            'mode_s': self.mode_s,
            'track_angle': self.track_angle,
            'ground_speed': self.ground_speed,
            'track_number': self.track_number,
            'raw_range': self.raw_range,
            'raw_azimuth': self.raw_azimuth,
            'pcap_time': self.pcap_time,
            'garbled': self.garbled,
            'vertical_rate_ftmin': self.vertical_rate_ftmin,
            'raw_bytes': getattr(self, 'raw_bytes', None),
        }

class IndraRDCUReader:
    def __init__(self, filepath):
        self.filepath = filepath
        # Categorías ASTERIX tácticas más comunes esperadas en el entorno
        self.categorias_validas = {1, 2, 21, 34, 48, 62, 65}
        self.last_timestamp = 1762858800.0  # Default initial timestamp

    def extraer_bloques(self, router=None):
        import struct
        with open(self.filepath, 'rb') as f:
            # 1. Leer y descartar la cabecera de texto RDCU inicial si existe
            head = f.read(512)
            inicio_datos = head.find(b'RDCU_RECORDING_ADAPT')
            if inicio_datos != -1:
                idx = inicio_datos
                while idx < len(head):
                    b = head[idx]
                    # Consideramos caracteres ASCII imprimibles y saltos de línea/tabuladores
                    if (32 <= b <= 126) or (b in (9, 10, 13)):
                        idx += 1
                    else:
                        break
                f.seek(idx)
            else:
                f.seek(0)

            # 2. Búsqueda Híbrida (Secuencial con Alineación por Deslizamiento)
            file_size = os.path.getsize(self.filepath)
            bytes_read = f.tell()

            while bytes_read < file_size:
                header_pos = f.tell()
                header_data = f.read(32)
                if len(header_data) < 32:
                    break

                # Unpack metadata
                meta_marker = struct.unpack('<i', header_data[16:20])[0]
                meta_len = struct.unpack('<I', header_data[28:32])[0]

                # Verificar si la cabecera de la grabación es válida
                if meta_marker == -1 and 3 <= meta_len <= 1500:
                    payload_data = f.read(meta_len)
                    if len(payload_data) < meta_len:
                        break

                    bytes_read = f.tell()

                    # Unpack timestamp de la grabación (16 bytes en la cabecera)
                    t_sec, t_usec = struct.unpack('<QQ', header_data[:16])
                    self.last_timestamp = t_sec + t_usec / 1000000.0

                    # Verificar si el payload es un bloque ASTERIX válido
                    cat = payload_data[0]
                    len_val = (payload_data[1] << 8) | payload_data[2]

                    if cat in self.categorias_validas and len_val == meta_len:
                        yield payload_data
                else:
                    # Pérdida de alineación: avanzar 1 byte
                    f.seek(header_pos + 1)
                    bytes_read = header_pos + 1

class DataEngine:
    """Motor de decodificación ASTERIX — SIN dependencias Qt."""
    
    def __init__(self, sensores: Dict = None, cache_dir: str = None, profile_config: Dict = None, repo_db: Any = None):
        self.router = AsterixRouter()
        self.sensores = sensores or {}
        # Toggle global de la corrección de registración por sensor (Fase 4).
        # La corrección igual requiere registration.enabled=true por sensor.
        self.aplicar_registracion = (profile_config or {}).get('aplicar_registracion', True)
        # Gestor de altimetría impulsado por perfil (TA dinámica, tabla ENR 1.7)
        from decoder.altimetry import AltimetryManager
        self.altimetry_manager = AltimetryManager(profile_config=profile_config)
        self.cache_dir = cache_dir or tempfile.gettempdir()
        self.plots: List[AsterixPlot] = []
        self.duration: float = 0.0
        
        # Callbacks (en lugar de señales)
        self.on_progress: Optional[Callable[[int, int], None]] = None
        self.on_sensor_detected: Optional[Callable[[int, int], None]] = None
        self.on_rotation_speed_detected: Optional[Callable[[int, int, float], None]] = None
        self.on_north_mark_detected: Optional[Callable[[int, int], None]] = None
        self.radar_health: Dict[Tuple[int, int], Dict] = {}
        self.on_radar_health_changed: Optional[Callable[[Tuple[int, int], Dict], None]] = None
        
        self._running = True
 
        # Repositorio analítico DuckDB: conexión PEREZOSA. Abrir el archivo en el
        # constructor hace que cada scan/playback contienda el lock del .duckdb
        # compartido (su hilo escritor + I/O compiten durante la decodificación),
        # inflando la carga ~6× aunque scan_pcap corra en bulk y no persista nada.
        # Se crea recién en el primer uso real (guardar_plot / query / PASS).
        self._repo_db = repo_db
        self.bulk_import_mode = False

        # Arquitectura dual de ingestión
        self.ingestion_mode = "LIVE"
        self.ultimo_tiempo_evaluacion = 0.0
        self.periodo_antena = 5.0

        # Reloj maestro ASTERIX y gestión de pistas (determinista, sin time.time())
        self.global_asterix_time = 0.0
        self.current_simulation_time = 0.0
        self.tracks: Dict[str, SystemTrack] = {}
        self.relojes_sensores: Dict[str, float] = {}  # último ToD visto por SAC/SIC
        self.is_playback_mode = False
        self.is_playing = False
        self.on_tracks_changed: Optional[Callable[[], None]] = None

        # QTimer para la recolección de basura del ciclo de vida (solo en LIVE)
        self.lifecycle_timer = None
        try:
            from PyQt6.QtCore import QTimer
            self.lifecycle_timer = QTimer()
            self.lifecycle_timer.timeout.connect(self.evaluar_vigencia_pistas)
            if self.ingestion_mode == "LIVE":
                self.lifecycle_timer.start(2000)
        except ImportError:
            pass

    def stop(self):
        self._running = False

    @property
    def repo_db(self):
        """Repo DuckDB perezoso: se conecta recién al primer acceso real."""
        if self._repo_db is None:
            from storage.duckdb_repo import DuckDBRepository
            self._repo_db = DuckDBRepository()
        return self._repo_db

    @repo_db.setter
    def repo_db(self, value):
        self._repo_db = value

    def close(self):
        """Cierra de forma limpia el repositorio analítico de DuckDB."""
        # No usar la property: cerrar no debe forzar la creación de un repo no usado.
        if getattr(self, '_repo_db', None) is not None:
            try:
                self._repo_db.close()
            except Exception:
                pass

    def set_playback_mode(self, enabled: bool):
        """Activa/desactiva el modo de reproducción estática (DRF)."""
        self.is_playback_mode = enabled

    def set_ingestion_mode(self, mode: str):
        """Activa/desactiva el origen de datos (LIVE o PLAYBACK) y gestiona el QTimer."""
        self.ingestion_mode = mode
        if self.ingestion_mode == "LIVE":
            if self.lifecycle_timer is not None and not self.lifecycle_timer.isActive():
                self.lifecycle_timer.start(2000)
        elif self.ingestion_mode == "PLAYBACK":
            if self.lifecycle_timer is not None and self.lifecycle_timer.isActive():
                self.lifecycle_timer.stop()

    def evaluar_vigencia_pistas(self):
        if not getattr(self, 'is_playing', False):
            return
        if not self.tracks:
            return

        TIMEOUT_MAXIMO = 25.0
        cambios = False

        for track_id in list(self.tracks.keys()):
            track = self.tracks[track_id]

            # Cat 62 / .Z: solo mueren por orden explícita del servidor
            if track.category in (62, 'Z'):
                if track.is_dropped_by_system:
                    del self.tracks[track_id]
                    cambios = True
                elif track.status != "ACTIVE":
                    track.status = "ACTIVE"
                    cambios = True
                continue

            # Cat 01, 21, 48: reloj aislado por SAC/SIC — lógica binaria
            reloj_sensor = self.relojes_sensores.get(track.sac_sic, track.last_asterix_time)
            delta_t = reloj_sensor - track.last_asterix_time
            if delta_t < -43200:
                delta_t += 86400

            if delta_t >= TIMEOUT_MAXIMO:
                print(f"💀 ASESINATO: {track_id} | Reloj Sensor: {reloj_sensor:.1f} | Tiempo Plot: {track.last_asterix_time:.1f} | Delta: {delta_t:.1f} seg")
                del self.tracks[track_id]
                cambios = True
            elif track.status != "ACTIVE":
                track.status = "ACTIVE"
                cambios = True

        if cambios:
            if hasattr(self, 'radar_widget') and self.radar_widget is not None:
                self.radar_widget.update()
            if self.on_tracks_changed is not None:
                self.on_tracks_changed()

    def procesar_paquete(self, payload: Any):
        """
        Método de ingestión unificado. Soporta:
        - payload de tipo bytes (paquete ASTERIX crudo de red/PCAP)
        - payload de tipo dict (registro ya decodificado)
        - payload de tipo tuple/list (fila leída de DuckDB)
        """
        if isinstance(payload, bytes):
            records = self.router.procesar_paquete_udp(payload)
            if records:
                proy_cache = {}
                sensores_vistos = set()
                plots_file = []
                for rec in records:
                    self._procesar_registro(rec, proy_cache, sensores_vistos, plots_file)
        elif isinstance(payload, dict):
            if 'sac_sic' in payload and ('sac' not in payload or 'sic' not in payload):
                try:
                    parts = payload['sac_sic'].split('/')
                    payload['sac'] = int(parts[0])
                    payload['sic'] = int(parts[1])
                except Exception:
                    pass
            proy_cache = {}
            sensores_vistos = set()
            plots_file = []
            self._procesar_registro(payload, proy_cache, sensores_vistos, plots_file)
        elif isinstance(payload, (tuple, list)):
            try:
                # Fila: (timestamp, category, sac_sic, track_id, lat, lon, flight_level, raw_azimuth, raw_range)
                timestamp, category, sac_sic, track_id, lat, lon, flight_level, raw_azimuth, raw_range = payload
                
                fl_val = None
                if flight_level and flight_level != '---':
                    try:
                        fl_val = float(flight_level.replace('FL', ''))
                    except ValueError:
                        fl_val = flight_level
                
                rec = {
                    'time': timestamp,
                    'category': category,
                    'sac_sic': sac_sic,
                    'lat': lat,
                    'lon': lon,
                    'flight_level': fl_val,
                    'raw_azimuth': raw_azimuth,
                    'raw_range': raw_range,
                }
                
                if track_id:
                    if len(track_id) == 4 and track_id.isdigit():
                        rec['mode3a'] = track_id
                    elif track_id.startswith('TRK_'):
                        try:
                            rec['track_number'] = int(track_id.split('_')[1])
                        except Exception:
                            pass
                    else:
                        rec['mode_s'] = track_id
                
                try:
                    parts = sac_sic.split('/')
                    rec['sac'] = int(parts[0])
                    rec['sic'] = int(parts[1])
                except Exception:
                    pass
                
                proy_cache = {}
                sensores_vistos = set()
                plots_file = []
                self._procesar_registro(rec, proy_cache, sensores_vistos, plots_file)
            except Exception as e:
                print(f"[DataEngine] Error procesando fila DuckDB: {e}")

    def leer_desde_duckdb(self):
        """
        Lee los plots guardados en DuckDB de manera cronológica
        y los procesa emulando una ingesta de PLAYBACK con evaluación manual.
        """
        self.set_ingestion_mode("PLAYBACK")
        self.ultimo_tiempo_evaluacion = 0.0
        
        filas = self.repo_db.query(
            "SELECT timestamp, category, sac_sic, track_id, lat, lon, flight_level, raw_azimuth, raw_range "
            "FROM asterix_plots ORDER BY timestamp ASC"
        )
        print(f"🔥 DUCKDB RESPONDE: Se leyeron {len(filas)} paquetes.")

        for fila in filas:
            self.procesar_paquete(fila)

    def _get_cache_filepath(self, pcap_file: str) -> str:
        pcap_abs_path = os.path.abspath(pcap_file)
        hasher = hashlib.md5()
        hasher.update(pcap_abs_path.encode('utf-8'))
        # Incluir la registración HABILITADA en la llave: un cambio de offset
        # invalida el caché. Sin registración activa, el caché previo sigue válido.
        if getattr(self, 'aplicar_registracion', True):
            for k in sorted(self.sensores.keys(), key=str):
                reg = (self.sensores.get(k) or {}).get('registration')
                if reg and reg.get('enabled'):
                    hasher.update(f"|{k}:{reg.get('azimuth_offset_deg', 0.0)}:"
                                  f"{reg.get('range_offset_nm', 0.0)}:"
                                  f"{reg.get('range_scale', 1.0)}".encode('utf-8'))
        cache_filename = f"{hasher.hexdigest()}.cache.pkl"
        return os.path.join(self.cache_dir, cache_filename)

    def _read_cache(self, pcap_file: str, incluir_raw_bytes: bool = False) -> Optional[List[AsterixPlot]]:
        # Caché local generado por la propia app desde un PCAP local (no es entrada
        # externa no confiable); el uso de pickle aquí es consistente con el resto.
        cache_path = self._get_cache_filepath(pcap_file)
        if not os.path.exists(cache_path):
            return None

        print(f"[DataEngine] Cache encontrado: {cache_path}. Validando...")

        try:
            pcap_size = os.path.getsize(pcap_file)
            pcap_mtime = os.path.getmtime(pcap_file)

            with open(cache_path, 'rb') as f:
                cache_data = pickle.load(f)

            CACHE_VERSION = 20
            metadata = cache_data.get('metadata', {})
            if (metadata.get('pcap_size') != pcap_size or
                metadata.get('pcap_mtime') != pcap_mtime or
                metadata.get('cache_version') != CACHE_VERSION):
                print("[DataEngine] Cache obsoleto o versión de estructura diferente. Re-decodificando.")
                return None

            plots = cache_data.get('plots', [])
            # raw_bytes (solo lo usa el inspector de la suite) vive en un archivo
            # lateral; el playback no lo necesita y así el caché principal es más
            # liviano. Se reanexa solo si se pide explícitamente.
            if incluir_raw_bytes:
                side_path = cache_path + ".rawbytes"
                if not os.path.exists(side_path):
                    print("[DataEngine] Falta el lateral de raw_bytes; re-decodificando para la suite.")
                    return None
                with open(side_path, 'rb') as f:
                    raws = pickle.load(f)
                if len(raws) == len(plots):
                    for p, rb in zip(plots, raws):
                        p.raw_bytes = rb

            print("[DataEngine] Cache válido. Cargando plots desde el caché.")
            return plots
        except Exception as e:
            print(f"[DataEngine] Error leyendo caché: {e}. Re-decodificando.")
            return None

    def _write_cache(self, pcap_file: str, plots: List[AsterixPlot]):
        cache_path = self._get_cache_filepath(pcap_file)
        print(f"[DataEngine] Escribiendo {len(plots)} plots al caché: {cache_path}")
        try:
            pcap_size = os.path.getsize(pcap_file)
            pcap_mtime = os.path.getmtime(pcap_file)

            # raw_bytes va a un archivo lateral: el caché principal (que usa el
            # playback) queda más liviano. Se extrae sin mutar los objetos vivos
            # (se restauran tras picklear el principal).
            raws = [getattr(p, 'raw_bytes', None) for p in plots]
            for p in plots:
                p.raw_bytes = None
            cache_data = {
                'metadata': {
                    'pcap_path': os.path.abspath(pcap_file),
                    'pcap_size': pcap_size,
                    'pcap_mtime': pcap_mtime,
                    'cache_time': time.time(),
                    'cache_version': 20
                },
                'plots': plots
            }
            try:
                with open(cache_path, 'wb') as f:
                    pickle.dump(cache_data, f)
            finally:
                for p, rb in zip(plots, raws):
                    p.raw_bytes = rb
            with open(cache_path + ".rawbytes", 'wb') as f:
                pickle.dump(raws, f)
        except Exception as e:
            print(f"[DataEngine] Error escribiendo al caché: {e}")

    def _procesar_registro(self, rec: Dict, proy_cache: Dict, sensores_vistos: Set, plots_file: List):
        """Procesa un registro ASTERIX individual decodificado y lo guarda/agrega."""
        try:
            cat = rec.get('category')
            if cat == 65:
                # CAT065 SDPS Service Status Reports: mensaje de estado, sin track.
                # Se persiste para el analizador/inspector y se marca en la timeline.
                import time
                if not self.bulk_import_mode:
                    self.repo_db.guardar_plot(rec)
                sac, sic = rec.get('sac'), rec.get('sic')
                if sac is not None and sic is not None:
                    t_val = rec.get('timestamp') or rec.get('time') or (
                        rec.get('pcap_time') % 86400.0
                        if rec.get('pcap_time') is not None else time.time())
                    dummy_plot = AsterixPlot(
                        id=f"TECH_65_{sac}_{sic}_{t_val}",
                        sac_sic=f"{sac}/{sic}", category=cat, time=t_val,
                        lat=0.0, lon=0.0, mode3a="", callsign="",
                        flight_level=None, altitude_ft=None, is_track=False,
                        raw_bytes=rec.get("raw_bytes"))
                    plots_file.append(dummy_plot)
                return

            if cat in (23, 34):
                import time
                if not self.bulk_import_mode:
                    self.repo_db.guardar_plot(rec)
                sac, sic = rec.get('sac'), rec.get('sic')
                if sac is not None and sic is not None:
                    t_val = rec.get('timestamp') or rec.get('time') or (rec.get('pcap_time') % 86400.0 if rec.get('pcap_time') is not None else time.time())
                    
                    data_health = self.radar_health.get((sac, sic), {
                        "channel_ab": "UNKNOWN",
                        "antenna_azimuth": None,
                        "sys_nogo": False,
                        "ovl_rdp": False,
                        "ovl_xmt": False,
                        "monitor_disc": False,
                        "time_invalid": False,
                        "psr_ovl": False,
                        "ssr_ovl": False,
                        "mds_ovl": False,
                        "system_state": None,
                        "ups_active": False
                    }).copy()
                    
                    data_health["local_time"] = t_val
                    
                    if cat == 34:
                        extra = rec.get('extra_data', {})
                        if extra.get('is_north_mark') and self.on_north_mark_detected:
                            self.on_north_mark_detected(sac, sic)
                        if 'antenna_rpm' in extra and self.on_rotation_speed_detected:
                            self.on_rotation_speed_detected(sac, sic, extra['antenna_rpm'])
                            
                        # Extraer telemetría de CAT 34 (I034/050 subcampo COM)
                        data_health["channel_ab"] = rec.get("channel_ab", "UNKNOWN")
                        data_health["antenna_azimuth"] = rec.get("azimuth")
                        # Solo actualizar el estado COM cuando el mensaje lo trae
                        # (mensajes de sector/norte no incluyen I034/050).
                        if "sys_nogo" in rec:
                            data_health["sys_nogo"] = rec.get("sys_nogo", False)
                            data_health["ovl_rdp"] = rec.get("ovl_rdp", False)
                            data_health["ovl_xmt"] = rec.get("ovl_xmt", False)
                            data_health["monitor_disc"] = rec.get("monitor_disc", False)
                            data_health["time_invalid"] = rec.get("time_invalid", False)
                            data_health["psr_ovl"] = rec.get("psr_ovl", False)
                            data_health["ssr_ovl"] = rec.get("ssr_ovl", False)
                            data_health["mds_ovl"] = rec.get("mds_ovl", False)
                    
                    elif cat == 23:
                        # Extraer telemetría de CAT 23
                        data_health["system_state"] = rec.get("system_state")
                        data_health["ups_active"] = rec.get("ups_active", False)
                        
                    self.radar_health[(sac, sic)] = data_health
                    if self.on_radar_health_changed:
                        self.on_radar_health_changed((sac, sic), data_health)
                    
                    # Generar un plot técnico ficticio para la línea de tiempo de reproducción
                    plot_id = f"TECH_{cat}_{sac}_{sic}_{t_val}"
                    dummy_plot = AsterixPlot(
                        id=plot_id,
                        sac_sic=f"{sac}/{sic}",
                        category=cat,
                        time=t_val,
                        lat=0.0,
                        lon=0.0,
                        mode3a="",
                        callsign="",
                        flight_level=None,
                        altitude_ft=None,
                        is_track=False,
                        raw_bytes=rec.get("raw_bytes")
                    )
                    dummy_plot.bds_data = data_health.copy()
                    plots_file.append(dummy_plot)
                return

            if cat == 2:
                sac, sic = rec.get('sac'), rec.get('sic')
                extra = rec.get('extra_data', {})
                if sac is not None and sic is not None:
                    if extra.get('is_north_mark') and self.on_north_mark_detected:
                        self.on_north_mark_detected(sac, sic)
                    if 'antenna_rpm' in extra and self.on_rotation_speed_detected:
                        self.on_rotation_speed_detected(sac, sic, extra['antenna_rpm'])

            plot = self._record_to_plot(rec, proy_cache)
            if plot is None:
                return

            # Guardar el plot proyectado con sus coordenadas lat/lon correctas
            if not self.bulk_import_mode:
                self.repo_db.guardar_plot(plot.to_dict())

            try:
                parts = plot.sac_sic.split('/')
                sk = (int(parts[0]), int(parts[1]))
                sensores_vistos.add(sk)
            except Exception:
                pass

            plots_file.append(plot)

            # Actualizar reloj maestro ASTERIX con el ToD del paquete
            if plot.time > 0.0:
                self.global_asterix_time = plot.time
                reloj_actual = self.relojes_sensores.get(plot.sac_sic, 0.0)
                delta_reloj = plot.time - reloj_actual
                if delta_reloj < -43200:
                    delta_reloj += 86400
                if delta_reloj >= 0 or reloj_actual == 0.0:
                    self.relojes_sensores[plot.sac_sic] = plot.time
            self.current_simulation_time = plot.time

            plot_id = plot.id
            if plot_id:
                track = self.tracks.get(plot_id)
                if not track:
                    track = SystemTrack(category=plot.category)
                    track.sac_sic = plot.sac_sic
                    self.tracks[plot_id] = track
                else:
                    track.refrescar_estado()
                track.reporting_sensors.add(plot.sac_sic)
                track.actualizar_tiempo(plot.time)
        except Exception:
            pass

    def _detectar_formato_raw(self, filepath: str) -> str:
        """Detecta si el archivo es wrapped (con metadatos y timestamps) o pure raw."""
        import struct
        try:
            file_size = os.path.getsize(filepath)
            if file_size < 32:
                return "pure_raw"
            with open(filepath, 'rb') as f:
                header1 = f.read(16)
                header2 = f.read(16)
                if len(header1) == 16 and len(header2) == 16:
                    t1_sec, t1_usec = struct.unpack('<QQ', header1)
                    t2_sec, t2_usec = struct.unpack('<QQ', header2)
                    if 1000000000 < t1_sec < 3000000000 and 1000000000 < t2_sec < 3000000000:
                        # Leer primera cabecera de registro para verificar consistencia
                        rec_header = f.read(16)
                        marker = f.read(8)
                        len_bytes = f.read(4)
                        if len(rec_header) == 16 and len(marker) == 8 and len(len_bytes) == 4:
                            payload_len = struct.unpack('<I', len_bytes)[0]
                            if 0 < payload_len < 65536:
                                payload = f.read(payload_len)
                                if len(payload) == payload_len:
                                    cat = payload[0]
                                    asterix_len = (payload[1] << 8) | payload[2]
                                    if cat in (1, 2, 21, 34, 48, 62, 65) and asterix_len == payload_len:
                                        return "wrapped"
        except Exception:
            pass
        return "pure_raw"

    def _scan_raw(
        self,
        filepath: str,
        file_idx: int,
        total_files: int,
        estimated_total: int,
        proy_cache: Dict,
        sensores_vistos: Set,
        plots_file: List
    ):
        """Escanea secuencialmente archivos binarios ASTERIX (wrapped o pure raw)."""
        import struct
        
        format_type = self._detectar_formato_raw(filepath)
        print(f"[DataEngine] Detectado formato binario: {format_type} para {filepath}")

        file_size = os.path.getsize(filepath)
        total_pkts = 0

        with open(filepath, 'rb') as f:
            if format_type == "wrapped":
                # Saltar cabeceras globales de 32 bytes
                f.read(32)
                bytes_read = 32

                while bytes_read < file_size:
                    if not self._running:
                        break
                    rec_header = f.read(16)
                    if len(rec_header) < 16:
                        break
                    bytes_read += 16

                    sec, usec = struct.unpack('<QQ', rec_header)
                    timestamp = sec + usec / 1000000.0

                    marker = f.read(8)
                    if len(marker) < 8:
                        break
                    bytes_read += 8

                    len_bytes = f.read(4)
                    if len(len_bytes) < 4:
                        break
                    bytes_read += 4

                    payload_len = struct.unpack('<I', len_bytes)[0]
                    payload = f.read(payload_len)
                    if len(payload) < payload_len:
                        break
                    bytes_read += payload_len

                    total_pkts += 1
                    if total_pkts % 1000 == 0 and self.on_progress:
                        progreso_base = int((file_idx / total_files) * estimated_total)
                        progreso_actual = progreso_base + min(estimated_total // total_files, total_pkts // total_files)
                        self.on_progress(progreso_actual, estimated_total)

                    records = self.router.procesar_paquete_udp(payload)
                    if records:
                        for rec in records:
                            rec['pcap_time'] = timestamp
                            self._procesar_registro(rec, proy_cache, sensores_vistos, plots_file)
            else:
                # Formato pure raw secuencial
                synthetic_time = 1762858800.0  # Epoch base standard (Nov 11, 2025 11:00)
                bytes_read = 0

                while bytes_read < file_size:
                    if not self._running:
                        break
                    header = f.read(3)
                    if len(header) < 3:
                        break
                    bytes_read += 3

                    cat = header[0]
                    len_val = (header[1] << 8) | header[2]
                    if len_val < 3:
                        break

                    remaining = len_val - 3
                    payload_rest = f.read(remaining)
                    if len(payload_rest) < remaining:
                        break
                    bytes_read += remaining

                    block = header + payload_rest

                    total_pkts += 1
                    if total_pkts % 1000 == 0 and self.on_progress:
                        progreso_base = int((file_idx / total_files) * estimated_total)
                        progreso_actual = progreso_base + min(estimated_total // total_files, total_pkts // total_files)
                        self.on_progress(progreso_actual, estimated_total)

                    records = self.router.procesar_paquete_udp(block)
                    if records:
                        for rec in records:
                            rec['pcap_time'] = synthetic_time
                            self._procesar_registro(rec, proy_cache, sensores_vistos, plots_file)
                    
                    synthetic_time += 0.02

    def scan_pcap(self, pcap_files, incluir_raw_bytes: bool = False) -> Tuple[List[AsterixPlot], float, Set[Tuple[int, int]]]:
        """
        Escanea y decodifica uno o múltiples archivos PCAP, PCAPNG o ASTERIX Binarios Crudos.
        Retorna (plots, duración total, sensores_detectados).

        `incluir_raw_bytes`: solo la suite técnica (inspector) lo necesita. Por
        defecto False -> el playback no carga ni retiene los bloques crudos
        (menos RAM y caché más liviano).
        """
        self.set_playback_mode(True)
        self.bulk_import_mode = True
        if isinstance(pcap_files, str):
            pcap_files = [pcap_files]
            
        all_plots: List[AsterixPlot] = []
        sensores_vistos: Set[Tuple[int, int]] = set()
        total_files = len(pcap_files)
        
        for file_idx, pcap_file in enumerate(pcap_files):
            if not os.path.exists(pcap_file):
                print(f"[DataEngine] Archivo no encontrado: {pcap_file}")
                continue

            cached_plots = self._read_cache(pcap_file, incluir_raw_bytes)
            if cached_plots is not None:
                print(f"[DataEngine] Usando caché para {pcap_file} ({len(cached_plots)} plots)")
                all_plots.extend(cached_plots)
                if not self.bulk_import_mode:
                    for plot in cached_plots:
                        self.repo_db.guardar_plot(plot.to_dict())
                for plot in cached_plots:
                    try:
                        parts = plot.sac_sic.split('/')
                        sk = (int(parts[0]), int(parts[1]))
                        sensores_vistos.add(sk)
                    except Exception:
                        pass
                    # Populate tracks for cached plots to ensure state parity
                    try:
                        if plot.time > 0.0:
                            self.global_asterix_time = plot.time
                        self.current_simulation_time = plot.time
                        plot_id = plot.id
                        if plot_id:
                            track = self.tracks.get(plot_id)
                            if not track:
                                track = SystemTrack(category=plot.category)
                                self.tracks[plot_id] = track
                            track.reporting_sensors.add(plot.sac_sic)
                            track.actualizar_tiempo(plot.time)
                    except Exception:
                        pass
                continue

            plots_file: List[AsterixPlot] = []
            proy_cache: Dict[Tuple[int, int], StereographicLocal] = {}
            self._running = True

            total_pkts = 0
            f = None
            es_raw = False
            es_rdcu = False

            try:
                with open(pcap_file, 'rb') as test_f:
                    header_bytes = test_f.read(100)
                    if b'RDCU' in header_bytes:
                        es_rdcu = True
            except Exception as e:
                print(f"[DataEngine] Error al pre-inspeccionar archivo {pcap_file}: {e}")

            if es_rdcu:
                es_raw = True
                print(f"[DataEngine] RDCU format detected in {pcap_file}. Instantiating IndraRDCUReader...")
                try:
                    rdcu_reader = IndraRDCUReader(pcap_file)
                    synthetic_time = 1762858800.0  # Base timestamp
                    
                    try:
                        file_size = os.path.getsize(pcap_file)
                        estimated_total = max(1, file_size // 200)
                    except Exception:
                        estimated_total = 10000

                    for packet in rdcu_reader.extraer_bloques(self.router):
                        if not self._running:
                            break
                        
                        total_pkts += 1
                        if total_pkts % 1000 == 0 and self.on_progress:
                            progreso_base = int((file_idx / total_files) * estimated_total)
                            progreso_actual = progreso_base + min(estimated_total // total_files, total_pkts // total_files)
                            self.on_progress(progreso_actual, estimated_total)

                        records = self.router.procesar_paquete_udp(packet)
                        if records:
                            for rec in records:
                                rec['pcap_time'] = synthetic_time
                                self._procesar_registro(rec, proy_cache, sensores_vistos, plots_file)
                        
                        synthetic_time += 0.02
                except Exception as rdcu_err:
                    print(f"[DataEngine] Error en escaneo RDCU para {pcap_file}: {rdcu_err}")

            if not es_rdcu:
                success = False
                total_pkts = 0

                # 1. Intentar como PCAP estándar (tanto apertura como iteración)
                f = None
                try:
                    f = open(pcap_file, 'rb')
                    pcap = dpkt.pcap.Reader(f)

                    try:
                        file_size = os.path.getsize(pcap_file)
                        estimated_total = max(1, file_size // 200)
                    except Exception:
                        estimated_total = 10000

                    print(f"[DataEngine] Escaneando archivo PCAP {file_idx + 1}/{total_files}: {pcap_file}")
                    datalink_type = getattr(pcap, 'datalink', lambda: 1)()
                    is_sll = (datalink_type == 113) # DLT_LINUX_SLL

                    for timestamp, buf in pcap:
                        if not self._running:
                            break
                        try:
                            if is_sll:
                                packet = dpkt.sll.SLL(buf)
                            else:
                                packet = dpkt.ethernet.Ethernet(buf)
                                
                            if not isinstance(packet.data, dpkt.ip.IP): continue
                            ip = packet.data
                            if not isinstance(ip.data, dpkt.udp.UDP): continue
                            udp = ip.data
                            asterix_payload = udp.data
                            
                            if len(asterix_payload) < 3: continue
                            total_pkts += 1

                            if total_pkts % 1000 == 0 and self.on_progress:
                                progreso_base = int((file_idx / total_files) * estimated_total)
                                progreso_actual = progreso_base + min(estimated_total // total_files, total_pkts // total_files)
                                self.on_progress(progreso_actual, estimated_total)

                            records = self.router.procesar_paquete_udp(asterix_payload)
                            if not records: continue

                            for rec in records:
                                rec['pcap_time'] = timestamp  # PCAP arrival epoch
                                self._procesar_registro(rec, proy_cache, sensores_vistos, plots_file)
                        except Exception:
                            continue
                    success = True
                except Exception as e:
                    print(f"[DataEngine] Error procesando como PCAP estándar: {e}. Reintentando como PCAPNG...")
                finally:
                    if f:
                        try: f.close()
                        except: pass

                # 2. Si falló, intentar PCAPNG
                if not success and self._running:
                    plots_file.clear()
                    total_pkts = 0
                    f = None
                    try:
                        f = open(pcap_file, 'rb')
                        pcap = dpkt.pcapng.Reader(f)

                        try:
                            file_size = os.path.getsize(pcap_file)
                            estimated_total = max(1, file_size // 200)
                        except Exception:
                            estimated_total = 10000

                        print(f"[DataEngine] Escaneando archivo PCAPNG {file_idx + 1}/{total_files}: {pcap_file}")
                        datalink_type = getattr(pcap, 'datalink', lambda: 1)()
                        is_sll = (datalink_type == 113) # DLT_LINUX_SLL

                        for timestamp, buf in pcap:
                            if not self._running:
                                break
                            try:
                                if is_sll:
                                    packet = dpkt.sll.SLL(buf)
                                else:
                                    packet = dpkt.ethernet.Ethernet(buf)
                                    
                                if not isinstance(packet.data, dpkt.ip.IP): continue
                                ip = packet.data
                                if not isinstance(ip.data, dpkt.udp.UDP): continue
                                udp = ip.data
                                asterix_payload = udp.data
                                
                                if len(asterix_payload) < 3: continue
                                total_pkts += 1

                                if total_pkts % 1000 == 0 and self.on_progress:
                                    progreso_base = int((file_idx / total_files) * estimated_total)
                                    progreso_actual = progreso_base + min(estimated_total // total_files, total_pkts // total_files)
                                    self.on_progress(progreso_actual, estimated_total)

                                records = self.router.procesar_paquete_udp(asterix_payload)
                                if not records: continue

                                for rec in records:
                                    rec['pcap_time'] = timestamp  # PCAP arrival epoch
                                    self._procesar_registro(rec, proy_cache, sensores_vistos, plots_file)
                            except Exception:
                                continue
                        success = True
                    except Exception as e:
                        print(f"[DataEngine] Error procesando como PCAPNG: {e}. Reintentando con fallback raw...")
                    finally:
                        if f:
                            try: f.close()
                            except: pass

                # 3. Si falló, intentar fallback a decodificador binario directo (raw / wrapped)
                if not success and self._running:
                    plots_file.clear()
                    try:
                        self._scan_raw(
                            pcap_file,
                            file_idx,
                            total_files,
                            10000,
                            proy_cache,
                            sensores_vistos,
                            plots_file
                        )
                    except Exception as raw_err:
                        print(f"[DataEngine] Error en escaneo raw fallback para {pcap_file}: {raw_err}")

            if plots_file:
                self._write_cache(pcap_file, plots_file)
                all_plots.extend(plots_file)

        self.bulk_import_mode = False

        # Disparar callback para todos los sensores detectados para combo box y autocentrado
        if self.on_sensor_detected:
            for sk in sorted(sensores_vistos):
                self.on_sensor_detected(sk[0], sk[1])

        if not all_plots:
            return [], 0.0, set()

        # Ordenar todos los plots de forma unificada y cronológica
        all_plots.sort(key=lambda p: p.time)

        # Deduplicar: mismo sensor + mismo rho/theta → misma detección física → fusionar
        all_plots = self._dedup_by_polar(all_plots)

        # Wraparound global
        if len(all_plots) > 1 and all_plots[-1].time < all_plots[0].time:
            max_gap = 0
            split_idx = 0
            for i in range(1, len(all_plots)):
                gap = all_plots[i].time - all_plots[i-1].time
                if gap > max_gap:
                    max_gap = gap
                    split_idx = i
            all_plots = all_plots[split_idx:] + all_plots[:split_idx]

        first_tod = all_plots[0].time
        last_tod = all_plots[-1].time
        self.duration = last_tod - first_tod
        if self.duration < 0: 
            self.duration += SECONDS_PER_DAY

        # Si no se pidieron, liberar los bloques crudos: en cold ya se persistieron
        # al lateral del caché; el playback no los usa y así no ocupan RAM.
        if not incluir_raw_bytes:
            for p in all_plots:
                p.raw_bytes = None

        self.plots = all_plots
        return all_plots, self.duration, sensores_vistos

    @staticmethod
    def _dedup_by_polar(plots: List['AsterixPlot']) -> List['AsterixPlot']:
        """
        Fusiona registros con mismo sensor + posición polar cuantizada dentro de una
        ventana de 3 segundos (mismo barrido de radar). Evita que un plot SSR y su
        system track correspondiente generen dos blancos separados en pantalla.
        """
        TIME_WIN = 3.0   # segundos — menos que el período mínimo de rotación (~4 s)

        seen: Dict[tuple, 'AsterixPlot'] = {}
        result: List['AsterixPlot'] = []

        for p in plots:
            if p.raw_range is None or p.raw_azimuth is None:
                result.append(p)
                continue

            qrho   = round(p.raw_range * 4)        # unidades de 0.25 NM
            qtheta = round(p.raw_azimuth) % 360    # unidades de 1°
            key = (p.sac_sic, qrho, qtheta)

            prev = seen.get(key)
            if prev is not None and abs(p.time - prev.time) < TIME_WIN:
                # Mismo barrido → fusionar campos faltantes en prev (ya está en result)
                if prev.mode_s is None and p.mode_s:
                    prev.mode_s = p.mode_s
                if prev.mode3a in ("----", "") and p.mode3a not in ("----", ""):
                    prev.mode3a = p.mode3a
                if prev.flight_level is None and p.flight_level is not None:
                    prev.flight_level = p.flight_level
                if prev.altitude_ft is None and p.altitude_ft is not None:
                    prev.altitude_ft = p.altitude_ft
                if not prev.callsign and p.callsign:
                    prev.callsign = p.callsign
                if prev.track_number is None and p.track_number is not None:
                    prev.track_number = p.track_number
                if not prev.is_track and p.is_track:
                    prev.is_track = p.is_track
                if not prev.bds_data and p.bds_data:
                    prev.bds_data = p.bds_data
                if prev.track_angle is None and p.track_angle is not None:
                    prev.track_angle = p.track_angle
                if prev.ground_speed is None and p.ground_speed is not None:
                    prev.ground_speed = p.ground_speed
                if prev.garbled and not p.garbled:
                    prev.garbled = False
                # No agregar p al resultado — ya está fusionado en prev
            else:
                seen[key] = p
                result.append(p)

        return result

    def _get_oar_sensor(self, sac, sic, proy_cache):
        if sac is None or sic is None:
            return None, None, None
        key = (sac, sic)
        sensor_info = self.sensores.get(key)
        proy = proy_cache.get(key)
        if proy is None and sensor_info:
            lat = sensor_info.get('lat')
            lon = sensor_info.get('lon')
            if lat is not None and lon is not None:
                proy = StereographicLocal(lat, lon)
                proy_cache[key] = proy
        return sac, sic, proy

    def _record_to_plot(self, rec: Dict, proy_cache: Dict) -> Optional[AsterixPlot]:
        try:
            cat = rec.get('category')
            if cat not in CATEGORIAS_SOPORTADAS:
                return None

            sac = rec.get('sac')
            sic = rec.get('sic')
            
            if cat == 62:
                if sac is None: sac = 0
                if sic is None: sic = 0
                
            sac, sic, proy = self._get_oar_sensor(sac, sic, proy_cache)
            if (sac is None or sic is None) and cat != 62:
                return None

            tod = rec.get('timestamp')
            if tod is None:
                tod = rec.get('time')
            if tod is None or tod == 0.0:
                pcap_time = rec.get('pcap_time')
                tod = (pcap_time % 86400.0) if pcap_time is not None else 0.0

            # I001/141 es ToD truncado (mod 512 s). Expandir a rango 24 h usando pcap_time
            # para que sea compatible con el ToD completo de CAT48/21/62.
            if cat == 1 and tod is not None and 0.0 < tod <= 512.0:
                pcap_time_cat1 = rec.get('pcap_time')
                if pcap_time_cat1 is not None:
                    pcap_tod = pcap_time_cat1 % 86400.0
                    base = pcap_tod - (pcap_tod % 512.0)
                    expanded = base + tod
                    if expanded - pcap_tod > 256.0:
                        expanded -= 512.0
                    elif pcap_tod - expanded > 256.0:
                        expanded += 512.0
                    tod = expanded

            if rec.get('valid_position') is False and cat != 62:
                return None

            sensor_info = self.sensores.get((sac, sic))
            if not sensor_info and sac is not None and sic is not None:
                fallback_lat = -31.31548
                fallback_lon = -64.21545
                if self.sensores:
                    first_known = next(iter(self.sensores.values()))
                    if first_known.get('lat') and first_known.get('lon'):
                        fallback_lat = first_known['lat']
                        fallback_lon = first_known['lon']
                
                self.sensores[(sac, sic)] = {
                    'lat': fallback_lat,
                    'lon': fallback_lon,
                    'name': f"Radar {sac}/{sic}"
                }
                sensor_info = self.sensores[(sac, sic)]
                proy_cache.pop((sac, sic), None)
                print(f"[DataEngine] Radar desconocido {sac}/{sic} registrado automáticamente en Lat={fallback_lat:.5f}, Lon={fallback_lon:.5f}")
            
            if not sensor_info:
                sensor_info = {}

            sensor_lat = sensor_info.get('lat')
            sensor_lon = sensor_info.get('lon')

            lat = lon = None
            # Determinar si es una pista (track) o un plot raw.
            # CAT 21, 62, 34, 2 son siempre pistas de sistema / mensajes de servicio.
            # CAT 48 y CAT 01 son pistas si contienen un track_number, o si CAT 48 trae información de Mode S (dirección ICAO o callsign).
            track_number = rec.get('track_number')
            is_track = (cat in (21, 62, 34, 2)) or (track_number is not None) or (cat == 48 and (rec.get('mode_s') is not None or rec.get('callsign') is not None))

            squawk = rec.get('mode_3a')
            squawk = f"{squawk:04o}" if squawk is not None else "----"

            callsign = rec.get('callsign', "")
            altitude_ft = rec.get('altitude')

            flight_level = rec.get('flight_level')
            if flight_level is None and altitude_ft is not None:
                flight_level = altitude_ft / 100.0
            mode_s = rec.get('mode_s')

            # CAT48: descartar detecciones sin ningún identificador.
            # En radar secundario (SSR-only) no hay retornos PSR, así que un
            # registro sin squawk, sin Mode-S, sin callsign y sin track_number
            # es ruido o garbling — no tiene utilidad y genera pistas fantasma.
            if cat == 48:
                has_id = (squawk != "----" or mode_s is not None or
                          (callsign and callsign.strip()) or track_number is not None)
                if not has_id:
                    return None
                if rec.get('detection_type') == 1:   # PSR-only en radar secundario
                    return None
            bds_data = rec.get('bds_data', {})
            track_angle = None
            ground_speed = None

            vertical_rate_ftmin = None
            if cat in (21, 62) and rec.get('latitude') is not None and rec.get('longitude') is not None:
                lat = rec.get('latitude')
                lon = rec.get('longitude')
                extra = rec.get('extra_data', {})
                if extra:
                    track_angle = extra.get('track_angle', extra.get('magnetic_heading'))
                    gs_kts = extra.get('ground_speed_kts')
                    if gs_kts is not None: ground_speed = gs_kts
                    gs_nms = extra.get('ground_speed_nms')
                    if gs_nms is not None: ground_speed = gs_nms * 3600.0
                    vr = extra.get('vertical_rate_ftmin')
                    if vr is not None: vertical_rate_ftmin = vr

            elif cat in (48, 1, 34, 2):
                if sensor_lat is not None and sensor_lon is not None:
                    rho = rec.get('raw_range')
                    theta = rec.get('raw_azimuth')
                    if rho is not None and theta is not None:
                        rho = float(rho)
                        theta = float(theta)
                        # Corrección de registración por sensor (opt-in: registration.enabled).
                        # Ajusta SOLO la posición; raw_azimuth/raw_range quedan crudos.
                        if getattr(self, 'aplicar_registracion', True) and sensor_info:
                            reg = sensor_info.get('registration')
                            if reg and reg.get('enabled'):
                                theta -= float(reg.get('azimuth_offset_deg', 0.0))
                                rho = rho * float(reg.get('range_scale', 1.0)) - float(reg.get('range_offset_nm', 0.0))
                        dist_m = rho * METERS_PER_NM
                        try:
                            if WGS84_GEOD:
                                lon_dest, lat_dest, _ = WGS84_GEOD.fwd(sensor_lon, sensor_lat, float(theta), dist_m)
                                lat, lon = lat_dest, lon_dest
                            else:
                                # Fallback if no pyproj
                                pass
                        except Exception:
                            pass
                
                extra = rec.get('extra_data', {})
                if extra.get('ground_speed_nms') is not None:
                    ground_speed = extra['ground_speed_nms'] * 3600.0
                if extra.get('track_angle') is not None:
                    track_angle = extra['track_angle']
                if bds_data:
                    if track_angle is None: track_angle = bds_data.get('mag_heading')
                    if ground_speed is None: ground_speed = bds_data.get('ground_speed_bds')

            if lat is None or lon is None or not (-90.0 <= lat <= 90.0) or not (-180.0 <= lon <= 180.0):
                flat = rec.get('lat', rec.get('latitude'))
                flon = rec.get('lon', rec.get('longitude'))
                if flat is not None and flon is not None and (-90.0 <= flat <= 90.0) and (-180.0 <= flon <= 180.0):
                    lat, lon = flat, flon
                else:
                    return None

            plot_id = None
            track_number = rec.get('track_number')

            if cat in (48, 1, 62) and track_number is not None:
                plot_id = f"{sac}_{sic}_{track_number}"
            elif cat == 21:
                if mode_s: plot_id = f"CAT21_{mode_s}"
                elif track_number is not None: plot_id = f"CAT21_TRK_{track_number}"
                elif callsign and callsign.strip(): plot_id = f"CAT21_CS_{callsign.strip()}"
            
            if not plot_id:
                if mode_s: plot_id = f"{sac}_{sic}_{mode_s}"
                elif track_number is not None: plot_id = f"{sac}_{sic}_TRK{track_number}"
                elif callsign and callsign.strip(): plot_id = f"{sac}_{sic}_{callsign.strip()}"
                elif squawk != "----": plot_id = f"{sac}_{sic}_{squawk}"
                else:
                    # PSR-only: usar coordenadas polares cuantizadas (más estables que WGS84)
                    rho_raw = rec.get('raw_range')
                    theta_raw = rec.get('raw_azimuth')
                    if rho_raw is not None and theta_raw is not None:
                        qrho = round(float(rho_raw) * 4) / 4      # cuantizar a 0.25 NM
                        qtheta = int(round(float(theta_raw))) % 360  # cuantizar a 1°
                        plot_id = f"PSR_{sac}_{sic}_{qrho:.2f}_{qtheta:03d}"
                    else:
                        qlat = round(lat / QUANTIZE_LAT) * QUANTIZE_LAT
                        qlon = round(lon / QUANTIZE_LON) * QUANTIZE_LON
                        plot_id = f"PSR_{sac}_{sic}_{qlat:.2f}_{qlon:.2f}"

            return AsterixPlot(
                id=plot_id, sac_sic=f"{sac}/{sic}", category=cat,
                time=float(tod), lat=lat, lon=lon,
                mode3a=squawk, callsign=callsign,
                flight_level=flight_level, altitude_ft=altitude_ft,
                is_track=is_track, bds_data=bds_data,
                mode_s=mode_s, track_angle=track_angle,
                ground_speed=ground_speed, track_number=track_number,
                raw_range=rec.get('raw_range'), raw_azimuth=rec.get('raw_azimuth'),
                pcap_time=rec.get('pcap_time'),
                garbled=rec.get('garbled', False),
                vertical_rate_ftmin=vertical_rate_ftmin,
                raw_bytes=rec.get('raw_bytes'),
            )
        except Exception as e:
            return None
