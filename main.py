#!/usr/bin/env python3
"""
ASTERIX Air Traffic Surveillance Data Analyzer

Herramienta completa para procesar, decodificar y analizar datos ASTERIX
generando mapas de cobertura geoespaciales.

Uso:
    python main.py <archivo.pcap|archivo.ast> [opciones]
    python main.py --interactive
"""

import sys
import os
import io
import queue
import re
import threading
import json
import time
from pathlib import Path
import math
import numpy as np
import argparse
from typing import List, Tuple, Optional, Dict

# Parche para corregir _tkinter.TclError: Can't find a usable init.tcl en Windows
def _fix_tcl_tk_environment():
    if sys.platform == 'win32':
        # Buscar en el prefijo base de Python (fuera del venv)
        base_path = getattr(sys, 'base_prefix', sys.prefix)
        tcl_dir = os.path.join(base_path, 'tcl')
        
        if os.path.exists(tcl_dir):
            # Intentar encontrar carpetas como tcl8.6 y tk8.6
            try:
                tcl_ver = [d for d in os.listdir(tcl_dir) if d.startswith('tcl8') and os.path.isdir(os.path.join(tcl_dir, d))]
                tk_ver = [d for d in os.listdir(tcl_dir) if d.startswith('tk8') and os.path.isdir(os.path.join(tcl_dir, d))]
                
                if tcl_ver:
                    os.environ['TCL_LIBRARY'] = os.path.join(tcl_dir, tcl_ver[0])
                if tk_ver:
                    os.environ['TK_LIBRARY'] = os.path.join(tcl_dir, tk_ver[0])
            except Exception:
                pass

_fix_tcl_tk_environment()

import tkinter as tk
from tkinter import ttk, messagebox, filedialog, scrolledtext, simpledialog

# Backend de Matplotlib para Tkinter
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
import matplotlib.pyplot as plt

# Forzar UTF-8 para evitar errores de codificación en terminales de Windows
if sys.stdout and hasattr(sys.stdout, 'encoding') and sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
if sys.stderr and hasattr(sys.stderr, 'encoding') and sys.stderr.encoding.lower() != 'utf-8':
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')


# --- Funciones de Utilidad de Tiempo ---
def seconds_to_hms(seconds: Optional[float]) -> str:
    if seconds is None: return "00:00:00"
    h = int(seconds // 3600) % 24
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    return f"{h:02d}:{m:02d}:{s:02d}"

def hms_to_seconds(hms_str: str) -> float:
    try:
        parts = hms_str.split(':')
        h = float(parts[0])
        m = float(parts[1]) if len(parts) > 1 else 0
        s = float(parts[2]) if len(parts) > 2 else 0
        return h * 3600 + m * 60 + s
    except: return 0.0

# Importar módulos locales
from decoders import AsterixRecord, decode_asterix_stream, find_sensors_in_stream, filter_asterix_stream_by_sensor
from geo_tools import SensorRegistry, TargetProcessor, GeoTools, TrackManager
from exporters import KMLExporter, GeoJSONExporter, CSVExporter, ReportGenerator, PDFReportGenerator
from config import input_sensor_interactive, input_coordinate_interactive, dms_to_string, display_sensors_in_data, get_sensor_position, KNOWN_SENSORS, add_sensor
from radar_selector import RadarSelector
from mode_analyzer import ModeAnalyzer
from flight_loss_analyzer import FlightLossAnalyzer
from atm_analytics import ATMAnalyticsEngine, PlaybackEngine

class PacketViewerFilterDialog(simpledialog.Dialog):
    def __init__(self, parent, title, available_categories):
        self.available_categories = available_categories
        self.result = None
        super().__init__(parent, title)

    def body(self, master):
        master.configure(padx=10, pady=10)
        
        # Time range
        ttk.Label(master, text="Hora de inicio (HH:MM:SS):").grid(row=0, column=0, sticky=tk.W, pady=2)
        self.start_ent = ttk.Entry(master)
        self.start_ent.grid(row=0, column=1, padx=5, pady=2)
        self.start_ent.insert(0, "00:00:00")

        ttk.Label(master, text="Hora de fin (HH:MM:SS):").grid(row=1, column=0, sticky=tk.W, pady=2)
        self.end_ent = ttk.Entry(master)
        self.end_ent.grid(row=1, column=1, padx=5, pady=2)
        self.end_ent.insert(0, "23:59:59")

        # Category selection
        ttk.Label(master, text="Categoría ASTERIX:").grid(row=2, column=0, sticky=tk.W, pady=2)
        self.cat_var = tk.StringVar(value="Todas")
        cat_choices = ["Todas"] + [f"CAT{c:03d}" for c in self.available_categories]
        self.cat_combo = ttk.Combobox(master, textvariable=self.cat_var, values=cat_choices, state='readonly')
        self.cat_combo.grid(row=2, column=1, padx=5, pady=2, sticky="ew")

        return self.start_ent

    def validate(self):
        time_pattern = r"^([01]?\d|2[0-3]):([0-5]?\d):([0-5]?\d)$"
        start_str = self.start_ent.get().strip()
        end_str = self.end_ent.get().strip()

        if not re.match(time_pattern, start_str):
            messagebox.showwarning("Formato Inválido", f"La hora de inicio '{start_str}' no es válida.\nUse el formato HH:MM:SS", parent=self)
            return False
        if not re.match(time_pattern, end_str):
            messagebox.showwarning("Formato Inválido", f"La hora de fin '{end_str}' no es válida.\nUse el formato HH:MM:SS", parent=self)
            return False
        if hms_to_seconds(start_str) > hms_to_seconds(end_str):
            messagebox.showwarning("Rango Inválido", "La hora de inicio no puede ser posterior a la hora de fin.", parent=self)
            return False
        return True

    def apply(self):
        selected_cat_str = self.cat_var.get()
        selected_cat = int(selected_cat_str.replace("CAT", "")) if selected_cat_str != "Todas" else None
        self.result = {"t_start": hms_to_seconds(self.start_ent.get()), "t_end": hms_to_seconds(self.end_ent.get()), "category": selected_cat}

class FilterDialog(simpledialog.Dialog):
    def __init__(self, parent, metadata):
        self.metadata = metadata
        self.result = None
        super().__init__(parent, title="Filtros de Decodificación")

    def body(self, master):
        master.configure(padx=10, pady=10)
        ttk.Label(master, text="Seleccione los criterios de filtrado:", font=("Arial", 10, "bold")).pack(pady=5)
        
        self.all_var = tk.BooleanVar(value=True)
        self.chk_all = ttk.Checkbutton(master, text="Procesar todos los registros (sin filtros)", 
                                      variable=self.all_var, command=self._toggle_fields)
        self.chk_all.pack(anchor=tk.W, pady=5)

        self.fields_frame = ttk.LabelFrame(master, text="Filtros Globales", padding=10)
        self.fields_frame.pack(fill=tk.X, pady=5)

        # Rango de tiempo detectado en los metadatos
        t_min = min((m['t_min'] for m in self.metadata.values()), default=0)
        t_max = max((m['t_max'] for m in self.metadata.values()), default=86400)

        ttk.Label(self.fields_frame, text="Hora Inicio (HH:MM:SS):").grid(row=0, column=0, sticky=tk.W, pady=2)
        self.start_ent = ttk.Entry(self.fields_frame)
        self.start_ent.grid(row=0, column=1, padx=5, pady=2)
        self.start_ent.insert(0, seconds_to_hms(t_min))

        ttk.Label(self.fields_frame, text="Hora Fin (HH:MM:SS):").grid(row=1, column=0, sticky=tk.W, pady=2)
        self.end_ent = ttk.Entry(self.fields_frame)
        self.end_ent.grid(row=1, column=1, padx=5, pady=2)
        self.end_ent.insert(0, seconds_to_hms(t_max))

        self._toggle_fields()
        return self.start_ent

    def _toggle_fields(self):
        state = tk.DISABLED if self.all_var.get() else tk.NORMAL
        for child in self.fields_frame.winfo_children():
            try: child.configure(state=state)
            except: pass

    def validate(self):
        """Valida que los formatos de hora sean correctos antes de cerrar el diálogo."""
        if self.all_var.get():
            return True

        # Expresión regular para formato HH:MM:SS (00-23:00-59:00-59)
        time_pattern = r"^([01]?\d|2[0-3]):([0-5]?\d):([0-5]?\d)$"
        
        start_str = self.start_ent.get().strip()
        end_str = self.end_ent.get().strip()

        if not re.match(time_pattern, start_str):
            messagebox.showwarning("Formato Inválido", f"La hora de inicio '{start_str}' no es válida.\nUse el formato HH:MM:SS")
            return False
        if not re.match(time_pattern, end_str):
            messagebox.showwarning("Formato Inválido", f"La hora de fin '{end_str}' no es válida.\nUse el formato HH:MM:SS")
            return False
        if hms_to_seconds(start_str) > hms_to_seconds(end_str):
            messagebox.showwarning("Rango Inválido", "La hora de inicio no puede ser posterior a la hora de fin.")
            return False
        return True

    def apply(self):
        if self.all_var.get():
            self.result = "all"
        else:
            # Generar filtros para cada categoría basada en la entrada del usuario
            t_start = hms_to_seconds(self.start_ent.get())
            t_end = hms_to_seconds(self.end_ent.get())
            
            res = {}
            for cat in self.metadata:
                res[cat] = {
                    't_min': t_start, 't_max': t_end,
                    'fl_min': 0, 'fl_max': 600,
                    'squawks': [], 'track_numbers': [], 'addresses': [], 'callsigns': []
                }
            self.result = res

try:
    import dpkt
except ImportError:
    print("Error: dpkt no está instalado. Ejecutar: pip install dpkt")
    sys.exit(1)


def print_progress_bar(iteration, total, prefix='', suffix='', decimals=1, length=50, fill='█', file=sys.stdout):
    """
    Llama a esta función en un bucle para crear una barra de progreso en la terminal.
    @params:
        iteration   - Requerido : iteración actual (Int)
        total       - Requerido : total de iteraciones (Int)
        prefix      - Opcional  : texto de prefijo (Str)
        suffix      - Opcional  : texto de sufijo (Str)
        decimals    - Opcional  : número de decimales en el porcentaje (Int)
        length      - Opcional  : longitud de la barra (Int)
        fill        - Opcional  : carácter de relleno de la barra (Str)
        file        - Opcional  : stream de salida (default: sys.stdout)
    """
    if total == 0:
        percent = "100.0"
        filled_length = length
    else:
        percent = ("{0:." + str(decimals) + "f}").format(100 * (iteration / float(total)))
        filled_length = int(length * iteration // total)

    bar = fill * filled_length + '-' * (length - filled_length)
    print(f'\r{prefix} |{bar}| {percent}% {suffix}', end='\r', file=file)
    if iteration >= total:
        print(file=file)

class WorkerThread(threading.Thread):
    """
    Hilo de trabajo genérico para ejecutar tareas pesadas sin bloquear la GUI.
    """
    def __init__(self, task_name: str, func, result_queue: queue.Queue, *args, **kwargs):
        super().__init__()
        self.task_name = task_name
        self.func = func
        self.result_queue = result_queue
        self.args = args
        self.kwargs = kwargs
        self.daemon = True

    def run(self):
        """Ejecuta la función y pone el resultado en la cola."""
        try:
            result = self.func(*self.args, **self.kwargs)
            self.result_queue.put((f'{self.task_name}_success', result))
        except Exception as e:
            self.result_queue.put(('error', e))


class AsterixAnalyzer:
    """Analizador principal de datos ASTERIX."""
    
    def __init__(self):
        self.sensor_registry = SensorRegistry()
        self.target_processor = TargetProcessor(self.sensor_registry)
        self.records = []
        self.original_records: List[AsterixRecord] = []
        self.decoded_records = []  # Registros decodificados en formato dict para análisis de sensores
        self.selected_sensors: Optional[set] = None
        self.current_file_path: Optional[str] = None # Para rastrear el archivo actualmente cargado
        self.asterix_data: bytes = b''
        self.filtered_asterix_data: Optional[bytes] = None
        self.metadata: Dict = {}
        self.last_directory: str = os.getcwd()

    def load_pcap(self, file_path: str, gui_progress_callback: Optional[callable] = None) -> bytes:
        """Extrae datos ASTERIX de un archivo PCAP."""
        print(f"\n[*] Leyendo archivo PCAP: {file_path}")
        
        try:
            file_size = os.path.getsize(file_path)
            with open(file_path, 'rb') as f:
                pcap = dpkt.pcap.Reader(f)
                asterix_data = bytearray()
                packet_count = 0
                last_update_time = time.time() # Para controlar la frecuencia de las actualizaciones

                if gui_progress_callback:
                    gui_progress_callback(0, file_size, prefix='Cargando PCAP:', suffix='Completado')
                else:
                    print_progress_bar(0, file_size, prefix='Cargando:', suffix='Completado', length=50)

                for timestamp, buf in pcap:
                    packet_count += 1
                    try:
                        eth = dpkt.ethernet.Ethernet(buf)
                        if isinstance(eth.data, dpkt.ip.IP):
                            ip = eth.data
                            if isinstance(ip.data, (dpkt.udp.UDP, dpkt.tcp.TCP)):
                                asterix_data.extend(ip.data.data)
                    except Exception:
                        pass
                    
                    # Control de frecuencia: Actualizar la barra de progreso solo cada 100ms
                    now = time.time()
                    if now - last_update_time > 0.1:
                        current_pos = f.tell()
                        if gui_progress_callback:
                            gui_progress_callback(current_pos, file_size, prefix='Cargando PCAP:', suffix='Completado')
                        else:
                            print_progress_bar(current_pos, file_size, prefix='Cargando:', suffix='Completado', length=50)
                        last_update_time = now

                if gui_progress_callback:
                    gui_progress_callback(file_size, file_size, prefix='Cargando PCAP:', suffix='Completado')

            print(f"[✓] Extraídos {len(asterix_data)} bytes de {packet_count} paquetes")
            return bytes(asterix_data)
        
        except FileNotFoundError:
            print(f"[✗] Archivo no encontrado: {file_path}")
            return b''
        except Exception as e:
            print(f"[✗] Error leyendo PCAP: {e}")
            return b''
    
    def reset(self):
        """Resetea el estado del analizador descartando los datos en memoria."""
        self.records = []
        self.decoded_records = []
        self.original_records = []
        self.selected_sensors = None
        self.asterix_data = b''
        self.current_file_path = None
        self.filtered_asterix_data = None
        self.metadata = {}
        self.sensor_registry = SensorRegistry()
        self.target_processor = TargetProcessor(self.sensor_registry)

    def load_ast(self, file_path: str) -> bytes:
        """Carga datos de un archivo AST."""
        print(f"\n[*] Leyendo archivo AST: {file_path}")
        
        try:
            with open(file_path, 'rb') as f:
                data = f.read()
            
            print(f"[✓] Cargados {len(data)} bytes")
            return data
        
        except FileNotFoundError:
            print(f"[✗] Archivo no encontrado: {file_path}")
            return b''
        except Exception as e:
            print(f"[✗] Error leyendo AST: {e}")
            return b''

    def filter_data_for_selection(self):
        """
        Filtra los datos ASTERIX crudos para mantener solo los registros de los sensores seleccionados.
        Esto optimiza la memoria y la velocidad de decodificación.
        """
        if not self.asterix_data:
            return

        if not self.selected_sensors:
            self.filtered_asterix_data = None # Usar datos completos
            return

        print("\n[*] Optimizando datos para la selección (puede tardar)...")

        def progress_hook(pos, total):
            print_progress_bar(pos, total, prefix='Filtrando:', suffix='Completado', length=50)

        original_size = len(self.asterix_data)
        self.filtered_asterix_data = filter_asterix_stream_by_sensor(
            self.asterix_data,
            self.selected_sensors,
            progress_hook=progress_hook
        )
        new_size = len(self.filtered_asterix_data)
        reduction = 100 * (1 - new_size / original_size) if original_size > 0 else 0
        
        print(f"[✓] Datos filtrados. Tamaño reducido de {original_size/1024/1024:.2f} MB a {new_size/1024/1024:.2f} MB ({reduction:.1f}% de reducción).")
    
    def decode_data(self, gui_progress_callback: Optional[callable] = None):
        """Decodifica el flujo de datos ASTERIX (filtrado o completo)."""
        data_to_decode = self.filtered_asterix_data if self.filtered_asterix_data is not None else self.asterix_data
        
        print(f"\n[*] Decodificando {len(data_to_decode)} bytes de datos ASTERIX...")

        def progress_hook(pos, total):
            print_progress_bar(pos, total, prefix='Decodificando:', suffix='Completado', length=50)

        decoded_records = decode_asterix_stream(data_to_decode, progress_hook=progress_hook, gui_progress_callback=gui_progress_callback)
        print(f"[✓] {len(decoded_records)} registros decodificados.")

        # Limpiar registros anteriores
        self.records = []
        self.decoded_records = []
        
        grouped_by_squawk = {}
        
        # Registrar sensores y procesar coordenadas
        for record in decoded_records:
            # Almacenar registro decodificado para análisis de sensores
            record_dict = {
                'category': record.category,
                'sac': record.sac,
                'sic': record.sic,
                'latitude': getattr(record, 'latitude', None),
                'latitude_hr': getattr(record, 'latitude_hr', None), # Soporte para Alta Res
                'longitude': getattr(record, 'longitude', None),
                'altitude': getattr(record, 'altitude', None),
                'mode_3a': getattr(record, 'mode_3a', None),
                'mode_s': getattr(record, 'target_address', None),
                'callsign': getattr(record, 'target_id', None),
                'track_number': getattr(record, 'track_number', None),
                'timestamp': getattr(record, 'timestamp', None),
                'flight_level': getattr(record, 'flight_level', None),
                'extra_data': getattr(record, 'extra_data', {})
            }
            self.decoded_records.append(record_dict)
            
            # Intentar obtener posición del radar si no la tenemos (ej. CAT048 no trae Lat/Lon)
            lat = record.latitude
            lon = record.longitude
            alt = record.altitude
            
            existing_sensor = self.sensor_registry.get_sensor(record.sac, record.sic)
            has_existing_pos = existing_sensor and existing_sensor['latitude'] is not None
            
            if (lat is None or lon is None) and not has_existing_pos:
                known_pos = get_sensor_position(record.sac, record.sic)
                if known_pos:
                    lat, lon, known_alt = known_pos
                    if alt is None:
                        alt = known_alt
                        
            # Registrar sensor (SAC/SIC)
            self.sensor_registry.register_sensor(
                record.sac, 
                record.sic,
                lat,
                lon,
                alt
            )
            
            # Procesar record (convertir coordenadas)
            processed = self.target_processor.process_record(record)
            self.records.append(processed)
            
            # Agrupar por squawk para mostrar
            if processed['category'] in [1, 48, 62]:  # Radar targets & System Tracks
                mode3a = processed.get('mode_3a')
                squawk_key = 'N/A' if mode3a is None else f"{mode3a:04o}"
                
                if squawk_key not in grouped_by_squawk:
                    grouped_by_squawk[squawk_key] = []
                grouped_by_squawk[squawk_key].append(processed)
                
        # Mostrar resultados agrupados
        print("\n[*] Resultados agrupados por código Squawk (Mode 3/A):")
        
        for squawk, records in sorted(grouped_by_squawk.items(), key=lambda x: (x[0] == 'N/A', x[0])):
            print(f"\n▶ Squawk: {squawk} ({len(records)} registros)")
            for processed in records:
                cat_name = f"CAT {processed['category']}"
                
                lat = processed.get('latitude')
                lat_str = 'N/A' if lat is None else f"{lat:.6f}"
                
                lon = processed.get('longitude')
                lon_str = 'N/A' if lon is None else f"{lon:.6f}"
                
                print(f"  {cat_name:8} | SAC:{processed['sac']:3d} SIC:{processed['sic']:3d} | "
                      f"Lat: {lat_str:10} | Lon: {lon_str:10} | "
                      f"ID: {processed.get('callsign', 'N/A'):8}")
    
    def preview_map(self, min_fl: Optional[float] = None, squawk_filter: Optional[str] = None):
        """Muestra una previsualización rápida de la cobertura usando matplotlib."""
        try:
            import matplotlib.pyplot as plt
        except ImportError:
            print("\n[!] Error: matplotlib no está instalado. Para ver la vista previa, ejecuta: pip install matplotlib")
            return False

        valid_records = [r for r in self.records 
                        if r.get('latitude') is not None and r.get('longitude') is not None]
        
        if min_fl is not None:
            valid_records = [r for r in valid_records if r.get('flight_level') is not None and r.get('flight_level') >= min_fl]

        if squawk_filter:
            try:
                target_squawk = int(squawk_filter, 8)
                valid_records = [r for r in valid_records if r.get('mode_3a') == target_squawk]
            except ValueError:
                print(f"[!] Código Squawk inválido: {squawk_filter}. Debe ser un valor octal (0-7).")

        if not valid_records:
            print("[!] No hay registros con coordenadas válidas para mostrar.")
            return False

        print("\n[*] Generando vista previa del mapa...")
        
        fig, ax = plt.subplots(figsize=(12, 8))
        
        # Configuración de estilos por categoría
        cat_styles = {
            48: {'color': '#1f77b4', 'marker': 'o', 'label_suffix': 'Plot (CAT 48)'},
            21: {'color': '#d62728', 'marker': '^', 'label_suffix': 'ADS-B (CAT 21)'},
            62: {'color': '#2ca02c', 'marker': 's', 'label_suffix': 'Track (CAT 62)'},
            1:  {'color': '#7f7f7f', 'marker': '.', 'label_suffix': 'Plot (CAT 01)'}
        }
        default_style = {'color': '#bcbd22', 'marker': 'x', 'label_suffix': 'Otros'}

        # Agrupar por Categoría y Sensor para la leyenda
        groups = {}
        for r in valid_records:
            cat = r['category']
            key = (cat, r['sac'], r['sic'])
            if key not in groups:
                groups[key] = {'lat': [], 'lon': []}
            groups[key]['lat'].append(r['latitude'])
            groups[key]['lon'].append(r['longitude'])
            
        for (cat, sac, sic), coords in groups.items():
            style = cat_styles.get(cat, default_style)
            label = f"S:{sac}/{sic} {style['label_suffix']}"
            ax.scatter(coords['lon'], coords['lat'], s=15, alpha=0.7, 
                       c=style['color'], marker=style['marker'], label=label)
            
        # Dibujar radares conocidos
        for (sac, sic), info in self.sensor_registry.get_all_sensors().items():
            if info['latitude'] is not None:
                plt.plot(info['longitude'], info['latitude'], 'kX', markersize=10)
                plt.annotate(f"Radar {sac}/{sic}", (info['longitude'], info['latitude']), 
                            xytext=(5, 5), textcoords='offset points')

            # Dibujar anillos de distancia (Range Rings) cada 50 NM hasta 250 NM
            for dist_nm in range(50, 251, 50):
                circle_lats = []
                circle_lons = []
                # Generar puntos para el círculo (pasos de 5 grados para suavidad)
                for angle in range(0, 361, 5):
                    c_lat, c_lon = GeoTools.polar_to_wgs84(info['latitude'], info['longitude'], angle, dist_nm)
                    circle_lats.append(c_lat)
                    circle_lons.append(c_lon)
                
                plt.plot(circle_lons, circle_lats, color='gray', linestyle=':', linewidth=0.7, alpha=0.3)
                # Etiqueta de distancia en el cuadrante NE (45°)
                l_lat, l_lon = GeoTools.polar_to_wgs84(info['latitude'], info['longitude'], 45, dist_nm)
                plt.text(l_lon, l_lat, f"{dist_nm}NM", color='gray', fontsize=7, alpha=0.4)

        title = f"Cobertura Radar - {os.path.basename(self.current_file_path or 'Datos ASTERIX')}"
        if min_fl is not None:
            title += f" (Filtrado FL >= {min_fl})"
        if squawk_filter:
            title += f" (Squawk: {squawk_filter})"
        plt.title(title)
        plt.xlabel("Longitud (WGS-84)")
        plt.ylabel("Latitud (WGS-84)")
        plt.grid(True, linestyle='--', alpha=0.7)
        plt.axis('equal')
        plt.legend()
        plt.tight_layout()
        plt.show()
        return True

    def preview_ppi_radar(self):
        """
        Genera una visualización tipo PPI (Plan Position Indicator) en coordenadas polares.
        Cumple con estética de radar clásica (fondo negro, rejilla verde neón).
        """
        try:
            import matplotlib.pyplot as plt
            import numpy as np
        except ImportError:
            print("\n[!] Error: matplotlib o numpy no están instalados.")
            print("    Ejecuta: pip install matplotlib numpy")
            return False

        # Filtrar registros que tengan datos de Azimut y Rango (Radar Crudo)
        radar_targets = [r for r in self.records 
                        if r.get('raw_azimuth') is not None and r.get('raw_range') is not None]

        if not radar_targets:
            print("[!] No se encontraron datos de Azimut/Rango para generar el PPI.")
            return False

        print("\n[*] Generando visualización PPI Radar...")

        fig = plt.figure(figsize=(9, 9), facecolor='black')
        # Configuración Polar: 0° arriba (Norte) y sentido horario
        ax = fig.add_subplot(111, projection='polar')
        ax.set_theta_offset(np.pi/2.0)
        ax.set_theta_direction(-1)
        
        # Estética Radar
        cat_ppi_styles = {
            48: {'color': 'lime', 'marker': 'o', 'size': 25, 'label': 'Radar Plot (48)'},
            21: {'color': 'cyan', 'marker': '^', 'size': 40, 'label': 'ADS-B (21)'},
            62: {'color': 'yellow', 'marker': 's', 'size': 40, 'label': 'System Track (62)'},
            1:  {'color': 'green', 'marker': '.', 'size': 20, 'label': 'Radar Plot (01)'}
        }
        default_ppi = {'color': 'white', 'marker': 'x', 'size': 30, 'label': 'Otro'}

        # Estética General
        ax.set_facecolor('black')
        ax.grid(color='lime', linestyle='--', alpha=0.4)
        ax.tick_params(colors='lime', labelsize=8)
        
        # Anillos de rango fijos (cada 50 NM hasta 250 NM)
        range_rings = [50, 100, 150, 200, 250]
        ax.set_rticks(range_rings)
        ax.set_rmin(0)
        ax.set_rmax(250)
        ax.set_yticklabels([f"{r}NM" for r in range_rings], color='lime', alpha=0.7)

        # Simulación de barrido (Sweep Beam)
        # Usamos el último azimut detectado para posicionar la línea de la antena
        last_az = np.radians(radar_targets[-1]['raw_azimuth'])
        ax.annotate('', xy=(last_az, 250), xytext=(0, 0),
                    arrowprops=dict(arrowstyle='-', color='lime', alpha=0.5, linewidth=2))
        
        # Dibujar un gradiente de barrido (Faded sweep)
        sweep_width = np.radians(30)
        angles = np.linspace(last_az - sweep_width, last_az, 20)
        for i, angle in enumerate(angles):
            ax.plot([angle, angle], [0, 250], color='lime', alpha=(i/20.0)*0.2, linewidth=1)

        # Agrupar por Track Number para mostrar historial (estela)
        tracks = {}
        for target in radar_targets:
            tn = target.get('track_number', 'N/A')
            if tn not in tracks:
                tracks[tn] = []
            tracks[tn].append(target)

        for tn, history in tracks.items():
            # Ordenar por tiempo para asegurar la estela cronológica correcta
            history.sort(key=lambda x: x.get('timestamp') or 0)
            
            thetas = [np.radians(h['raw_azimuth']) for h in history]
            rs = [h['raw_range'] for h in history]
            
            # Identificar estilo según categoría del último punto
            last_pos = history[-1]
            cat = last_pos.get('category')
            style = cat_ppi_styles.get(cat, default_ppi)

            # Dibujar la estela (línea tenue y puntos históricos)
            if len(history) > 1:
                ax.plot(thetas, rs, color=style['color'], linestyle='-', linewidth=0.8, alpha=0.2)
                ax.scatter(thetas[:-1], rs[:-1], c=style['color'], s=style['size']/4, marker=style['marker'], alpha=0.3)
            
            # Dibujar la posición actual (última recibida)
            t_last, r_last = thetas[-1], rs[-1]
            
            ax.scatter(t_last, r_last, c=style['color'], s=style['size'], 
                       marker=style['marker'], edgecolors='white', linewidths=0.5, alpha=1.0)

        plt.title(f"PPI Radar Display - {os.path.basename(self.current_file_path or 'ASTERIX')}", 
                  color='lime', pad=20)
        plt.tight_layout()
        plt.show()
        return True

    def set_sensor_position(self, sac: int, sic: int, lat: float, lon: float, elev: float = 0):
        """Establece manualmente la posición de un sensor."""
        self.sensor_registry.register_sensor(sac, sic, lat, lon, elev)
        print(f"[✓] Sensor {sac:03d}/{sic:03d} configurado en ({lat:.6f}, {lon:.6f})")
    
    def export(self, output_dir: str = "c:/documentos/resultados"):
        """Exporta datos a múltiples formatos."""
        Path(output_dir).mkdir(exist_ok=True, parents=True)
        
        print(f"\n[*] Exportando datos a: {output_dir}/")
        
        # Filtrar registros con coordenadas válidas
        valid_records = [r for r in self.records 
                        if r['latitude'] is not None and r['longitude'] is not None]
        
        if not valid_records:
            print("[!] Advertencia: No hay registros con coordenadas válidas para exportar")
            return
        
        # Exportar KML
        kml_path = os.path.join(output_dir, "asterix_data.kml")
        KMLExporter.export(valid_records, kml_path)
        print(f"[✓] KML exportado: {kml_path}")
        
        # Exportar GeoJSON
        geojson_path = os.path.join(output_dir, "asterix_data.geojson")
        GeoJSONExporter.export(valid_records, geojson_path)
        print(f"[✓] GeoJSON exportado: {geojson_path}")
        
        # Exportar CSV
        csv_path = os.path.join(output_dir, "asterix_data.csv")
        CSVExporter.export(self.records, csv_path)
        print(f"[✓] CSV exportado: {csv_path}")
        
        # Generar reporte
        report = ReportGenerator.generate_summary(self.records, self.sensor_registry)
        report_path = os.path.join(output_dir, "analysis_report.txt")
        ReportGenerator.save_report(report, report_path)
        print(f"[✓] Reporte generado: {report_path}")
        
        print("\n" + report)


class AsterixGUI:
    """Interfaz Gráfica para el Analizador ASTERIX."""
    def __init__(self, root, analyzer: AsterixAnalyzer):
        self.root = root
        self.analyzer = analyzer
        self.root.title("ASTERIX Air Traffic Surveillance Analyzer v2.0")
        self.root.geometry("800x600")
        self.track_manager = TrackManager() # Gestor de estado para trazas activas
        self.engine = ATMAnalyticsEngine(rotation_period=4.0) # Default 15 RPM
        self.playback_engine = None
        self.detected_rpm = 15.0
        self.sweep_angle = 0
        self.prev_sweep_angle = 0
        self.pending_plots = []
        self.active_tracks = {} # Replaces active_plots

        self.sector_last_update = None # Para gaps de cobertura
        self.gap_patches = [] # Para los wedges del PPI
        self.ppi_highlight_artist = None # Para resaltar eventos

        # Cola para comunicación con hilos de trabajo y estado de carga
        self.worker_queue = queue.Queue()
        self.loading_file_path: Optional[str] = None

        self._setup_professional_ui()

        # Iniciar el procesador de la cola de eventos del hilo
        self.root.after(100, self._process_worker_queue)
        # Iniciar el recolector de basura para trazas inactivas
        self.root.after(10000, self._run_garbage_collection)

    def _setup_professional_ui(self):
        # --- Tema Profesional Oscuro Mejorado ---
        BG_COLOR = "#1e1e1e"
        FRAME_BG = "#2b2b2b"
        TEXT_COLOR = "#e0e0e0"
        BTN_BG = "#007acc"  # Azul moderno
        BTN_FG = "#ffffff"
        ACCENT_COLOR = "#00ff7f"  # SpringGreen para elementos destacados
        
        self.root.configure(bg=BG_COLOR)
        style = ttk.Style()
        style.theme_use('clam')
        
        style.configure(".", background=BG_COLOR, foreground=TEXT_COLOR, bordercolor=FRAME_BG)
        style.configure("TFrame", background=BG_COLOR)
        style.configure("TLabel", background=BG_COLOR, foreground=TEXT_COLOR, font=('Segoe UI', 9))
        style.configure("TButton", background=BTN_BG, foreground=BTN_FG, font=('Segoe UI', 9, 'bold'), borderwidth=0, focusthickness=0, padding=5)
        style.map("TButton", background=[('active', '#005f9e')])
        style.configure("TLabelframe", background=FRAME_BG, bordercolor="#444444", relief=tk.SOLID, borderwidth=1)
        style.configure("TLabelframe.Label", background=FRAME_BG, foreground=TEXT_COLOR, font=('Segoe UI', 10, 'bold'))
        style.configure("TProgressbar", troughcolor=FRAME_BG, background=ACCENT_COLOR, bordercolor=FRAME_BG)
        style.configure("TNotebook", background=BG_COLOR, borderwidth=0)
        style.configure("TNotebook.Tab", background=FRAME_BG, foreground=TEXT_COLOR, padding=[10, 5], font=('Segoe UI', 9, 'bold'), borderwidth=0)
        style.map("TNotebook.Tab", background=[("selected", BTN_BG)], foreground=[("selected", BTN_FG)])
        style.configure("TCombobox", fieldbackground=FRAME_BG, background=BTN_BG, arrowcolor=BTN_FG)

        # --- Menú Superior ---
        menubar = tk.Menu(self.root, bg=FRAME_BG, fg=TEXT_COLOR, activebackground=BTN_BG, activeforeground=BTN_FG, relief=tk.FLAT)
        self.root.config(menu=menubar)
        stats_menu = tk.Menu(menubar, tearoff=0, bg=FRAME_BG, fg=TEXT_COLOR, activebackground=BTN_BG, activeforeground=BTN_FG)
        menubar.add_cascade(label="Estadística", menu=stats_menu)
        stats_menu.add_command(label="Probabilidad de Detección (Pd)", command=self._show_pd_view)
        stats_menu.add_command(label="Análisis de Fenómenos (Garbling/FRUIT)", command=self._show_phenomena_view)
        stats_menu.add_command(label="Integridad de Paquetes", command=self._show_integrity_view)

        # --- Layout Principal con PanedWindow ---
        main_pane = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        main_pane.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # --- Panel Izquierdo: Controles ---
        controls_pane = ttk.Frame(main_pane, width=350)
        main_pane.add(controls_pane, weight=1)

        notebook = ttk.Notebook(controls_pane)
        notebook.pack(fill=tk.BOTH, expand=True)

        # --- Pestaña 1: Proceso ---
        tab_process = ttk.Frame(notebook, padding=10)
        notebook.add(tab_process, text=" Archivo y Proceso ")

        file_frame = ttk.LabelFrame(tab_process, text="1. Carga de Archivo", padding=10)
        file_frame.pack(fill=tk.X, pady=(0, 10))
        self.file_label = ttk.Label(file_frame, text="No se ha seleccionado archivo", wraplength=300)
        self.file_label.pack(side=tk.LEFT, padx=5, expand=True, fill=tk.X)
        self.btn_load = ttk.Button(file_frame, text="Cargar...", command=self._load_file)
        self.btn_load.pack(side=tk.RIGHT, padx=5)

        decode_frame = ttk.LabelFrame(tab_process, text="2. Decodificación y Exportación", padding=10)
        decode_frame.pack(fill=tk.X, pady=10)
        self.progress_bar = ttk.Progressbar(decode_frame, orient="horizontal", mode="determinate")
        self.progress_bar.pack(fill=tk.X, expand=True, pady=(0, 2))
        self.progress_label = ttk.Label(decode_frame, text="Progreso de Carga")
        self.progress_label.pack(pady=(0, 5))
        self.decode_progress_bar = ttk.Progressbar(decode_frame, orient="horizontal", mode="determinate")
        self.decode_progress_bar.pack(fill=tk.X, expand=True, pady=(0, 2))
        self.decode_progress_label = ttk.Label(decode_frame, text="Progreso de Decodificación")
        self.decode_progress_label.pack(pady=(0, 10))
        
        process_actions_frame = ttk.Frame(decode_frame)
        process_actions_frame.pack(fill=tk.X)
        self.btn_decode = ttk.Button(process_actions_frame, text="Decodificar", command=self._start_decode_thread, state=tk.DISABLED)
        self.btn_decode.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(0, 5))
        self.btn_export = ttk.Button(process_actions_frame, text="Exportar para GIS", command=self._export_gis, state=tk.DISABLED)
        self.btn_export.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(5, 0))

        # --- Pestaña 2: Visualización y Simulación ---
        tab_viz = ttk.Frame(notebook, padding=10)
        notebook.add(tab_viz, text=" Simulación y Vistas ")

        viz_actions_frame = ttk.LabelFrame(tab_viz, text="Vistas Estáticas", padding=10)
        viz_actions_frame.pack(fill=tk.X, pady=(0, 10))
        self.btn_preview = ttk.Button(viz_actions_frame, text="Vista Previa Mapa", command=self._preview_map, state=tk.DISABLED)
        self.btn_preview.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(0, 5))
        self.btn_ppi = ttk.Button(viz_actions_frame, text="Radar PPI (Polar)", command=self._preview_ppi, state=tk.DISABLED)
        self.btn_ppi.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(5, 0))

        playback_frame = ttk.LabelFrame(tab_viz, text="Simulación (Playback)", padding=10)
        playback_frame.pack(fill=tk.X, pady=10)
        btn_row = ttk.Frame(playback_frame)
        btn_row.pack(fill=tk.X, pady=(0, 5))
        self.btn_play = ttk.Button(btn_row, text="▶ Play", command=self._toggle_playback, state=tk.DISABLED)
        self.btn_play.pack(side=tk.LEFT, padx=(0, 2))
        self.btn_stop_playback = ttk.Button(btn_row, text="⏹ Stop", command=self._stop_playback, state=tk.DISABLED)
        self.btn_stop_playback.pack(side=tk.LEFT, padx=2)
        self.speed_var = tk.StringVar(value="1x")
        speed_combo = ttk.Combobox(btn_row, textvariable=self.speed_var, values=("1x", "2x", "4x", "10x", "50x", "100x"), width=5, state='readonly')
        speed_combo.pack(side=tk.LEFT, padx=(10, 0))
        speed_combo.bind("<<ComboboxSelected>>", self._update_speed)
        # Espaciador para empujar la etiqueta de tiempo a la derecha
        ttk.Frame(btn_row).pack(side=tk.LEFT, expand=True, fill=tk.X)
        self.time_label = ttk.Label(btn_row, text="TOD: 00:00:00", font=("Consolas", 11, "bold"), foreground=ACCENT_COLOR)
        self.time_label.pack(side=tk.RIGHT, padx=5)
        slider_row = ttk.Frame(playback_frame)
        slider_row.pack(fill=tk.X, pady=5)
        self.start_time_label = ttk.Label(slider_row, text="00:00:00")
        self.start_time_label.pack(side=tk.LEFT)
        self.timeline_slider = ttk.Scale(slider_row, from_=0, to=100, orient=tk.HORIZONTAL, state=tk.DISABLED, command=self._on_slider_drag)
        self.timeline_slider.pack(fill=tk.X, expand=True, side=tk.LEFT, padx=5)
        self.timeline_slider.bind("<ButtonRelease-1>", self._on_slider_release)
        self.end_time_label = ttk.Label(slider_row, text="00:00:00")
        self.end_time_label.pack(side=tk.RIGHT)
        state_row = ttk.Frame(playback_frame)
        state_row.pack(fill=tk.X, pady=5)
        self.btn_save_state = ttk.Button(state_row, text="Guardar Estado", command=self._save_playback_state, state=tk.DISABLED)
        self.btn_save_state.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(0, 5))
        self.btn_load_state = ttk.Button(state_row, text="Cargar Estado", command=self._load_playback_state, state=tk.DISABLED)
        self.btn_load_state.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(5, 0))

        # --- Pestaña 3: Herramientas ---
        tab_tools = ttk.Frame(notebook, padding=10)
        notebook.add(tab_tools, text=" Análisis y Herramientas ")
        
        tools_frame = ttk.LabelFrame(tab_tools, text="Análisis y Configuración", padding=10)
        tools_frame.pack(fill=tk.X, pady=(0, 10))
        self.btn_view_packets = ttk.Button(tools_frame, text="Ver Paquetes (Tiempo)", command=self._show_packet_viewer, state=tk.DISABLED)
        self.btn_view_packets.pack(fill=tk.X, pady=2)
        self.btn_config_sensor = ttk.Button(tools_frame, text="Configurar Sensor Manualmente", command=self._config_sensor)
        self.btn_config_sensor.pack(fill=tk.X, pady=2)

        # --- Pestaña 4: Resumen Estadístico ---
        tab_summary = ttk.Frame(notebook, padding=10)
        notebook.add(tab_summary, text=" Resumen Estadístico ")
        
        summary_frame = ttk.LabelFrame(tab_summary, text="Resumen del Archivo Cargado", padding=(10, 5))
        summary_frame.pack(fill=tk.BOTH, expand=True)
        self.summary_area = scrolledtext.ScrolledText(summary_frame, state=tk.DISABLED, bg="#1c1c1c", fg="#d0d0d0", relief=tk.FLAT, borderwidth=0, font=('Consolas', 9))
        self.summary_area.pack(fill=tk.BOTH, expand=True)


        # --- Panel Derecho: Log ---
        log_pane = ttk.Frame(main_pane, width=500)
        main_pane.add(log_pane, weight=2)
        
        console_frame = ttk.LabelFrame(log_pane, text="Log de Operaciones", padding=(10, 5))
        console_frame.pack(fill=tk.BOTH, expand=True)
        self.log_area = scrolledtext.ScrolledText(console_frame, height=15, state=tk.DISABLED, bg="#1c1c1c", fg=ACCENT_COLOR, relief=tk.FLAT, borderwidth=0, font=('Consolas', 9))
        self.log_area.pack(fill=tk.BOTH, expand=True)


    def _toggle_playback(self):
        if not self.playback_engine:
            self.playback_engine = PlaybackEngine(self.analyzer.records, antenna_rpm=self.detected_rpm)
        
        if self.playback_engine.is_playing:
            self.playback_engine.is_playing = False
            self.btn_play.config(text="▶ Play")
        else:
            self.playback_engine.is_playing = True
            self.playback_engine.last_update_wall_clock = 0
            self.btn_play.config(text="⏸ Pause")
            self.btn_stop_playback.config(state=tk.NORMAL)
            self._playback_loop()

    def _stop_playback(self):
        if self.playback_engine:
            self.playback_engine.reset()
            self.btn_play.config(text="▶ Play")
            self.time_label.config(text="TOD: 00:00:00")
            self.btn_stop_playback.config(state=tk.DISABLED)
            self.timeline_slider.set(self.timeline_slider.cget("from"))
            self.active_plots = []

    def _update_speed(self, event):
        if self.playback_engine:
            try:
                speed_val = float(self.speed_var.get().replace('x', ''))
                self.playback_engine.playback_speed = speed_val
            except ValueError:
                pass
    
    def _on_slider_drag(self, value):
        """Actualiza la etiqueta de tiempo mientras se arrastra el slider."""
        if self.playback_engine:
            self.time_label.config(text=f"TOD: {seconds_to_hms(float(value))}")

    def _on_slider_release(self, event):
        """Se ejecuta cuando el usuario suelta el slider para buscar un tiempo."""
        if self.playback_engine:
            new_time = self.timeline_slider.get()
            self._log(f"[*] Buscando en la simulación el tiempo: {seconds_to_hms(new_time)}")
            self.playback_engine.seek(new_time)
            # Limpiar plots activos para evitar artefactos visuales después del salto
            self.active_tracks.clear()
            self.pending_plots.clear()
            self.track_manager.clear_all()
            if hasattr(self, 'unwrapped_sweep_angle'): delattr(self, 'unwrapped_sweep_angle')
            self._update_ppi_display()

    def _save_playback_state(self):
        if not self.playback_engine:
            messagebox.showwarning("Aviso", "La simulación no ha sido iniciada.")
            return

        state = self.playback_engine.get_state()
        
        save_path = filedialog.asksaveasfilename(
            title="Guardar Estado de Simulación",
            defaultextension=".json",
            filetypes=[("JSON State files", "*.json")],
            initialdir=self.analyzer.last_directory
        )

        if save_path:
            try:
                with open(save_path, 'w') as f:
                    json.dump(state, f, indent=2)
                self._log(f"[✓] Estado de la simulación guardado en: {os.path.basename(save_path)}")
            except Exception as e:
                self._log(f"[✗] Error al guardar estado: {e}")
                messagebox.showerror("Error", f"No se pudo guardar el estado: {e}")

    def _load_playback_state(self):
        if not self.analyzer.records:
            messagebox.showwarning("Aviso", "Primero debe decodificar datos para poder cargar un estado.")
            return

        load_path = filedialog.askopenfilename(
            title="Cargar Estado de Simulación",
            filetypes=[("JSON State files", "*.json")],
            initialdir=self.analyzer.last_directory
        )

        if load_path:
            try:
                with open(load_path, 'r') as f:
                    state = json.load(f)
                
                if not self.playback_engine:
                    self.playback_engine = PlaybackEngine(self.analyzer.records, antenna_rpm=self.detected_rpm)
                
                self.playback_engine.set_state(state)
                
                self.timeline_slider.set(self.playback_engine.current_sim_time)
                self.time_label.config(text=f"TOD: {seconds_to_hms(self.playback_engine.current_sim_time)}")
                self.speed_var.set(f"{self.playback_engine.playback_speed}x")
                self.active_tracks.clear()
                self.pending_plots.clear()
                self.track_manager.clear_all()
                if hasattr(self, 'unwrapped_sweep_angle'): delattr(self, 'unwrapped_sweep_angle')
                self._update_ppi_display()

                self._log(f"[✓] Estado de simulación cargado desde: {os.path.basename(load_path)}")

            except Exception as e:
                self._log(f"[✗] Error al cargar estado: {e}")
                messagebox.showerror("Error", f"No se pudo cargar el estado: {e}")

    def _playback_loop(self):
        if not self.playback_engine or not self.playback_engine.is_playing:
            return

        new_records = self.playback_engine.step()
        
        current_time = self.playback_engine.current_sim_time
        self.time_label.config(text=f"TOD: {seconds_to_hms(current_time)}")
        self.timeline_slider.set(current_time)
        
        # El barrido de antena solo tiene sentido si hay RPM (no es ADS-B puro)
        if self.playback_engine.antenna_rpm > 0:
            deg_per_sec = (self.playback_engine.antenna_rpm * 360) / 60
            self.sweep_angle = (self.playback_engine.current_sim_time * deg_per_sec) % 360
        else:
            self.sweep_angle = 0

        # Lógica de persistencia (fade-out) de los blancos
        # 50ms loop = 0.05s por ciclo. Fade-out basado en el tiempo de escaneo.
        scan_time = self.engine.rotation_period if self.engine.rotation_period > 0 else 4.0
        fade_rate = 0.05 / (scan_time * 1.5)
        
        for p in self.active_plots:
            # La vida útil de los plots de ADS-B (CAT 21) se reduce más lentamente
            if p['data'].get('category') == 21:
                p['life'] -= (fade_rate * 0.5)
            else:
                p['life'] -= fade_rate
        self.active_plots = [p for p in self.active_plots if p['life'] > 0]

        if new_records:
            for r in new_records:
                # --- Lógica de Gestión de Trazas ---
                # Actualizar el TrackManager con el nuevo plot para mantener el estado.
                tid = str(r.get('mode_s') or r.get('mode_3a') or r.get('track_number'))
                if tid != 'None':
                    self.track_manager.update_track(tid, r)

                # Actualizar el tiempo del último reporte para el sector azimutal correspondiente
                if self.sector_last_update is not None and r.get('raw_azimuth') is not None:
                    azimuth = r['raw_azimuth']
                    sector_index = int(azimuth / 3) % 120
                    self.sector_last_update[sector_index] = current_time

                # Actualizar RPM si se detecta en CAT 002 o CAT 034 durante el playback
                if r.get('category') in [2, 34] and 'antenna_speed' in r.get('extra_data', {}):
                    self.detected_rpm = r['extra_data']['antenna_speed']
                    self.engine.rotation_period = 60.0 / self.detected_rpm
                    self.playback_engine.antenna_rpm = self.detected_rpm
                    if hasattr(self, 'ppi_win') and self.ppi_win and self.ppi_win.winfo_exists():
                        self.ppi_rpm_text.set_text(f"{self.detected_rpm:.1f} RPM")

                # Se añaden todos los plots nuevos para asegurar visibilidad.
                # La simulación de barrido se mantiene visualmente con la línea, pero no filtra la aparición de los blancos.
                self.active_plots.append({'data': r, 'life': 1.0})

        # Actualizar la visualización si la ventana PPI está abierta
        self._update_ppi_display()

        self.root.after(50, self._playback_loop)

    def _update_ppi_display(self):
        """Actualiza los elementos gráficos de la ventana PPI animada."""
        if not hasattr(self, 'ppi_win') or not self.ppi_win or not self.ppi_win.winfo_exists() or not hasattr(self, 'ppi_canvas'):
            return
            
        # Actualizar la línea de barrido (sweep line)
        if self.detected_rpm > 0:
            rad_angle = np.radians(self.sweep_angle)
            self.ppi_sweep_line.set_data([rad_angle, rad_angle], [0, 250])
            self.ppi_sweep_line.set_visible(True)
        else:
            self.ppi_sweep_line.set_visible(False)

        if hasattr(self, 'ppi_scatter') and self.ppi_scatter in self.ppi_ax.collections:
            self.ppi_scatter.remove()

        # Renderizado optimizado: Actualizar solo datos del scatter existente
        filtered_plots = []
        # Usar el diccionario dinámico de variables de categoría
        for p in self.active_plots:
            cat = p['data']['category']
            # Si la categoría tiene su propio checkbox
            if cat in self.ppi_category_vars:
                if self.ppi_category_vars[cat].get():
                    filtered_plots.append(p)
            # Si no, y existe el checkbox "Otros"
            elif 'others' in self.ppi_category_vars and self.ppi_category_vars['others'].get():
                filtered_plots.append(p)

        # Filtrar adicionalmente para asegurar que solo los plots con coordenadas polares válidas se rendericen
        renderable_plots = [
            p for p in filtered_plots
            if p['data'].get('raw_azimuth') is not None and p['data'].get('raw_range') is not None
            and p['data'].get('raw_range') >= 0 and p['data'].get('raw_azimuth') >= 0
        ]

        if renderable_plots:
            # Vectorización con NumPy para mejorar el rendimiento
            plot_data = np.array([
                (float(p['data']['raw_azimuth']), float(p['data']['raw_range']), int(p['data']['category']), float(p['life']))
                for p in renderable_plots
            ], dtype=float)
            
            thetas = np.radians(plot_data[:, 0])
            rs = plot_data[:, 1]
            categories = plot_data[:, 2]
            alphas = plot_data[:, 3]
            
            # Mapeo de colores vectorizado
            colors = np.zeros((len(renderable_plots), 4))
            mask_cat48 = (categories == 48)
            mask_cat62 = (categories == 62)
            mask_other = ~mask_cat48 & ~mask_cat62
            
            colors[mask_cat48] = [0.0, 1.0, 0.0, 1.0]  # Verde
            colors[mask_cat62] = [1.0, 1.0, 0.0, 1.0]  # Amarillo
            colors[mask_other] = [0.0, 1.0, 1.0, 1.0]  # Cian
            
            colors[:, 3] = alphas  # Aplicar el alfa (vida útil) a todos
            
            self.ppi_scatter = self.ppi_ax.scatter(thetas, rs, c=colors, s=25, edgecolors='white', linewidths=0.2)
        else:
            self.ppi_scatter = self.ppi_ax.scatter([], [], c=[], s=25)

        # --- Actualización de Gaps de Cobertura ---
        if self.playback_engine and self.sector_last_update is not None and self.show_gaps_var.get():
            # El umbral es 3 rotaciones, o 20s para ADS-B (sin rotación)
            gap_threshold = (self.engine.rotation_period * 3) if self.engine.rotation_period > 0 else 20.0
            current_time = self.playback_engine.current_sim_time
            
            for i, patch in enumerate(self.gap_patches):
                last_update_time = self.sector_last_update[i]
                is_gap = (current_time - last_update_time) > gap_threshold
                
                # Optimización: solo cambiar el alfa si es necesario
                current_alpha = patch.get_alpha()
                target_alpha = 0.3 if is_gap else 0.0
                if current_alpha != target_alpha:
                    patch.set_alpha(target_alpha)
        elif self.gap_patches: # Si el checkbox está desactivado, ocultar todos
            for patch in self.gap_patches:
                if patch.get_alpha() != 0.0:
                    patch.set_alpha(0.0)
        # 7. Redibujar el canvas
        self.ppi_canvas.draw_idle()

    def _on_ppi_click(self, event):
        """Maneja el inicio/fin de la medición con regla en la vista PPI."""
        if event.inaxes != self.ppi_ax:
            return
        
        if not hasattr(self, 'ruler_start') or self.ruler_start is None:
            self.ruler_start = (event.xdata, event.ydata)
        else:
            self.ruler_start = None
            self.ppi_ruler_line.set_data([], [])
            self.ppi_ruler_text.set_text("")
            self.ppi_canvas.draw_idle()

    def _on_ppi_move(self, event):
        """Actualiza la línea de la regla y calcula la distancia en NM y ΔAz."""
        if not hasattr(self, 'ruler_start') or self.ruler_start is None or event.inaxes != self.ppi_ax or event.xdata is None:
            return
        
        theta1, r1 = self.ruler_start
        theta2, r2 = event.xdata, event.ydata
        
        dist = math.sqrt(max(0, r1**2 + r2**2 - 2 * r1 * r2 * math.cos(theta2 - theta1)))
        az_diff = abs(math.degrees(theta2 - theta1))
        if az_diff > 180: az_diff = 360 - az_diff
        
        self.ppi_ruler_line.set_data([theta1, theta2], [r1, r2])
        self.ppi_ruler_text.set_position((theta2, r2))
        self.ppi_ruler_text.set_text(f" {dist:.2f} NM\n ΔAz: {az_diff:.1f}°")
        self.ppi_canvas.draw_idle()

    def _show_pd_view(self):
        win = tk.Toplevel(self.root)
        win.title("Pd Motor - Modo A/C/S")
        win.geometry("800x500")
        win.configure(bg="#1e1e1e")

        if not self.analyzer.decoded_records:
            ttk.Label(win, text="Error: No hay datos decodificados para analizar.", foreground="red").pack(pady=20)
            return

        # Obtener datos del motor de analítica
        intervalos, pd_dict = self.engine.calculate_pd_series(self.analyzer.records)

        if not intervalos:
            ttk.Label(win, text="Error: No se pudieron calcular rotaciones. Verifique los Timestamps.").pack(pady=20)
            return

        # Crear la figura de Matplotlib con estilo oscuro
        plt.style.use('dark_background')
        fig, ax = plt.subplots(figsize=(7, 4), dpi=100)
        fig.patch.set_facecolor('#1e1e1e')
        ax.set_facecolor('#1e1e1e')
        
        is_adsb_only = self.engine.rotation_period == 0.0
        
        # Plotear cada categoría encontrada
        colors = ['lime', 'cyan', 'magenta']
        total_avg_pd = 0
        num_series = 0
        for i, (cat, values) in enumerate(pd_dict.items()):
            ax.plot(intervalos, values, color=colors[i % len(colors)], marker='o', linestyle='-', linewidth=2, markersize=4, label=f'CAT {cat}')
            if values:
                total_avg_pd += sum(values) / len(values)
                num_series += 1

        avg_pd = (total_avg_pd / num_series) if num_series > 0 else 0
        
        if is_adsb_only:
            ax.set_title("Tasa de Actualización de Trazas por Intervalo de 4s", color='white', fontsize=12)
            ax.set_xlabel("Intervalo de Tiempo (4s)", color='gray')
            ax.set_ylabel("Tasa de Actualización (%)", color='gray')
            info_text = f"Tasa Promedio: {avg_pd:.2f}% | Análisis por Intervalos de 4s"
        else:
            ax.set_title("Probabilidad de Detección (Pd) por Rotación de Antena", color='white', fontsize=12)
            ax.set_xlabel("Número de Rotación", color='gray')
            ax.set_ylabel("Pd (%)", color='gray')
            info_text = f"Pd Promedio: {avg_pd:.2f}% | Periodo Antena: {self.engine.rotation_period:.2f}s"

        ax.set_ylim(0, 105)
        ax.grid(True, linestyle='--', alpha=0.3)

        # Insertar el canvas de Matplotlib en Tkinter
        canvas = FigureCanvasTkAgg(fig, master=win)
        canvas.draw()
        canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # Información estadística rápida
        info_label = ttk.Label(win, text=info_text)
        info_label.pack(pady=5)

    def _jump_to_phenomenon(self, item_values: tuple):
        """Salta al momento y lugar de un evento de fenómeno en el PPI."""
        if not self.playback_engine:
            messagebox.showwarning("Aviso", "La simulación no está activa. Inicie la decodificación y el playback.", parent=self.root)
            return

        if not hasattr(self, 'ppi_win') or not self.ppi_win.winfo_exists():
            messagebox.showinfo("Info", "La ventana PPI no está abierta. Abriendo ahora y buscando el evento.", parent=self.root)
            self._preview_ppi()
            self.root.after(200, lambda: self._jump_to_phenomenon(item_values))
            return

        try:
            timestamp_str, details_str = item_values[1], item_values[3]
            timestamp = hms_to_seconds(timestamp_str)

            az_match = re.search(r"Az1:([\d\.]+)", details_str)
            r_match = re.search(r"R:([\d\.]+)", details_str)

            if not az_match or not r_match:
                self._log(f"[!] No se pudo parsear la posición del evento: {details_str}")
                return

            azimuth, range_nm = float(az_match.group(1)), float(r_match.group(1))
            self._log(f"[*] Saltando al evento en T={timestamp_str}, Az={azimuth}°, R={range_nm}NM")

            self.playback_engine.seek(timestamp)
            self.timeline_slider.set(timestamp)
            self.time_label.config(text=f"TOD: {seconds_to_hms(timestamp)}")

            theta = np.radians(azimuth)
            self.ppi_highlight_artist.set_data([theta], [range_nm])
            self.ppi_highlight_artist.set_visible(True)
            self.ppi_canvas.draw_idle()

            self.root.after(4000, self._hide_ppi_highlight)
            self.ppi_win.lift()
        except Exception as e:
            self._log(f"[✗] Error al saltar al evento: {e}")
            messagebox.showerror("Error", f"No se pudo procesar el evento: {e}", parent=self.root)

    def _hide_ppi_highlight(self):
        """Oculta el marcador de resaltado de eventos en el PPI."""
        if hasattr(self, 'ppi_highlight_artist') and self.ppi_highlight_artist:
            self.ppi_highlight_artist.set_visible(False)
            if hasattr(self, 'ppi_canvas') and self.ppi_canvas.get_tk_widget().winfo_exists():
                self.ppi_canvas.draw_idle()

    def _show_phenomena_view(self):
        win = tk.Toplevel(self.root)
        win.title("Detección de Degradación RSMA-S")
        win.geometry("750x300")

        tree = ttk.Treeview(win, columns=("Tipo", "Timestamp", "Squawk", "Detalles"), show="headings")
        tree.heading("Tipo", text="Fenómeno", anchor=tk.W)
        tree.heading("Timestamp", text="Tiempo", anchor=tk.W)
        tree.heading("Squawk", text="Identificador", anchor=tk.W)
        tree.heading("Detalles", text="Parámetros (Az/R)", anchor=tk.W)
        tree.column("Tipo", width=180)
        tree.column("Timestamp", width=100)
        tree.column("Squawk", width=100)
        tree.column("Detalles", width=250)
        tree.pack(fill=tk.BOTH, expand=True)
        
        for event in self.engine.degradations:
            tree.insert("", tk.END, values=(event['type'], seconds_to_hms(event['time']), event['id'], event['details']))

        def on_item_double_click(event):
            selection = tree.selection()
            if not selection: return
            item_values = tree.item(selection[0], 'values')
            self._jump_to_phenomenon(item_values)

        tree.bind("<Double-1>", on_item_double_click)

        info_label = ttk.Label(win, text="Doble clic en un evento para saltar a ese momento en el PPI.",
                               font=('Segoe UI', 8, 'italic'), foreground="#aaaaaa")
        info_label.pack(side=tk.BOTTOM, fill=tk.X, padx=5, pady=2)

    def _show_integrity_view(self):
        # Mostrar contadores de paquetes sin A/C y misses
        msg = f"Paquetes sin Modo A: {self.engine.stats['mode_a_missing']}\n"
        msg += f"Paquetes sin Modo C: {self.engine.stats['mode_c_missing']}"
        messagebox.showinfo("Integridad de Datos", msg)
        
    def _show_packet_viewer(self):
        """Muestra una ventana con el contenido completo de los paquetes en un rango de tiempo."""
        if not self.analyzer.original_records:
            messagebox.showwarning("Aviso", "No hay datos decodificados.")
            return

        # Obtener categorías disponibles para el diálogo de filtro
        available_categories = sorted(list({r.category for r in self.analyzer.original_records}))

        # Usar el diálogo personalizado para obtener los filtros
        dialog = PacketViewerFilterDialog(self.root, "Visor de Paquetes - Filtros", available_categories)
        if not dialog.result:
            return  # El usuario canceló

        filters = dialog.result
        t_start = filters['t_start']
        t_end = filters['t_end']
        selected_cat = filters['category']

        # Filtrar registros
        packets = [r for r in self.analyzer.original_records
                   if r.timestamp is not None and t_start <= r.timestamp <= t_end]
        
        if selected_cat is not None:
            packets = [r for r in packets if r.category == selected_cat]

        if not packets:
            messagebox.showinfo("Info", "No se encontraron paquetes con los filtros aplicados.")
            return

        # Crear ventana de visualización
        title = f"Inspección de Paquetes: {seconds_to_hms(t_start)} - {seconds_to_hms(t_end)}"
        if selected_cat is not None:
            title += f" | CAT{selected_cat:03d}"
        
        view_win = tk.Toplevel(self.root)
        view_win.title(title)
        view_win.geometry("700x500")
        
        txt = scrolledtext.ScrolledText(view_win, bg="#000000", fg="#00FF00", font=("Consolas", 10))
        txt.pack(fill=tk.BOTH, expand=True)

        from dataclasses import asdict

        for i, p in enumerate(packets):
            txt.insert(tk.END, f"--- REGISTRO #{i+1} | HORA: {seconds_to_hms(p.timestamp)} ---\n")
            txt.insert(tk.END, f"Categoría: CAT{p.category:03d} | Sensor: {p.sac}/{p.sic}\n")
            
            record_dict = asdict(p)
            for key, val in sorted(record_dict.items()):
                if val is None or (isinstance(val, (dict, list)) and not val):
                    continue
                
                if key == 'extra_data':
                    txt.insert(tk.END, "  [Extra Data/FSPEC Items]:\n")
                    for ek, ev in sorted(val.items()):
                        txt.insert(tk.END, f"    > {ek}: {ev}\n")
                else:
                    val_str = f"{val:.6f}" if isinstance(val, float) else str(val)
                    txt.insert(tk.END, f"  {key}: {val_str}\n")
            txt.insert(tk.END, "-"*50 + "\n\n")
        txt.config(state=tk.DISABLED)

    def _update_summary_tab(self):
        """Genera y muestra el resumen estadístico en su pestaña dedicada."""
        if not self.analyzer.records and not self.analyzer.current_file_path:
            report_text = "Cargue un archivo y decodifíquelo para ver el resumen."
        elif not self.analyzer.records:
            report_text = "Los datos aún no han sido decodificados."
        else:
            report_text = ReportGenerator.generate_summary(self.analyzer.records, self.analyzer.sensor_registry)
        
        self.summary_area.config(state=tk.NORMAL)
        self.summary_area.delete('1.0', tk.END)
        self.summary_area.insert(tk.END, report_text)
        self.summary_area.config(state=tk.DISABLED)

    def _log(self, message):
        self.log_area.config(state=tk.NORMAL)
        self.log_area.insert(tk.END, f"{message}\n")
        self.log_area.see(tk.END)
        self.log_area.config(state=tk.DISABLED)
        self.root.update_idletasks()

    def _run_garbage_collection(self):
        """Ejecuta periódicamente la purga de trazas inactivas del TrackManager."""
        if self.track_manager:
            purged_count = self.track_manager.purge_stale_tracks()
            if purged_count > 0:
                self._log(f"[GC] {purged_count} trazas inactivas eliminadas de la memoria.")
        
        # Re-agendar la próxima ejecución para dentro de 10 segundos
        self.root.after(10000, self._run_garbage_collection)

    def _process_worker_queue(self):
        """
        Procesa mensajes de la cola del hilo de trabajo en el hilo principal.
        
        Este método se ejecuta periódicamente en el hilo de la GUI para
        recoger los resultados de las tareas pesadas (carga, decodificación)
        que se ejecutan en hilos secundarios. Esto evita que la interfaz
        se congele.
        
        Maneja diferentes tipos de mensajes: progreso, éxito, error.
        """
        try:
            msg = self.worker_queue.get_nowait()
            msg_type, data = msg

            if msg_type == 'load_progress':
                # Actualizar la barra de progreso de carga de archivo
                current, total, prefix, _ = data
                self._gui_load_progress(current, total, prefix=prefix)
            elif msg_type == 'decode_progress':
                current, total, prefix, suffix = data
                percentage = (current / total) * 100 if total > 0 else 100
                self.decode_progress_bar["value"] = percentage
                self.decode_progress_label.config(text=f"{prefix} {percentage:.1f}% {suffix}")
            elif msg_type == 'load_success':
                # Tarea de carga de archivo completada con éxito
                self._on_load_finished(data)
            elif msg_type == 'decode_success':
                # Tarea de decodificación completada con éxito
                self._on_decode_finished(data)
            elif msg_type == 'error':
                error = data
                self._log(f"[✗] Error en el hilo de trabajo: {error}")
                messagebox.showerror("Error en Hilo Secundario", str(error))
                # Re-habilitar botones en caso de error
                self.btn_load.config(state=tk.NORMAL)
                self.btn_decode.config(state=tk.NORMAL)
                self.progress_label.config(text="Error en carga.")
                self.decode_progress_label.config(text="Error en decodificación.")

        except queue.Empty:
            pass  # No hay mensajes
        finally:
            # Re-agendar la revisión de la cola
            self.root.after(100, self._process_worker_queue)

    def _on_load_finished(self, data):
        """Se ejecuta en el hilo principal cuando la carga de un archivo ha terminado."""
        self.btn_load.config(state=tk.NORMAL)
        if data:
            self.analyzer.asterix_data = data
            self.analyzer.current_file_path = self.loading_file_path
            self.file_label.config(text=f"Archivo: {os.path.basename(self.loading_file_path)}")
            self._log("[✓] Archivo cargado. Listo para decodificar.")
            self.btn_decode.config(state=tk.NORMAL)
            self.btn_export.config(state=tk.DISABLED)
            self.btn_preview.config(state=tk.DISABLED)
            self.btn_ppi.config(state=tk.DISABLED)
            self.btn_play.config(state=tk.DISABLED)
            self.btn_stop_playback.config(state=tk.DISABLED)
            self.btn_save_state.config(state=tk.DISABLED)
            self.btn_load_state.config(state=tk.DISABLED)
        else:
            messagebox.showerror("Error", "No se pudieron cargar los datos del archivo.")

    def _gui_load_progress(self, current, total, prefix="", suffix=""):
        percentage = (current / total) * 100 if total > 0 else 100
        self.progress_bar["value"] = percentage
        self.progress_label.config(text=f"{prefix} {percentage:.1f}%")
        self.root.update_idletasks()

    def _load_file(self):
        file_path = filedialog.askopenfilename(
            title="Seleccionar archivo ASTERIX",
            filetypes=(("PCAP files", "*.pcap"), ("AST files", "*.ast"), ("All files", "*.*"))
        )
        if file_path:
            self.analyzer.reset()
            self._update_summary_tab() # Limpiar la pestaña de resumen
            self.loading_file_path = file_path
            # Reiniciar motores de análisis y estado de reproducción para evitar acumulación
            self.engine = ATMAnalyticsEngine(rotation_period=self.engine.rotation_period)
            self.playback_engine = None
            self.detected_rpm = 15.0
            self.active_plots = []
            self.sweep_angle = 0

            # Deshabilitar botones durante la carga
            self.btn_load.config(state=tk.DISABLED)
            self.btn_decode.config(state=tk.DISABLED)
            self.btn_export.config(state=tk.DISABLED)
            self.btn_preview.config(state=tk.DISABLED)
            self.btn_ppi.config(state=tk.DISABLED)
            self.btn_play.config(state=tk.DISABLED)
            self.btn_stop_playback.config(state=tk.DISABLED)
            self.btn_save_state.config(state=tk.DISABLED)
            self.btn_load_state.config(state=tk.DISABLED)

            _, ext = os.path.splitext(file_path)

            def progress_callback_for_thread(current, total, prefix, suffix):
                self.worker_queue.put(('load_progress', (current, total, prefix, suffix)))

            if ext.lower() == '.pcap':
                self._log("[*] Cargando PCAP en hilo secundario...")
                worker = WorkerThread(
                    'load', self.analyzer.load_pcap, self.worker_queue,
                    file_path, gui_progress_callback=progress_callback_for_thread
                )
                worker.start()
            else:  # .ast es generalmente rápido, se puede hacer síncrono
                data = self.analyzer.load_ast(file_path)
                self._on_load_finished(data)

    def _start_decode_thread(self):
        """Inicia la decodificación en un hilo secundario para no bloquear la GUI."""
        self._log("[*] Iniciando decodificación en hilo secundario...")
        self.btn_decode.config(state=tk.DISABLED)
        try:
            self.decode_progress_bar["value"] = 0
            self.decode_progress_label.config(text="Decodificando...")
            self.root.update_idletasks()

            def gui_decode_progress_callback(current, total, prefix="", suffix=""):
                self.worker_queue.put(('decode_progress', (current, total, prefix, suffix)))

            # Crear y lanzar el hilo de trabajo para la tarea pesada
            worker = WorkerThread(
                'decode', decode_asterix_stream, self.worker_queue,
                self.analyzer.asterix_data,
                gui_progress_callback=gui_decode_progress_callback
            )
            worker.start()
        except Exception as e:
            self._log(f"[✗] Error al iniciar el hilo de decodificación: {e}")
            messagebox.showerror("Error de Hilo", str(e))
            self.btn_decode.config(state=tk.NORMAL)

    def _on_decode_finished(self, all_records):
        """Se ejecuta en el hilo principal cuando la decodificación ha terminado."""
        self._log(f"[*] {len(all_records)} registros decodificados. Procesando metadatos...")
        try:
            self._log("[*] Analizando estructura de categorías...")

            # Resetear y preparar estructuras de datos
            self.analyzer.decoded_records = []
            self.analyzer.original_records = all_records

            # Extraer metadatos reales agrupados por categoría para el diálogo
            cat_metadata = {}
            found_categories = set()
            for r in all_records:
                # 1. Registrar sensor (Vital para CAT 48/01 que requiere posición del radar)
                lat, lon, alt = None, None, None # Iniciar sin posición

                # Solo confiar en la posición de los mensajes de servicio del radar (CAT 034/002)
                if r.category in [34, 2] and r.latitude is not None:
                    lat, lon, alt = r.latitude, r.longitude, r.altitude
                else:
                    # Para todos los demás, buscar en la configuración estática
                    known_pos = get_sensor_position(r.sac, r.sic)
                    if known_pos:
                        lat, lon, known_alt = known_pos
                        alt = known_alt
                self.analyzer.sensor_registry.register_sensor(r.sac, r.sic, lat, lon, alt)

                # 2. Guardar en decoded_records para analítica (Pd, integridad) y playback
                self.analyzer.decoded_records.append({
                    'category': r.category, 'sac': r.sac, 'sic': r.sic,
                    'latitude': r.latitude, 'longitude': r.longitude, 'altitude': r.altitude,
                    'mode_3a': r.mode_3a, 'mode_s': r.target_address, 'callsign': r.target_id,
                    'track_number': r.track_number, 'timestamp': r.timestamp,
                    'flight_level': r.flight_level, 'extra_data': r.extra_data
                })

                # 3. Recopilar metadatos para el diálogo de filtros
                cat = r.category
                found_categories.add(cat)
                if cat not in cat_metadata:
                    cat_metadata[cat] = {
                        "squawks": set(),
                        "track_numbers": set(),
                        "addresses": set(),
                        "callsigns": set(),
                        "fl_list": [],
                        "t_list": []
                    }
                if r.mode_3a is not None: cat_metadata[cat]["squawks"].add(r.mode_3a)
                if r.track_number is not None: cat_metadata[cat]["track_numbers"].add(r.track_number)
                if r.target_address is not None: cat_metadata[cat]["addresses"].add(r.target_address)
                if r.flight_level is not None: cat_metadata[cat]["fl_list"].append(r.flight_level)
                if r.timestamp is not None: cat_metadata[cat]["t_list"].append(r.timestamp)

            cat_list_str = ", ".join([f"CAT {c:03d}" for c in sorted(found_categories)])
            self._log(f"[i] Categorías detectadas: {cat_list_str}")

            # Advertir si categorías que necesitan posición de sensor no la tienen
            cats_needing_sensor_pos = {21, 62}
            present_cats_needing_pos = found_categories.intersection(cats_needing_sensor_pos)
            
            if present_cats_needing_pos:
                sensors_in_data = {(r.sac, r.sic) for r in all_records if r.category in present_cats_needing_pos}
                for sac, sic in sensors_in_data:
                    if not self.analyzer.sensor_registry.has_position(sac, sic):
                        msg = f"El sensor {sac}/{sic} no tiene una posición geográfica configurada. Los datos de CAT {list(present_cats_needing_pos)} no se podrán mostrar en la vista PPI. Use 'Configurar Sensor' o añada el sensor a los archivos de configuración."
                        self._log(f"[!] Advertencia: {msg}")
                        messagebox.showwarning("Sensor sin Posición", msg)
                        break # Mostrar advertencia solo una vez

            # Si solo hay datos ADS-B, no hay rotación de antena.
            is_adsb_only = found_categories == {21}
            detected_rpm = None

            if is_adsb_only:
                detected_rpm = 0.0
                self._log("[i] Datos ADS-B puros detectados. La simulación PPI no tendrá barrido de antena.")
            else:
                # Para datos de radar, intentar detectar RPM o preguntar al usuario.
                for r in all_records:
                    if r.category in [2, 34] and 'antenna_speed' in r.extra_data:
                        detected_rpm = r.extra_data['antenna_speed']
                        break
                
                if detected_rpm is None:
                    detected_rpm = simpledialog.askfloat(
                        "Velocidad de Antena", 
                        "No se detectó velocidad de rotación automática en los datos (CAT 002).\nPor favor, ingrese las RPM del radar para la simulación y análisis:",
                        initialvalue=15.0, minvalue=0.1, maxvalue=60.0,
                        parent=self.root
                    )
                
            if detected_rpm is not None: # Puede ser 0.0 para ADS-B
                self.detected_rpm = detected_rpm
                if self.detected_rpm > 0:
                    self.engine.rotation_period = 60.0 / self.detected_rpm
                    self._log(f"[i] Velocidad de antena establecida: {self.detected_rpm} RPM (Periodo: {self.engine.rotation_period:.2f}s)")
                else:
                    self.engine.rotation_period = 0.0

            self._log("[i] Omitiendo diálogo de filtros. El slider de tiempo puede usarse para la navegación.")
            filtered_records = all_records

            # Procesar los registros filtrados
            self.analyzer.records = []
            for r in filtered_records:
                self.analyzer.records.append(self.analyzer.target_processor.process_record(r))

            # --- Configuración del Timeline Slider ---
            if self.analyzer.records:
                timestamps = [r['timestamp'] for r in self.analyzer.records if r.get('timestamp') is not None]
                if timestamps:
                    min_time = min(timestamps)
                    max_time = max(timestamps)
                    # Asegurarse de que haya un rango para el slider
                    if min_time == max_time:
                        max_time += 1.0

                    self.timeline_slider.config(from_=min_time, to=max_time, state=tk.NORMAL)
                    self.start_time_label.config(text=seconds_to_hms(min_time))
                    self.end_time_label.config(text=seconds_to_hms(max_time))
                    self.timeline_slider.set(min_time)

                    # Inicializar el array de seguimiento de sectores para la detección de gaps
                    self.sector_last_update = np.full(120, min_time) # 120 sectores de 3 grados

            self._log(f"[✓] {len(self.analyzer.records)} registros procesados.")
            self.btn_export.config(state=tk.NORMAL)
            # Habilitar previsualización solo si hay datos con coordenadas
            self.btn_preview.config(state=tk.NORMAL) 
            self.btn_view_packets.config(state=tk.NORMAL)
            self.btn_ppi.config(state=tk.NORMAL)
            self.btn_play.config(state=tk.NORMAL)
            self.btn_stop_playback.config(state=tk.NORMAL)
            self.btn_save_state.config(state=tk.NORMAL)
            self.btn_load_state.config(state=tk.NORMAL)

            self._update_summary_tab()

            messagebox.showinfo("Éxito", f"Se han decodificado {len(self.analyzer.records)} registros.")
            self.btn_decode.config(state=tk.NORMAL)
            self.decode_progress_label.config(text="Decodificación completada.")
        except Exception as e:
            self._log(f"[✗] Error: {e}")
            messagebox.showerror("Error de Decodificación", str(e))
            self.decode_progress_label.config(text="Error en decodificación.")
            self.btn_decode.config(state=tk.NORMAL)

    def _preview_map(self):
        """Muestra una ventana de mapa interactiva con controles de zoom y pan."""
        min_fl_str = simpledialog.askstring("Filtro de Altitud", "Mínimo Nivel de Vuelo (FL) a mostrar (Dejar vacío para todos):", parent=self.root)
        if min_fl_str is None: return

        min_fl = None
        if min_fl_str.strip():
            try:
                min_fl = float(min_fl_str)
            except ValueError:
                messagebox.showerror("Error", "El nivel de vuelo (FL) debe ser un valor numérico.")
                return

        squawk = simpledialog.askstring("Filtro de Squawk", "Código Squawk octal a filtrar (Dejar vacío para todos):", parent=self.root)

        valid_records = [r for r in self.analyzer.records if r.get('latitude') is not None and r.get('longitude') is not None]
        if min_fl is not None:
            valid_records = [r for r in valid_records if r.get('flight_level') is not None and r.get('flight_level') >= min_fl]
        if squawk:
            try:
                target_squawk = int(squawk, 8)
                valid_records = [r for r in valid_records if r.get('mode_3a') == target_squawk]
            except ValueError:
                messagebox.showerror("Error", f"Código Squawk inválido: {squawk}. Debe ser un valor octal (0-7).")
                return

        if not valid_records:
            messagebox.showwarning("Aviso", "No hay datos con coordenadas para mostrar con los filtros aplicados.")
            return

        self._log("[*] Generando vista previa del mapa interactivo...")

        map_win = tk.Toplevel(self.root)
        map_win.title("Vista Previa de Mapa Interactivo")
        map_win.geometry("900x700")
        map_win.configure(bg="#1e1e1e")

        fig = plt.figure(figsize=(12, 8), facecolor="#1e1e1e")
        ax = fig.add_subplot(111)
        ax.set_facecolor("#101010")
        ax.tick_params(axis='x', colors='white')
        ax.tick_params(axis='y', colors='white')

        cat_styles = {
            48: {'color': '#1f77b4', 'marker': 'o', 'label_suffix': 'Plot (CAT 48)'},
            21: {'color': '#d62728', 'marker': '^', 'label_suffix': 'ADS-B (CAT 21)'},
            62: {'color': '#2ca02c', 'marker': 's', 'label_suffix': 'Track (CAT 62)'},
            1:  {'color': '#7f7f7f', 'marker': '.', 'label_suffix': 'Plot (CAT 01)'}
        }
        default_style = {'color': '#bcbd22', 'marker': 'x', 'label_suffix': 'Otros'}

        groups = {}
        for r in valid_records:
            cat, sac, sic = r['category'], r['sac'], r['sic']
            key = (cat, sac, sic)
            if key not in groups:
                groups[key] = {'lat': [], 'lon': []}
            groups[key]['lat'].append(r['latitude'])
            groups[key]['lon'].append(r['longitude'])

        for (cat, sac, sic), coords in groups.items():
            style = cat_styles.get(cat, default_style)
            label = f"S:{sac}/{sic} {style['label_suffix']}"
            ax.scatter(coords['lon'], coords['lat'], s=15, alpha=0.7, c=style['color'], marker=style['marker'], label=label)

        for (sac, sic), info in self.analyzer.sensor_registry.get_all_sensors().items():
            if info['latitude'] is not None:
                ax.plot(info['longitude'], info['latitude'], 'X', markersize=10, color='yellow', label=f"Radar {sac}/{sic}")
                ax.annotate(f"Radar {sac}/{sic}", (info['longitude'], info['latitude']), xytext=(5, 5), textcoords='offset points', color='white')
                for dist_nm in range(50, 251, 50):
                    circle_lats, circle_lons = [], []
                    for angle in range(0, 361, 5):
                        c_lat, c_lon = GeoTools.polar_to_wgs84(info['latitude'], info['longitude'], angle, dist_nm)
                        circle_lats.append(c_lat)
                        circle_lons.append(c_lon)
                    ax.plot(circle_lons, circle_lats, color='gray', linestyle=':', linewidth=0.7, alpha=0.3)
                    l_lat, l_lon = GeoTools.polar_to_wgs84(info['latitude'], info['longitude'], 45, dist_nm)
                    ax.text(l_lon, l_lat, f"{dist_nm}NM", color='gray', fontsize=7, alpha=0.4)

        title = f"Cobertura Radar - {os.path.basename(self.analyzer.current_file_path or 'Datos ASTERIX')}"
        if min_fl is not None: title += f" (Filtrado FL >= {min_fl})"
        if squawk: title += f" (Squawk: {squawk})"
        
        ax.set_title(title, color='white')
        ax.set_xlabel("Longitud (WGS-84)", color='white')
        ax.set_ylabel("Latitud (WGS-84)", color='white')
        ax.grid(True, linestyle='--', alpha=0.7)
        ax.axis('equal')
        ax.legend()
        fig.tight_layout()

        canvas = FigureCanvasTkAgg(fig, master=map_win)
        canvas.draw()
        toolbar = NavigationToolbar2Tk(canvas, map_win)
        toolbar.update()
        toolbar.pack(side=tk.BOTTOM, fill=tk.X)
        canvas.get_tk_widget().pack(side=tk.TOP, fill=tk.BOTH, expand=True)

    def _preview_ppi(self):
        """Inicia la ventana de visualización PPI animada sincronizada con el Playback."""
        if hasattr(self, 'ppi_win') and self.ppi_win and self.ppi_win.winfo_exists():
            self.ppi_win.lift()
            return

        if not any(r.get('raw_azimuth') is not None for r in self.analyzer.records):
            messagebox.showwarning("Aviso", "No hay datos de Azimut/Rango para generar el PPI.")
            return

        self.ppi_win = tk.Toplevel(self.root)
        self.ppi_win.title("Real-Time Radar PPI Scope")
        self.ppi_win.geometry("600x720")
        self.ppi_win.configure(bg="black")

        # Panel de Filtros de Categoría dinámicos con Checkbuttons
        filter_frame = ttk.Frame(self.ppi_win, padding=5)
        filter_frame.pack(fill=tk.X)
        
        self.ppi_category_vars = {}
        # Filtrar solo categorías con datos ploteables (tienen azimut y rango)
        plottable_categories = sorted(list({
            r['category'] for r in self.analyzer.records 
            if r.get('raw_azimuth') is not None and r.get('raw_range') is not None
        }))
        
        cat_map = {
            48: "Plots (CAT 48)", 
            62: "Tracks (CAT 62)", 
            21: "ADS-B (CAT 21)", 
            34: "Info (CAT 34)",
            1: "Plots (CAT 01)"
        }
        
        # Crear checkboxes para TODAS las categorías mapeadas
        for cat, name in cat_map.items():
            is_present = cat in plottable_categories
            var = tk.BooleanVar(value=is_present)
            self.ppi_category_vars[cat] = var
            cb = ttk.Checkbutton(filter_frame, text=name, variable=var, command=self._update_ppi_display)
            cb.pack(side=tk.LEFT, padx=5)
            if not is_present:
                cb.config(state=tk.DISABLED) # Deshabilita las CAT que no están en el archivo

        # Checkbox para mostrar/ocultar gaps
        self.show_gaps_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(filter_frame, text="Mostrar Gaps", variable=self.show_gaps_var, command=self._update_ppi_display).pack(side=tk.LEFT, padx=10)

        # Selector de tipo de etiqueta
        ttk.Label(filter_frame, text="Etiquetas:").pack(side=tk.LEFT, padx=(15, 2))
        self.ppi_label_var = tk.StringVar(value="Callsign")
        label_combo = ttk.Combobox(filter_frame, textvariable=self.ppi_label_var, values=["Callsign", "Squawk", "Ninguna"], width=8, state='readonly')
        label_combo.pack(side=tk.LEFT)
        label_combo.bind("<<ComboboxSelected>>", lambda _: self._update_ppi_display())

        # Selector de historial
        ttk.Label(filter_frame, text="Historial:").pack(side=tk.LEFT, padx=(15, 2))
        self.ppi_history_var = tk.IntVar(value=5)
        history_slider = ttk.Scale(filter_frame, from_=1, to=20, variable=self.ppi_history_var, orient=tk.HORIZONTAL, length=80, command=lambda _: self._update_ppi_display())
        history_slider.pack(side=tk.LEFT)
        history_label = ttk.Label(filter_frame, textvariable=self.ppi_history_var, width=3)
        history_label.pack(side=tk.LEFT)

        others_present = any(c not in cat_map for c in plottable_categories)
        if others_present:
            var = tk.BooleanVar(value=True)
            self.ppi_category_vars['others'] = var
            ttk.Checkbutton(filter_frame, text="Otros", variable=var, command=self._update_ppi_display).pack(side=tk.LEFT, padx=10)

        # Herramientas de Medición
        meas_frame = ttk.Frame(self.ppi_win, padding=5)
        meas_frame.pack(fill=tk.X)
        
        self.ruler_mode = "OFF"
        self.btn_ruler_center = ttk.Button(meas_frame, text="📏 Medir (Centro)", command=self._toggle_ruler_center)
        self.btn_ruler_center.pack(side=tk.LEFT, padx=5)
        
        self.btn_ruler_free = ttk.Button(meas_frame, text="📏 Medir (Libre)", command=self._toggle_ruler_free)
        self.btn_ruler_free.pack(side=tk.LEFT, padx=5)

        self.ppi_fig = plt.figure(figsize=(6, 6), facecolor='black')
        self.ppi_ax = self.ppi_fig.add_subplot(111, projection='polar')
        self.ppi_cat_styles = {
            48: {'color_rgb': (0, 1, 0), 'marker': 'o', 'size': 25}, # lime
            21: {'color_rgb': (0, 1, 1), 'marker': '^', 'size': 40}, # cyan
            62: {'color_rgb': (1, 1, 0), 'marker': 's', 'size': 40}, # yellow
            1:  {'color_rgb': (0.5, 1, 0.5), 'marker': '.', 'size': 20}, # light green
            'default': {'color_rgb': (1, 1, 1), 'marker': 'x', 'size': 30} # white
        }
        self.ppi_ax.set_theta_offset(np.pi/2.0) # Norte arriba
        self.ppi_ax.set_theta_direction(-1)    # Sentido horario
        self.ppi_ax.set_facecolor('black')
        self.ppi_ax.grid(color='lime', linestyle='--', alpha=0.3)
        self.ppi_ax.tick_params(colors='lime', labelsize=8)
        
        # Forzar el límite del radar estrictamente de 0 a 250 NM sin causar conflictos de origen
        self.ppi_ax.set_ylim(0, 250)

        # Crear los wedges para los gaps de cobertura, inicialmente invisibles
        from matplotlib.patches import Wedge
        self.gap_patches = []
        for i in range(120): # 120 sectores de 3 grados
            # Los ángulos del Wedge de Matplotlib son CCW desde el eje X.
            # Nuestro gráfico polar es CW desde el eje Y (Norte). Hay que convertir.
            # Ángulo en el gráfico 'p_ang' -> Ángulo del Wedge 'w_ang' = 90 - p_ang
            start_angle_on_plot = i * 3
            end_angle_on_plot = (i + 1) * 3
            
            # Dibujamos de theta1 a theta2 en CCW.
            # Por tanto, theta1 es el ángulo final convertido y theta2 el inicial.
            w_theta1 = 90 - end_angle_on_plot
            w_theta2 = 90 - start_angle_on_plot
            
            wedge = Wedge(center=(0, 0), r=250, theta1=w_theta1, theta2=w_theta2,
                          width=250, color='red', alpha=0.0)
            self.ppi_ax.add_patch(wedge)
            self.gap_patches.append(wedge)

        # Artista para resaltar eventos de fenómenos
        self.ppi_highlight_artist, = self.ppi_ax.plot([], [], 'o', markersize=25,
                                                      markerfacecolor='none',
                                                      markeredgecolor='yellow',
                                                      markeredgewidth=3,
                                                      visible=False, zorder=20)
        # Elementos iniciales de la simulación
        self.ppi_sweep_line, = self.ppi_ax.plot([0, 0], [0, 250], color='lime', alpha=0.7, linewidth=2)
        self.ppi_scatters = []
        self.ppi_texts = []

        # Elementos de la Regla (Ruler)
        self.ruler_start = None
        self.ppi_ruler_line, = self.ppi_ax.plot([], [], color='red', linestyle='--', linewidth=1.5, alpha=0.8, zorder=10)
        self.ppi_ruler_text = self.ppi_ax.text(0, 0, "", color='white', fontsize=8, fontweight='bold',
                                              bbox=dict(facecolor='black', alpha=0.7, edgecolor='red', boxstyle='round,pad=0.3'), 
                                              zorder=11)
        
        # Indicador visual de RPM
        self.ppi_rpm_text = self.ppi_ax.text(np.radians(20), 240, f"{self.detected_rpm:.1f} RPM", 
                                             color='cyan', fontsize=10, fontweight='bold',
                                             bbox=dict(facecolor='black', alpha=0.7, edgecolor='cyan', boxstyle='round,pad=0.3'), zorder=11)

        # Conectar eventos de mouse para la regla interactiva
        self.ppi_fig.canvas.mpl_connect('button_press_event', self._on_ppi_click)
        self.ppi_fig.canvas.mpl_connect('motion_notify_event', self._on_ppi_move)

        self.ppi_canvas = FigureCanvasTkAgg(self.ppi_fig, master=self.ppi_win)
        self.ppi_canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        self.ppi_canvas.draw()
        
        # Iniciar sin plots activos para que aparezcan progresivamente con el Playback
        self.active_plots = []
        self._update_ppi_display()
        
        self._log("[i] Osciloscopio PPI iniciado. Use los controles de Playback para animar.")

    def _export_gis(self):
        """Diálogo de exportación profesional para GIS."""
        if not self.analyzer.records:
            return

        export_win = tk.Toplevel(self.root)
        export_win.title("Configuración de Exportación GIS")
        export_win.geometry("400x300")

        ttk.Label(export_win, text="Opciones de Capas:", font=("Arial", 10, "bold")).pack(pady=10)
        
        traj_var = tk.BooleanVar(value=True)
        rings_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(export_win, text="Incluir Trayectorias 3D (LineString)", variable=traj_var).pack(anchor=tk.W, padx=20)
        ttk.Checkbutton(export_win, text="Incluir Anillos de Distancia y ARP", variable=rings_var).pack(anchor=tk.W, padx=20)

        def run_export():
            output_dir = filedialog.askdirectory(title="Carpeta de Destino")
            if not output_dir: return
            
            try:
                valid_records = [r for r in self.analyzer.records if r.get('latitude')]
                
                # Exportación KML Avanzada
                kml_path = os.path.join(output_dir, "asterix_expert.kml")
                KMLExporter.export(valid_records, kml_path, 
                                   sensor_registry=self.analyzer.sensor_registry,
                                   include_trajectories=traj_var.get(),
                                   include_rings=rings_var.get())
                
                # Exportación GeoJSON para QGIS
                geojson_path = os.path.join(output_dir, "asterix_expert.geojson")
                GeoJSONExporter.export(valid_records, geojson_path)
                
                # CSV para QGIS
                csv_path = os.path.join(output_dir, "asterix_qgis.csv")
                CSVExporter.export(self.analyzer.records, csv_path)

                # Reporte PDF Profesional
                pdf_path = os.path.join(output_dir, "audit_report.pdf")
                stats_text = ReportGenerator.generate_summary(self.analyzer.records, self.analyzer.sensor_registry)
                PDFReportGenerator.export_pdf(self.analyzer.records, stats_text, pdf_path)

                messagebox.showinfo("Éxito", f"Archivos generados en:\n{output_dir}")
                export_win.destroy()
            except Exception as e:
                messagebox.showerror("Error", str(e))

        ttk.Button(export_win, text="Generar Archivos GIS", command=run_export).pack(pady=20)

    def _config_sensor(self):
        win = tk.Toplevel(self.root)
        win.title("Configurar Sensor")
        win.geometry("300x250")
        
        fields = ["SAC", "SIC", "Latitud", "Longitud", "Elevación (ft)"]
        entries = {}
        
        for f in fields:
            frame = ttk.Frame(win, padding=5)
            frame.pack(fill=tk.X, padx=5)
            ttk.Label(frame, text=f"{f}:", width=12).pack(side=tk.LEFT)
            e = ttk.Entry(frame)
            e.pack(side=tk.RIGHT, expand=True, fill=tk.X)
            entries[f] = e

        def save():
            try:
                self.analyzer.set_sensor_position(
                    int(entries["SAC"].get()), int(entries["SIC"].get()),
                    float(entries["Latitud"].get()), float(entries["Longitud"].get()),
                    float(entries["Elevación (ft)"].get() or 0)
                )
                self._log(f"[✓] Sensor {entries['SAC'].get()}/{entries['SIC'].get()} configurado.")
                win.destroy()
            except ValueError:
                messagebox.showerror("Error", "Por favor ingrese valores numéricos válidos.")

        ttk.Button(win, text="Guardar Sensor", command=save).pack(pady=10)

def run_gui_mode(analyzer: AsterixAnalyzer):
    root = tk.Tk()
    gui = AsterixGUI(root, analyzer)
    root.mainloop()


def main():
    parser = argparse.ArgumentParser(
        description='ASTERIX Air Traffic Surveillance Data Analyzer',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Ejemplos:
  python main.py archivo.pcap
  python main.py archivo.pcap --output resultados/
  python main.py archivo.ast --sensor 1 1 40.416775 -3.703790 2000
  python main.py --interactive
        '''
    )
    
    parser.add_argument('input_file', nargs='?', help='Archivo PCAP o AST a procesar')
    parser.add_argument('--output', '-o', default='c:/documentos/resultados', help='Directorio de salida (default: c:/documentos/resultados)')
    parser.add_argument('--sensor', '-s', nargs=4, metavar=('SAC', 'SIC', 'LAT', 'LON'),
                        help='Configurar posición de sensor: SAC SIC LATITUD LONGITUD')
    parser.add_argument('--elevation', '-e', type=float, default=0, 
                        help='Elevación del sensor en pies (default: 0)')
    parser.add_argument('--interactive', '-i', action='store_true', 
                        help='Modo interactivo')
    parser.add_argument('--gui', '-g', action='store_true', 
                        help='Iniciar aplicación en modo GUI')
    
    args = parser.parse_args()
    
    analyzer = AsterixAnalyzer()
    
    if args.input_file:
        file_path = args.input_file
        
        if not os.path.exists(file_path):
            print(f"[✗] Archivo no encontrado: {file_path}")
            sys.exit(1)
        
        _, ext = os.path.splitext(file_path)
        
        # Cargar datos según extensión
        if ext.lower() == '.pcap':
            asterix_data = analyzer.load_pcap(file_path)
        elif ext.lower() == '.ast':
            asterix_data = analyzer.load_ast(file_path)
        else:
            print(f"[✗] Formato no soportado: {ext}")
            print("[i] Formatos soportados: .pcap, .ast")
            sys.exit(1)
        
        if not asterix_data:
            analyzer.current_file_path = None # Asegurarse de que no haya un path si la carga falla
            print("[✗] No se pudo cargar datos")
            sys.exit(1)
            
        analyzer.asterix_data = asterix_data
        analyzer.current_file_path = file_path
        analyzer.last_directory = os.path.dirname(os.path.abspath(file_path))
        
        if not args.interactive:
            # Decodificar
            analyzer.decode_data()
            
            # Configurar sensor si se especifica
            if args.sensor:
                sac, sic, lat, lon = args.sensor
                analyzer.set_sensor_position(int(sac), int(sic), float(lat), float(lon), args.elevation)
            
            # Exportar resultados
            analyzer.export(args.output)
            return

    if args.gui:
        run_gui_mode(analyzer)
    elif args.interactive or not args.input_file:
        run_interactive_mode(analyzer)
    else:
        parser.print_help()
        sys.exit(1)


def ask_and_save_sensor(sensor_data: dict):
    """Pregunta al usuario si desea guardar el sensor y lo hace."""
    save_choice = input("\n¿Desea guardar este sensor en un archivo para uso futuro? (s/n): ").strip().lower()
    if save_choice == 's':
        # Asegurar que se añada a la memoria global KNOWN_SENSORS para la sesión actual
        add_sensor(
            sac=sensor_data['sac'],
            sic=sensor_data['sic'],
            name=sensor_data['name'],
            latitude=sensor_data['latitude'],
            longitude=sensor_data['longitude'],
            elevation=sensor_data['elevation'],
            description=sensor_data['description']
        )
        from config import save_sensor_to_file
        if save_sensor_to_file(sensor_data):
            print("[i] El nuevo sensor estará disponible automáticamente en la próxima ejecución.")


def run_interactive_mode(analyzer: AsterixAnalyzer):
    """Modo interactivo para el usuario."""
    print("\n" + "=" * 70)
    print("ASTERIX Air Traffic Surveillance Data Analyzer - Modo Interactivo")
    print("=" * 70)
    
    while True:
        print("\n[Menu Principal]")
        print("1. Cargar archivo PCAP/AST (Recomendado: < 100MB)")
        print("2. Configurar posición de sensor (modo interactivo)")
        print("3. Configurar sensor con grados decimales")
        print("4. Decodificar datos cargados")
        print("5. Mostrar sensores en los datos")
        print("6. Exportar resultados")
        print("7. Ver estadísticas")
        print("8. Seleccionar y ver datos de radares disponibles")
        print("9. Analizar Modo A/C y Código Squawk")
        print("10. Analizar vuelos por Squawk y pérdidas")
        print("11. Vista previa del mapa de cobertura")
        print("12. Vista previa PPI (Radar Polar)")
        print("13. Salir")
        
        choice = input("\nSeleccionar opción (1-13): ").strip()
        
        if choice == '1':
            if analyzer.asterix_data and analyzer.current_file_path:
                print(f"\n[!] Aviso: El archivo '{analyzer.current_file_path}' ya se encuentra cargado y en uso.")
                overwrite_choice = input("¿Desea continuar con el archivo original (n) o descartarlo de memoria y cargar uno nuevo (s)? (s/n): ").strip().lower()
                if overwrite_choice != 's':
                    print("[i] Continuando con el archivo original.")
                    continue # Volver al menú principal
                else:
                    print("[i] Descartando archivo original de la memoria...")
                    analyzer.reset()
            file_path = ""
            
            # Estrategia de selección de archivo:
            # 1. Si es Windows, intentar PowerShell primero (más estable en algunos sistemas).
            # 2. Si no es Windows o PowerShell falla, usar Tkinter (estándar multiplataforma).
            # 3. Si todo falla, usar entrada de texto.

            if sys.platform == "win32":
                print("[i] Abriendo cuadro de diálogo (método PowerShell)...")
                try:
                    import subprocess
                    safe_dir = analyzer.last_directory.replace("'", "''")
                    ps_script = (
                        "Add-Type -AssemblyName System.Windows.Forms; "
                        "$f = New-Object System.Windows.Forms.OpenFileDialog; "
                        "$f.Filter = 'Archivos soportados (*.pcap, *.ast)|*.pcap;*.ast|Archivos PCAP (*.pcap)|*.pcap|Archivos AST (*.ast)|*.ast|Todos los archivos (*.*)|*.*'; "
                        "$f.Title = 'Seleccionar archivo ASTERIX (PCAP o AST)'; "
                        f"$f.InitialDirectory = '{safe_dir}'; "
                        "if ($f.ShowDialog() -eq 'OK') { Write-Output $f.FileName }"
                    )
                    result = subprocess.run(["powershell", "-NoProfile", "-Command", ps_script], capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
                    file_path = result.stdout.strip()
                except Exception as e_ps:
                    print(f"[!] Diálogo de PowerShell falló ({e_ps.__class__.__name__}). Intentando con Tkinter...")
                    # Fallback a Tkinter si PowerShell falla
                    try:
                        import tkinter as tk
                        from tkinter import filedialog
                        root = tk.Tk()
                        root.withdraw()
                        file_path = filedialog.askopenfilename(
                            title="Seleccionar archivo", 
                            filetypes=(("Soportados", "*.pcap *.ast"),("Todos", "*.*")),
                            initialdir=analyzer.last_directory
                        )
                    except Exception as e_tk:
                        print(f"[!] El diálogo Tkinter también falló ({e_tk.__class__.__name__}).")
            else:
                # Para sistemas no-Windows, usar Tkinter directamente
                try:
                    import tkinter as tk
                    from tkinter import filedialog
                    print("[i] Abriendo cuadro de diálogo (método Tkinter)...")
                    root = tk.Tk()
                    root.withdraw()
                    file_path = filedialog.askopenfilename(
                        title="Seleccionar archivo", 
                        filetypes=(("Soportados", "*.pcap *.ast"),("Todos", "*.*")),
                        initialdir=analyzer.last_directory
                    )
                except Exception as e_tk:
                    print(f"[!] No se pudo abrir el cuadro de diálogo gráfico ({e_tk.__class__.__name__}).")
                    print("[i] Si usas Linux, asegúrate de tener 'python3-tk' instalado.")

            # 3. Si no se obtuvo ruta (cancelado o falló), usar entrada de texto
            if not file_path:
                print("[i] Se usará la entrada de texto manual.")
                file_path = input("Ingrese ruta del archivo: ").strip().strip('"').strip("'")

            # Si al final no hay ruta, cancelar y volver al menú
            if not file_path:
                print("[i] Selección cancelada.")
                continue

            analyzer.last_directory = os.path.dirname(os.path.abspath(file_path))
            print(f"[✓] Archivo seleccionado: {file_path}")

            _, ext = os.path.splitext(file_path)
            
            if ext.lower() == '.pcap':
                analyzer.asterix_data = analyzer.load_pcap(file_path)
            elif ext.lower() == '.ast':
                analyzer.asterix_data = analyzer.load_ast(file_path)
            else:
                print("[✗] Formato no soportado. Usa .pcap o .ast")
                continue
            
            if analyzer.asterix_data:
                analyzer.current_file_path = file_path
                print("\n[i] Buscando información del radar en los datos (puede tardar unos segundos)...")

                def progress_hook(pos, total):
                    print_progress_bar(pos, total, prefix='Analizando:', suffix='Completado', length=50)

                try:
                    # Usar una función optimizada que solo busca SAC/SIC sin decodificar todo.
                    # Analizar solo el primer megabyte para una vista previa rápida.
                    preview_data = analyzer.asterix_data[:1048576]
                    
                    # Ajustar umbral dinámicamente: si el archivo es < 50KB, bajamos la exigencia
                    # para no ignorar sensores en archivos con pocos registros.
                    detection_threshold = 3 if len(preview_data) > 51200 else 1
                    
                    scan_result = find_sensors_in_stream(preview_data, progress_hook=progress_hook, min_occurrences=detection_threshold)
                    sensors_dict = scan_result.get("sensors", {})
                    categories_found = scan_result.get("categories", set())
                except Exception as e:
                    sensors_dict = {}
                    categories_found = set()
                    print(f"[!] Ocurrió un error durante el análisis rápido de sensores: {e}")
                
                if categories_found:
                    cat_str = ", ".join([f"CAT {c:03d}" for c in sorted(categories_found)])
                    print(f"[i] Categorías ASTERIX detectadas: {cat_str}")

                if sensors_dict:
                    # Permitir al usuario elegir el criterio de ordenamiento si hay múltiples sensores
                    if len(sensors_dict) > 1:
                        print("\n[?] ¿Cómo desea ordenar la lista de sensores?")
                        print("    1. Por Identificador (SAC/SIC)")
                        print("    2. Por Volumen de Datos (Cantidad de registros)")
                        s_choice = input("    Seleccione (1-2, Enter para 1): ").strip()
                        if s_choice == '2':
                            sorted_sensors = sorted(sensors_dict.keys(), key=lambda x: sensors_dict[x], reverse=True)
                        else:
                            sorted_sensors = sorted(list(sensors_dict.keys()))
                    else:
                        sorted_sensors = sorted(list(sensors_dict.keys()))

                    print("\n" + "═" * 65)
                    print(f"📡 SENSORES DETECTADOS EN LA MUESTRA ({len(sorted_sensors)})")
                    print("═" * 65)
                    unknown_sensors_indices = []
                    for i, (sac, sic) in enumerate(sorted_sensors):
                        count = sensors_dict[(sac, sic)]
                        is_known = (sac, sic) in KNOWN_SENSORS
                        
                        if is_known:
                            s_info = KNOWN_SENSORS[(sac, sic)]
                            name = s_info.get('name', 'Sin nombre')
                            lat = s_info.get('latitude', 0.0)
                            lon = s_info.get('longitude', 0.0)
                            status = f" - {name} [{lat:.4f}, {lon:.4f}]"
                        else:
                            status = " [⚠️ DESCONOCIDO - Sin parámetros de sitio]"
                            unknown_sensors_indices.append(i)
                        print(f"  [{i+1}] SAC: {sac:03d} / SIC: {sic:03d} ({count} registros){status}")

                    if unknown_sensors_indices:
                        print("\n[!] Se detectaron sensores sin configuración geográfica en 'default-site-params'.")
                        config_now = input("¿Desea configurar alguno de estos sensores ahora para habilitar cálculos de posición? (s/n): ").strip().lower()
                        if config_now == 's':
                            try:
                                idx_to_config = int(input(f"Seleccione el número del sensor a configurar (1-{len(sorted_sensors)}): ")) - 1
                                if 0 <= idx_to_config < len(sorted_sensors):
                                    sel_sac, sel_sic = sorted_sensors[idx_to_config]
                                    print(f"\n[*] Iniciando configuración para Sensor {sel_sac:03d}/{sel_sic:03d}:")
                                    s_data = input_sensor_interactive()
                                    # Registrar en memoria inmediatamente
                                    add_sensor(
                                        s_data['sac'], s_data['sic'], s_data['name'],
                                        s_data['latitude'], s_data['longitude'], 
                                        s_data['elevation'], s_data['description']
                                    )
                                    analyzer.set_sensor_position(
                                        s_data['sac'],
                                        s_data['sic'],
                                        s_data['latitude'],
                                        s_data['longitude'],
                                        s_data['elevation']
                                    )
                                    ask_and_save_sensor(s_data)
                                else:
                                    print("[✗] Selección inválida.")
                            except ValueError:
                                print("[✗] Entrada inválida.")

                    # Si solo hay un sensor, seleccionarlo automáticamente
                    if len(sorted_sensors) == 1:
                        analyzer.selected_sensors = {sorted_sensors[0]}
                        print(f"\n[✓] Único sensor detectado: SAC:{sorted_sensors[0][0]:03d} / SIC:{sorted_sensors[0][1]:03d}")
                        print("[i] Seleccionado automáticamente para el análisis.")
                        analyzer.filter_data_for_selection()
                    else:
                        print("\n[i] Puede seleccionar hasta 5 sensores para el análisis.")
                        print("    Ingrese los números separados por comas (ej: 1,3,5).")
                        print("    Presione Enter o escriba 'all' para analizar todos.")

                        while True:
                            selection_input = input("Seleccione sensores: ").strip().lower()

                            if not selection_input or selection_input == 'all':
                                analyzer.selected_sensors = None
                                analyzer.filtered_asterix_data = None
                                print("[i] Se analizarán todos los sensores detectados.")
                                break
                            
                            try:
                                selected_indices = sorted(list(set([int(i.strip()) - 1 for i in selection_input.split(',')])))

                                if len(selected_indices) > 5:
                                    print("[!] No puede seleccionar más de 5 sensores. Intente de nuevo.")
                                    continue

                                if any(i < 0 or i >= len(sorted_sensors) for i in selected_indices):
                                    print("[!] Uno o más números están fuera de rango. Intente de nuevo.")
                                    continue

                                analyzer.selected_sensors = {sorted_sensors[i] for i in selected_indices}
                                print(f"[✓] Sensores seleccionados para el análisis: {analyzer.selected_sensors}")
                                analyzer.filter_data_for_selection()
                                break
                            except ValueError:
                                print("[!] Entrada inválida. Ingrese números separados por comas (ej: 1,3,5).")

                elif preview_data:
                    print("[i] No se encontraron sensores (SAC/SIC) en la muestra de datos inicial.")
        elif choice == '2':
            # Modo interactivo avanzado con soporte DMS
            try:
                sensor_data = input_sensor_interactive()
                analyzer.set_sensor_position(
                    sensor_data['sac'],
                    sensor_data['sic'],
                    sensor_data['latitude'],
                    sensor_data['longitude'],
                    sensor_data['elevation']
                )
                # Añadir la opción de guardar
                ask_and_save_sensor(sensor_data)
            except Exception as e:
                print(f"[✗] Error: {e}")
        
        elif choice == '3':
            # Modo básico con grados decimales
            try:
                sac = int(input("SAC: "))
                sic = int(input("SIC: "))
                lat = float(input("Latitud (grados decimales): "))
                lon = float(input("Longitud (grados decimales): "))
                elev_input = input("Elevación (pies, opcional, enter para dejar en blanco): ").strip()
                elev = float(elev_input) if elev_input else 0.0
                analyzer.set_sensor_position(sac, sic, lat, lon, elev)
                
                # Crear diccionario de datos del sensor para guardarlo
                sensor_data = {
                    'sac': sac,
                    'sic': sic,
                    'name': f"Sensor {sac}/{sic}",
                    'latitude': lat,
                    'longitude': lon,
                    'elevation': elev,
                    'description': "Sensor añadido manualmente via modo decimal."
                }
                ask_and_save_sensor(sensor_data)
            except ValueError:
                print("[✗] Valores inválidos")
        
        elif choice == '4':
            if analyzer.asterix_data:
                try:
                    analyzer.decode_data()
                except Exception as e:
                    print(f"\n[✗] Error durante la decodificación: {e}")
            else:
                print("[!] Primero carga un archivo")
        
        elif choice == '5':
            if analyzer.decoded_records:
                display_sensors_in_data(analyzer.decoded_records)
            else:
                print("[!] Primero decodifica los datos (opción 4)")
        
        elif choice == '6':
            output_dir = input("Directorio de salida (default: c:/documentos/resultados): ").strip().strip('"').strip("'") or "c:/documentos/resultados"
            analyzer.export(output_dir)
        
        elif choice == '7':
            if analyzer.decoded_records:
                report = ReportGenerator.generate_summary(analyzer.records, analyzer.sensor_registry)
                print("\n" + report)
            else:
                print("[!] No hay datos en memoria. Asegúrese de haber cargado un archivo (1) y decodificado (4).")
        
        elif choice == '8':
            # Selector de radares disponibles
            try:
                from config import get_all_available_radars, load_radar_parameters, get_sensors_from_radar_data
                available_radars = get_all_available_radars()
                print(f"\n[i] Explorando base de datos en 'default-site-params/'...")
                print(f"[i] Se encontraron {len(available_radars)} configuraciones de radar.")
                
                selector = RadarSelector()
                if selector.radars:
                    selected_ids = selector.select_radars_interactive()
                    if selected_ids:
                        selector.display_radar_details(selected_ids)
                        
                        # Vincular los radares seleccionados al analizador para el procesamiento de coordenadas
                        print("\n[*] Cargando parámetros técnicos de los radares en el analizador...")
                        for rid in selected_ids:
                            r_data = load_radar_parameters(rid)
                            if r_data:
                                sensors = get_sensors_from_radar_data(r_data)
                                loc = r_data.get('location', {})
                                lat = loc.get('latitude') or r_data.get('RADAR_LAT') or 0
                                lon = loc.get('longitude') or r_data.get('RADAR_LON') or 0
                                alt = loc.get('altitude_ft') or loc.get('altitude') or 0
                                for sac, sic in sensors:
                                    analyzer.set_sensor_position(int(sac), int(sic), float(lat), float(lon), float(alt))
                        
                        # Opción de exportar
                        export_choice = input("\n¿Exportar a archivo JSON? (yes/no): ").strip().lower()
                        if export_choice == "yes":
                            filename = input("Ingrese nombre de archivo (default: selected_radars.json): ").strip().strip('"').strip("'")
                            if not filename:
                                filename = "selected_radars.json"
                            selector.export_selected_radars(selected_ids, filename)
                else:
                    print("[!] No hay radares disponibles en default-site-params/")
            except Exception as e:
                print(f"[✗] Error: {e}")
        
        elif choice == '9':
            # Analizador de Modo A/C
            if analyzer.decoded_records:
                try:
                    mode_analyzer = ModeAnalyzer()
                    print("\n[*] Analizando Modo A/C en registros decodificados...")
                    
                    results = mode_analyzer.analyze_batch(analyzer.decoded_records)
                    
                    # Mostrar opciones
                    print("\nOpciones de visualización:")
                    print("1. Ver todos los registros individualmente")
                    print("2. Ver solo estadísticas")
                    print("3. Exportar a JSON y CSV")
                    print("4. Ver registro específico")
                    
                    sub_choice = input("\nSeleccionar (1-4): ").strip()
                    
                    if sub_choice == '1':
                        for idx, detection in enumerate(results[:20]):  # Mostrar primeros 20
                            mode_analyzer.display_single_record(detection, idx)
                        if len(results) > 20:
                            print(f"[*] Se mostraron 20 de {len(results)} registros")
                    
                    elif sub_choice == '2':
                        mode_analyzer.display_statistics()
                    
                    elif sub_choice == '3':
                        mode_analyzer.export_to_json()
                        mode_analyzer.export_to_csv()
                    
                    elif sub_choice == '4':
                        try:
                            rec_num = int(input(f"Ingrese número de registro (1-{len(results)}): "))
                            if 1 <= rec_num <= len(results):
                                mode_analyzer.display_single_record(results[rec_num - 1], rec_num - 1)
                            else:
                                print("[✗] Número de registro inválido")
                        except ValueError:
                            print("[✗] Valor inválido")
                
                except Exception as e:
                    print(f"[✗] Error en análisis: {e}")
            else:
                print("[!] Primero decodifica los datos (opción 4)")
        
        elif choice == '10':
            # Analizador de vuelos por Squawk
            if analyzer.decoded_records:
                try:
                    flight_analyzer = FlightLossAnalyzer()
                    categories_present = {rec.get('category') for rec in analyzer.decoded_records}
                    is_radar_present = any(cat in [1, 2, 34, 48, 62] for cat in categories_present)
                    is_adsb_only = 21 in categories_present and not is_radar_present
                    
                    # Opción para configurar RPM de la antena
                    if is_radar_present:
                        print("\nConfiguración de Antena (para datos de Radar: CAT001/002/048):")
                        print(f"RPM actual: {flight_analyzer.antenna_rpm}")
                        custom_rpm = input("Ingrese RPM de la antena (Enter para default): ").strip()
                        
                        if custom_rpm:
                            try:
                                flight_analyzer.update_antenna_speed(float(custom_rpm))
                            except ValueError:
                                print("[!] RPM inválido, usando default (12 RPM)")
                    elif is_adsb_only:
                        print("\n[i] Se han detectado principalmente datos ADS-B (CAT021).")
                        print("[i] El análisis se basará en el intervalo de actualización entre reportes, no en la rotación de antena.")

                    # Analizar
                    print("\n[*] Analizando vuelos por Squawk/ID...")
                    flight_analyzer.analyze_records(analyzer.decoded_records, is_adsb_only=is_adsb_only)
                    
                    # Mostrar opciones
                    print("\nOpciones de visualización:")
                    if is_adsb_only:
                        print("1. Resumen de vuelos (intervalos de actualización)")
                        print("2. Top 10 por cantidad de reportes")
                        print("3. Top 10 por máximo intervalo (posibles pérdidas de señal)")
                    else:
                        print("1. Resumen de vuelos por Squawk (pérdidas por rotación)")
                        print("2. Top 10 Squawks por cantidad de vuelos")
                        print("3. Top 10 Squawks por pérdidas estimadas")
                    
                    print("4. Estadísticas generales")
                    print("5. Análisis detallado de Squawk específico")
                    print("6. Exportar a JSON y CSV")
                    
                    sub_choice = input("\nSeleccionar (1-6): ").strip()
                    
                    if sub_choice == '1':
                        flight_analyzer.display_flight_summary(is_adsb_only=is_adsb_only)
                    
                    elif sub_choice == '2':
                        flight_analyzer.display_top_squawks(limit=10, sort_by="flights")
                    
                    elif sub_choice == '3':
                        sort_key = "max_interval" if is_adsb_only else "losses"
                        flight_analyzer.display_top_squawks(limit=10, sort_by=sort_key)
                    
                    elif sub_choice == '4':
                        flight_analyzer.display_statistics()
                    
                    elif sub_choice == '5':
                        squawk_input = input("Ingrese código Squawk/ID (octal, ej: 7654): ").strip()
                        flight_analyzer.display_detailed_analysis(squawk_input)
                    
                    elif sub_choice == '6':
                        flight_analyzer.export_to_json()
                        flight_analyzer.export_to_csv()
                
                except Exception as e:
                    print(f"[✗] Error en análisis: {e}")
            else:
                print("[!] Primero decodifica los datos (opción 4)")
        
        elif choice == '11':
            if analyzer.records:
                # Verificar si hay registros con coordenadas antes de intentar mostrar
                has_coords = any(r.get('latitude') is not None for r in analyzer.records)
                if not has_coords:
                    print("[!] Los registros existen pero ninguno tiene coordenadas geográficas.")
                    print("[i] Esto ocurre cuando no se ha configurado la posición del sensor (SAC/SIC). Use las opciones 2, 3 u 8.")
                
                fl_input = input("Mínimo Nivel de Vuelo (FL) a mostrar (Enter para todos): ").strip()
                try:
                    min_fl = float(fl_input) if fl_input else None
                except ValueError:
                    print("[!] Error: El nivel de vuelo debe ser un valor numérico.")
                    continue
                squawk_input = input("Código Squawk a filtrar (octal, Enter para todos): ").strip()
                analyzer.preview_map(min_fl=min_fl, squawk_filter=squawk_input)
            else:
                print("[!] No hay datos decodificados. Ejecuta la opción 4 primero.")
        elif choice == '12':
            if analyzer.records:
                analyzer.preview_ppi_radar()
            else:
                print("[!] No hay datos decodificados. Ejecuta la opción 4 primero.")

        elif choice == '13':
            print("[*] Saliendo...")
            break
        
        else:
            print("[ERROR] Opción inválida (1-13)")


if __name__ == "__main__":
    main()