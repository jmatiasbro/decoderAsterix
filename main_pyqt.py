"""
main_pyqt.py — ASTERIX Radar Decoder (Arquitectura Modular)
============================================================
Punto de entrada de la GUI PyQt6.

Módulos:
  - geo_utils         → StereographicLocal, cargar_sensores, METERS_PER_NM
  - asterix_worker    → AsterixWorker QThread (scan + play)
  - radar_widget      → RadarWidget PPI (visualización)
  - dashboard_widget  → DashboardWidget (control lateral Glassmorphism)

Colores:  Fondo #0B0E14 | Ploteos Cian #00FFFF | Barrido Verde #39FF14

FLUJO FASE 1 (Decodificar Archivo):
  Paso 1 (Cargar Archivo): Usuario selecciona PCAP. Sistema escanea superficialmente
    para contar frames, detectar SAC/SIC y habilitar botón "Decodificar Archivo".
    Play permanece deshabilitado.
  Paso 2 (Presionar Decodificar): AsterixWorker procesa en segundo plano, indexa
    timestamps, llena buffers y ejecuta relocalización geográfica (Fase 2).
    Al terminar, se habilita Play.
"""

import sys
import os
import time
import json
import glob
import math
import tempfile
import shutil
from typing import Dict, Tuple, List, Optional, Set, Any

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout,
    QHBoxLayout, QFileDialog, QMessageBox, QGroupBox, QSizePolicy,
    QListWidget, QListWidgetItem, QPushButton, QLabel, QSlider, QComboBox,
    QSpinBox, QCheckBox
)
from PyQt6.QtCore import Qt, QThread, QTimer, pyqtSignal
from PyQt6.QtGui import QFont, QColor, QPainterPath

import ezdxf

from geo_utils import cargar_sensores, METERS_PER_NM
from asterix_worker import AsterixWorker
from radar_widget import RadarWidget, RadarPlot
from dashboard_widget import DashboardWidget
from io_tools import load_pcap


# ============================================================
# CONSTANTES DE COLOR
# ============================================================
COLOR_BG_MAIN = QColor("#0B0E14")


# ============================================================
# HILO LIGERO DE ESCANEO SUPERFICIAL (FASE 1)
# ============================================================
class PcapScannerThread(QThread):
    """
    Escanea superficialmente un PCAP para detectar:
    - Cantidad total de frames
    - SAC/SIC del primer radar detectado
    - Duración estimada (primer y último ToD)

    NO decodifica datos completos. Solo lectura rápida para habilitar
    la UI y preparar al usuario para la decodificación real.
    """
    scan_result = pyqtSignal(int, float, set)  # total_frames, duration_sec, detected_sensors
    scan_error = pyqtSignal(str)

    def __init__(self, pcap_path: str):
        super().__init__()
        self.pcap_path = pcap_path

    def run(self):
        from scapy.all import PcapReader, UDP
        from native_asterix import parse_payload

        if not os.path.exists(self.pcap_path):
            self.scan_error.emit(f"PCAP no encontrado: {self.pcap_path}")
            return

        try:
            reader = PcapReader(self.pcap_path)
        except Exception as e:
            self.scan_error.emit(f"Error abriendo PCAP: {e}")
            return

        total_pkts = 0
        first_tod = None
        last_tod = None
        detected_sensors: Set[Tuple[int, int]] = set()
        max_scan = 20000  # Límite para escaneo superficial rápido

        for i, pkt in enumerate(reader):
            if i >= max_scan:
                break
            try:
                if UDP not in pkt:
                    continue
                payload = bytes(pkt[UDP].payload)
                if len(payload) <= 10:
                    continue

                records = parse_payload(payload)
                if not records:
                    continue

                for rec in records:
                    cat = rec.get('category')
                    if cat not in (1, 2, 21, 34, 48, 62):
                        continue
                    
                    sac = rec.get('sac')
                    sic = rec.get('sic')
                    if sac is not None and sic is not None:
                        detected_sensors.add((sac, sic))

                    tod = rec.get('timestamp')
                    if tod is not None:
                        if first_tod is None:
                            first_tod = tod
                        last_tod = tod
                    
                    total_pkts += 1
            except Exception:
                continue

        reader.close()

        duration = 0.0
        if first_tod is not None and last_tod is not None:
            duration = last_tod - first_tod
            if duration < 0:
                duration += 86400.0

        self.scan_result.emit(total_pkts, duration, detected_sensors)


# ============================================================
# HILO DE CARGA DEL DXF (asíncrono)
# ============================================================
class DxfLoaderThread(QThread):
    """Carga mapa.dxf en hilo separado. Emite segmentos serializables."""
    dxf_data = pyqtSignal(object, float, float, float, float)
    dxf_error = pyqtSignal(str)

    def __init__(self, filepath: str):
        super().__init__()
        self.filepath = filepath

    def run(self):
        # Intentar ruta directa o relativa al directorio raíz del proyecto
        path = self.filepath
        if not os.path.exists(path):
            base_dir = os.path.dirname(os.path.abspath(__file__))
            path = os.path.join(base_dir, self.filepath)
        if not os.path.exists(path):
            # Probar un nivel superior
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            path = os.path.join(base_dir, self.filepath)
        
        if not os.path.exists(path):
            self.dxf_error.emit(f"DXF no encontrado: {self.filepath}")
            return
            
        try:
            doc = ezdxf.readfile(path)
            msp = doc.modelspace()
            # Segmentos raw: coordenadas en NM (NO multiplicadas por METERS_PER_NM)
            # El DXF fue diseñado para San Luis (lat=-33.274444, lon=-66.348611)
            # y las coordenadas representan offsets en NM desde ese punto.
            segments: list = []
            min_x = min_y = float('inf')
            max_x = max_y = float('-inf')

            def update_ext(x, y):
                nonlocal min_x, max_x, min_y, max_y
                min_x = min(min_x, x)
                max_x = max(max_x, x)
                min_y = min(min_y, y)
                max_y = max(max_y, y)

            def add_seg(t, layer, *coords):
                segments.append((t, layer, *coords))
                for i in range(0, len(coords), 2):
                    update_ext(coords[i], coords[i+1])

            for entity in msp:
                try:
                    dxft = entity.dxftype()
                    layer = entity.dxf.layer
                    if dxft == 'LINE':
                        add_seg('M', layer, entity.dxf.start.x, entity.dxf.start.y)
                        add_seg('L', layer, entity.dxf.end.x, entity.dxf.end.y)
                    elif dxft == 'LWPOLYLINE':
                        pts = list(entity.get_points())
                        if pts:
                            add_seg('M', layer, pts[0][0], pts[0][1])
                            for p in pts[1:]:
                                add_seg('L', layer, p[0], p[1])
                            if entity.closed:
                                segments.append(('C', layer))
                    elif dxft == 'POLYLINE':
                        verts = list(entity.vertices)
                        if verts:
                            v0 = verts[0].dxf.location
                            add_seg('M', layer, v0.x, v0.y)
                            for v in verts[1:]:
                                loc = v.dxf.location
                                add_seg('L', layer, loc.x, loc.y)
                            if entity.is_closed:
                                segments.append(('C', layer))
                    elif dxft == 'ARC':
                        cx, cy = entity.dxf.center.x, entity.dxf.center.y
                        r = entity.dxf.radius
                        sa, ea = entity.dxf.start_angle, entity.dxf.end_angle
                        steps = max(12, int(abs(ea - sa) / 5))
                        first = True
                        for i in range(steps + 1):
                            a = math.radians(sa + (ea - sa) * i / steps)
                            x = cx + r * math.cos(a)
                            y = cy + r * math.sin(a)
                            if first:
                                add_seg('M', layer, x, y)
                                first = False
                            else:
                                add_seg('L', layer, x, y)
                    elif dxft == 'CIRCLE':
                        cx, cy = entity.dxf.center.x, entity.dxf.center.y
                        r = entity.dxf.radius
                        first = True
                        for i in range(37):
                            a = math.radians(360.0 * i / 36)
                            x = cx + r * math.cos(a)
                            y = cy + r * math.sin(a)
                            if first:
                                add_seg('M', layer, x, y)
                                first = False
                            else:
                                add_seg('L', layer, x, y)
                        segments.append(('C', layer))
                except Exception:
                    continue

            if min_x == float('inf'):
                self.dxf_error.emit("Sin entidades válidas en DXF")
                return
            self.dxf_data.emit(segments, min_x, min_y, max_x, max_y)
        except Exception as e:
            self.dxf_error.emit(f"Error DXF: {e}")


def build_path_from_segments(segments: list) -> QPainterPath:
    """Reconstruye QPainterPath desde segmentos serializables."""
    path = QPainterPath()
    for seg in segments:
        t = seg[0]
        if t == 'M':
            path.moveTo(seg[1], seg[2])
        elif t == 'L':
            path.lineTo(seg[1], seg[2])
        elif t == 'C':
            path.closeSubpath()
    return path


def raw_decode_cat48(payload: bytes) -> List[Dict[str, Any]]:
    """Raw decoder de emergencia para CAT048 (fallback si asterix falla), corregido."""
    if not payload or len(payload) < 3:
        return []

    if payload[0] != 0x30:
        return []

    try:
        length = (payload[1] << 8) | payload[2]
        if length > len(payload):
            return []
        payload = payload[:length]
    except IndexError:
        return []

    fspec_bytes = []
    idx = 3
    while idx < length:
        b = payload[idx]
        fspec_bytes.append(b)
        idx += 1
        if not (b & 1):
            break
    
    if not fspec_bytes:
        return []
    
    rec = {'category': 48}
    fspec1 = fspec_bytes[0]

    # I048/010 Data Source Identifier (SAC/SIC)
    if fspec1 & 0x80:
        if idx + 2 <= length:
            rec['I048/010'] = {'SAC': payload[idx], 'SIC': payload[idx+1]}
            idx += 2
            
    # I048/140 Time of Day
    if fspec1 & 0x40:
        if idx + 3 <= length:
            tod = ((payload[idx] << 16) | (payload[idx+1] << 8) | payload[idx+2]) / 128.0
            rec['I048/140'] = {'Time of Day': tod}
            idx += 3

    # I048/020 Target Report Descriptor (variable)
    if fspec1 & 0x20:
        while idx < length:
            b = payload[idx]
            idx += 1
            if not (b & 1): break
            
    # I048/040 Measured Position in Polar Coordinates
    if fspec1 & 0x10:
        if idx + 4 <= length:
            rho = ((payload[idx] << 8) | payload[idx+1]) / 256.0 # NM
            theta = ((payload[idx+2] << 8) | payload[idx+3]) * (360.0 / 65536.0) # degrees
            rec['I048/040'] = {'RHO': rho, 'THETA': theta}
            idx += 4
            
    # I048/070 Mode-3/A Code
    if fspec1 & 0x08:
        if idx + 2 <= length:
            idx += 2

    # I048/090 Flight Level
    if fspec1 & 0x04:
        if idx + 2 <= length:
            idx += 2

    # I048/130 Radar Plot Characteristics (compound)
    if fspec1 & 0x02:
        while idx < length:
            b = payload[idx]
            idx += 1
            if not (b & 1): break

    # Add default SAC/SIC if missing to allow plot drawing
    if 'I048/010' not in rec:
        rec['I048/010'] = {'SAC': 0, 'SIC': 0}

    # Only return if we have the minimum data for plotting
    if 'I048/040' in rec and 'I048/140' in rec:
        return [rec]

    return []



# ============================================================
# VENTANA PRINCIPAL
# ============================================================
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("ASTERIX Radar Decoder - Multi-Category")
        self.resize(1280, 800)
        self.main_sensor_set = False
        self._sensor_rpms: Dict[Tuple[int, int], float] = {}
        self._center_sensor_key: Optional[Tuple[int, int]] = None
        self._decode_complete = False  # FASE 1: flag de decodificación completada

        # Cargar sensores — Resolve default-site-params directory robustly
        base_dir = os.path.dirname(os.path.abspath(__file__))
        site_params_dir = os.path.join(base_dir, "default-site-params")
        self.sensores = cargar_sensores(site_params_dir)

        # Filtro de Sensores - memoria activa
        self.sensores_conocidos: Set[str] = set()

        # Worker y thread
        self._worker: Optional[AsterixWorker] = None
        self._playing = False
        self._pcap_duration = 0.0
        self._total_frames = 0
        self._pcap_path = ""  # Sin archivo por defecto

        self.cache_dir = tempfile.mkdtemp(prefix="asterix_cache_")
        print(f"[Main] Directorio de caché de sesión creado en: {self.cache_dir}")

        self._setup_ui()
        self._load_dxf_async()

        # FASE 4: Conectar señal de contadores de categoría
        # self.radar.category_counts_updated.connect(self.dashboard.update_category_counts)

        # REGLA DE ESTILO (Inyectar al final del __init__):
        estilo_profesional = """
/* Fondo principal y texto general */
QMainWindow, QWidget {
    background-color: #1A1C23;
    color: #E0E6ED;
    font-family: 'Segoe UI', Arial, sans-serif;
    font-size: 10pt;
}

/* Estilo para los paneles de agrupación */
QGroupBox {
    background-color: #242730;
    border: 1px solid #3A3F4C;
    border-radius: 6px;
    margin-top: 18px;
    font-weight: bold;
}
QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 0 8px;
    color: #61AFEF; /* Azul técnico */
    background-color: #1A1C23;
    border-radius: 4px;
}

/* Botones modernos y responsivos */
QPushButton {
    background-color: #2D313C;
    border: 1px solid #4B5263;
    border-radius: 4px;
    padding: 6px 12px;
    color: #FFFFFF;
    font-weight: bold;
}
QPushButton:hover {
    background-color: #3E4451;
    border: 1px solid #61AFEF;
    color: #61AFEF;
}
QPushButton:pressed {
    background-color: #61AFEF;
    color: #1A1C23;
}

/* Lista de sensores (QListWidget) */
QListWidget {
    background-color: #1A1C23;
    border: 1px solid #3A3F4C;
    border-radius: 4px;
    padding: 4px;
}
QListWidget::item {
    padding: 4px;
    border-bottom: 1px solid #242730;
}
QListWidget::item:hover {
    background-color: #2D313C;
}
QListWidget::item:selected {
    background-color: #3E4451;
    color: #61AFEF;
    border-left: 3px solid #61AFEF;
}
"""

        self.setStyleSheet(estilo_profesional)

    # ----------------------------------------------------------
    # UI
    # ----------------------------------------------------------
    def _setup_ui(self):
        # REGLA DE ARQUITECTURA PRINCIPAL:
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.layout_principal = QVBoxLayout(self.central_widget)
        self.layout_principal.setContentsMargins(5, 5, 5, 5)
        self.layout_principal.setSpacing(5)

        # REGLA DE LA BARRA SUPERIOR:
        self.panel_superior = QWidget()
        self.panel_superior.setMaximumHeight(130) # Altura fija tipo "Dashboard"
        self.panel_superior.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        self.layout_superior = QHBoxLayout(self.panel_superior)
        self.layout_superior.setContentsMargins(0, 0, 0, 0)

        # 1. Zona de controles de reproducción (Play/Stop/Carga)
        self.grupo_reproduccion = QGroupBox("Controles de Archivo")
        layout_reproduccion = QHBoxLayout()
        layout_reproduccion.setSpacing(10)
        layout_reproduccion.setContentsMargins(10, 10, 10, 10)

        self.btn_cargar = QPushButton("Cargar Archivo")
        self.btn_decodificar = QPushButton("Decodificar / Play")
        self.btn_detener = QPushButton("Detener")

        self.btn_cargar.setMinimumHeight(30)
        self.btn_decodificar.setMinimumHeight(30)
        self.btn_detener.setMinimumHeight(30)
        self.btn_decodificar.setEnabled(False)

        layout_reproduccion.addWidget(self.btn_cargar)
        layout_reproduccion.addWidget(self.btn_decodificar)
        layout_reproduccion.addWidget(self.btn_detener)

        self.grupo_reproduccion.setLayout(layout_reproduccion)
        self.layout_superior.addWidget(self.grupo_reproduccion)

        self.btn_cargar.clicked.connect(self._on_load_pcap)
        self.btn_decodificar.clicked.connect(self._on_play_toggle)
        self.btn_detener.clicked.connect(self._on_stop)

        # 2. Zona TDD: Tiempo, Slider y Velocidad
        self.grupo_tdd = QGroupBox("Tiempo")
        layout_tdd = QVBoxLayout()
        layout_tdd.setSpacing(4)
        layout_tdd.setContentsMargins(8, 8, 8, 8)

        # TDD Label: tiempo actual
        self.lbl_tiempo = QLabel("00:00:00")
        self.lbl_tiempo.setFont(QFont("Monospace", 14, QFont.Weight.Bold))
        self.lbl_tiempo.setStyleSheet("color: #00FF00;")
        self.lbl_tiempo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout_tdd.addWidget(self.lbl_tiempo)

        # Slider de tiempo
        self.slider_tiempo = QSlider(Qt.Orientation.Horizontal)
        self.slider_tiempo.setMinimum(0)
        self.slider_tiempo.setMaximum(1000)
        self.slider_tiempo.setValue(0)
        self.slider_tiempo.setEnabled(False)
        layout_tdd.addWidget(self.slider_tiempo)

        # Combo de velocidad
        self.combo_velocidad = QComboBox()
        self.combo_velocidad.addItems(["1x", "2x", "4x", "5x", "10x"])
        self.combo_velocidad.setCurrentIndex(0)
        layout_tdd.addWidget(self.combo_velocidad)

        self.grupo_tdd.setLayout(layout_tdd)
        self.layout_superior.addWidget(self.grupo_tdd)

        # 3. Zona del Filtro de Sensores
        self.grupo_sensores = QGroupBox("Filtro de Sensores Múltiple")
        layout_sensores = QHBoxLayout() # Horizontal para que conviva la lista y los botones

        # Botones apilados verticalmente a la izquierda de la lista
        layout_botones = QVBoxLayout()
        self.btn_todos = QPushButton("Todos")
        self.btn_ninguno = QPushButton("Ninguno")
        layout_botones.addWidget(self.btn_todos)
        layout_botones.addWidget(self.btn_ninguno)
        layout_sensores.addLayout(layout_botones)

        # Lista de sensores a la derecha de los botones
        self.lista_sensores = QListWidget()
        layout_sensores.addWidget(self.lista_sensores, stretch=1) # Le damos stretch para que ocupe el ancho sobrante

        self.grupo_sensores.setLayout(layout_sensores)
        self.layout_superior.addWidget(self.grupo_sensores, stretch=2)

        # Conexiones de señales del filtro
        self.sensores_activos = set()
        self.lista_sensores.itemChanged.connect(self.actualizar_filtro)
        self.lista_sensores.itemClicked.connect(self._on_sensor_item_clicked)
        self.btn_todos.clicked.connect(self.seleccionar_todos)
        self.btn_ninguno.clicked.connect(self.deseleccionar_todos)

        # FASE 1: Conectar señales TDD
        self.combo_velocidad.currentIndexChanged.connect(self.cambiar_velocidad)
        self.slider_tiempo.sliderMoved.connect(self.seek_tiempo)
        
        # Historial y Estela
        self.grupo_hist = QGroupBox("Historial / Estela")
        l_hist = QVBoxLayout()

        # Fila 1: Modo de visualización
        l_modo = QHBoxLayout()
        self.lbl_mode = QLabel("Modo:")
        self.lbl_mode.setStyleSheet("background-color: transparent; border: none; color: #E0E6ED; font-weight: normal;")
        self.combo_mode = QComboBox()
        self.combo_mode.addItems(["Tracking", "Historic"])
        self.combo_mode.setCurrentText("Tracking")
        self.combo_mode.setStyleSheet("background-color: #2D313C; color: white; border: 1px solid #4B5263; border-radius: 4px; padding: 2px;")
        l_modo.addWidget(self.lbl_mode)
        l_modo.addWidget(self.combo_mode, stretch=1)

        # Fila 2: Cantidad de puntos
        l_cant = QHBoxLayout()
        lbl_cant = QLabel("Puntos:")
        lbl_cant.setStyleSheet("background-color: transparent; border: none; color: #E0E6ED; font-weight: normal;")
        self.spin_hist = QSpinBox()
        self.spin_hist.setRange(0, 500)
        self.spin_hist.setValue(500)
        self.spin_hist.setStyleSheet("background-color: #2D313C; color: white; border: 1px solid #4B5263; border-radius: 4px; padding: 2px;")
        l_cant.addWidget(lbl_cant)
        l_cant.addWidget(self.spin_hist, stretch=1)
        
        self.btn_clear_hist = QPushButton("Limpiar")
        self.btn_clear_hist.setStyleSheet("""
            QPushButton {
                background-color: rgba(244, 67, 54, 150);
                border: 1px solid #F44336;
            }
            QPushButton:hover {
                background-color: #F44336;
                color: white;
            }
        """)
        
        self.chk_sweep = QCheckBox("Barrido Radar")
        self.chk_sweep.setChecked(True)
        self.chk_sweep.setStyleSheet("""
            QCheckBox {
                color: #E0E6ED;
                background-color: transparent;
                font-weight: normal;
                border: none;
                margin-top: 4px;
            }
            QCheckBox::indicator {
                width: 14px;
                height: 14px;
                border: 1px solid #00E5FF;
                background-color: #2D313C;
                border-radius: 3px;
            }
            QCheckBox::indicator:checked {
                background-color: #00E5FF;
                border: 1px solid #00E5FF;
            }
        """)
        
        l_hist.addLayout(l_modo)
        l_hist.addLayout(l_cant)
        l_hist.addWidget(self.btn_clear_hist)
        l_hist.addWidget(self.chk_sweep)
        self.grupo_hist.setLayout(l_hist)
        
        self.layout_superior.addWidget(self.grupo_hist)

        # ---- RADAR WIDGET (PPI central) ----
        self.radar = RadarWidget(sensores=self.sensores)
        self.radar.sensores_visibles = self.sensores_activos
        self.radar.setStyleSheet("background-color: transparent;")

        # Conectar señales que dependen de self.radar (creado arriba)
        self.combo_mode.setCurrentText(self.radar.history_mode)
        self.combo_mode.currentTextChanged.connect(self._on_mode_changed)
        self.spin_hist.valueChanged.connect(self._on_history_limit_changed)
        self.btn_clear_hist.clicked.connect(self._clear_history)
        self.chk_sweep.toggled.connect(self.radar.set_sweep_enabled)

        # REGLA DE ENSAMBLAJE (Al final de la configuración de la UI):
        self.layout_principal.addWidget(self.panel_superior)
        self.layout_principal.addWidget(self.radar, stretch=1)

    # ----------------------------------------------------------
    # CARGA DEL DXF (asíncrona)
    # ----------------------------------------------------------
    def _load_dxf_async(self):
        self.dxf_loader = DxfLoaderThread("mapa/mapa.dxf")
        self.dxf_loader.dxf_data.connect(self._on_dxf_data)
        self.dxf_loader.dxf_error.connect(self._on_dxf_error)
        self.dxf_loader.start()

    def _on_dxf_data(self, segments, min_x, min_y, max_x, max_y):
        self.radar.set_raw_map_segments(segments, min_x, min_y, max_x, max_y)
        self.radar._set_default_view()
        # self.dashboard.set_progress_text("Mapa DXF cargado ✓ (reproyectable)")

    def _on_dxf_error(self, msg):
        print(f"[DXF] {msg}")

    def _on_history_limit_changed(self, val: int):
        self.radar.history_limit = val
        self.radar.update()


    def _clear_history(self):
        if hasattr(self.radar, 'history'):
            self.radar.history.clear()
        if hasattr(self.radar, 'plots_raw'):
            self.radar.plots_raw.clear()
        self.radar.update()
        # self.dashboard.set_progress_text("Mapa DXF: no disponible")

    def _on_mode_changed(self, mode: str):
        """Handle UI mode change between Tracking and Historic."""
        self.radar.history_mode = mode
        self.radar.update()
    # ----------------------------------------------------------
    # WORKER ASTERIX
    # ----------------------------------------------------------
    def _start_worker(self):
        if self._worker is not None or not self._pcap_path:
            return

        self._worker = AsterixWorker(
            pcap_file=self._pcap_path,
            sensores=self.sensores,
            cache_dir=self.cache_dir)
        self._connect_worker_signals()
        self._worker.start()

    def _connect_worker_signals(self):
        if self._worker is None:
            return
        self._worker.new_plot.connect(self.radar.on_new_plot)
        # FASE 2: Interceptar batch para detectar sensores dinámicamente
        self._worker.new_plot_batch.connect(self._on_new_plot_batch)
        self._worker.scan_progress.connect(self._on_scan_progress)
        self._worker.scan_done.connect(self._on_scan_done)
        self._worker.playback_finished.connect(self._on_playback_finished)
        self._worker.sensor_detected.connect(self._on_sensor_detected)
        self._worker.state_changed.connect(self._on_worker_state_changed)
        self._worker.clear_plots.connect(self.radar.stop_sweep)
        self._worker.rotation_speed_detected.connect(self._on_rotation_speed_detected)
        self._worker.sensors_scanned.connect(self._on_sensors_scanned)
        self._worker.north_mark_detected.connect(self._on_north_mark_detected)
        # FASE 1: Señales TDD
        self._worker.tod_update.connect(self._on_tod_update)
        self._worker.progress_updated.connect(self.actualizar_progreso)

    # ----------------------------------------------------------
    # FASE 2: DETECCIÓN DINÁMICA DE SENSORES EN PLOTS ENTRANTES
    # ----------------------------------------------------------
    def _on_new_plot_batch(self, batch: List[Any]):
        if not batch:
            return

        # Si la proyección no se ha inicializado (ej. archivo CAT 62 sin coordenadas de radar),
        # auto-centramos la proyección en el primer plot válido del lote para habilitar el mapa y tracking.
        if not self.radar.projection_set:
            for datos_recibidos in batch:
                if isinstance(datos_recibidos, list):
                    lista_plots = datos_recibidos
                elif isinstance(datos_recibidos, dict) and 'plots' in datos_recibidos:
                    lista_plots = datos_recibidos['plots']
                else:
                    lista_plots = [datos_recibidos]
                
                found = False
                for plot in lista_plots:
                    if isinstance(plot, dict):
                        plat = plot.get('lat')
                        plon = plot.get('lon')
                        if plat is not None and plon is not None and abs(plat) > 1.0 and abs(plon) > 1.0:
                            sid = plot.get('sac_sic', '0/0')
                            try:
                                sac, sic = map(int, sid.split('/'))
                            except ValueError:
                                sac, sic = 0, 0
                            print(f"[AUTOCENTER FALLBACK] Inicializando proyección en primer blanco válido: Lat={plat:.5f}, Lon={plon:.5f}")
                            self.radar.reset_origin_for_new_file(
                                float(plat), float(plon), sac, sic, "System Center (CAT62)"
                            )
                            found = True
                            break
                if found:
                    break

        # El router ya ha normalizado el batch. No se necesita búsqueda recursiva aquí.
        for datos_recibidos in batch:
            if isinstance(datos_recibidos, list):
                lista_plots = datos_recibidos
            elif isinstance(datos_recibidos, dict) and 'plots' in datos_recibidos:
                lista_plots = datos_recibidos['plots']
            else:
                lista_plots = [datos_recibidos]

            for plot in lista_plots:
                if not isinstance(plot, dict):
                    continue

                # Las claves 'sac_sic', 'lat', 'lon' ya vienen normalizadas por el router.
                sensor_id = plot.get('sac_sic', f"UNK_CAT{plot.get('category', 'XX')}")
                lat = plot.get('lat')
                lon = plot.get('lon')
                cat = plot.get('category', 'XX')

                # Inyectar claves de renderizado para el RadarWidget
                if lat is not None:
                    plot['lat_render'] = float(lat)
                if lon is not None:
                    plot['lon_render'] = float(lon)

                if sensor_id not in self.sensores_conocidos:
                    self.sensores_conocidos.add(sensor_id)
                    self.sensores_activos.add(sensor_id)
                    item = QListWidgetItem(f"{sensor_id} (CAT {cat})")
                    item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                    item.setCheckState(Qt.CheckState.Checked)
                    item.setData(Qt.ItemDataRole.UserRole, sensor_id)
                    self.lista_sensores.addItem(item)

                # Enviar el plot normalizado al RadarWidget
                if lat is not None and lon is not None:
                    self.radar.agregar_plot_individual(plot, trigger_update=False)

        # Refrescar el widget de radar una única vez para todo el lote
        self.radar.update()

    # ----------------------------------------------------------
    # FASE 3: CAMBIO DE SENSOR ACTIVO (QListWidget)
    # ----------------------------------------------------------
    def actualizar_filtro(self, item):
        sensor_id = item.data(Qt.ItemDataRole.UserRole)
        if item.checkState() == Qt.CheckState.Checked:
            self.sensores_activos.add(sensor_id)
        else:
            self.sensores_activos.discard(sensor_id)
        
        # Sincronizar con el widget de radar
        self.radar.sensores_visibles = self.sensores_activos
        self.radar.update()
        

    def _on_sensor_item_clicked(self, item):
        sensor_id = item.data(Qt.ItemDataRole.UserRole)
        if not sensor_id or "/" not in sensor_id:
            return

        try:
            sac, sic = map(int, sensor_id.split('/'))
        except ValueError:
            return

        info = self.sensores.get((sac, sic))
        if info and info.get('lat') and info.get('lon'):
            lat, lon = info['lat'], info['lon']
            sensor_name = info.get('name', f"Radar {sac}/{sic}")

            # Re-centrar proyección geográfica del widget
            self.radar.set_projection_center(lat, lon, (sac, sic))
            self.radar.reproject_all_coordinates()
            self.radar._active_sensor_label = f"SENSOR ACTIVO: {sensor_name} ({sac}/{sic})"
            
            # Sincronizar velocidad de rotación de la antena (RPM) si fue detectada
            rpm = self._sensor_rpms.get((sac, sic), 12.0)
            self.radar.set_sweep_speed(rpm)
            
            print(f"[REPROYECTOR] Re-centrado en el sensor seleccionado {sensor_id} (Lat: {lat:.5f}, Lon: {lon:.5f}) - {rpm:.2f} RPM")


    def seleccionar_todos(self):
        self.lista_sensores.blockSignals(True)
        for i in range(self.lista_sensores.count()):
            item = self.lista_sensores.item(i)
            item.setCheckState(Qt.CheckState.Checked)
            self.sensores_activos.add(item.data(Qt.ItemDataRole.UserRole))
        self.lista_sensores.blockSignals(False)
        self.radar.sensores_visibles = self.sensores_activos
        self.radar.update()

    def deseleccionar_todos(self):
        self.lista_sensores.blockSignals(True)
        for i in range(self.lista_sensores.count()):
            self.lista_sensores.item(i).setCheckState(Qt.CheckState.Unchecked)
        self.sensores_activos.clear()
        self.lista_sensores.blockSignals(False)
        self.radar.sensores_visibles = self.sensores_activos
        self.radar.update()

    # ----------------------------------------------------------
    # WORKER CALLBACKS
    # ----------------------------------------------------------
    def _on_scan_progress(self, current: int, total: int):
        if total > 0:
            pass

    def _on_scan_done(self, total_frames: int, duration: float):
        self._total_frames = total_frames
        self._pcap_duration = duration
        self._decode_complete = True
        self.btn_decodificar.setEnabled(True)
        if total_frames > 0:
            self.slider_tiempo.setMaximum(total_frames - 1)
            self.slider_tiempo.setEnabled(True)

    def _on_playback_finished(self):
        self._playing = False
        self.btn_decodificar.setText("Decodificar / Play")

    def _on_sensor_detected(self, sac: int, sic: int):
        info = self.sensores.get((sac, sic), {'name': f"Radar {sac}/{sic}"})

    def _on_rotation_speed_detected(self, sac: int, sic: int, rpm: float):
        sensor_key = (sac, sic)
        self._sensor_rpms[sensor_key] = rpm
        if hasattr(self.radar, 'center_key') and self.radar.center_key == sensor_key:
            self.radar.set_sweep_speed(rpm)
        print(f"[Main] Velocidad de rotación para {sac}/{sic} -> {rpm:.2f} RPM")

    def _on_north_mark_detected(self, sac: int, sic: int):
        # FASE 3: El centro del radar ahora se gestiona en RadarWidget
        if hasattr(self.radar, 'center_key') and self.radar.center_key == (sac, sic):
            self.radar.reset_sweep_angle()

    def _on_sensors_scanned(self, detected_sensors: Set[Tuple[int, int]]):
        missing = []
        for (sac, sic) in detected_sensors:
            fp = os.path.join("default-site-params", f"{sac}_{sic}.json")
            if not os.path.exists(fp):
                missing.append(f"SAC {sac}/SIC {sic}")
            elif (sac, sic) not in self.sensores:
                missing.append(f"SAC {sac}/SIC {sic} (sin configuración)")

        if missing:
            msg = "⚠ Radars sin config: " + ", ".join(missing[:3])
            if len(missing) > 3:
                msg += f" +{len(missing)-3} más"
            print(f"[Main] Advertencia: {msg}")
        else:
            pass

    def _on_worker_state_changed(self, state: str):
        self._playing = (state == "PLAYING")

        if state == "STOPPED":
            self.btn_decodificar.setText("Decodificar / Play")
        elif state == "PAUSED":
            self.btn_decodificar.setText("▶ Play")
        elif state == "PLAYING":
            self.btn_decodificar.setText("❚❚ Pausa")
            self.radar.play()

    def _update_dashboard_status(self):
        if self._worker and self._worker.isRunning():
            pass

    # ----------------------------------------------------------
    # FASE 1: CARGA DE PCAP (solo escaneo superficial)
    # ----------------------------------------------------------
    def _on_load_pcap(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Seleccionar archivo PCAP", ".",
            "Archivos PCAP (*.pcap *.pcapng);;Todos (*)"
        )
        if not file_path:
            return

        # REGLA DE RESETEO DE UI:
        if hasattr(self, 'radar'):
            self.radar.limpiar_pantalla()
        elif hasattr(self, 'radar_widget'):
            self.radar_widget.limpiar_pantalla()

        # Reiniciar TDD y Slider visualmente
        if hasattr(self, 'lbl_tiempo'):
            self.lbl_tiempo.setText("00:00:00")
        if hasattr(self, 'slider_tiempo'):
            self.slider_tiempo.setValue(0)

        self._cleanup_session()

        basename = os.path.basename(file_path)
        self.setWindowTitle(f"ASTERIX Radar Decoder - {basename}")

        self._pcap_path = file_path

        self._light_scanner = PcapScannerThread(file_path)
        self._light_scanner.scan_result.connect(self._on_light_scan_done)
        self._light_scanner.scan_error.connect(self._on_light_scan_error)
        self._light_scanner.start()

    def _cleanup_session(self):
        if self._worker is not None:
            self._worker.stop()
            if self._worker.isRunning():
                self._worker.quit()
                self._worker.wait(2000)

        self._playing = False
        self._worker = None
        self._pcap_duration = 0.0
        self._total_frames = 0
        self._decode_complete = False
        self.btn_decodificar.setEnabled(False)
        self._pcap_path = ""

        # Limpiar sensores conocidos y la lista de sensores
        self.sensores_conocidos.clear()
        self.sensores_activos.clear()
        self.lista_sensores.blockSignals(True)
        self.lista_sensores.clear()
        self.lista_sensores.blockSignals(False)
        self.radar.sensores_visibles = self.sensores_activos
        self.radar.update()

        self.radar.clear_all_plots()

    def _on_light_scan_done(self, total_frames: int, duration: float, sensors: Set[Tuple[int, int]]):
        self._total_frames = total_frames
        self._pcap_duration = duration

        msg = f"Escaneo: {total_frames} frames"
        if duration > 0:
            msg += f" ({duration:.1f}s)"

        if total_frames > 0:
            self._on_decode_file(sensors) # Auto-decode after scan
        else:
            pass

        for sac, sic in sensors:
            info = self.sensores.get((sac, sic), {'name': f"Radar {sac}/{sic}"})

    def _on_light_scan_error(self, msg: str):
        print(f"[Main] Error en escaneo superficial: {msg}")

    def _on_udp_connect(self, ip: str, port: int):
        print(f"[Main] Solicitud de conexión a UDP: {ip}:{port}")
        self._cleanup_session()
        self.setWindowTitle(f"ASTERIX Radar Decoder - LIVE UDP @ {ip}:{port}")
        self._decode_complete = True
        self._worker = AsterixWorker(
            pcap_file=None,
            sensores=self.sensores,
            cache_dir=self.cache_dir,
            udp_ip=ip,
            udp_port=port
        )
        self._connect_worker_signals()
        self._worker.start()
        self.btn_play.setEnabled(True)

    # ----------------------------------------------------------
    # FASE 1 - Paso 2: DECODIFICAR ARCHIVO + FASE 2 HARD RESET
    # ----------------------------------------------------------
    def _on_decode_file(self, detected_from_scan: Set[Tuple[int, int]]):
        if not self._pcap_path:
            return

        target_center_key = None

        if target_center_key is None and detected_from_scan:
            # Convert set to list to get an element
            target_center_key = list(detected_from_scan)[0]
            if len(detected_from_scan) > 1:
                sanluis_key = (226, 221)
                cordoba_key = (226, 210)
                if sanluis_key in detected_from_scan:
                    target_center_key = sanluis_key
                elif cordoba_key in detected_from_scan:
                    target_center_key = cordoba_key

        if target_center_key is not None:
            center_info = self.sensores.get(target_center_key, {})
            lat = center_info.get('lat', 0.0)
            lon = center_info.get('lon', 0.0)
            name = center_info.get('name', f'Radar {target_center_key[0]}/{target_center_key[1]}')

            if lat != 0.0 and lon != 0.0:
                asterix_version = self._detect_asterix_version(self._pcap_path)
                self._center_sensor_key = target_center_key
                self.radar.reset_origin_for_new_file(
                    lat, lon,
                    target_center_key[0], target_center_key[1],
                    name,
                    asterix_version=asterix_version
                )
                self.main_sensor_set = True
                if asterix_version:
                    print(f"[ASE 1] Versión ASTERIX detectada: {asterix_version}")
                else:
                    print("[ASE 1] No se detectó CAT048 en la previsualización. Usando versión por defecto.")
            else:
                print(f"⚠ Sensor {target_center_key} sin coordenadas de ubicación")
        else:
            print("⚠ No se detectaron sensores en el archivo. La proyección usará valores por defecto.")

        self.radar.clear_all_plots()
        self._start_worker()

    # ----------------------------------------------------------
    # FILTROS
    # ----------------------------------------------------------
    def _on_filters_changed(self, active_sensors: Set[Tuple[int, int]],
                            squawk_filter: str):
        self.radar.update()

    # ----------------------------------------------------------
    # ASE 1: DETECCIÓN DE VERSIÓN ASTERIX
    # ----------------------------------------------------------
    def _detect_asterix_version(self, pcap_path: str) -> str:
        try:
            from scapy.all import PcapReader, UDP
            from native_asterix import parse_payload
            
            if not os.path.exists(pcap_path):
                return ""
            
            v1_30_hits = 0
            v1_21_hits = 0
            max_scan = 5000
            
            reader = PcapReader(pcap_path)
            for i, pkt in enumerate(reader):
                if i >= max_scan:
                    break
                try:
                    if UDP not in pkt:
                        continue
                    payload = bytes(pkt[UDP].payload)
                    if len(payload) <= 10:
                        continue
                    
                    records = parse_payload(payload)
                    for rec in records:
                        if rec.get('category') == 48:
                            version_str = rec.get('version', '1.21')
                            extra_data = rec.get('extra_data', {})
                            max_we = extra_data.get('i048_030_max_we', 0)
                            
                            if version_str == '1.30' or max_we >= 24:
                                v1_30_hits += 1
                            else:
                                v1_21_hits += 1
                except Exception:
                    continue
            reader.close()
            
            if v1_30_hits > 0 and v1_30_hits >= v1_21_hits:
                return "v1.30"
            elif v1_21_hits > 0:
                return "v1.21"
            
            return ""
            
        except Exception as e:
            print(f"[ASE 1] Error detectando versión ASTERIX: {e}")
            return ""

    # ----------------------------------------------------------
    # CONTROL DE PROYECCIÓN
    # ----------------------------------------------------------
    def _on_center_sensor_changed(self, sensor_key: Tuple[int, int]):
        self._center_sensor_key = sensor_key
        center_info = self.sensores.get(sensor_key)
        if center_info and 'lat' in center_info and 'lon' in center_info:
            lat, lon = center_info['lat'], center_info['lon']
            name = center_info.get('name', f'Radar {sensor_key[0]}/{sensor_key[1]}')
            self.radar.reset_origin_for_new_file(lat, lon, sensor_key[0], sensor_key[1], name)
            self.main_sensor_set = True
            rpm = self._sensor_rpms.get(sensor_key, 12.0)
            self.radar.set_sweep_speed(rpm)
        else:
            print(f"[Main] No se pudo centrar en {sensor_key}, no se encontró información.")
        self.radar.update()

    # ----------------------------------------------------------
    # CONTROL DE REPRODUCCIÓN
    # ----------------------------------------------------------
    def _on_play_toggle(self):
        if self._worker is None:
            return
        self._worker.toggle_play_pause()

    def _on_stop(self):
        if self._worker is not None and self._decode_complete:
            self._worker.stop_playback()
        else:
            self._playing = False
            self.btn_decodificar.setText("Decodificar / Play")
            self.radar.stop_sweep()

        if hasattr(self, 'radar'):
            self.radar.limpiar_pantalla()
        elif hasattr(self, 'radar_widget'):
            self.radar_widget.limpiar_pantalla()

    # ----------------------------------------------------------
    # TDD: SLIDER, TIEMPO Y VELOCIDAD
    # ----------------------------------------------------------
    def _on_tod_update(self, tod: float):
        """Actualiza el label del TDD con el formato HH:MM:SS."""
        hours = int(tod // 3600) % 24
        minutes = int((tod % 3600) // 60)
        seconds = int(tod % 60)
        self.lbl_tiempo.setText(f"{hours:02d}:{minutes:02d}:{seconds:02d}")

    def actualizar_progreso(self, valor_slider: int, tiempo_str: str):
        self.lbl_tiempo.setText(tiempo_str)
        # Evitar recursividad bloqueando señales mientras actualizamos por código
        self.slider_tiempo.blockSignals(True)
        self.slider_tiempo.setValue(valor_slider)
        self.slider_tiempo.blockSignals(False)

    def cambiar_velocidad(self):
        if hasattr(self, '_worker') and self._worker:
            texto = self.combo_velocidad.currentText().replace('x', '')
            try:
                self._worker.velocidad = float(texto)
                print(f"[Main] Velocidad cambiada a {texto}x")
            except ValueError:
                pass

    def seek_tiempo(self, valor: int):
        if hasattr(self, '_worker') and self._worker:
            self._worker.paquete_actual = valor # Lógica de salto en el Worker
            if self._worker.state != "PLAYING":
                self._worker.toggle_play_pause()
            print(f"[Main] Seek a frame index: {valor}")

    def _on_sweep_toggled(self, visible: bool):
        self.radar.set_sweep_visible(visible)

    def _on_centrar_mendoza(self):
        MENDOZA_LAT = -32.89
        MENDOZA_LON = -69.95
        self.radar.centrar_en_coordenadas(MENDOZA_LAT, MENDOZA_LON)

    def _on_fit_view(self):
        self.radar._needs_adjust = True
        self.radar._adjust_view()

    def _on_seek_requested(self, tod: float):
        if self._worker is None or self._pcap_duration <= 0:
            return
        self._worker.seek_to_tod(tod)
        if self._worker.state != "PLAYING":
            self._worker.toggle_play_pause()

    # ----------------------------------------------------------
    # CIERRE SEGURO
    # ----------------------------------------------------------
    def closeEvent(self, event):
        print("[Main] Cerrando aplicación...")
        if self._worker is not None:
            self._worker.stop()
            if self._worker.isRunning():
                self._worker.quit()
                if not self._worker.wait(3000):
                    print("[Main] Worker no respondió, forzando terminación")
                    self._worker.terminate()
                    self._worker.wait(2000)
        if hasattr(self, 'dxf_loader') and self.dxf_loader.isRunning():
            self.dxf_loader.wait(1000)
        
        if hasattr(self, 'cache_dir') and os.path.exists(self.cache_dir):
            print(f"[Main] Limpiando directorio de caché de sesión: {self.cache_dir}")
            shutil.rmtree(self.cache_dir, ignore_errors=True)

        print("[Main] Cerrado completado")
        event.accept()


# ============================================================
# PUNTO DE ENTRADA
# ============================================================
if __name__ == '__main__':
    if 'QT_QPA_PLATFORM' not in os.environ:
        os.environ['QT_QPA_PLATFORM'] = 'xcb'

    app = QApplication(sys.argv)
    app.setFont(QFont("Consolas", 10))
    
    app.setStyleSheet("""
        QToolTip {
            background-color: #e8e8e8;
            color: #222222;
            border: 1px solid #999999;
            padding: 6px;
            font-family: 'Consolas', 'Monospace';
            font-size: 11px;
        }
    """)

    window = MainWindow()
    window.show()
    sys.exit(app.exec())