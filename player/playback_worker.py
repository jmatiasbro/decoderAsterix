import time
import socket
from typing import List, Dict, Optional, Set
from PyQt6.QtCore import QThread, pyqtSignal, QMutex

from decoder.data_engine import DataEngine, AsterixPlot

class PlaybackWorker(QThread):
    """
    Worker basado en QThread exclusivo para la reproducción y sincronización de UI.
    Toda la lógica pesada de decodificación PCAP reside en DataEngine (agnóstico a Qt).
    """
    
    # Señales UI
    progress_updated = pyqtSignal(int, int)          # (actual, total)
    new_plot_batch = pyqtSignal(list)                # Batch de diccionarios de plots
    playback_finished = pyqtSignal()
    tod_updated = pyqtSignal(float)                  # Tiempo de simulación actual
    duration_updated = pyqtSignal(float)             # Duración total calculada
    error_occurred = pyqtSignal(str)
    
    sensor_detected = pyqtSignal(int, int)           # sac, sic
    north_mark_detected = pyqtSignal(int, int)       # sac, sic
    rotation_speed_detected = pyqtSignal(int, int, float) # sac, sic, rpm
    scan_complete = pyqtSignal(bool)

    def __init__(
        self,
        pcap_file: str = None,
        udp_ip: str = None,
        udp_port: int = None,
        pcap_record_file: str = None,
        sensores: Dict = None,
        playback_speed: float = 1.0,
        batch_size: int = 50,
        cache_dir: str = None,
        profile_config: Dict = None
    ):
        super().__init__()
        
        # Referencias de configuración
        self.pcap_file = pcap_file
        self.udp_ip = udp_ip
        self.udp_port = udp_port
        # Normalizar a lista de puertos (soporta int único o lista para multi-sensor)
        if udp_port is None:
            self.udp_ports = []
        elif isinstance(udp_port, (list, tuple, set)):
            self.udp_ports = [int(p) for p in udp_port]
        else:
            self.udp_ports = [int(udp_port)]
        self.pcap_record_file = pcap_record_file
        self.sensores = sensores or {}

        # Motor de decodificación sin Qt
        self.engine = DataEngine(sensores=self.sensores, cache_dir=cache_dir, profile_config=profile_config)
        
        # Conectar callbacks del engine a las señales Qt
        self.engine.on_progress = self.progress_updated.emit
        self.engine.on_sensor_detected = self.sensor_detected.emit
        self.engine.on_north_mark_detected = self.north_mark_detected.emit
        self.engine.on_rotation_speed_detected = self.rotation_speed_detected.emit
        
        # Control de reproducción
        self.playback_speed = playback_speed
        self.batch_size = batch_size
        self._running = True
        self._paused = False
        self._mutex = QMutex()
        
        # Estado
        self._plots: List[AsterixPlot] = []
        self._play_index = 0
        self._duration = 0.0
        self._scanned = False
        self._udp_socket = None
        self._udp_sockets = []

    def stop(self):
        self._mutex.lock()
        self._running = False
        self.engine.stop()
        try:
            self.engine.close()
        except Exception:
            pass
        for s in ([self._udp_socket] if self._udp_socket else []) + list(self._udp_sockets):
            try:
                # Cerrar inmediatamente los sockets para desbloquear la espera de recepción
                s.close()
            except Exception:
                pass
        self._mutex.unlock()
        self.wait()

    def set_paused(self, paused: bool):
        self._mutex.lock()
        self._paused = paused
        self._mutex.unlock()

    def set_speed(self, speed: float):
        self._mutex.lock()
        self.playback_speed = speed
        self._mutex.unlock()

    def seek_to_percent(self, percent: float):
        self._mutex.lock()
        if self._plots:
            self._play_index = int(len(self._plots) * (percent / 100.0))
            self._play_index = max(0, min(len(self._plots) - 1, self._play_index))
            # Resync tiempo UI
            self.tod_updated.emit(self._plots[self._play_index].time)
        self._mutex.unlock()

    def seek_to_time(self, t: float):
        """Reposiciona el playback al primer plot con time >= t (los plots están
        ordenados temporalmente). Usado por el analizador de paquetes para
        'teletransportar' la pantalla táctica al instante de una fila."""
        self._mutex.lock()
        if self._plots:
            idx = len(self._plots) - 1
            for i, p in enumerate(self._plots):
                if p.time >= t:
                    idx = i
                    break
            self._play_index = max(0, min(len(self._plots) - 1, idx))
            self.tod_updated.emit(self._plots[self._play_index].time)
        self._mutex.unlock()

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

    def scan(self):
        """Envuelve la llamada al DataEngine.scan_pcap y notifica a Qt."""
        if not self.pcap_file:
            return
            
        try:
            plots, duration, sensores_vistos = self.engine.scan_pcap(self.pcap_file)
            
            self._mutex.lock()
            self._plots = plots
            self._duration = duration
            self._scanned = True
            self._mutex.unlock()
            
            if duration > 0:
                self.duration_updated.emit(duration)
            
            self.scan_complete.emit(bool(plots))
            
        except Exception as e:
            self.error_occurred.emit(f"Error en escaneo PCAP: {str(e)}")
            self.scan_complete.emit(False)

    def run(self):
        if self.pcap_file:
            if not self._scanned:
                self.scan()
            else:
                self._playback_loop()
        elif self.udp_ip is not None and self.udp_ports:
            self._udp_live_loop()

    def _udp_live_loop(self):
        import dpkt
        import socket as pysocket
        import select as pyselect
        import time as pytime

        # 1. Configurar sockets UDP (uno por puerto para soporte multi-sensor)
        self._mutex.lock()
        ip = self.udp_ip
        ports = list(self.udp_ports)
        pcap_record = getattr(self, 'pcap_record_file', None)
        self._mutex.unlock()

        socks = []
        sock_port = {}
        for p in ports:
            s = pysocket.socket(pysocket.AF_INET, pysocket.SOCK_DGRAM)
            s.setsockopt(pysocket.SOL_SOCKET, pysocket.SO_REUSEADDR, 1)
            try:
                s.bind((ip, p))
                s.setblocking(False)
                socks.append(s)
                sock_port[s.fileno()] = p
            except Exception as e:
                msg = f"Error en socket {ip}:{p} - {str(e)}"
                print(f"[UDP Live] {msg}")
                self.error_occurred.emit(msg)
                for so in socks:
                    try: so.close()
                    except Exception: pass
                return

        self._udp_sockets = socks
        print(f"[UDP Live] Escuchando en {ip}:{','.join(str(p) for p in ports)}")

        # 2. Configurar escritor PCAP si se habilitó grabación
        pcap_writer = None
        pcap_f = None
        if pcap_record:
            try:
                pcap_f = open(pcap_record, 'wb')
                pcap_writer = dpkt.pcap.Writer(pcap_f)
                print(f"[UDP Live] Grabando tráfico PCAP en {pcap_record}")
            except Exception as e:
                msg = f"Error creando archivo de grabación PCAP: {str(e)}"
                print(f"[UDP Live] {msg}")
                self.error_occurred.emit(msg)

        proy_cache = {}
        batch = []
        last_emit = pytime.time()

        while True:
            self._mutex.lock()
            running = self._running
            self._mutex.unlock()

            if not running:
                break

            # Esperar datos en cualquiera de los sockets (multi-puerto)
            try:
                ready, _, _ = pyselect.select(socks, [], [], 0.2)
            except Exception:
                # Algún socket se cerró o se detuvo el hilo
                break

            if not ready:
                if batch:
                    self.new_plot_batch.emit(batch)
                    batch = []
                continue

            # Drenar cada socket listo
            packets = []  # (data, addr, dst_port)
            for s in ready:
                dst_port = sock_port.get(s.fileno())
                while True:
                    try:
                        data, addr = s.recvfrom(65535)
                    except (BlockingIOError, pysocket.error):
                        break
                    if not data:
                        break
                    packets.append((data, addr, dst_port))

            for data, addr, port in packets:
                if not data:
                    continue

                # 3. Serializar y guardar en PCAP
                if pcap_writer:
                    try:
                        try:
                            src_ip = pysocket.inet_aton(addr[0])
                        except Exception:
                            src_ip = pysocket.inet_aton("127.0.0.1")

                        try:
                            dst_ip = pysocket.inet_aton(ip)
                        except Exception:
                            dst_ip = pysocket.inet_aton("127.0.0.1")

                        udp_pkt = dpkt.udp.UDP(
                            sport=addr[1],
                            dport=port,
                            data=data
                        )
                        udp_pkt.ulen = len(udp_pkt)

                        ip_pkt = dpkt.ip.IP(
                            src=src_ip,
                            dst=dst_ip,
                            p=dpkt.ip.IP_PROTO_UDP,
                            data=udp_pkt
                        )
                        ip_pkt.len = len(ip_pkt)

                        eth_pkt = dpkt.ethernet.Ethernet(
                            src=b'\x00\x00\x00\x00\x00\x00',
                            dst=b'\x00\x00\x00\x00\x00\x00',
                            type=dpkt.ethernet.ETH_TYPE_IP,
                            data=ip_pkt
                        )

                        pcap_writer.writepkt(eth_pkt.pack(), pytime.time())
                    except Exception as e:
                        print(f"[UDP Live] Error escribiendo al PCAP: {e}")

                # 4. Decodificar ASTERIX y emitir plots
                try:
                    records = self.engine.router.procesar_paquete_udp(data)
                    if records:
                        for rec in records:
                            cat = rec.get('category')
                            if cat in (2, 34):
                                sac, sic = rec.get('sac'), rec.get('sic')
                                extra = rec.get('extra_data', {})
                                if sac is not None and sic is not None:
                                    if extra.get('is_north_mark'):
                                        self.north_mark_detected.emit(sac, sic)
                                    if 'antenna_rpm' in extra:
                                        self.rotation_speed_detected.emit(sac, sic, extra['antenna_rpm'])

                            plot = self.engine._record_to_plot(rec, proy_cache)
                            if plot is None:
                                continue

                            # Notificar sensor detectado para registro dinámico
                            try:
                                parts = plot.sac_sic.split('/')
                                sac, sic = int(parts[0]), int(parts[1])
                                self.sensor_detected.emit(sac, sic)
                            except Exception:
                                pass

                            # Usamos la hora actual para presentación en línea
                            plot_dict = plot.to_dict()
                            plot_dict['time'] = pytime.time()
                            batch.append(plot_dict)

                            # Acumular plots en memoria con límite de seguridad de 150,000 para habilitar el Análisis PASS en vivo
                            self._mutex.lock()
                            self._plots.append(plot)
                            if len(self._plots) > 150000:
                                self._plots.pop(0)
                            if len(self._plots) > 1:
                                self._duration = self._plots[-1].time - self._plots[0].time
                            self._mutex.unlock()
                except Exception as e:
                    print(f"[UDP Live] Error procesando paquete ASTERIX: {e}")

            now = pytime.time()
            if batch and (now - last_emit >= 0.05 or len(batch) >= self.batch_size):
                self.new_plot_batch.emit(batch)
                batch = []
                last_emit = now

        if batch:
            self.new_plot_batch.emit(batch)

        # 5. Limpieza de recursos
        for s in socks:
            try:
                s.close()
            except Exception:
                pass

        if pcap_f:
            try:
                pcap_f.flush()
                pcap_f.close()
                print(f"[UDP Live] Captura guardada en {pcap_record}")
            except Exception as e:
                print(f"[UDP Live] Error cerrando PCAP: {e}")

        self.playback_finished.emit()

    def _playback_loop(self):
        total_plots = len(self._plots)
        last_wall_time = time.time()
        
        self._mutex.lock()
        if total_plots > 0 and self._play_index < total_plots:
            last_sim_time = self._plots[self._play_index].time
        else:
            last_sim_time = 0.0
        self._mutex.unlock()

        batch = []
        last_emit_time = time.time()
        emit_interval = 0.05

        while True:
            self._mutex.lock()
            running = self._running
            paused = self._paused
            speed = self.playback_speed
            idx = self._play_index
            self._mutex.unlock()

            if not running: break
            
            if idx >= total_plots:
                break
            
            if paused:
                if batch:
                    self.new_plot_batch.emit(batch)
                    batch = []
                time.sleep(0.1)
                last_wall_time = time.time()
                # Re-sincronizar el tiempo de simulación para evitar saltos al reanudar o cambiar de posición
                self._mutex.lock()
                if total_plots > 0 and 0 <= self._play_index < total_plots:
                    last_sim_time = self._plots[self._play_index].time
                self._mutex.unlock()
                continue

            self._mutex.lock()
            plot = self._plots[idx]
            sim_time = plot.time
            self._mutex.unlock()

            sim_delta = sim_time - last_sim_time
            if sim_delta < 0: sim_delta = 0

            wall_delta = time.time() - last_wall_time
            expected_wall_delta = sim_delta / max(0.01, speed)

            if expected_wall_delta > wall_delta:
                # Emitir tiempo interpolado para que el reloj avance suavemente durante el gap
                interp_time = last_sim_time + wall_delta * speed
                self.tod_updated.emit(interp_time)
                sleep_time = min(0.1, expected_wall_delta - wall_delta)
                time.sleep(sleep_time)
                continue

            # Avanzamos un plot
            batch.append(plot.to_dict())
            self._mutex.lock()
            self._play_index += 1
            idx = self._play_index
            self._mutex.unlock()

            if time.time() - last_emit_time >= emit_interval or len(batch) >= self.batch_size:
                self.new_plot_batch.emit(batch)
                batch = []
                self.progress_updated.emit(idx, total_plots)
                self.tod_updated.emit(sim_time)
                last_emit_time = time.time()

            last_sim_time = sim_time
            last_wall_time = time.time()

        if batch:
            self.new_plot_batch.emit(batch)
            self.progress_updated.emit(idx, total_plots)

        self.playback_finished.emit()
