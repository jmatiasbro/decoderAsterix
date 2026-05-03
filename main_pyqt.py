import sys
import os
import math
import re
import time
from PyQt6.QtWidgets import (QApplication, QMainWindow, QVBoxLayout, QWidget, 
                             QPushButton, QSlider, QLabel, QStatusBar, QFileDialog, QTabWidget, 
                             QHBoxLayout, QComboBox, QDialog, QTableWidget, QTableWidgetItem, 
                             QHeaderView, QGraphicsEllipseItem, QGridLayout, QFrame)
from PyQt6.QtCore import QThread, pyqtSignal, Qt, QTimer
from PyQt6.QtGui import QAction
import pyqtgraph as pg

from config import get_sensor_position
from decoders import decode_asterix_stream
from geo_tools import TrackManager, TargetProcessor, SensorRegistry
from main import AsterixAnalyzer
from atm_analytics import ATMAnalyticsEngine
from exporters import KMLExporter, PDFReportGenerator, ReportGenerator

# ============================================================================
# VENTANAS DE DIÁLOGO PARA ANALÍTICA
# ============================================================================

class StatsDialog(QDialog):
    """Diálogo para mostrar estadísticas de Pd y performance."""
    def __init__(self, parent, pd_intervals, pd_dict, analytics_stats):
        super().__init__(parent)
        self.setWindowTitle("Estadísticas de Detección y Performance")
        self.setMinimumSize(600, 400)
        self.setStyleSheet("background-color: #1a1a1a; color: #e0e0e0;")

        layout = QVBoxLayout(self)
        
        # Estadísticas de integridad
        stats_text = (f"Registros sin Modo A: {analytics_stats.get('mode_a_missing', 0)}\n"
                      f"Registros sin Modo C (FL): {analytics_stats.get('mode_c_missing', 0)}")
        layout.addWidget(QLabel(stats_text))

        # Gráfico de Pd Interactivo
        self.plot_widget = pg.PlotWidget(title="Curva de Probabilidad de Detección (Pd)")
        self.plot_widget.setLabel('left', 'Pd (%)')
        self.plot_widget.setLabel('bottom', 'Rotación / Intervalo')
        self.plot_widget.setYRange(0, 105)
        self.plot_widget.showGrid(x=True, y=True, alpha=0.3)
        self.plot_widget.addLegend()
        
        colors = [(0, 255, 0), (0, 255, 255), (255, 255, 0)]
        for i, (cat, values) in enumerate(pd_dict.items()):
            color = colors[i % len(colors)]
            self.plot_widget.plot(pd_intervals, values, pen=pg.mkPen(color, width=2), symbol='o', symbolBrush=color, name=f'CAT {cat}')
            
        layout.addWidget(self.plot_widget, stretch=2)

        # Tabla de Pd
        table = QTableWidget()
        table.setColumnCount(len(pd_dict) + 1)
        
        header_labels = ["Rotación"] + [f"Pd CAT {cat} (%)" for cat in pd_dict.keys()]
        table.setHorizontalHeaderLabels(header_labels)
        table.setRowCount(len(pd_intervals))

        for i, interval in enumerate(pd_intervals):
            table.setItem(i, 0, QTableWidgetItem(str(interval)))
            for j, cat in enumerate(pd_dict.keys()):
                pd_value = pd_dict[cat][i]
                table.setItem(i, j + 1, QTableWidgetItem(f"{pd_value:.2f}"))
        
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        layout.addWidget(table, stretch=1)


class DegradationDialog(QDialog):
    """Diálogo para mostrar eventos de degradación detectados."""
    def __init__(self, parent, degradations):
        super().__init__(parent)
        self.setWindowTitle("Eventos de Degradación Detectados")
        self.setMinimumSize(700, 400)
        self.setStyleSheet("background-color: #1a1a1a; color: #e0e0e0;")

        layout = QVBoxLayout(self)
        table = QTableWidget()
        table.setColumnCount(4)
        table.setHorizontalHeaderLabels(["Timestamp", "Tipo", "ID (Squawk)", "Detalles"])
        table.setRowCount(len(degradations))

        for i, event in enumerate(degradations):
            timestamp_str = time.strftime('%H:%M:%S', time.gmtime(event.get('time', 0)))
            table.setItem(i, 0, QTableWidgetItem(timestamp_str))
            table.setItem(i, 1, QTableWidgetItem(str(event.get('type', 'N/A'))))
            table.setItem(i, 2, QTableWidgetItem(str(event.get('id', 'N/A'))))
            table.setItem(i, 3, QTableWidgetItem(str(event.get('details', 'N/A'))))

        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        layout.addWidget(table)

# ============================================================================
# 1. CONTROLADOR / HILO ASÍNCRONO (Data Ingestion & Processing)
# ============================================================================
class IngestionWorker(QThread):
    """
    Hilo secundario que engloba toda la E/S (I/O) y carga de CPU 
    para no bloquear jamás la GUI. Implementa Batching.
    """
    progress = pyqtSignal(int, str)
    tracks_state_ready = pyqtSignal(dict)  # Emite el estado final del buffer
    finished = pyqtSignal(int, list, dict, dict, list, float)
    error = pyqtSignal(str)

    def __init__(self, file_paths, processor, track_manager):
        super().__init__()
        self.file_paths = file_paths
        self.processor = processor
        self.track_manager = track_manager
        self._is_running = True

    def run(self):
        try:
            total_processed = 0
            all_processed_records = []
            detected_rpm = 15.0
            for file_idx, file_path in enumerate(self.file_paths):
                if not self._is_running:
                    break
                
                self.progress.emit(5, f"Leyendo archivo {file_idx+1}/{len(self.file_paths)}: {os.path.basename(file_path)}...")
                
                # Instanciamos el analizador local para invocar sus métodos de ingesta
                analyzer_temp = AsterixAnalyzer()
                
                _, ext = os.path.splitext(file_path)
                if ext.lower() == '.pcap':
                    raw_data = analyzer_temp.load_pcap(file_path)
                elif ext.lower() == '.ast':
                    raw_data = analyzer_temp.load_ast(file_path)
                else:
                    self.error.emit(f"Formato no soportado: {os.path.basename(file_path)}")
                    continue

                if not raw_data:
                    self.error.emit(f"No se extrajeron datos de {os.path.basename(file_path)}")
                    continue

                self.progress.emit(20, f"Decodificando {os.path.basename(file_path)}...")
                records = decode_asterix_stream(raw_data)
                total = len(records)
                
                if total == 0:
                    continue

                # PREVENCIÓN DE SIGNAL FLOOD: Procesamiento por Lotes (Batching)
                batch_size = 1000
                
                for i, raw_rec in enumerate(records):
                    if not self._is_running:
                        break
                    
                    # Auto-registrar el sensor para que el TargetProcessor sepa proyectarlo
                    sensor = self.processor.sensor_registry.get_sensor(raw_rec.sac, raw_rec.sic)
                    if not sensor or sensor['latitude'] is None:
                        if getattr(raw_rec, 'latitude', None) is not None and raw_rec.category in [34, 2]:
                            self.processor.sensor_registry.register_sensor(raw_rec.sac, raw_rec.sic, raw_rec.latitude, raw_rec.longitude, getattr(raw_rec, 'altitude', 0))
                        else:
                            known_pos = get_sensor_position(raw_rec.sac, raw_rec.sic)
                            if known_pos:
                                self.processor.sensor_registry.register_sensor(raw_rec.sac, raw_rec.sic, known_pos[0], known_pos[1], known_pos[2])
                    
                    processed = self.processor.process_record(raw_rec)
                    all_processed_records.append(processed)
                    
                    if processed.get('category') in [2, 34] and 'antenna_speed' in processed.get('extra_data', {}):
                        detected_rpm = processed['extra_data']['antenna_speed']
                    
                    # Aislamiento por SAC/SIC para evitar colisiones Multi-Sensor
                    sac = processed.get('sac', 0)
                    sic = processed.get('sic', 0)
                    tid_val = processed.get('mode_s') or processed.get('mode_3a') or processed.get('track_number')
                    tid = f"{sac:03d}_{sic:03d}_{tid_val}" if tid_val is not None else 'None'
                    
                    if tid != 'None':
                        self.track_manager.update_track(tid, processed)
                    
                    if i % batch_size == 0:
                        self.tracks_state_ready.emit(dict(self.track_manager.tracks))
                        pct = int(20 + (i / total) * 80)
                        self.progress.emit(pct, f"Procesando archivo {file_idx+1}/{len(self.file_paths)}: {i}/{total} targets...")
                
                total_processed += total

            if self._is_running:
                self.progress.emit(90, "Calculando Probabilidad de Detección (Pd) Global...")
                analytics = ATMAnalyticsEngine(rotation_period=60.0/detected_rpm if detected_rpm > 0 else 4.0)
                pd_intervals, pd_dict, stats = analytics.calculate_pd_series(all_processed_records)
                degradations = analytics.degradations
                
                self.tracks_state_ready.emit(dict(self.track_manager.tracks))

            self.progress.emit(100, "Procesamiento completado.")
            self.finished.emit(total_processed, pd_intervals, pd_dict, stats, degradations, detected_rpm)

        except Exception as e:
            self.error.emit(str(e))

    def stop(self):
        self._is_running = False


# ============================================================================
# 2. VISTA (Interfaz Gráfica Principal)
# ============================================================================
class ATCNightWindow(QMainWindow):
    """Interfaz Profesional ATC en modo oscuro."""
    def __init__(self):
        super().__init__()
        self.setWindowTitle("ASTERIX Mission-Critical Analyzer - Fase 1")
        self.setMinimumSize(1200, 800)
        self.setStyleSheet("""
            QMainWindow { background-color: #0a0a0a; color: #00ff00; font-family: 'Consolas'; }
            QTabWidget::pane { border: 1px solid #004400; background: #050505; }
            QTabBar::tab { background: #1a1a1a; color: #aaaaaa; padding: 8px; border: 1px solid #004400; }
            QTabBar::tab:selected { background: #004400; color: #ffffff; font-weight: bold; }
            QComboBox, QPushButton { background-color: #1a1a1a; color: #00ff00; border: 1px solid #00ff00; padding: 5px; }
            QPushButton:hover { background-color: #004400; }
        """)
        
        # Modelos de Estado
        self.sensor_registry = SensorRegistry()
        self.processor = TargetProcessor(self.sensor_registry)
        self.track_manager = TrackManager(history_minutes=10, timeout_seconds=60)
        self.worker = None
        self.analytics_engine = ATMAnalyticsEngine()
        self.degradation_events = []
        self.known_track_ids = set()
        
        # Animación de barrido
        self.sweep_angle = 0.0
        
        self._setup_ui()
        
        # Timer para Garbage Collection cada 10 segundos
        self.gc_timer = QTimer(self)
        self.gc_timer.timeout.connect(self._run_garbage_collection)
        self.gc_timer.start(10000)
        
        # Timer para animación de antena PPI (60 FPS)
        self.anim_timer = QTimer(self)
        self.anim_timer.timeout.connect(self._animate_sweep)
        self.anim_timer.start(16)

    def _setup_ui(self):
        # --- Menú Superior Requerido ---
        menubar = self.menuBar()
        menubar.setStyleSheet("background-color: #1a1a1a; color: #00ff00;")
        file_menu = menubar.addMenu("Archivo")
        
        load_action = QAction("Cargar Archivo...", self)
        load_action.setShortcut("Ctrl+O")
        load_action.triggered.connect(self._load_file_dialog)
        file_menu.addAction(load_action)
        
        file_menu.addSeparator()
        kml_export_action = QAction("Exportar KML Avanzado (<gx:Track>)", self)
        kml_export_action.triggered.connect(self._export_kml_advanced)
        file_menu.addAction(kml_export_action)
        
        pdf_export_action = QAction("Exportar Reporte a PDF", self)
        pdf_export_action.triggered.connect(self._export_pdf_report)
        file_menu.addAction(pdf_export_action)
        
        file_menu.addSeparator()
        exit_action = QAction("Salir", self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)

        # --- Panel de Control de Simulación (Fase 2) ---
        playback_layout = QHBoxLayout()
        
        self.btn_play = QPushButton("▶ Play")
        self.btn_play.clicked.connect(self._toggle_playback)
        playback_layout.addWidget(self.btn_play)
        
        self.speed_combo = QComboBox()
        self.speed_combo.addItems(["1x", "2x", "5x", "10x", "50x"])
        playback_layout.addWidget(self.speed_combo)
        
        self.time_label = QLabel("TOD: 00:00:00")
        self.time_label.setStyleSheet("font-size: 14px; font-weight: bold; color: #00ff00;")
        playback_layout.addWidget(self.time_label)
        
        playback_layout.addWidget(QLabel("Sensor Source (PPI):"))
        self.sensor_source_combo = QComboBox()
        self.sensor_source_combo.currentIndexChanged.connect(self._force_redraw)
        playback_layout.addWidget(self.sensor_source_combo, stretch=1)
        
        layout.addLayout(playback_layout)

        # --- Panel de Control (Filtro HMI) ---
        control_layout = QHBoxLayout()
        
        control_layout.addWidget(QLabel("Filtrar Aeronave:"))
        self.track_filter_combo = QComboBox()
        self.track_filter_combo.addItem("Mostrar Todos", "ALL")
        self.track_filter_combo.currentIndexChanged.connect(self._force_redraw)
        control_layout.addWidget(self.track_filter_combo, stretch=1)

        # 4. Sistema de Etiquetas Dinámicas (Data Block Switch)
        self.label_mode_combo = QComboBox()
        self.label_mode_combo.addItems(["Callsign", "Squawk"])
        self.label_mode_combo.currentIndexChanged.connect(self._force_redraw)
        control_layout.addWidget(self.label_mode_combo)

        btn_clear = QPushButton("LIMPIAR BUFFER")
        btn_clear.clicked.connect(self._clear_buffer)
        btn_clear.setStyleSheet("background-color: #440000; color: white;")
        control_layout.addWidget(btn_clear)
        
        layout.addLayout(control_layout)

        # --- Panel de Herramientas (Medición e Historial) ---
        tools_layout = QHBoxLayout()
        tools_layout.addWidget(QLabel("Persistencia (segundos):"))
        self.history_slider = QSlider(Qt.Orientation.Horizontal)
        self.history_slider.setRange(0, 600) # 0 a 10 minutos
        self.history_slider.setValue(60)
        self.history_slider.valueChanged.connect(self._force_redraw)
        tools_layout.addWidget(self.history_slider, stretch=1)
        
        self.btn_ruler_center = QPushButton("📏 Medir (Centro)")
        self.btn_ruler_center.setCheckable(True)
        self.btn_ruler_center.clicked.connect(self._toggle_ruler_center)
        tools_layout.addWidget(self.btn_ruler_center)

        self.btn_ruler_free = QPushButton("📏 Medir (Libre)")
        self.btn_ruler_free.setCheckable(True)
        self.btn_ruler_free.clicked.connect(self._toggle_ruler_free)
        tools_layout.addWidget(self.btn_ruler_free)
        
        layout.addLayout(tools_layout)

        # --- Estructura de Vistas (TabWidget) ---
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs, stretch=1)
        
        # Configuración global de PyQtGraph
        pg.setConfigOption('background', '#050505')
        pg.setConfigOption('foreground', '#00ff00')

        # --- Módulo 1: Vista Previa por Cuadrantes (Dashboard) ---
        self.dashboard_tab = QWidget()
        dash_layout = QGridLayout(self.dashboard_tab)
        
        def create_dash_frame(title):
            frame = QFrame()
            frame.setStyleSheet("QFrame { border: 2px solid #00ffff; border-radius: 5px; background-color: #0a0a0a; }")
            vbox = QVBoxLayout(frame)
            vbox.setContentsMargins(5, 5, 5, 5)
            lbl = QLabel(title)
            lbl.setStyleSheet("color: #00ffff; font-weight: bold; border: none; padding: 2px;")
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            pw = pg.PlotWidget()
            pw.setAspectLocked(True)
            pw.showGrid(x=True, y=True, alpha=0.2)
            pw.hideAxis('bottom')
            pw.hideAxis('left')
            pw.setStyleSheet("border: none;")
            vbox.addWidget(lbl)
            vbox.addWidget(pw)
            return frame, pw
            
        frame01, self.dash_c01 = create_dash_frame("CAT 001 - Monoradar Surface")
        frame48, self.dash_c48 = create_dash_frame("CAT 048 - Monoradar Target")
        frame21, self.dash_c21 = create_dash_frame("CAT 021 - ADS-B Reports")
        frame62, self.dash_c62 = create_dash_frame("CAT 062 - System Tracks")
        
        # Añadir scatters estáticos
        self.scatter_cat01 = pg.ScatterPlotItem(size=3, pen=pg.mkPen(None), brush=pg.mkBrush(255, 100, 255, 200)) # Magenta
        self.dash_c01.addItem(self.scatter_cat01)
        self.scatter_cat48 = pg.ScatterPlotItem(size=3, pen=pg.mkPen(None), brush=pg.mkBrush(0, 255, 0, 200)) # Verde
        self.dash_c48.addItem(self.scatter_cat48)
        self.scatter_cat21 = pg.ScatterPlotItem(size=3, pen=pg.mkPen(None), brush=pg.mkBrush(0, 255, 255, 200)) # Cian
        self.dash_c21.addItem(self.scatter_cat21)
        self.scatter_cat62 = pg.ScatterPlotItem(size=3, pen=pg.mkPen(None), brush=pg.mkBrush(255, 255, 0, 200)) # Amarillo
        self.dash_c62.addItem(self.scatter_cat62)
        
        dash_layout.addWidget(frame01, 0, 0)
        dash_layout.addWidget(frame48, 0, 1)
        dash_layout.addWidget(frame21, 1, 0)
        dash_layout.addWidget(frame62, 1, 1)
        
        self.tabs.addTab(self.dashboard_tab, "Dashboard Preview")

        # Vista 1: PPI Sensor
        self.ppi_view = pg.PlotWidget(title="Vista 1: PPI Sensor (Plano Polar)")
        self.ppi_view.setAspectLocked(True)
        self.ppi_view.showGrid(x=False, y=False)
        self.ppi_view.hideAxis('bottom')
        self.ppi_view.hideAxis('left')
        self.ppi_view.setMouseEnabled(x=True, y=True)
        
        # --- Retícula Polar (Range Rings y Líneas Acimutales) ---
        text_zero = pg.TextItem("0", color=(0, 150, 0, 180), anchor=(0.5, 0.5))
        text_zero.setPos(0, 0)
        self.ppi_view.addItem(text_zero)
        
        for r in range(50, 251, 50): # Anillos cada 50 NM hasta 250 NM
            circle = QGraphicsEllipseItem(-r, -r, r*2, r*2)
            circle.setPen(pg.mkPen(color=(0, 100, 0, 150), width=1, style=Qt.PenStyle.DashLine))
            self.ppi_view.addItem(circle)
            # Etiqueta de distancia
            text = pg.TextItem(f"{r} NM", color=(0, 150, 0, 180), anchor=(0.5, 1))
            text.setPos(0, r)
            self.ppi_view.addItem(text)
            
        for angle in range(0, 360, 30): # Líneas radiales cada 30 grados
            rad = math.radians(angle)
            x = 250 * math.sin(rad)
            y = 250 * math.cos(rad)
            line = pg.PlotCurveItem([0, x], [0, y], pen=pg.mkPen(color=(0, 100, 0, 150), width=1, style=Qt.PenStyle.DashLine))
            self.ppi_view.addItem(line)
            
        self.ppi_scatters = {}
        for sym in ['o', 't', 's', 'x', '+']:
            scatter = pg.ScatterPlotItem(symbol=sym, pen=pg.mkPen(None))
            self.ppi_scatters[sym] = scatter
            self.ppi_view.addItem(scatter)
            
        self.sweep_line = pg.PlotCurveItem(pen=pg.mkPen(color='#00ff00', width=2, style=Qt.PenStyle.DashLine))
        self.degradation_scatter = pg.ScatterPlotItem(size=15, pen=pg.mkPen(None), symbol='o')
        self.ppi_view.addItem(self.degradation_scatter)
        
        # --- Herramientas de Medición (Ruler) ---
        self.ruler_start_point = None
        self.ruler_line_item = pg.PlotCurveItem(pen=pg.mkPen(color='r', width=2, style=Qt.PenStyle.DashLine))
        self.ruler_label = pg.TextItem(color='r', anchor=(0, 1), fill=pg.mkBrush(0, 0, 0, 150))
        self.ppi_view.addItem(self.ruler_line_item)
        self.ppi_view.addItem(self.ruler_label)
        self.ruler_line_item.hide()
        self.ruler_label.hide()
        
        self.ppi_view.scene().sigMouseClicked.connect(self._on_ppi_mouse_clicked)
        self.ppi_view.scene().sigMouseMoved.connect(self._on_ppi_mouse_moved)

        # Animación de pulso para degradaciones
        self.degradation_pulse_timer = QTimer(self)
        self.degradation_pulse_timer.timeout.connect(self._pulse_degradations)
        self.degradation_pulse_timer.start(250)
        self.pulse_state = 0

        self.ppi_view.addItem(self.sweep_line)
        self.tabs.addTab(self.ppi_view, "PPI Sensor")

        # Vista 2: Mapa Situacional WGS84
        self.map_view = pg.PlotWidget(title="Vista 2: Mapa Situacional (WGS84)")
        self.map_view.setAspectLocked(True)
        self.map_view.showGrid(x=True, y=True, alpha=0.3)
        
        self.map_scatters = {}
        for sym in ['o', 't', 's', 'x', '+']:
            scatter = pg.ScatterPlotItem(symbol=sym, pen=pg.mkPen(None))
            self.map_scatters[sym] = scatter
            self.map_view.addItem(scatter)
            
        self.tabs.addTab(self.map_view, "Mapa Situacional")

        # --- Menú de Análisis ---
        analysis_menu = menubar.addMenu("Análisis")
        pd_action = QAction("Estadísticas de Detección (Pd)", self)
        pd_action.triggered.connect(self._show_pd_dialog)
        analysis_menu.addAction(pd_action)
        degradation_action = QAction("Eventos de Degradación", self)
        degradation_action.triggered.connect(self._show_degradation_dialog)
        analysis_menu.addAction(degradation_action)
        
        self.statusBar = QStatusBar()
        self.setStatusBar(self.statusBar)
        self.statusBar.showMessage("Listo.")
        
        self.current_tod = None
        self.is_playing = False
        self.playback_timer = QTimer(self)
        self.playback_timer.timeout.connect(self._advance_playback)
        
        # Optimización: Object Pooling para elementos dinámicos
        self.ppi_text_pool = {}
        self.ppi_vector_pool = {}
        self.ppi_trail_pool = {}
        
        self.map_text_pool = {}
        self.map_vector_pool = {}
        self.map_trail_pool = {}
        
        self.detected_rpm = 15.0  # Fallback RPM
        self.antenna_offset_deg = 0.0

    def _load_dxf_map(self, filepath):
        if not HAS_EZDXF:
            self.statusBar.showMessage("ezdxf no instalado (pip install ezdxf). Sin mapa DXF.", 5000)
            return

        if not os.path.exists(filepath):
            self.statusBar.showMessage(f"Archivo {filepath} no encontrado. Fondo negro.", 5000)
            return

        try:
            doc = ezdxf.readfile(filepath)
            msp = doc.modelspace()
            
            path = QPainterPath()
            # Escala de Mapping: Suponemos que el DXF está en metros y lo pasamos a Millas Náuticas (NM)
            scale_factor = 1.0 / 1852.0  
            
            text_items = []
            
            for entity in msp:
                if entity.dxftype() == 'LINE':
                    start = entity.dxf.start
                    end = entity.dxf.end
                    path.moveTo(start.x * scale_factor, start.y * scale_factor)
                    path.lineTo(end.x * scale_factor, end.y * scale_factor)
                elif entity.dxftype() == 'LWPOLYLINE':
                    points = entity.get_points(format='xy')
                    if points:
                        path.moveTo(points[0][0] * scale_factor, points[0][1] * scale_factor)
                        for p in points[1:]:
                            path.lineTo(p[0] * scale_factor, p[1] * scale_factor)
                        if entity.closed:
                            path.lineTo(points[0][0] * scale_factor, points[0][1] * scale_factor)
                elif entity.dxftype() == 'CIRCLE':
                    center = entity.dxf.center
                    radius = entity.dxf.radius * scale_factor
                    cx, cy = center.x * scale_factor, center.y * scale_factor
                    path.addEllipse(QPointF(cx, cy), radius, radius)
                elif entity.dxftype() == 'TEXT':
                    insert = entity.dxf.insert
                    text = entity.dxf.text
                    x, y = insert.x * scale_factor, insert.y * scale_factor
                    text_items.append((x, y, text))
            
            # Capa inferior estática unificada (Glass Cockpit Style)
            path_item = QGraphicsPathItem(path)
            pen = QPen(QColor(50, 100, 50, 150)) # Verde tenue 
            pen.setWidth(0) # Lápiz cosmético: no se engrosa indeseadamente al hacer zoom
            path_item.setPen(pen)
            path_item.setZValue(-1) # Capa Inferior
            self.ppi_view.addItem(path_item)
            
            font = QFont("Consolas", 7)
            for x, y, text in text_items:
                ti = pg.TextItem(text=text, color=(100, 150, 100, 200))
                ti.setFont(font)
                ti.setPos(x, y)
                ti.setZValue(-1)
                self.ppi_view.addItem(ti)
                
            self.statusBar.showMessage(f"Mapa vectorial DXF '{filepath}' renderizado correctamente.", 5000)

        except Exception as e:
            self.statusBar.showMessage(f"Error al cargar DXF: {e}", 5000)

    def _toggle_ruler_center(self):
        if self.btn_ruler_free.isChecked():
            self.btn_ruler_free.setChecked(False)
            self._toggle_ruler_free()
            
        if not self.btn_ruler_center.isChecked():
            self.ruler_start_point = None
            self.ruler_line_item.hide()
            self.ruler_label.hide()
            self.statusBar.showMessage("Medición desde centro desactivada.")
        else:
            self.ruler_start_point = (0, 0)
            self.ruler_line_item.setData([0, 0], [0, 0])
            self.ruler_line_item.show()
            self.ruler_label.show()
            self.statusBar.showMessage("Moviendo ratón para medir desde el centro (Radar). Clic para fijar.")

    def _toggle_ruler_free(self):
        if self.btn_ruler_center.isChecked():
            self.btn_ruler_center.setChecked(False)
            self._toggle_ruler_center()

        if not self.btn_ruler_free.isChecked():
            self.ruler_start_point = None
            self.ruler_line_item.hide()
            self.ruler_label.hide()
            self.statusBar.showMessage("Medición libre desactivada.")
        else:
            self.ruler_start_point = None
            self.statusBar.showMessage("Haga clic izquierdo en el PPI para iniciar medición libre.")

    def _on_ppi_mouse_clicked(self, evt):
        if self.btn_ruler_center.isChecked():
            if evt.button() == Qt.MouseButton.LeftButton:
                self.btn_ruler_center.setChecked(False) # Clic fija la línea
            elif evt.button() == Qt.MouseButton.RightButton:
                self.btn_ruler_center.setChecked(False)
                self._toggle_ruler_center() # Cancelar por completo
            return

        if self.btn_ruler_free.isChecked():
            if evt.button() == Qt.MouseButton.LeftButton:
                pos = self.ppi_view.plotItem.vb.mapSceneToView(evt.scenePos())
                if self.ruler_start_point is None:
                    self.ruler_start_point = (pos.x(), pos.y())
                    self.ruler_line_item.setData([pos.x(), pos.x()], [pos.y(), pos.y()])
                    self.ruler_line_item.show()
                    self.ruler_label.show()
                else:
                    self.btn_ruler_free.setChecked(False) # Segundo clic fija la línea
            elif evt.button() == Qt.MouseButton.RightButton:
                self.btn_ruler_free.setChecked(False)
                self._toggle_ruler_free() # Cancelar

    def _on_ppi_mouse_moved(self, pos):
        if (self.btn_ruler_free.isChecked() or self.btn_ruler_center.isChecked()) and self.ruler_start_point is not None:
            view_pos = self.ppi_view.plotItem.vb.mapSceneToView(pos)
            x0, y0 = self.ruler_start_point
            x1, y1 = view_pos.x(), view_pos.y()
            self.ruler_line_item.setData([x0, x1], [y0, y1])
            
            dist = math.hypot(x1 - x0, y1 - y0)
            angle = (math.degrees(math.atan2(x1 - x0, y1 - y0)) + 360) % 360
            
            self.ruler_label.setText(f"{dist:.2f} NM\nΔAz: {angle:.1f}°")
            self.ruler_label.setPos(x1, y1)

    def _load_file_dialog(self):
        file_paths, _ = QFileDialog.getOpenFileNames(
            self, "Seleccionar archivos ASTERIX", "", "Archivos Soportados (*.pcap *.ast);;Todos los archivos (*.*)"
        )
        if file_paths:
            self._start_ingestion(file_paths)

    def _start_ingestion(self, file_paths):
        if self.worker and self.worker.isRunning():
            self.worker.stop()
            self.worker.wait()

        self._clear_buffer()
        self.worker = IngestionWorker(file_paths, self.processor, self.track_manager)
        
        self.worker.progress.connect(self._update_progress)
        self.worker.tracks_state_ready.connect(self._on_tracks_state)
        self.worker.finished.connect(self._on_ingestion_finished)
        self.worker.error.connect(self._on_ingestion_error)
        
        self.worker.start()

    def _update_progress(self, percent, message):
        self.statusBar.showMessage(f"{message} [{percent}%]")

    def _on_tracks_state(self, tracks_dict):
        self.current_tracks_dict = tracks_dict
        
        # 1. Actualizar QComboBox dinámicamente sin bloquear
        for tid, track_deque in tracks_dict.items():
            if tid not in self.known_track_ids and track_deque:
                self.known_track_ids.add(tid)
                latest = track_deque[-1]
                cat = latest.get('category', 'UNK')
                trk = latest.get('track_number', 'N/A')
                sq = latest.get('mode_3a', 'N/A')
                sq_str = f"{sq:04o}" if isinstance(sq, int) else str(sq)
                
                label = f"CAT {cat} - TRK: {trk} - SQ: {sq_str} [{tid}]"
                self.track_filter_combo.addItem(label, tid)

        self._force_redraw()
        
    def _toggle_playback(self):
        if not hasattr(self, 'current_tod') or self.current_tod is None:
            self.statusBar.showMessage("Debe cargar un archivo primero.", 3000)
            return
            
        self.is_playing = not self.is_playing
        if self.is_playing:
            self.btn_play.setText("⏸ Pause")
            self.last_wall_time = time.time()
            self.playback_timer.start(50)  # 20 FPS para renderizado fluido
        else:
            self.btn_play.setText("▶ Play")
            self.playback_timer.stop()

    def _advance_playback(self):
        now = time.time()
        dt = now - getattr(self, 'last_wall_time', now)
        self.last_wall_time = now
        
        speed_str = self.speed_combo.currentText().replace('x', '')
        speed = float(speed_str)
        
        if self.current_tod is not None:
            self.current_tod += dt * speed
            hms = time.strftime('%H:%M:%S', time.gmtime(self.current_tod))
            self.time_label.setText(f"TOD: {hms}")
            self._force_redraw()

    def _force_redraw(self):
        if not hasattr(self, 'current_tracks_dict'):
            return
            
        # Evitar mostrar un "manchón" de datos o "vista previa" antes de que el tiempo inicie
        if not hasattr(self, 'current_tod') or self.current_tod is None:
            if hasattr(self, 'ppi_scatters'): 
                for scatter in self.ppi_scatters.values(): scatter.clear()
            if hasattr(self, 'map_scatters'): 
                for scatter in self.map_scatters.values(): scatter.clear()
            return
            
        selected_tid = self.track_filter_combo.currentData()
        selected_sensor = self.sensor_source_combo.currentData()
        fade_limit = self.history_slider.value()
        current_time = self.current_tod
        label_mode = self.label_mode_combo.currentText()
        
        ppi_spots = {sym: [] for sym in ['o', 't', 's', 'x', '+']}
        map_spots = {sym: [] for sym in ['o', 't', 's', 'x', '+']}
        
        # Anclaje de sincronización para el barrido
        self.latest_sweep_anchor_time = -1
        self.latest_sweep_anchor_az = 0.0
        
        degradation_pos = []
        degradation_brushes = []
        
        active_tids = set()
        
        for tid, track_deque in self.current_tracks_dict.items():
            if selected_tid != "ALL" and tid != selected_tid:
                continue
                
            is_selected = (selected_tid == tid)
            
            # Filtrar historial de la traza hasta el TOD actual de la simulación
            valid_records = [r for r in track_deque if r.get('timestamp') is not None and r['timestamp'] <= current_time]
            if not valid_records:
                continue
                
            latest_record = valid_records[-1]
            cat = latest_record.get('category')
            typ = latest_record.get('extra_data', {}).get('TYP', 0)
            sac = latest_record.get('sac')
            sic = latest_record.get('sic')
            
            # Criterios de Renderizado Separado (Fase 2)
            is_ppi = True # Renderizar en PPI todas las categorías que posean coordenadas polares
            is_map = True # Renderizar en Mapa todas las categorías que posean lat/lon
            
            ppi_track_points = []
            map_track_points = []
            
            # 2. Sincronización de Iluminación y Efecto Fósforo (Afterglow)
            for record in valid_records:
                age = current_time - record['timestamp']
                if age > fade_limit or age < 0:
                    continue
                
                # Fading de Opacidad y Tamaño (Efecto Fósforo)
                alpha = max(20, 255 - int((age / fade_limit) * 235))
                size = max(4, 12 - int((age / fade_limit) * 8))
                brush = pg.mkBrush(color=(0, 255, 0, alpha))
                
                # 3. Simbología Operativa ATM (PPS)
                sq = record.get('mode_3a')
                sym = 'o'
                
                # Blancos de Prueba (UMR/Parrot) o Squawk reservado (0000/7777)
                is_test_target = (sq in [0, 7777]) or record.get('extra_data', {}).get('SIM', False) or record.get('extra_data', {}).get('TST', False)
                
                if is_test_target:
                    sym = 't' # Triángulo
                    brush = pg.mkBrush(color=(255, 255, 0, alpha)) # Amarillo estático
                elif cat == 62:
                    sym = 's' # Cuadrado (System Track)
                elif cat == 21:
                    sym = 'o' # Círculo (ADS-B)
                elif cat in [1, 48]:
                    if sq is not None:
                        sym = 'x' # Cruz Diagonal (SSR Only)
                    else:
                        sym = '+' # Cruz Recta (PSR Only)
                
                if is_selected:
                    brush = pg.mkBrush(color=(255, 255, 0, max(100, alpha)))
                    size += 4
                
                # Vista 1: PPI (Local Polar convertido a Cartesiano)
                if is_ppi and (selected_sensor is None or selected_sensor == (sac, sic)):
                    r_hist = record.get('raw_range')
                    az_hist = record.get('raw_azimuth')
                    if r_hist is not None and az_hist is not None and r_hist >= 0 and az_hist >= 0:
                        x_ppi_hist = r_hist * math.sin(math.radians(az_hist))
                        y_ppi_hist = r_hist * math.cos(math.radians(az_hist))
                        ppi_spots[sym].append({'pos': (x_ppi_hist, y_ppi_hist), 'brush': brush, 'size': size})
                        ppi_track_points.append((x_ppi_hist, y_ppi_hist))
                        
                        if record['timestamp'] > self.latest_sweep_anchor_time:
                            self.latest_sweep_anchor_time = record['timestamp']
                            self.latest_sweep_anchor_az = az_hist

                # Vista 2: Mapa Situacional (WGS84)
                if is_map:
                    lat = record.get('latitude')
                    lon = record.get('longitude')
                    if lat is not None and lon is not None:
                        map_spots[sym].append({'pos': (lon, lat), 'brush': brush, 'size': size})
                        map_track_points.append((lon, lat))
            
            # --- Simbología ATC Avanzada (Optimizada con Pool Multivista) ---
            r = latest_record.get('raw_range')
            az = latest_record.get('raw_azimuth')
            x_ppi, y_ppi = None, None
            if r is not None and az is not None and r >= 0 and az >= 0:
                x_ppi = r * math.sin(math.radians(az))
                y_ppi = r * math.cos(math.radians(az))
                
            lat = latest_record.get('latitude')
            lon = latest_record.get('longitude')
            
            if (lat is not None and lon is not None) or (x_ppi is not None and y_ppi is not None):
                age_latest = current_time - latest_record.get('timestamp', current_time)
                if 0 <= age_latest <= fade_limit:
                    active_tids.add(tid)
                    
                    # 4. Etiqueta Principal (Data Block Switch)
                    callsign = latest_record.get('callsign', '').strip()
                    sq = latest_record.get('mode_3a', 'N/A')
                    sq_str = f"{sq:04o}" if isinstance(sq, int) else str(sq)
                    
                    main_label = callsign if (label_mode == "Callsign" and callsign) else sq_str
                    
                    fl = latest_record.get('flight_level', '---')
                    gs_kts = latest_record.get('extra_data', {}).get('ground_speed_nms', 0) * 3600
                    spd_text = f" {int(gs_kts)}kt" if gs_kts > 0 else ""
                    
                    text = f"{main_label}\nFL{fl}{spd_text}"
                    text_color = (255, 255, 0) if is_selected else (200, 200, 200)
                    
                    def update_symbology(is_active, view, pools, pos, trend_pos, trail_points):
                        text_pool, vector_pool, trail_pool = pools
                        if not is_active or pos[0] is None:
                            if tid in text_pool: text_pool[tid].setVisible(False)
                            if tid in vector_pool: vector_pool[tid].setVisible(False)
                            if tid in trail_pool: trail_pool[tid].setVisible(False)
                            return
                            
                        # Text
                        if tid not in text_pool:
                            txt_item = pg.TextItem(anchor=(0, 1))
                            view.addItem(txt_item)
                            text_pool[tid] = txt_item
                        text_item = text_pool[tid]
                        text_item.setText(text, color=text_color)
                        text_item.setPos(pos[0], pos[1])
                        text_item.setVisible(True)
                        
                        if trend_pos:
                            if tid not in vector_pool:
                                vec_item = pg.PlotCurveItem()
                                view.addItem(vec_item)
                                vector_pool[tid] = vec_item
                            vector_line = vector_pool[tid]
                            vec_color_line = (255, 255, 0) if is_selected else (0, 255, 255)
                            vector_line.setData([pos[0], trend_pos[0]], [pos[1], trend_pos[1]])
                            vector_line.setPen(pg.mkPen(color=vec_color_line, width=1))
                            vector_line.setVisible(True)
                        else:
                            if tid in vector_pool: vector_pool[tid].setVisible(False)
                            
                        # Trail
                        if len(trail_points) > 1:
                            if tid not in trail_pool:
                                trail_item = pg.PlotCurveItem()
                                view.addItem(trail_item)
                                trail_pool[tid] = trail_item
                            trail_item = trail_pool[tid]
                            trail_item.setData([p[0] for p in trail_points], [p[1] for p in trail_points])
                            trail_item.setPen(pg.mkPen(color=(0, 150, 0, 150), width=1))
                            trail_item.setVisible(True)
                        else:
                            if tid in trail_pool: trail_pool[tid].setVisible(False)
                    
                    # Vector de velocidad tendencial a 3 Minutos (180s)
                    trend_map = None
                    trend_ppi = None
                    if len(valid_records) >= 2:
                        prev = valid_records[-2]
                        dt = latest_record.get('timestamp', 0) - prev.get('timestamp', 0)
                        if 0 < dt < 60:
                            if lat is not None and lon is not None:
                                v_lon = (lon - prev.get('longitude', lon)) / dt
                                v_lat = (lat - prev.get('latitude', lat)) / dt
                                trend_map = (lon + v_lon * 180, lat + v_lat * 180)
                                
                            if x_ppi is not None and y_ppi is not None:
                                prev_r = prev.get('raw_range')
                                prev_az = prev.get('raw_azimuth')
                                if prev_r is not None and prev_az is not None:
                                    prev_x = prev_r * math.sin(math.radians(prev_az))
                                    prev_y = prev_r * math.cos(math.radians(prev_az))
                                    v_x = (x_ppi - prev_x) / dt
                                    v_y = (y_ppi - prev_y) / dt
                                    trend_ppi = (x_ppi + v_x * 180, y_ppi + v_y * 180)
                            
                    is_ppi_valid = is_ppi and (selected_sensor is None or selected_sensor == (sac, sic))
                    ppi_pools = (self.ppi_text_pool, self.ppi_vector_pool, self.ppi_trail_pool)
                    update_symbology(is_ppi_valid, self.ppi_view, ppi_pools, (x_ppi, y_ppi), trend_ppi, ppi_track_points)
                    
                    map_pools = (self.map_text_pool, self.map_vector_pool, self.map_trail_pool)
                    update_symbology(is_map, self.map_view, map_pools, (lon, lat), trend_map, map_track_points)

        # Ocultar la simbología de los blancos caducados sin destruirlos
        for tid in list(self.ppi_text_pool.keys()):
            if tid not in active_tids:
                if tid in self.ppi_text_pool: self.ppi_text_pool[tid].setVisible(False)
                if tid in self.ppi_vector_pool: self.ppi_vector_pool[tid].setVisible(False)
                if tid in self.ppi_trail_pool: self.ppi_trail_pool[tid].setVisible(False)
                
        for tid in list(self.map_text_pool.keys()):
            if tid not in active_tids:
                if tid in self.map_text_pool: self.map_text_pool[tid].setVisible(False)
                if tid in self.map_vector_pool: self.map_vector_pool[tid].setVisible(False)
                if tid in self.map_trail_pool: self.map_trail_pool[tid].setVisible(False)

        for sym in ['o', 't', 's', 'x', '+']:
            if ppi_spots[sym]:
                self.ppi_scatters[sym].setData(ppi_spots[sym])
            else:
                self.ppi_scatters[sym].clear()
                
            if map_spots[sym]:
                self.map_scatters[sym].setData(map_spots[sym])
            else:
                self.map_scatters[sym].clear()
        
        # Renderizar eventos de degradación en el PPI
        for event in self.degradation_events:
            details = event.get('details', '')
            r_match = re.search(r"R:([\d\.]+)", details)
            az_match = re.search(r"Az:([\d\.]+)|Az1:([\d\.]+)", details)
            
            if r_match and az_match:
                r = float(r_match.group(1))
                az = float(az_match.group(1) or az_match.group(2))
                x_ppi = r * math.sin(math.radians(az))
                y_ppi = r * math.cos(math.radians(az))
                degradation_pos.append((x_ppi, y_ppi))
                degradation_brushes.append(pg.mkBrush(255, 0, 0, 150))
        
        if degradation_pos:
            spots = [{'pos': pos, 'brush': br, 'size': 15} for pos, br in zip(degradation_pos, degradation_brushes)]
            self.degradation_scatter.setData(spots)
        else:
            self.degradation_scatter.clear()

    def _pulse_degradations(self):
        """Anima el tamaño de los marcadores de degradación para que parpadeen."""
        if not self.degradation_scatter.isVisible():
            return
        
        self.pulse_state = (self.pulse_state + 1) % 2
        if self.pulse_state == 0:
            self.degradation_scatter.setSize(15)
        else:
            self.degradation_scatter.setSize(25)

    def _on_ingestion_finished(self, total, pd_intervals, pd_dict, analytics_stats, degradations, detected_rpm):
        self.statusBar.showMessage("Configurando entorno de simulación...", 3000)
        
        # Asignar resultados del hilo
        self.pd_intervals = pd_intervals
        self.pd_dict = pd_dict
        self.analytics_stats = analytics_stats
        self.degradation_events = degradations
        self.detected_rpm = detected_rpm if detected_rpm > 0 else 15.0
        
        # Aplanar la lista de deques a una lista simple de récords (Para iniciar el TOD de la GUI)
        all_records_in_tracks = [record for track_deque in self.track_manager.tracks.values() for record in track_deque]
        
        # --- Actualizar Módulo 1: Dashboard de Vistas Previas ---
        pos_01, pos_48, pos_21, pos_62 = [], [], [], []
        
        for rec in all_records_in_tracks:
            cat = rec.get('category')
            if cat in [1, 48]:
                r = rec.get('raw_range')
                az = rec.get('raw_azimuth')
                if r is not None and az is not None and r >= 0 and az >= 0:
                    x = r * math.sin(math.radians(az))
                    y = r * math.cos(math.radians(az))
                    if cat == 1: pos_01.append({'pos': (x, y)})
                    else: pos_48.append({'pos': (x, y)})
            elif cat in [21, 62]:
                lat = rec.get('latitude')
                lon = rec.get('longitude')
                if lat is not None and lon is not None:
                    if cat == 21: pos_21.append({'pos': (lon, lat)})
                    else: pos_62.append({'pos': (lon, lat)})
                    
        self.scatter_cat01.setData(pos_01)
        self.scatter_cat48.setData(pos_48)
        self.scatter_cat21.setData(pos_21)
        self.scatter_cat62.setData(pos_62)
        
        # Cambiar a la pestaña del Dashboard automáticamente al terminar la carga
        self.tabs.setCurrentIndex(0)

        # Inicializar el Tiempo Base (TOD) de la simulación y llenar Combo de Sensores
        min_t = float('inf')
        sensors = set()
        
        for rec in all_records_in_tracks:
            t = rec.get('timestamp')
            if t is not None:
                min_t = min(min_t, t)
            sac = rec.get('sac')
            sic = rec.get('sic')
            if sac is not None and sic is not None:
                sensors.add((sac, sic))
                
        if min_t != float('inf'):
            # Avanzamos el TOD inicial 30 segundos para que la vista táctica ya tenga blancos visibles al cargar
            self.current_tod = min_t + 30.0
            self.time_label.setText(f"TOD: {time.strftime('%H:%M:%S', time.gmtime(self.current_tod))}")
        else:
            self.current_tod = 0
            self.time_label.setText("TOD: 00:00:00")
            
        # Calcular el Offset de la antena para sincronizar el barrido visual con los plots
        self.antenna_offset_deg = 0.0
        if self.detected_rpm > 0:
            deg_per_sec = (self.detected_rpm / 60.0) * 360.0
            for rec in all_records_in_tracks:
                if rec.get('category') in [1, 48] and rec.get('raw_azimuth') is not None and rec.get('timestamp') is not None:
                    expected_angle = (rec['timestamp'] * deg_per_sec) % 360
                    self.antenna_offset_deg = rec['raw_azimuth'] - expected_angle
                    break
            
        self.sensor_source_combo.clear()
        for sac, sic in sorted(sensors):
            self.sensor_source_combo.addItem(f"SAC: {sac:03d} / SIC: {sic:03d}", (sac, sic))
        if self.sensor_source_combo.count() > 0:
            self.sensor_source_combo.setCurrentIndex(0)
        
        self.statusBar.showMessage(f"Ingesta lista. RPM detectada (CAT 02/34): {self.detected_rpm:.2f}. Total targets: {total}", 5000)
        self._force_redraw() # Forzar redibujo para mostrar marcadores de degradación

    def _on_ingestion_error(self, error_msg):
        self.statusBar.showMessage(f"Error en la ingesta: {error_msg}", 10000)

    def _show_pd_dialog(self):
        if hasattr(self, 'pd_intervals'):
            dialog = StatsDialog(self, self.pd_intervals, self.pd_dict, self.analytics_stats)
            dialog.exec()
        else:
            self.statusBar.showMessage("Primero debe cargar y procesar un archivo.", 3000)

    def _show_degradation_dialog(self):
        if hasattr(self, 'degradation_events'):
            dialog = DegradationDialog(self, self.degradation_events)
            dialog.exec()
        else:
            self.statusBar.showMessage("Primero debe cargar y procesar un archivo.", 3000)

    def _animate_sweep(self):
        """Anima la línea de barrido del radar en el PPI (Rotación atada al TOD)."""
        if hasattr(self, 'current_tod') and self.current_tod is not None:
            rpm = getattr(self, 'detected_rpm', 15.0)
            if rpm <= 0:
                self.sweep_line.setVisible(False)
                return
                
            deg_per_sec = (rpm / 60.0) * 360.0
            
            # Sincronización perfecta (Zero-Drift): Proyectar desde el último plot dibujado
            anchor_time = getattr(self, 'latest_sweep_anchor_time', -1)
            anchor_az = getattr(self, 'latest_sweep_anchor_az', 0.0)
            
            if anchor_time > 0 and self.current_tod >= anchor_time:
                dt = self.current_tod - anchor_time
                self.sweep_angle = (anchor_az + (dt * deg_per_sec)) % 360
            else:
                offset = getattr(self, 'antenna_offset_deg', 0.0)
                self.sweep_angle = ((self.current_tod * deg_per_sec) + offset) % 360
            
            r_max = 250 
            x = r_max * math.sin(math.radians(self.sweep_angle))
            y = r_max * math.cos(math.radians(self.sweep_angle))
            self.sweep_line.setData([0, x], [0, y])
            self.sweep_line.setVisible(True)

    def _run_garbage_collection(self):
        # Se desactiva intencionalmente durante la Fase 2 para que el Playback no pierda datos de memoria
        pass

    def _clear_buffer(self):
        self.track_manager.clear_all()
        self.known_track_ids.clear()
        self.track_filter_combo.clear()
        self.track_filter_combo.addItem("Mostrar Todos", "ALL")
        for scatter in self.ppi_scatters.values(): scatter.clear()
        for scatter in self.map_scatters.values(): scatter.clear()
        self.degradation_scatter.clear()
        
        # Limpiar cuadrantes del Dashboard
        if hasattr(self, 'scatter_cat01'):
            self.scatter_cat01.clear()
            self.scatter_cat48.clear()
            self.scatter_cat21.clear()
            self.scatter_cat62.clear()
        
        for item in self.ppi_text_pool.values(): self.ppi_view.removeItem(item)
        for item in self.ppi_vector_pool.values(): self.ppi_view.removeItem(item)
        for item in self.ppi_trail_pool.values(): self.ppi_view.removeItem(item)
        self.ppi_text_pool.clear()
        self.ppi_vector_pool.clear()
        self.ppi_trail_pool.clear()
        
        for item in self.map_text_pool.values(): self.map_view.removeItem(item)
        for item in self.map_vector_pool.values(): self.map_view.removeItem(item)
        for item in self.map_trail_pool.values(): self.map_view.removeItem(item)
        self.map_text_pool.clear()
        self.map_vector_pool.clear()
        self.map_trail_pool.clear()
        
        self.timeline_slider.setEnabled(False)
        self.timeline_slider.setValue(0)
        self.statusBar.showMessage("Buffer de memoria vaciado instantáneamente.", 5000)
        
    def _export_kml_advanced(self):
        if not self.track_manager.tracks:
            self.statusBar.showMessage("No hay datos de trazas para exportar.", 3000)
            return
        
        file_path, _ = QFileDialog.getSaveFileName(self, "Guardar KML Avanzado", "", "KML Files (*.kml)")
        if file_path:
            all_records = [rec for deq in self.track_manager.tracks.values() for rec in deq]
            KMLExporter.export(all_records, file_path)
            self.statusBar.showMessage(f"Exportado a {file_path}", 5000)

    def _export_pdf_report(self):
        if not self.track_manager.tracks:
            self.statusBar.showMessage("No hay datos para generar un reporte.", 3000)
            return
            
        file_path, _ = QFileDialog.getSaveFileName(self, "Guardar Reporte PDF", "", "PDF Files (*.pdf)")
        if file_path:
            all_records = [rec for deq in self.track_manager.tracks.values() for rec in deq]
            summary_text = ReportGenerator.generate_summary(all_records, self.sensor_registry)
            PDFReportGenerator.export_pdf(summary_text, file_path)
            self.statusBar.showMessage(f"Reporte PDF guardado en {file_path}", 5000)

    def closeEvent(self, event):
        if self.worker and self.worker.isRunning():
            self.worker.stop()
            self.worker.wait()
        event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = ATCNightWindow()
    window.show()
    sys.exit(app.exec())