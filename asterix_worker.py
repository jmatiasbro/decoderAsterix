"""
asterix_worker.py — Worker QThread de decodificación ASTERIX
=============================================================
Lee un PCAP con scapy, filtra UDP, decodifica CAT 01/02/21/34/48/62 con
asterix.parse(), y emite señales con coordenadas proyectadas vía geo_utils.

Sincronización TDD:
  - Extrae Time of Day (ToD) de cada paquete
  - Calcula delta entre paquetes consecutivos
  - time.sleep() dinámico para reproducción en tiempo real

Optimización de comunicación:
  - Los plots se acumulan en buffer y se emiten SOLO en lotes cada 100ms
  - NO se emiten señales individuales durante play() para no saturar la UI
  - Señal tod_update independiente para el reloj digital
  - Diagnóstico cada 100 paquetes durante escaneo

CRÍTICO: El play loop se ejecuta DENTRO del QThread (run → scan → play),
NO en el hilo principal. Así el while+TDD sleep no bloquea la UI.

Señales de salida:
  new_plot_batch(list)  — Lote de plots (throttled, cada 100ms)
  tod_update(float)     — ToD actual para el reloj (señal independiente)

FASE 1 - ESTABILIZACIÓN TRACK_ID (CAT 021):
  - El ID de traza para CAT 021 usa como PRIMARY la Target Address (I021/080)
  - FALLBACK a Track Number (I021/161) con prefijo "CAT21_TRK_"
  - FALLBACK a Callsign con prefijo "CAT21_CS_"
  - ÚLTIMO RECURSO: cuantización de lat/lon para agrupar squitters sin dirección
"""

import os
import time
import math
import json
import pickle
import hashlib
import tempfile
import socket
from typing import Dict, Tuple, List, Optional, Set, Any
from dataclasses import dataclass, field

from PyQt6.QtCore import QThread, pyqtSignal, QMutex

import dpkt
from geo_utils import StereographicLocal, cargar_sensores, METERS_PER_NM, WGS84_GEOD
from asterix_router import AsterixRouter


# ============================================================
# CONSTANTES
# ============================================================
SECONDS_PER_DAY = 86400.0
CATEGORIAS_SOPORTADAS = {1, 2, 21, 34, 48, 62}
BATCH_INTERVAL = 0.10        # 100ms entre lotes
DIAG_INTERVAL = 500          # print cada 500 paquetes en scan
PROGRESS_INTERVAL = 1000     # emitir progress cada 1000 paquetes

# FASE 1: Resolución de cuantización para agrupar squitters sin dirección
# En grados: 0.01° ≈ 1.1 km — suficiente para agrupar posiciones cercanas
QUANTIZE_LAT = 0.01
QUANTIZE_LON = 0.01


# ============================================================
# ESTRUCTURA DEL PAQUETE DECODIFICADO
# ============================================================
@dataclass
class AsterixPlot:
    """
    Estructura de datos que se emite vía new_plot.
    Coincide con el diccionario requerido por la UI.
    """
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
    bds_data: Dict[str, Any] = field(default_factory=dict) # Decoded BDS register data
    mode_s: Optional[str] = None
    track_angle: Optional[float] = None
    ground_speed: Optional[float] = None
    track_number: Optional[int] = None  # Track Number (I048/161, I062/040)
    raw_range: Optional[float] = None   # RHO en NM (I048/040)
    raw_azimuth: Optional[float] = None # THETA en grados (I048/040)

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
        }


# ============================================================
# WORKER QThread
# ============================================================
class AsterixWorker(QThread):
    """
    Worker que procesa un archivo PCAP en un hilo separado.

    Flujo completo dentro del thread:
      run() → scan() → espera señal play → play() (loop TDD)

    CRÍTICO: El play loop (while + TDD sleep) se ejecuta dentro
    del QThread, NO en el hilo principal, para no bloquear la UI.
    """

    new_plot = pyqtSignal(object)           # Señal legacy (un solo plot)
    new_plot_batch = pyqtSignal(list)       # Lote de plots (throttled)
    tod_update = pyqtSignal(float)          # ToD actual para el reloj (independiente)
    scan_progress = pyqtSignal(int, int)    # current, total
    scan_percent = pyqtSignal(int)          # 0-100% para barra de progreso
    scan_done = pyqtSignal(int, float)      # total_frames, duración seg
    playback_finished = pyqtSignal()
    sensor_detected = pyqtSignal(int, int)  # SAC, SIC
    state_changed = pyqtSignal(str)         # "STOPPED", "PLAYING", "PAUSED"
    clear_plots = pyqtSignal()              # FASE 1: para limpiar el PPI
    sensors_scanned = pyqtSignal(set)       # {(sac,sic), ...} detectados en PCAP
    rotation_speed_detected = pyqtSignal(int, int, float) # sac, sic, rpm
    north_mark_detected = pyqtSignal(int, int) # sac, sic
    # FASE 1: Señales para TDD/Slider
    playback_progress = pyqtSignal(float, float)  # current_tod, duration (para slider)
    # FASE 2: Progreso
    progress_updated = pyqtSignal(int, str) # Recibe (porcentaje_o_indice, tiempo_formateado_str)

    def __init__(self, pcap_file: Optional[str], sensores: Dict, parent=None, 
                 cache_dir: Optional[str] = None,
                 udp_ip: Optional[str] = None,
                 udp_port: Optional[int] = None):
        super().__init__(parent)
        self.pcap_file = pcap_file
        self.sensores = sensores
        self.udp_ip = udp_ip
        self.udp_port = udp_port

        # FASE 2: Instanciar el router
        self.router = AsterixRouter()

        # Directorio de caché
        if cache_dir:
            self.cache_dir = cache_dir
        else:
            self.cache_dir = tempfile.gettempdir()

        # Cache en memoria
        self._plots: List[AsterixPlot] = []
        self._mutex = QMutex()
        self._running = True
        self.state = "STOPPED"  # "STOPPED", "PLAYING", "PAUSED"
        self._play_index = 0
        self._scanned = False
        self._duration = 0.0

        # Buffer de throttling (solo para play())
        self._plot_buffer: List[Dict] = []
        self._last_batch_emit = 0.0

        # Proyección estereográfica
        self.proy = StereographicLocal()

        # Filtros activos
        self.active_sensors: Set[Tuple[int, int]] = set()
        self.squawk_filter = ""
        self.filter_enabled = False

        # FASE 1: Multiplicador de velocidad (1x, 2x, 4x, 5x, 10x)
        self._speed_multiplier: float = 1.0

        # FASE 2: Atributos de control
        self.velocidad = 1.0
        self.total_paquetes = 0
        self.paquete_actual = 0


    # ================================================================
    # CONTROL DEL WORKER (thread-safe)
    # ================================================================

    def stop(self):
        """Detiene el worker de forma segura."""
        self.state = "STOPPED"
        self._running = False

    def stop_playback(self):
        """FASE 1: Resetea la reproducción al inicio y limpia la pantalla."""
        if self.state != "STOPPED":
            self.state = "STOPPED"
            self._play_index = 0
            self.clear_plots.emit()
            if self._plots:
                self.tod_update.emit(self._plots[0].time)
            else:
                self.tod_update.emit(0.0)
            self.state_changed.emit(self.state)

    def toggle_play_pause(self):
        """FASE 1: Máquina de estados para Play/Pause/Stop."""
        if self.state == "PLAYING":
            self.state = "PAUSED"
        elif self.state in ("PAUSED", "STOPPED"):
            if self.state == "STOPPED":
                self._play_index = 0
                self.clear_plots.emit()
            self.state = "PLAYING"
        self.state_changed.emit(self.state)

    def seek_to_tod(self, tod: float):
        """Busca el frame con ToD más cercano (búsqueda binaria)."""
        self._mutex.lock()
        if self._plots:
            lo, hi = 0, len(self._plots) - 1
            while lo < hi:
                mid = (lo + hi) // 2
                if self._plots[mid].time < tod:
                    lo = mid + 1
                else:
                    hi = mid
            self._play_index = max(0, lo - 1)
        self._mutex.unlock()

    def set_filters(self, active_sensors: Set[Tuple[int, int]], squawk_filter: str):
        """Establece los filtros activos desde la UI."""
        self.active_sensors = active_sensors
        self.squawk_filter = squawk_filter
        self.filter_enabled = bool(active_sensors) or bool(squawk_filter)

    def set_speed_multiplier(self, multiplier: float):
        """FASE 1: Establece el multiplicador de velocidad de reproducción.
        Valores típicos: 1.0, 2.0, 4.0, 5.0, 10.0."""
        if multiplier > 0:
            self._speed_multiplier = multiplier

    def _plot_passes_filter(self, plot: AsterixPlot) -> bool:
        """Verifica si un plot pasa los filtros activos."""
        # REGLA DE BYPASS PARA CAT 62: No se filtra por SAC/SIC.
        if self.active_sensors and plot.category != 62:
            if not plot.sac_sic:
                return False  # No tiene SAC/SIC para filtrar, se descarta
            try:
                parts = plot.sac_sic.split('/')
                sac, sic = int(parts[0]), int(parts[1])
                if (sac, sic) not in self.active_sensors:
                    return False
            except (ValueError, IndexError):
                return False  # Malformado, se descarta

        if self.squawk_filter:
            if self.squawk_filter not in plot.mode3a and \
               self.squawk_filter.lower() not in plot.callsign.lower():
                return False

        return True

    # ================================================================
    # CACHÉ EN DISCO (para carga rápida)
    # ================================================================

    def _get_cache_filepath(self) -> str:
        """Genera una ruta de archivo de caché única basada en la ruta del PCAP."""
        pcap_abs_path = os.path.abspath(self.pcap_file)
        hasher = hashlib.md5()
        hasher.update(pcap_abs_path.encode('utf-8'))
        cache_filename = f"{hasher.hexdigest()}.cache.pkl"
        return os.path.join(self.cache_dir, cache_filename)

    def _read_cache(self) -> Optional[List[AsterixPlot]]:
        """Lee y valida el archivo de caché. Retorna plots si es válido, si no None."""
        cache_path = self._get_cache_filepath()
        if not os.path.exists(cache_path):
            return None

        print(f"[AsterixWorker] Cache encontrado: {cache_path}. Validando...")

        try:
            pcap_size = os.path.getsize(self.pcap_file)
            pcap_mtime = os.path.getmtime(self.pcap_file)

            with open(cache_path, 'rb') as f:
                cache_data = pickle.load(f)
            
            CACHE_VERSION = 14
            metadata = cache_data.get('metadata', {})
            
            if (metadata.get('pcap_size') != pcap_size or
                metadata.get('pcap_mtime') != pcap_mtime or
                metadata.get('cache_version') != CACHE_VERSION):
                print("[AsterixWorker] Cache obsoleto o versión de estructura diferente. Re-decodificando.")
                return None

            print("[AsterixWorker] Cache válido. Cargando plots desde el caché.")
            
            return cache_data.get('plots', [])

        except (IOError, json.JSONDecodeError, pickle.UnpicklingError, KeyError, TypeError) as e:
            print(f"[AsterixWorker] Error leyendo caché: {e}. Re-decodificando.")
            return None

    def _write_cache(self, plots: List[AsterixPlot]):
        """Escribe los plots decodificados a un archivo de caché."""
        cache_path = self._get_cache_filepath()
        print(f"[AsterixWorker] Escribiendo {len(plots)} plots al caché: {cache_path}")

        try:
            pcap_size = os.path.getsize(self.pcap_file)
            pcap_mtime = os.path.getmtime(self.pcap_file)

            cache_data = {
                'metadata': {
                    'pcap_path': os.path.abspath(self.pcap_file),
                    'pcap_size': pcap_size,
                    'pcap_mtime': pcap_mtime,
                    'cache_time': time.time(),
                    'cache_version': 14
                },
                'plots': plots
            }
            with open(cache_path, 'wb') as f:
                pickle.dump(cache_data, f)
        except (IOError, TypeError) as e:
            print(f"[AsterixWorker] Error escribiendo al caché: {e}")

    # ================================================================
    # FASE 1: ESCANEO DEL PCAP (se ejecuta en el hilo worker)
    # ================================================================

    def scan(self):
        """Escanea el PCAP completo y cachea los plots."""
        if not os.path.exists(self.pcap_file):
            print(f"[AsterixWorker] PCAP no encontrado: {self.pcap_file}")
            self.playback_finished.emit()
            self._scanned = True  # Marcar como escaneado aunque haya fallado
            return

        # --- VERIFICACIÓN DE CACHÉ ---
        cached_plots = self._read_cache()
        if cached_plots is not None:
            self._plots = cached_plots
            
            first_tod = None
            last_tod = None
            sensores_vistos: Set[Tuple[int, int]] = set()

            if self._plots:
                first_tod = self._plots[0].time
                last_tod = self._plots[-1].time
                dur = last_tod - first_tod
                if dur < 0:
                    dur += SECONDS_PER_DAY
                self._duration = dur

                for plot in self._plots:
                    try:
                        parts = plot.sac_sic.split('/')
                        sk = (int(parts[0]), int(parts[1]))
                        if sk not in sensores_vistos:
                            sensores_vistos.add(sk)
                            self.sensor_detected.emit(sk[0], sk[1])
                    except Exception:
                        pass
            
            self.sensors_scanned.emit(sensores_vistos)
            self._mutex.lock()
            self._scanned = True
            self._mutex.unlock()
            self.scan_done.emit(len(self._plots), self._duration)
            return

        plots: List[AsterixPlot] = []
        first_tod = None
        last_tod = None
        total_pkts = 0
        sensores_vistos: Set[Tuple[int, int]] = set()
        proy_cache: Dict[Tuple[int, int], StereographicLocal] = {}

        try:
            # Usar dpkt para leer el PCAP (más rápido que Scapy para archivos masivos)
            f = open(self.pcap_file, 'rb')
            pcap = dpkt.pcap.Reader(f)
        except Exception as e:
            print(f"[AsterixWorker] Error abriendo PCAP con dpkt: {e}")
            self.playback_finished.emit()
            self._scanned = True
            return

        try:
            file_size = os.path.getsize(self.pcap_file)
            estimated_total = max(1, file_size // 200)
        except Exception:
            estimated_total = 10000

        last_pct = -1
        last_diag_print = 0

        print(f"[AsterixWorker] Escaneando: {self.pcap_file}")

        pcap_iter_error = False
        try:
            for timestamp, buf in pcap:
                try:
                    if not self._running:
                        self._scanned = True
                        return

                    # 1. Desempaquetar Ethernet
                    try:
                        eth = dpkt.ethernet.Ethernet(buf)
                    except Exception:
                        continue

                    # 2. Verificar que sea IP
                    if not isinstance(eth.data, dpkt.ip.IP):
                        continue
                    ip = eth.data

                    # 3. Verificar que sea UDP
                    if not isinstance(ip.data, dpkt.udp.UDP):
                        continue
                    udp = ip.data

                    # 4. Extraer payload ASTERIX puro (sin cabeceras de red)
                    asterix_payload = udp.data
                    if len(asterix_payload) < 3:
                        continue

                    total_pkts += 1

                    # Diagnóstico
                    if total_pkts - last_diag_print >= DIAG_INTERVAL:
                        last_diag_print = total_pkts
                        print(f"[AsterixWorker] Escaneando: {total_pkts} paquetes...")

                    # Progreso
                    if total_pkts % PROGRESS_INTERVAL == 0:
                        self.scan_progress.emit(total_pkts, estimated_total)
                        pct = min(99, int(100 * total_pkts / max(1, estimated_total)))
                        if pct != last_pct:
                            last_pct = pct
                            # self.scan_percent.emit(pct) # Deshabilitado temporalmente

                    records = self.router.procesar_paquete_udp(asterix_payload)
                    if not records:
                        continue

                    for rec in records:
                        try:
                            cat = rec.get('category')
                            # Mensajes de servicio
                            if cat in (2, 34):
                                sac = rec.get('sac')
                                sic = rec.get('sic')
                                extra_data = rec.get('extra_data', {})
                                if sac is not None and sic is not None:
                                    if extra_data.get('is_north_mark'):
                                        self.north_mark_detected.emit(sac, sic)
                                    if 'antenna_rpm' in extra_data:
                                        self.rotation_speed_detected.emit(sac, sic, extra_data['antenna_rpm'])

                            # Target
                            plot = self._record_to_plot(rec, proy_cache)
                            if plot is None:
                                continue

                            # Nuevo sensor
                            try:
                                parts = plot.sac_sic.split('/')
                                sk = (int(parts[0]), int(parts[1]))
                                if sk not in sensores_vistos:
                                    sensores_vistos.add(sk)
                                    self.sensor_detected.emit(sk[0], sk[1])
                            except Exception:
                                pass

                            if first_tod is None:
                                first_tod = plot.time
                            last_tod = plot.time
                            plots.append(plot)
                        except Exception as e:
                            import traceback
                            print(f"[AsterixWorker] Error processing record: {e}\n{traceback.format_exc()}")
                            continue
                except Exception as e:
                    import traceback
                    print(f"[AsterixWorker] Error processing packet (dpkt): {e}\n{traceback.format_exc()}")
                    continue
        except Exception as e:
            import traceback
            print(f"[AsterixWorker] Error iterating pcap: {e}\n{traceback.format_exc()}")
            pcap_iter_error = True
        finally:
            # Cerrar el file handle del pcap
            try:
                f.close()
            except Exception:
                pass

        if pcap_iter_error:
            print("[AsterixWorker] Iteración del PCAP interrumpida por error.")

        # Post-procesamiento
        if not plots:
            print("[AsterixWorker] No se decodificaron plots.")
            self._scanned = True
            self.playback_finished.emit()
            return

        if first_tod is not None and last_tod is not None:
            dur = last_tod - first_tod
            if dur < 0:
                dur += SECONDS_PER_DAY
            self._duration = dur
        plots.sort(key=lambda p: p.time)

        # Wraparound
        if len(plots) > 1 and plots[-1].time < plots[0].time:
            max_gap = 0
            split_idx = 0
            for i in range(1, len(plots)):
                gap = plots[i].time - plots[i-1].time
                if gap > max_gap:
                    max_gap = gap
                    split_idx = i
            plots = plots[split_idx:] + plots[:split_idx]

        # --- ESCRIBIR A CACHÉ ---
        self._write_cache(plots)

        self.sensors_scanned.emit(sensores_vistos)

        self._mutex.lock()
        self._plots = plots
        self._scanned = True
        self._play_index = 0
        self._mutex.unlock()

        self.scan_percent.emit(100)
        self.scan_done.emit(len(plots), self._duration)
        print(f"[AsterixWorker] Escaneo completado: {len(plots)} frames en {self._duration:.1f}s")

    def _udp_listen_loop(self):
        """
        Loop de escucha de socket UDP en vivo.
        Recibe paquetes, los decodifica y los emite en lotes.
        """
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind((self.udp_ip, self.udp_port))
            sock.settimeout(1.0) # Timeout para poder chequear self._running
            print(f"[AsterixWorker] Socket UDP bindeado exitosamente a {self.udp_ip}:{self.udp_port}")
        except OSError as e:
            print(f"[AsterixWorker] ERROR al bindear socket UDP: {e}")
            self.playback_finished.emit() # Usar esta señal para indicar que terminó
            return

        proy_cache: Dict[Tuple[int, int], StereographicLocal] = {}
        sensores_vistos: Set[Tuple[int, int]] = set()
        self._plot_buffer.clear()
        self._last_batch_emit = time.time()
        self.state = "PLAYING"
        self.state_changed.emit(self.state)

        # Para emisión de progreso al slider
        last_progress_emit = 0.0

        while self._running:
            if self.state != "PLAYING":
                QThread.msleep(100)
                continue
            
            try:
                payload, addr = sock.recvfrom(8192)
            except socket.timeout:
                continue # Volver al inicio del loop para chequear self._running

            if not payload:
                continue

            records = self.router.procesar_paquete_udp(payload)
            if not records:
                continue

            for rec in records:
                try:
                    plot = self._record_to_plot(rec, proy_cache)
                    if plot is None:
                        continue

                    try:
                        parts = plot.sac_sic.split('/')
                        sk = (int(parts[0]), int(parts[1]))
                        if sk not in sensores_vistos:
                            sensores_vistos.add(sk)
                            self.sensor_detected.emit(sk[0], sk[1])
                    except Exception:
                        pass

                    if not self.filter_enabled or self._plot_passes_filter(plot):
                        self._plot_buffer.append(plot.to_dict())
                except Exception:
                    continue
            
            now = time.time()
            if now - self._last_batch_emit >= BATCH_INTERVAL:
                self._emit_batch()
                self._last_batch_emit = now

        sock.close()
        self._emit_batch()
        self.playback_finished.emit()
        print("[AsterixWorker] Escucha UDP finalizada.")

    # ================================================================
    # FASE 2: REPRODUCCIÓN TDD (se ejecuta en el hilo worker)
    # ================================================================

    def _emit_batch(self):
        """Vacía el buffer emitiendo un solo lote a la UI."""
        if self._plot_buffer:
            self.new_plot_batch.emit(self._plot_buffer)
            last_tod = self._plot_buffer[-1].get('time', 0.0)
            self.tod_update.emit(last_tod)
            self._plot_buffer.clear()

    def _playback_loop(self):
        """
        Loop de reproducción TDD.
        Se ejecuta DENTRO del QThread (llamado desde run()),
        por lo que time.sleep() NO bloquea la UI.
        """
        if not self._plots:
            self.playback_finished.emit()
            return

        first_tod = self._plots[0].time
        wall_start = time.time()
        wall_offset = 0.0
        self._plot_buffer.clear()
        self._last_batch_emit = time.time()

        print(f"[AsterixWorker] Reproduciendo {len(self._plots)} frames...")
        is_resuming = False
        # Para emisión de progreso al slider
        last_progress_emit = 0.0

        while self._running:
            # Máquina de estados: solo se procesa si está en PLAYING
            if self.state != "PLAYING":
                QThread.msleep(50)
                # Recalcular el offset del reloj de pared para que la pausa no cause un salto en el tiempo
                wall_offset = time.time() - wall_start
                is_resuming = True
                continue

            if is_resuming:
                # Al reanudar, recalibrar el tiempo de inicio para evitar saltos
                current_plot_tod = self._plots[self._play_index].time
                elapsed_tod_since_start = current_plot_tod - first_tod
                if elapsed_tod_since_start < 0: elapsed_tod_since_start += SECONDS_PER_DAY
                wall_start = time.time() - elapsed_tod_since_start
                is_resuming = False

            if not self._running:
                break

            # Índice actual
            self._mutex.lock()
            if self.paquete_actual != self._play_index and self.paquete_actual != (self._play_index - 1):
                 # Si fue modificado externamente
                 self._play_index = self.paquete_actual
                 is_resuming = True # Force recalibration of wall_start
            
            idx = self._play_index
            plots = self._plots
            self._mutex.unlock()

            if idx >= len(plots):
                break

            plot = plots[idx]

            # Sincronización TDD con multiplicador de velocidad
            elapsed_tod = plot.time - first_tod
            if elapsed_tod < 0:
                elapsed_tod += SECONDS_PER_DAY

            # FASE 2: Aplicar velocidad y actualizar paquete actual
            self.paquete_actual = idx
            target_wall = wall_start + (elapsed_tod / self.velocidad) - wall_offset
            now = time.time()
            sleep_time = target_wall - now

            if sleep_time > 0.05:
                time.sleep(sleep_time * 0.8)
            elif sleep_time > 0.001:
                time.sleep(sleep_time)

            # Emitir progress_updated
            from datetime import datetime, timezone
            try:
                # Usar utcfromtimestamp para evitar desfases por timezone local (ya que ToD es en UTC)
                tiempo_str = datetime.utcfromtimestamp(plot.time).strftime('%H:%M:%S')
            except Exception:
                tiempo_str = time.strftime('%H:%M:%S', time.gmtime(plot.time))
            self.progress_updated.emit(idx, tiempo_str)

            # Acumular en buffer (NO emitir individual)
            try:
                if not self.filter_enabled or self._plot_passes_filter(plot):
                    self._plot_buffer.append(plot.to_dict())
            except Exception:
                pass

            # Emitir lote cada 100ms
            now = time.time()
            if now - self._last_batch_emit >= BATCH_INTERVAL:
                self._emit_batch()
                self._last_batch_emit = now

            # Emitir progreso al slider cada 250ms (thread-safe)
            if now - last_progress_emit >= 0.25:
                last_progress_emit = now
                self.playback_progress.emit(plot.time, self._duration)

            # Avanzar
            self._mutex.lock()
            self._play_index = idx + 1
            self._mutex.unlock()

        # Remanente
        self._emit_batch()
        self.playback_finished.emit()
        print("[AsterixWorker] Reproducción finalizada")

    # ================================================================
    # DECODIFICACIÓN
    # ================================================================

    def _get_oar_sensor(self, sac, sic, proy_cache):
        """Obtiene/crea proyección para un sensor."""
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
        """Convierte un registro decodificado a AsterixPlot."""
        try:
            cat = rec.get('category')
            if cat not in CATEGORIAS_SOPORTADAS:
                return None

            sac = rec.get('sac')
            sic = rec.get('sic')
            
            # FASE 3: BYPASS SAC/SIC PARA CAT 62
            if cat == 62:
                if sac is None: sac = 0
                if sic is None: sic = 0
                
            sac, sic, proy = self._get_oar_sensor(sac, sic, proy_cache)
            if (sac is None or sic is None) and cat != 62:
                print("DEBUG: Missing sac/sic")
                return None

            tod = rec.get('timestamp')
            if tod is None:
                # print("DEBUG: Missing tod") # too noisy? Let's see
                return None

            if rec.get('valid_position') is False and cat != 62:
                print("DEBUG: Invalid position")
                return None

            sensor_info = self.sensores.get((sac, sic), {})
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
            # FASE 1: I048/090 con bitmasking correcto
            # El decodificador nativo ahora extrae flight_level directamente con
            # separación de banderas V/G y máscara de 14 bits.
            # PRIORIDAD: usar flight_level si está disponible (CAMPO NUEVO con bitmasking).
            # FALLBACK: usar altitude_ft / 100.0 para compatibilidad hacia atrás.
            flight_level = rec.get('flight_level')
            if flight_level is None and altitude_ft is not None:
                flight_level = altitude_ft / 100.0
            mode_s = rec.get('mode_s')
            bds_data = rec.get('bds_data', {})
            track_angle = None
            ground_speed = None

            if cat in (21, 62) and rec.get('latitude') is not None and rec.get('longitude') is not None:
                lat = rec.get('latitude')
                lon = rec.get('longitude')
                extra = rec.get('extra_data', {})
                if extra:
                    track_angle = extra.get('track_angle')
                    # Fallback a Magnetic Heading (I021/152) si Track Angle (I021/160) no está
                    if track_angle is None:
                        track_angle = extra.get('magnetic_heading')
                    # CAT062: ground_speed_kts ya está en nudos directamente (desde I062/185)
                    gs_kts = extra.get('ground_speed_kts')
                    if gs_kts is not None:
                        ground_speed = gs_kts
                    # CAT021: ground_speed_nms necesita conversion
                    gs_nms = extra.get('ground_speed_nms')
                    if gs_nms is not None:
                        ground_speed = gs_nms * 3600.0

            elif cat in (48, 1, 34, 2):
                if sensor_lat is not None and sensor_lon is not None:
                    rho = rec.get('raw_range')
                    theta = rec.get('raw_azimuth')
                    if rho is not None and theta is not None:
                        dist_m = float(rho) * METERS_PER_NM
                        try:
                            lon_dest, lat_dest, _ = WGS84_GEOD.fwd(
                                sensor_lon, sensor_lat, float(theta), dist_m
                            )
                            lat, lon = lat_dest, lon_dest
                        except Exception:
                            pass
                # FASE 1: I048/200 Calculated Track Velocity con bitmasking V/G + 14 bits
                # PRIORIDAD 1: Datos del I048/200 extraídos con bitmasking correcto
                extra = rec.get('extra_data', {})
                if extra.get('ground_speed_nms') is not None:
                    ground_speed = extra['ground_speed_nms'] * 3600.0
                if extra.get('track_angle') is not None:
                    track_angle = extra['track_angle']
                # PRIORIDAD 2: BDS data (I048/250) como fallback
                if bds_data:
                    if track_angle is None:
                        track_angle = bds_data.get('mag_heading')
                    if ground_speed is None:
                        gs_kts = bds_data.get('ground_speed_bds')
                        if gs_kts is not None:
                            ground_speed = gs_kts

            if lat is None or lon is None:
                return None

            # ================================================================
            # FASE 1: ESTABILIZACIÓN DEL TRACK_ID (TARGET ADDRESS)
            # ================================================================
            # Para CAT 021 (ADS-B), los squitters llegan fragmentados.
            # Algunos paquetes tienen Target Address (I021/080), otros no.
            # Si usamos un ID inestable, cada paquete fragmentado crea un
            # "Squitter Huérfano" que se dibuja como target activo con
            # información incompleta, en lugar de consolidarse en una traza.
            #
            # REGLA DE ESTABILIZACIÓN:
            #   PRIMARY:   mode_s (Target Address I021/080) → CAT21_{mode_s}
            #   SECONDARY: track_number (I021/161)          → CAT21_TRK_{track_number}
            #   TERTIARY:  callsign                         → CAT21_CS_{callsign}
            #   LAST:      posición cuantizada              → CAT21_{sac}_{sic}_{qlat}_{qlon}
            # ================================================================
            plot_id = None
            track_number = rec.get('track_number')

            if cat in (48, 1, 62) and track_number is not None:
                plot_id = f"{sac}_{sic}_{track_number}"
            elif cat == 21:
                # CAT 021: Primary = Target Address (I021/080)
                if mode_s:
                    plot_id = f"CAT21_{mode_s}"
                # CAT 021: Secondary = Track Number (I021/161)
                elif track_number is not None:
                    plot_id = f"CAT21_TRK_{track_number}"
                # CAT 021: Tertiary = Callsign
                elif callsign and callsign.strip():
                    plot_id = f"CAT21_CS_{callsign.strip()}"
            
            # Último recurso para cualquier categoría
            if not plot_id:
                if mode_s:
                    plot_id = f"{sac}_{sic}_{mode_s}"
                elif track_number is not None:
                    plot_id = f"{sac}_{sic}_TRK{track_number}"
                elif callsign and callsign.strip():
                    plot_id = f"{sac}_{sic}_{callsign.strip()}"
                elif squawk != "----":
                    plot_id = f"{sac}_{sic}_{squawk}"
                else:
                    # ÚLTIMO RECURSO ABSOLUTO: cuantizar lat/lon para agrupar
                    # squitters sin ningún identificador
                    qlat = round(lat / QUANTIZE_LAT) * QUANTIZE_LAT
                    qlon = round(lon / QUANTIZE_LON) * QUANTIZE_LON
                    plot_id = f"CAT21_{sac}_{sic}_{qlat:.2f}_{qlon:.2f}"

            # Extraer track_number, raw_range, raw_azimuth
            track_number = rec.get('track_number')
            raw_range = rec.get('raw_range')
            raw_azimuth = rec.get('raw_azimuth')

            return AsterixPlot(
                id=plot_id, sac_sic=f"{sac}/{sic}", category=cat,
                time=float(tod), lat=lat, lon=lon,
                mode3a=squawk, callsign=callsign,
                flight_level=flight_level, altitude_ft=altitude_ft,
                is_track=is_track, bds_data=bds_data,
                mode_s=mode_s, track_angle=track_angle,
                ground_speed=ground_speed,
                track_number=track_number,
                raw_range=raw_range,
                raw_azimuth=raw_azimuth,
            )
        except Exception:
            return None

    # ================================================================
    # PROPIEDADES DE ACCESO (thread-safe)
    # ================================================================

    @property
    def total_frames(self) -> int:
        self._mutex.lock()
        n = len(self._plots)
        self._mutex.unlock()
        return n

    @property
    def play_position(self) -> int:
        self._mutex.lock()
        p = self._play_index
        self._mutex.unlock()
        return p

    @property
    def current_tod(self) -> float:
        self._mutex.lock()
        if self._plots and 0 <= self._play_index < len(self._plots):
            tod = self._plots[self._play_index].time
        else:
            tod = 0.0
        self._mutex.unlock()
        return tod

    @property
    def duration(self) -> float:
        return self._duration

    @property
    def scanned(self) -> bool:
        return self._scanned

    # ================================================================
    # EJECUCIÓN DEL QThread — TODO DENTRO DEL HILO WORKER
    # ================================================================

    def run(self):
        """
        Punto de entrada del hilo worker.
        Se bifurca entre modo PCAP (con escaneo y reproducción) y modo UDP (escucha en vivo).
        """
        print("[AsterixWorker] Iniciando hilo worker...")

        if self.pcap_file:
            # MODO PCAP: Escanear y luego reproducir
            print(f"[AsterixWorker] Modo PCAP: {self.pcap_file}")
            self.scan()
            if not self._plots or not self._running:
                print("[AsterixWorker] Sin datos para reproducir o detenido.")
            else:
                self._playback_loop()
        elif self.udp_ip is not None and self.udp_port is not None:
            # MODO UDP: Escuchar en un socket
            print(f"[AsterixWorker] Modo UDP: Escuchando en {self.udp_ip}:{self.udp_port}")
            self._udp_listen_loop()
        else:
            print("[AsterixWorker] Error: No se especificó fuente de datos (ni PCAP ni UDP).")

        print("[AsterixWorker] Hilo finalizado.")