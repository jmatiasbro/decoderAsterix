import duckdb
import threading
import queue
import os
import time
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

        self._inicializar_esquema()
        
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
                category INTEGER,
                sac_sic VARCHAR,
                track_id VARCHAR,
                lat DOUBLE,
                lon DOUBLE,
                flight_level VARCHAR,
                raw_azimuth DOUBLE,
                raw_range DOUBLE
            )
        ''')

    def guardar_plot(self, plot_dict: Dict[str, Any]):
        """Punto de entrada no bloqueante para guardar un plot."""
        if self._running:
            self.cola_insercion.put(plot_dict)

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
                plot = self.cola_insercion.get(timeout=0.1)
                if plot is None:
                    # Señal de parada
                    self.cola_insercion.task_done()
                    break

                # Extraer robustamente campos tanto del diccionario bruto como de AsterixPlot.to_dict()
                time_val = plot.get('time') or plot.get('timestamp') or 0.0
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
                
                lat_val = plot.get('lat') or plot.get('lat_render') or 0.0
                lon_val = plot.get('lon') or plot.get('lon_render') or 0.0
                
                fl_val = plot.get('flight_level')
                fl_str = '---' if fl_val is None else str(fl_val)
                
                az_val = plot.get('raw_azimuth') or 0.0
                rg_val = plot.get('raw_range') or 0.0

                lote.append((
                    float(time_val),
                    int(cat_val),
                    str(sac_sic_val),
                    track_id,
                    float(lat_val),
                    float(lon_val),
                    fl_str,
                    float(az_val),
                    float(rg_val)
                ))

                # Batch Insert de DuckDB
                if len(lote) >= 200 or self.cola_insercion.empty():
                    hilo_conn.executemany(
                        "INSERT INTO asterix_plots VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        lote
                    )
                    lote = []
                    
                self.cola_insercion.task_done()
            except queue.Empty:
                if lote:
                    try:
                        hilo_conn.executemany(
                            "INSERT INTO asterix_plots VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
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
                    "INSERT INTO asterix_plots VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    lote
                )
            except Exception:
                pass
        try:
            if self.db_path != ":memory:":
                hilo_conn.close()
        except Exception:
            pass
