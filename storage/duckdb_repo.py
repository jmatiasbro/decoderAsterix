import duckdb
import threading
import queue
import os
import time
import csv
import tempfile
from typing import Dict, List, Tuple, Any

class DuckDBRepository:
    """
    Repositorio de persistencia analítica (OLAP) basado en DuckDB.
    Infiere y guarda ploteos decodificados de manera asíncrona en segundo plano
    para evitar bloquear o degradar el rendimiento de la reproducción visual (60 FPS).
    """
    def __init__(self, db_path="pass_analytics.duckdb"):
        # Asegurar que el directorio de la BD exista
        os.makedirs(os.path.dirname(db_path) if os.path.dirname(db_path) else '.', exist_ok=True)
        self.db_path = db_path
        self.is_fallback = False
        
        try:
            self.conn = duckdb.connect(self.db_path)
        except Exception as e:
            pid = os.getpid()
            fallback_path = f"pass_analytics_fallback_{pid}.duckdb"
            print(f"[Storage Layer Warning] No se pudo abrir la BD principal '{db_path}' ({e}). Reintentando con fallback temporal '{fallback_path}'...")
            try:
                self.db_path = fallback_path
                self.conn = duckdb.connect(self.db_path)
                self.is_fallback = True
            except Exception as e2:
                print(f"[Storage Layer Warning] Fallback en disco falló ({e2}). Usando base de datos en memoria (:memory:)...")
                self.db_path = ":memory:"
                self.conn = duckdb.connect(self.db_path)
                self.is_fallback = True

        self._bytes_lookup = [f"\\x{i:02x}" for i in range(256)]
        self._inicializar_esquema()
        self._local = threading.local()
        
        self.cola_insercion = queue.Queue()
        self._running = True
        self.hilo_worker = threading.Thread(target=self._procesar_lotes, daemon=True)
        self.hilo_worker.start()

    def _inicializar_esquema(self):
        # Asegurar que la tabla esté limpia para evitar duplicaciones o contaminación entre diferentes PCAPs
        self.conn.execute('DROP TABLE IF EXISTS asterix_plots')
        self.conn.execute('''
            CREATE TABLE asterix_plots (
                timestamp DOUBLE,
                rx_time DOUBLE,
                category INTEGER,
                sac_sic VARCHAR,
                track_id VARCHAR,
                callsign VARCHAR,
                mode3a VARCHAR,
                lat DOUBLE,
                lon DOUBLE,
                flight_level VARCHAR,
                raw_azimuth DOUBLE,
                raw_range DOUBLE,
                track_number INTEGER,
                mode_s VARCHAR,
                altitude_ft DOUBLE,
                ground_speed DOUBLE,
                track_angle DOUBLE,
                vertical_rate DOUBLE,
                plot_id VARCHAR,
                raw_bytes BLOB,
                garbled BOOLEAN,
                frequency DOUBLE,
                pd DOUBLE
            )
        ''')

    def guardar_plot(self, plot_dict: Dict[str, Any]):
        """Punto de entrada no bloqueante para guardar un plot."""
        if self._running:
            self.cola_insercion.put(plot_dict)

    def flush(self):
        """Fuerza al hilo worker a escribir cualquier lote residual inmediatamente."""
        if self._running:
            self.cola_insercion.put("FLUSH")
            self.cola_insercion.join()

    def _stop_worker(self):
        self.log_repo("Stopping worker thread...")
        self._running = False
        self.cola_insercion.put(None)  # Enviar señal de parada
        if hasattr(self, "hilo_worker") and self.hilo_worker.is_alive():
            self.hilo_worker.join(timeout=3.0)
        self.log_repo("Worker thread stopped.")

    def _start_worker(self):
        self.log_repo("Starting worker thread...")
        self._running = True
        self.hilo_worker = threading.Thread(target=self._procesar_lotes, daemon=True)
        self.hilo_worker.start()
        self.log_repo("Worker thread started.")

    def log_repo(self, msg):
        import time
        import os
        try:
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            log_path = os.path.join(base_dir, "technical_import.log")
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(f"[{time.strftime('%H:%M:%S')}] [Repo] {msg}\n")
        except Exception:
            pass

    @property
    def thread_conn(self):
        """Retorna una conexión a DuckDB válida y exclusiva para el hilo actual."""
        import threading
        if threading.current_thread() == threading.main_thread():
            return self.conn

        t_name = threading.current_thread().name
        if not hasattr(self._local, "conn") or self._local.conn is None:
            self.log_repo(f"thread_conn requesting new connection for thread '{t_name}'")
            if self.db_path == ":memory:":
                self._local.conn = self.conn
            else:
                try:
                    self._local.conn = duckdb.connect(self.db_path)
                    self.log_repo(f"thread_conn connection created for thread '{t_name}'")
                except Exception as e:
                    self.log_repo(f"thread_conn failed to create connection for thread '{t_name}': {e}")
                    self._local.conn = self.conn
        return self._local.conn

    def recrear_tabla(self):
        self.log_repo("recrear_tabla() starting")
        self.flush()
        self._stop_worker()
        try:
            conn = self.thread_conn
            self.log_repo("recrear_tabla() got thread_conn")
            conn.execute("DROP TABLE IF EXISTS asterix_plots")
            self.log_repo("recrear_tabla() table dropped")
            conn.execute('''
                CREATE TABLE asterix_plots (
                    timestamp DOUBLE,
                    rx_time DOUBLE,
                    category INTEGER,
                    sac_sic VARCHAR,
                    track_id VARCHAR,
                    callsign VARCHAR,
                    mode3a VARCHAR,
                    lat DOUBLE,
                    lon DOUBLE,
                    flight_level VARCHAR,
                    raw_azimuth DOUBLE,
                    raw_range DOUBLE,
                    track_number INTEGER,
                    mode_s VARCHAR,
                    altitude_ft DOUBLE,
                    ground_speed DOUBLE,
                    track_angle DOUBLE,
                    vertical_rate DOUBLE,
                    plot_id VARCHAR,
                    raw_bytes BLOB,
                    garbled BOOLEAN,
                    frequency DOUBLE,
                    pd DOUBLE
                )
            ''')
            self.log_repo("recrear_tabla() table created successfully")
        finally:
            self._start_worker()

    def guardar_plots_bulk(self, plots_list: List[Dict[str, Any]]):
        self.log_repo(f"guardar_plots_bulk() starting with {len(plots_list)} plots")
        if not plots_list:
            return
        
        self.flush()  # Asegurar que no hay escrituras concurrentes pendientes
        self.log_repo("guardar_plots_bulk() flushed")
        
        self._stop_worker()
        
        # Generar un archivo CSV temporal
        fd, temp_csv_path = tempfile.mkstemp(suffix=".csv")
        os.close(fd)
        
        try:
            with open(temp_csv_path, 'w', newline='', encoding='utf-8') as f:
                w = csv.writer(f, lineterminator='\r\n')
                for plot in plots_list:
                    time_val = plot.get('time') or plot.get('timestamp') or 0.0
                    rx_val = plot.get('pcap_time') or 0.0
                    cat_val = plot.get('category') or 0
                    sac_sic_val = plot.get('sac_sic') or 'UNK'
                    
                    track_id = str(
                        plot.get('mode_s') or 
                        plot.get('target_address') or 
                        plot.get('mode_3a') or 
                        plot.get('mode3a') or 
                        plot.get('track_number') or 
                        ''
                    )
                    
                    callsign_val = (plot.get('callsign') or '').strip().upper()

                    m3a_raw = plot.get('mode3a')
                    if isinstance(m3a_raw, int):
                        mode3a_val = f"{m3a_raw:04o}"
                    else:
                        mode3a_val = str(m3a_raw).strip() if m3a_raw else ''

                    lat_val = plot.get('lat') or plot.get('lat_render') or 0.0
                    lon_val = plot.get('lon') or plot.get('lon_render') or 0.0

                    fl_val = plot.get('flight_level')
                    fl_str = '---' if fl_val is None else str(fl_val)

                    az_val = plot.get('raw_azimuth') or 0.0
                    rg_val = plot.get('raw_range') or 0.0

                    tn_raw = plot.get('track_number')
                    track_number_val = int(tn_raw) if tn_raw is not None else None
                    mode_s_val = str(plot.get('mode_s')) if plot.get('mode_s') else ''
                    alt_ft_val = plot.get('altitude_ft')
                    gs_val = plot.get('ground_speed')
                    ta_val = plot.get('track_angle')
                    vr_val = plot.get('vertical_rate_ftmin')
                    plot_id_val = str(plot.get('id') or '')
                    
                    rb = plot.get('raw_bytes')
                    if rb:
                        raw_bytes_val = "".join(self._bytes_lookup[b] for b in rb)
                    else:
                        raw_bytes_val = None
                    
                    garbled_val = bool(plot.get('garbled', False))
                    freq_raw = plot.get('frequency')
                    freq_val = float(freq_raw) if freq_raw is not None else None
                    pd_val = float(plot.get('pd', 100.0))

                    w.writerow([
                        float(time_val),
                        float(rx_val),
                        int(cat_val),
                        str(sac_sic_val),
                        track_id,
                        callsign_val,
                        mode3a_val,
                        float(lat_val),
                        float(lon_val),
                        fl_str,
                        float(az_val),
                        float(rg_val),
                        track_number_val,
                        mode_s_val,
                        None if alt_ft_val is None else float(alt_ft_val),
                        None if gs_val is None else float(gs_val),
                        None if ta_val is None else float(ta_val),
                        None if vr_val is None else float(vr_val),
                        plot_id_val,
                        raw_bytes_val,
                        garbled_val,
                        freq_val,
                        pd_val,
                    ])

            try:
                cursor = self.thread_conn.cursor()
                safe_path = temp_csv_path.replace('\\', '/')
                self.log_repo(f"Executing COPY from {safe_path}")
                cursor.execute(f"COPY asterix_plots FROM '{safe_path}' (DELIMITER ',', HEADER FALSE, NULL '', QUOTE '\"', ESCAPE '\"', AUTO_DETECT FALSE, PARALLEL FALSE, new_line '\\r\\n')")
                self.log_repo("Bulk insertion completed.")
            except Exception as e:
                self.log_repo(f"Error in bulk insert execution: {e}")
                raise e
        finally:
            if os.path.exists(temp_csv_path):
                try:
                    os.remove(temp_csv_path)
                except Exception as ex:
                    self.log_repo(f"Error removing temp CSV: {ex}")
            self._start_worker()

    def query(self, sql: str, *args) -> List[Tuple]:
        """Permite ejecutar consultas de análisis OLAP directamente en DuckDB."""
        try:
            cursor = self.conn.cursor()
            return cursor.execute(sql, *args).fetchall()
        except Exception as e:
            print(f"[Storage Layer] Error en consulta SQL: {e}")
            return []

    def close(self):
        """Detiene el hilo worker y cierra la conexión de DuckDB de forma limpia."""
        self._running = False
        self.cola_insercion.put(None)  # Enviar señal de parada
        if self.hilo_worker.is_alive():
            self.hilo_worker.join(timeout=2.0)
        try:
            self.conn.close()
        except Exception:
            pass
            
        # Eliminar archivo temporal si es fallback
        if getattr(self, 'is_fallback', False) and self.db_path != ":memory:":
            if os.path.exists(self.db_path):
                try:
                    # Esperar un instante para que el S.O. libere locks de archivo
                    time.sleep(0.1)
                    os.remove(self.db_path)
                    wal_path = f"{self.db_path}.wal"
                    if os.path.exists(wal_path):
                        os.remove(wal_path)
                    print(f"[Storage Layer] Archivo de fallback temporal '{self.db_path}' eliminado limpiamente.")
                except Exception as e:
                    print(f"[Storage Layer Warning] No se pudo eliminar el archivo temporal '{self.db_path}': {e}")

    def _procesar_lotes(self):
        # Crear una conexión dedicada para este hilo para asegurar aislamiento y evitar conflictos
        if self.db_path == ":memory:":
            hilo_conn = self.conn.cursor()
        else:
            try:
                hilo_conn = duckdb.connect(self.db_path)
            except Exception as e:
                print(f"[Storage Layer Warning] Hilo worker no pudo conectar a {self.db_path} ({e}). Usando cursor de la conexión principal.")
                hilo_conn = self.conn.cursor()
                
        lote = []
        while self._running or not self.cola_insercion.empty():
            try:
                plot = self.cola_insercion.get(timeout=0.05)
                if plot is None:
                    # Señal de parada
                    self.cola_insercion.task_done()
                    break

                if plot == "FLUSH":
                    if lote:
                        try:
                            hilo_conn.executemany(
                                "INSERT INTO asterix_plots VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                                lote
                            )
                            lote = []
                        except Exception as e:
                            print(f"[Storage Layer] Error al vaciar lote en flush: {e}")
                            lote = []
                    self.cola_insercion.task_done()
                    continue

                # Extraer robustamente campos tanto del diccionario bruto como de AsterixPlot.to_dict()
                time_val = plot.get('time') or plot.get('timestamp') or 0.0   # TX: ToD del mensaje (seg-del-día)
                rx_val = plot.get('pcap_time') or 0.0                          # RX: llegada del paquete (epoch)
                cat_val = plot.get('category') or 0
                sac_sic_val = plot.get('sac_sic') or 'UNK'
                
                track_id = str(
                    plot.get('mode_s') or 
                    plot.get('target_address') or 
                    plot.get('mode_3a') or 
                    plot.get('mode3a') or 
                    plot.get('track_number') or 
                    ''
                )
                
                callsign_val = (plot.get('callsign') or '').strip().upper()

                # Squawk / Mode 3-A: el plot lo trae como int octal (ej. 0o2375).
                m3a_raw = plot.get('mode3a')
                if isinstance(m3a_raw, int):
                    mode3a_val = f"{m3a_raw:04o}"
                else:
                    mode3a_val = str(m3a_raw).strip() if m3a_raw else ''

                lat_val = plot.get('lat') or plot.get('lat_render') or 0.0
                lon_val = plot.get('lon') or plot.get('lon_render') or 0.0

                fl_val = plot.get('flight_level')
                fl_str = '---' if fl_val is None else str(fl_val)

                az_val = plot.get('raw_azimuth') or 0.0
                rg_val = plot.get('raw_range') or 0.0

                # Campos específicos por categoría (se guardan crudos; None => NULL/blanco)
                tn_raw = plot.get('track_number')
                track_number_val = int(tn_raw) if tn_raw is not None else None
                mode_s_val = str(plot.get('mode_s')) if plot.get('mode_s') else ''
                alt_ft_val = plot.get('altitude_ft')
                gs_val = plot.get('ground_speed')
                ta_val = plot.get('track_angle')
                vr_val = plot.get('vertical_rate_ftmin')
                plot_id_val = str(plot.get('id') or '')
                rb = plot.get('raw_bytes')
                raw_bytes_val = bytes(rb) if rb else None
                
                garbled_val = bool(plot.get('garbled', False))
                freq_raw = plot.get('frequency')
                freq_val = float(freq_raw) if freq_raw is not None else None
                pd_val = float(plot.get('pd', 100.0))

                lote.append((
                    float(time_val),
                    float(rx_val),
                    int(cat_val),
                    str(sac_sic_val),
                    track_id,
                    callsign_val,
                    mode3a_val,
                    float(lat_val),
                    float(lon_val),
                    fl_str,
                    float(az_val),
                    float(rg_val),
                    track_number_val,
                    mode_s_val,
                    None if alt_ft_val is None else float(alt_ft_val),
                    None if gs_val is None else float(gs_val),
                    None if ta_val is None else float(ta_val),
                    None if vr_val is None else float(vr_val),
                    plot_id_val,
                    raw_bytes_val,
                    garbled_val,
                    freq_val,
                    pd_val,
                ))

                # Batch Insert de DuckDB
                if len(lote) >= 10000:
                    hilo_conn.executemany(
                        "INSERT INTO asterix_plots VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        lote
                    )
                    lote = []
                    
                self.cola_insercion.task_done()
            except queue.Empty:
                if lote:
                    try:
                        hilo_conn.executemany(
                            "INSERT INTO asterix_plots VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                            lote
                        )
                        lote = []
                    except Exception as e:
                        print(f"[Storage Layer] Error al vaciar lote residual: {e}")
                        lote = []
            except Exception as e:
                print(f"[Storage Layer] Error DuckDB en hilo worker: {e}")
                try:
                    self.cola_insercion.task_done()
                except ValueError:
                    pass
 
        # Vaciado final ante salida
        if lote:
            try:
                hilo_conn.executemany(
                    "INSERT INTO asterix_plots VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    lote
                )
            except Exception:
                pass
        try:
            if self.db_path != ":memory:":
                hilo_conn.close()
        except Exception:
            pass
