"""
dashboard_widget.py — Dashboard de Control Lateral (Glassmorphism)
===================================================================
Panel de control para ASTERIX Radar Decoder con estilo Glassmorphism.

Funcionalidades:
  1. Reloj digital ToD (HH:mm:ss) en la parte superior
  2. Filtro de Squawk/Callsign con resaltado (highlight amarillo)
  3. Lista dinámica de checkboxes SAC/SIC
  4. Control de reproducción TDD (Slider + Play/Pausa/Stop)
  5. Botón Fit View
  6. Panel de estado (sensores detectados, ploteos activos)
  7. Barra de progreso del escaneo
  8. Indicador de archivo cargado
  9. Botón "Decodificar Archivo" (FASE 1)
 10. Botón "Mostrar Barrido" (FASE 3)

Estética:
  - Fondo translúcido semi-oscuro (efecto vidrio)
  - Bordes redondeados
  - Tipografía Consolas / Monospace
  - Reloj ToD verde neón
"""

from typing import Dict, Tuple, List, Optional, Set, Callable, Any

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QCheckBox, QScrollArea, QGroupBox, QPushButton, QSlider,
    QFrame, QSizePolicy, QProgressBar, QRadioButton, QButtonGroup, QAbstractButton,
    QComboBox,
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QFont, QColor, QPalette


# ============================================================
# CONSTANTES DE COLOR (Glassmorphism)
# ============================================================
COLOR_BG_GLASS       = QColor(20, 24, 32, 220)   # #141820 con alpha
COLOR_BORDER         = QColor(42, 58, 74, 180)   # #2A3A4A
COLOR_TEXT_PRIMARY   = QColor("#FFFFFF")
COLOR_TEXT_SECONDARY = QColor("#AAAAAA")
COLOR_ACCENT_CYAN    = QColor("#00FFFF")
COLOR_ACCENT_GREEN   = QColor("#00FF00")
COLOR_HIGHLIGHT      = QColor(255, 255, 0, 200)  # Amarillo para highlight
COLOR_BUTTON_BG      = QColor(30, 42, 58, 200)
COLOR_BUTTON_HOVER   = QColor(42, 58, 74, 200)
COLOR_INPUT_BG       = QColor(26, 34, 48, 200)
COLOR_INPUT_BORDER   = QColor(42, 58, 74)
COLOR_WARNING        = QColor(255, 170, 0, 220)   # Naranja para advertencias
COLOR_DECODE_READY   = QColor("#00FF00")           # Verde brillante para decode listo
COLOR_DECODE_BG      = QColor(0, 80, 0, 200)       # Verde oscuro translúcido


class DashboardWidget(QFrame):
    """
    Panel lateral de control con estilo Glassmorphism.

    Señales emitidas:
      filters_changed(set[tuple[int,int]], str)
          -> (active_sensors, squawk_filter)
      play_toggle()
      stop_playback()
      fit_view()
      seek_requested(float)  -> ToD objetivo
      load_pcap_requested()  -> botón "Cargar PCAP"
      decode_requested()     -> FASE 1: botón "Decodificar Archivo"
      sweep_toggled(bool)    -> FASE 3: toggle barrido
    """

    filters_changed = pyqtSignal(set, str)   # active_sensors, squawk_filter
    center_sensor_changed = pyqtSignal(tuple)  # (sac, sic)
    play_toggle = pyqtSignal()
    stop_requested = pyqtSignal()
    fit_requested = pyqtSignal()
    seek_requested = pyqtSignal(float)       # ToD objetivo
    load_pcap_requested = pyqtSignal()       # botón "Cargar PCAP"
    decode_requested = pyqtSignal()          # FASE 1: botón "Decodificar Archivo"
    udp_connect_requested = pyqtSignal(str, int) # Conexión a stream UDP
    sweep_toggled = pyqtSignal(bool)         # FASE 3: toggle barrido
    centrar_mendoza_requested = pyqtSignal()  # FASE 2/3: centrar en Mendoza CAT 62

    def __init__(self, sensores: Dict[Tuple[int, int], Dict], parent=None):
        super().__init__(parent)
        self.sensores = sensores
        self._playing = False

        self.sensor_widgets: Dict[Tuple[int, int], QWidget] = {}
        self.sensor_checkboxes: Dict[Tuple[int, int], QCheckBox] = {}
        self.sensor_center_radios: Dict[Tuple[int, int], QRadioButton] = {}
        self.center_button_group = QButtonGroup()

        # Estilo container
        # FASE 1: Geometría de barra lateral rígida
        self.setMinimumWidth(300)
        self.setMaximumWidth(340)
        self.setStyleSheet(self._glass_style())

        self._setup_ui()

        # Timer para actualizar reloj ToD
        self._tod_timer = QTimer(self)
        self._tod_timer.timeout.connect(self._update_clock)
        self._tod_timer.start(200)

        self.center_button_group.buttonClicked.connect(self._on_center_changed)

        # Último ToD recibido
        self._current_tod = 0.0

    # ================================================================
    # ESTILO GLASSMORPHISM
    # ================================================================

    def _glass_style(self) -> str:
        bg = f"rgba({COLOR_BG_GLASS.red()},{COLOR_BG_GLASS.green()},{COLOR_BG_GLASS.blue()},{COLOR_BG_GLASS.alpha()})"
        border = f"rgba({COLOR_BORDER.red()},{COLOR_BORDER.green()},{COLOR_BORDER.blue()},{COLOR_BORDER.alpha()})"
        accent = COLOR_ACCENT_CYAN.name()
        return f"""
            QFrame {{
                background-color: {bg};
                border: 1px solid {border};
                border-radius: 12px;
                margin: 4px;
            }}
            QGroupBox {{
                background-color: transparent;
                border: 1px solid {border};
                border-radius: 8px;
                margin-top: 14px;
                padding-top: 18px;
                font-family: 'Consolas', 'Monospace';
                font-size: 11px;
                color: {COLOR_TEXT_SECONDARY.name()};
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                left: 12px;
                padding: 0 6px;
                color: {accent};
                font-weight: bold;
            }}
            QLabel {{
                color: {COLOR_TEXT_SECONDARY.name()};
                font-family: 'Consolas', 'Monospace';
                font-size: 11px;
            }}
            QCheckBox {{
                color: {COLOR_TEXT_SECONDARY.name()};
                font-family: 'Consolas', 'Monospace';
                font-size: 10px;
                padding: 2px 0;
                spacing: 6px;
            }}
            QCheckBox::indicator {{
                width: 14px;
                height: 14px;
                border: 1px solid {border};
                border-radius: 3px;
                background-color: transparent;
            }}
            QCheckBox::indicator:checked {{
                background-color: {accent};
                border-color: {accent};
            }}
            QRadioButton {{
                font-size: 9px;
                color: {COLOR_TEXT_SECONDARY.name()};
            }}
            QRadioButton::indicator {{
                width: 14px;
                height: 14px;
                border: 1px solid {border};
                border-radius: 3px;
                background-color: transparent;
            }}
            QRadioButton::indicator:checked {{
                background-color: {COLOR_ACCENT_GREEN.name()};
                border-color: {accent};
            }}
            QLineEdit {{
                background-color: {COLOR_INPUT_BG.name()};
                color: {accent};
                border: 1px solid {COLOR_INPUT_BORDER.name()};
                border-radius: 5px;
                padding: 6px 10px;
                font-family: 'Consolas', 'Monospace';
                font-size: 11px;
            }}
            QLineEdit:focus {{
                border-color: {accent};
            }}
            QPushButton {{
                background-color: {COLOR_BUTTON_BG.name()};
                color: {COLOR_TEXT_PRIMARY.name()};
                border: 1px solid {border};
                border-radius: 6px;
                padding: 8px 14px;
                font-family: 'Consolas', 'Monospace';
                font-size: 12px;
                min-width: 50px;
            }}
            QPushButton:hover {{
                background-color: {COLOR_BUTTON_HOVER.name()};
                border-color: {accent};
            }}
            QPushButton:pressed {{
                background-color: rgba(11, 14, 20, 200);
            }}
            QScrollArea {{
                border: none;
                background-color: transparent;
            }}
            QSlider::groove:horizontal {{
                height: 5px;
                background: rgba(26, 34, 48, 200);
                border-radius: 2px;
            }}
            QSlider::handle:horizontal {{
                background: {accent};
                width: 14px;
                height: 14px;
                margin: -5px 0;
                border-radius: 7px;
            }}
            QSlider::sub-page:horizontal {{
                background: {COLOR_ACCENT_GREEN.name()};
                border-radius: 2px;
            }}
            QProgressBar {{
                background-color: rgba(26, 34, 48, 200);
                border: 1px solid {border};
                border-radius: 5px;
                text-align: center;
                font-family: 'Consolas', 'Monospace';
                font-size: 9px;
                color: {COLOR_ACCENT_CYAN.name()};
                height: 14px;
            }}
            QProgressBar::chunk {{
                background-color: {accent};
                border-radius: 4px;
            }}
        """

    # ================================================================
    # UI
    # ================================================================

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(10, 10, 10, 10)

        # ---- INDICADOR DE ARCHIVO CARGADO ----
        self.lbl_filename = QLabel("📁 Sin archivo")
        self.lbl_filename.setStyleSheet(f"""
            font-family: 'Consolas', 'Monospace';
            font-size: 10px;
            color: {COLOR_ACCENT_CYAN.name()};
            background-color: rgba(0, 0, 0, 60);
            border: 1px solid rgba(42, 58, 74, 100);
            border-radius: 6px;
            padding: 4px 8px;
        """)
        self.lbl_filename.setWordWrap(True)
        layout.addWidget(self.lbl_filename)

        # ---- RELOJ DIGITAL ToD ----
        self.lbl_clock = QLabel("00:00:00")
        self.lbl_clock.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_clock.setStyleSheet(f"""
            font-family: 'Consolas', 'Monospace';
            font-size: 28px;
            font-weight: bold;
            color: {COLOR_ACCENT_GREEN.name()};
            background-color: rgba(0, 0, 0, 80);
            border: 1px solid rgba(42, 58, 74, 120);
            border-radius: 8px;
            padding: 8px;
        """)
        layout.addWidget(self.lbl_clock)

        # ---- BARRA DE PROGRESO DE ESCANEO ----
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(False)
        self.progress_bar.setTextVisible(True)
        layout.addWidget(self.progress_bar)

        # ---- FILTRO SQUAWK (con highlight) ----
        gb_squawk = QGroupBox("Filtro Squawk / Callsign")
        sq_layout = QVBoxLayout()

        lbl_hint = QLabel("Ingrese código (4 dígitos) o callsign:")
        sq_layout.addWidget(lbl_hint)

        self.squawk_input = QLineEdit()
        self.squawk_input.setPlaceholderText("Ej: 1234  o  ARG1234")
        self.squawk_input.textChanged.connect(self._on_filters_changed)
        sq_layout.addWidget(self.squawk_input)

        lbl_highlight = QLabel("(Coincidencia → resaltado amarillo)")
        lbl_highlight.setStyleSheet("color: rgba(255, 255, 0, 150); font-size: 9px;")
        sq_layout.addWidget(lbl_highlight)

        gb_squawk.setLayout(sq_layout)
        layout.addWidget(gb_squawk)

        # ---- FILTRO SENSORES (SAC/SIC) ----
        gb_sensors = QGroupBox("Sensores (SAC/SIC)")
        sensors_layout = QVBoxLayout()

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }"
                             "QScrollBar:vertical { width: 6px; }")
        scroll_container = QWidget()
        scroll_container.setStyleSheet("background: transparent;")
        self.scroll_inner_layout = QVBoxLayout(scroll_container)
        self.scroll_inner_layout.setContentsMargins(0, 0, 0, 0)
        self.scroll_inner_layout.setSpacing(2)

        self.scroll_inner_layout.addStretch()
        scroll.setWidget(scroll_container)
        sensors_layout.addWidget(scroll)
        gb_sensors.setLayout(sensors_layout)
        layout.addWidget(gb_sensors)

        # ---- FILTRO DE SENSORES (SAC/SIC) con QComboBox ----
        self.gb_filtros_sensores = QGroupBox("Filtro de Sensores (SAC/SIC)")
        filtros_layout = QVBoxLayout()
        self.lbl_filtros_info = QLabel("Todos los sensores visibles")
        self.lbl_filtros_info.setStyleSheet("font-size: 10px; color: #00FF00;")
        filtros_layout.addWidget(self.lbl_filtros_info)
        self.combo_sensores = QComboBox()
        self.combo_sensores.addItem("Todos los sensores")  # Opción por defecto
        self.combo_sensores.setStyleSheet("""
            QComboBox {
                background-color: rgba(26, 34, 48, 200);
                color: #00FFFF;
                border: 1px solid rgba(42, 58, 74, 180);
                border-radius: 5px;
                padding: 4px 8px;
                font-family: 'Consolas', 'Monospace';
                font-size: 11px;
            }
            QComboBox::drop-down {
                border: none;
                width: 20px;
            }
            QComboBox QAbstractItemView {
                background-color: #1a2230;
                color: #00FFFF;
                selection-background-color: #2a3a4a;
                font-family: 'Consolas', 'Monospace';
                font-size: 11px;
            }
        """)
        filtros_layout.addWidget(self.combo_sensores)
        self.gb_filtros_sensores.setLayout(filtros_layout)
        layout.addWidget(self.gb_filtros_sensores)

        # ---- CONEXIÓN UDP ----
        gb_udp = QGroupBox("Conexión UDP")
        udp_layout = QVBoxLayout()
        
        ip_layout = QHBoxLayout()
        lbl_ip = QLabel("IP:")
        self.ip_input = QLineEdit("127.0.0.1")
        ip_layout.addWidget(lbl_ip)
        ip_layout.addWidget(self.ip_input)
        udp_layout.addLayout(ip_layout)

        port_layout = QHBoxLayout()
        lbl_port = QLabel("Puerto:")
        self.port_input = QLineEdit("9999")
        port_layout.addWidget(lbl_port)
        port_layout.addWidget(self.port_input)
        udp_layout.addLayout(port_layout)

        self.btn_connect_udp = QPushButton("Conectar a Stream UDP")
        self.btn_connect_udp.setMinimumHeight(32)
        self.btn_connect_udp.clicked.connect(self._on_udp_connect)
        udp_layout.addWidget(self.btn_connect_udp)

        gb_udp.setLayout(udp_layout)
        layout.addWidget(gb_udp)

        # ---- BOTÓN FÍSICO DE BARRIDO (FASE 3) ----
        # QPushButton con toggle ON/OFF: Línea de Barrido
        # OFF: Se oculta el haz verde. Los ploteos se actualizan de inmediato según ToD.
        # ON: Se dibuja la línea giratoria y los blancos aplican persistencia síncrona.
        self.btn_sweep = QPushButton("Línea de Barrido ON")
        self.btn_sweep.setCheckable(True)
        self.btn_sweep.setMinimumHeight(32)
        self.btn_sweep.setChecked(True)
        self.btn_sweep.clicked.connect(self._on_sweep_toggle)
        self.btn_sweep.setStyleSheet("""
            QPushButton {
                background-color: rgba(42, 58, 74, 200);
                color: #00FF00;
                border: 1px solid rgba(42, 58, 74, 180);
                border-radius: 6px;
                padding: 8px 14px;
                font-family: 'Consolas', 'Monospace';
                font-size: 11px;
                min-width: 50px;
            }
            QPushButton:checked {
                background-color: rgba(0, 100, 0, 200);
                border-color: #39FF14;
            }
            QPushButton:hover {
                background-color: rgba(42, 58, 74, 200);
                border-color: #00FFFF;
            }
        """)
        layout.addWidget(self.btn_sweep)

        # ---- BOTÓN DE AUTO-CENTRADO GEOGRÁFICO (FASE 2/3) ----
        self.btn_centrar_mendoza = QPushButton("📍 Centrar en Mendoza (CAT 62)")
        self.btn_centrar_mendoza.setMinimumHeight(32)
        self.btn_centrar_mendoza.clicked.connect(self._on_centrar_mendoza)
        self.btn_centrar_mendoza.setStyleSheet("""
            QPushButton {
                background-color: rgba(180, 80, 0, 180);
                color: #FFCC00;
                border: 1px solid rgba(255, 200, 0, 80);
                border-radius: 6px;
                padding: 8px 14px;
                font-family: 'Consolas', 'Monospace';
                font-size: 10px;
                min-width: 50px;
            }
            QPushButton:hover {
                background-color: rgba(200, 100, 0, 200);
                border-color: #FFCC00;
            }
        """)
        layout.addWidget(self.btn_centrar_mendoza)

        # ---- CONTROL DE REPRODUCCIÓN TDD ----
        gb_playback = QGroupBox("Reproducción TDD")
        pb_layout = QVBoxLayout()

        # Slider
        self.time_slider = QSlider(Qt.Orientation.Horizontal)
        self.time_slider.setRange(0, 1000)
        self.time_slider.sliderPressed.connect(self._on_slider_pressed)
        self.time_slider.sliderReleased.connect(self._on_slider_released)
        pb_layout.addWidget(self.time_slider)

        # Botones
        btn_row = QHBoxLayout()
        btn_row.setSpacing(4)

        self.btn_play = QPushButton("▶")
        self.btn_play.setEnabled(False)  # FASE 1: Deshabilitado hasta decodificar
        self.btn_play.setMinimumHeight(32)
        self.btn_play.clicked.connect(self._toggle_play)
        btn_row.addWidget(self.btn_play)

        self.btn_stop = QPushButton("■")
        self.btn_stop.setMinimumHeight(32)
        self.btn_stop.clicked.connect(self._on_stop)
        btn_row.addWidget(self.btn_stop)

        self.btn_fit = QPushButton("⟲ Fit")
        self.btn_fit.setMinimumHeight(32)
        self.btn_fit.clicked.connect(self.fit_requested.emit)
        btn_row.addWidget(self.btn_fit)

        pb_layout.addLayout(btn_row)

        # Label de progreso
        self.lbl_progress = QLabel("Inicializando...")
        self.lbl_progress.setStyleSheet("font-size: 10px; color: rgba(136, 136, 136, 180);")
        pb_layout.addWidget(self.lbl_progress)

        # Label de advertencias (sensores sin configuración)
        self.lbl_warning = QLabel("")
        self.lbl_warning.setStyleSheet(f"""
            font-size: 9px;
            color: rgba(255, 170, 0, 200);
            background-color: rgba(255, 170, 0, 20);
            border: 1px solid rgba(255, 170, 0, 60);
            border-radius: 4px;
            padding: 3px 6px;
        """)
        self.lbl_warning.setWordWrap(True)
        self.lbl_warning.setVisible(False)
        pb_layout.addWidget(self.lbl_warning)

        gb_playback.setLayout(pb_layout)
        layout.addWidget(gb_playback)

        # ---- BOTÓN DECODIFICAR ARCHIVO (FASE 1) ----
        self.btn_decode = QPushButton("⚙  Decodificar Archivo")
        self.btn_decode.setEnabled(False)  # Se habilita tras escaneo
        self.btn_decode.setMinimumHeight(32)
        self.btn_decode.clicked.connect(self._on_decode_clicked)
        self.btn_decode.setStyleSheet(f"""
            QPushButton {{
                background-color: rgba(0, 80, 0, 180);
                color: #00FF00;
                border: 2px solid rgba(0, 255, 0, 80);
                border-radius: 8px;
                padding: 12px 14px;
                font-family: 'Consolas', 'Monospace';
                font-size: 13px;
                font-weight: bold;
                min-width: 50px;
            }}
            QPushButton:hover {{
                background-color: rgba(0, 120, 0, 200);
                border-color: #00FF00;
            }}
            QPushButton:disabled {{
                background-color: rgba(30, 42, 58, 200);
                color: rgba(136, 136, 136, 150);
                border: 1px solid rgba(42, 58, 74, 100);
            }}
            QPushButton:pressed {{
                background-color: rgba(0, 160, 0, 220);
            }}
        """)
        layout.addWidget(self.btn_decode)

        # ---- BOTÓN CARGAR PCAP ----
        btn_load = QPushButton("📁  Cargar PCAP...")
        btn_load.setMinimumHeight(32)
        btn_load.clicked.connect(self.load_pcap_requested.emit)
        layout.addWidget(btn_load)

        # ---- PANEL DE ESTADO ----
        gb_status = QGroupBox("Estado")
        status_layout = QVBoxLayout()
        status_layout.setSpacing(2)

        self.lbl_sensors = QLabel("Sensores: 0")
        self.lbl_sensors.setStyleSheet("font-size: 10px;")
        status_layout.addWidget(self.lbl_sensors)

        self.lbl_targets = QLabel("Ploteos: 0")
        self.lbl_targets.setStyleSheet("font-size: 10px;")
        status_layout.addWidget(self.lbl_targets)

        # FASE 4: CONTADORES POR CATEGORÍA
        self.lbl_cat_counts = QLabel("⬜ 01: 0 | ◯ 48: 0 | △ 21: 0 | ⬡ 62: 0")
        self.lbl_cat_counts.setStyleSheet("font-size: 10px;")
        status_layout.addWidget(self.lbl_cat_counts)

        gb_status.setLayout(status_layout)
        layout.addWidget(gb_status)

        layout.addStretch()

    # ================================================================
    # SLOTS PÚBLICOS (conectados desde MainWindow)
    # ================================================================

    @pyqtSlot(float)
    def update_tod(self, tod: float):
        """Actualiza el ToD actual (desde Worker o RadarWidget)."""
        self._current_tod = tod

    @pyqtSlot(float)
    def set_duration(self, duration: float):
        """Configura el rango del slider según la duración del PCAP."""
        if duration > 0:
            self.time_slider.setRange(0, int(duration * 1000))
            self.lbl_progress.setText(f"Duración: {duration:.1f}s")
        else:
            self.time_slider.setRange(0, 1000)
            self.lbl_progress.setText("Duración: N/A")

    @pyqtSlot(int)
    def set_total_frames(self, total: int):
        """Muestra el total de frames decodificados."""
        self.lbl_targets.setText(f"Total: {total}")

    @pyqtSlot(dict)
    def update_category_counts(self, counts: Dict[int, int]):
        """FASE 4: Actualiza los contadores de blancos por categoría."""
        c01 = counts.get(1, 0)
        c21 = counts.get(21, 0)
        c48 = counts.get(48, 0)
        c62 = counts.get(62, 0)
        text = f"⬜ 01: {c01} | ◯ 48: {c48} | △ 21: {c21} | ⬡ 62: {c62}"
        self.lbl_cat_counts.setText(text)

    @pyqtSlot(int)
    def set_sensor_count(self, count: int):
        """Actualiza contador de sensores detectados."""
        self.lbl_sensors.setText(f"Sensores detectados: {count}")

    @pyqtSlot(str)
    def set_progress_text(self, text: str):
        """Actualiza texto de progreso."""
        self.lbl_progress.setText(text)

    @pyqtSlot(int)
    def set_scan_percent(self, pct: int):
        """Actualiza la barra de progreso de escaneo."""
        if pct < 0 or pct >= 100:
            self.progress_bar.setVisible(False)
            self.progress_bar.setValue(0)
        else:
            self.progress_bar.setVisible(True)
            self.progress_bar.setValue(pct)

    @pyqtSlot(str)
    def set_loaded_filename(self, filename: str):
        """Muestra el nombre del archivo cargado en el dashboard."""
        self.lbl_filename.setText(f"📁 {filename}")

    @pyqtSlot(str)
    def set_warning_message(self, msg: str):
        """Muestra un mensaje de advertencia (ej. sensores sin config)."""
        if msg:
            self.lbl_warning.setText(msg)
            self.lbl_warning.setVisible(True)
        else:
            self.lbl_warning.setVisible(False)
            self.lbl_warning.setText("")

    @pyqtSlot(bool)
    def set_decode_enabled(self, enabled: bool):
        """FASE 1: Habilita/deshabilita el botón Decodificar Archivo."""
        self.btn_decode.setEnabled(enabled)

    @pyqtSlot(bool)
    def set_play_enabled(self, enabled: bool):
        """FASE 1: Habilita/deshabilita el botón Play."""
        self.btn_play.setEnabled(enabled)

    @pyqtSlot(object)
    def on_new_plot(self, data: Dict[str, Any]):
        """
        Slot para recibir plots y actualizar el reloj ToD.
        Conectar directamente desde AsterixWorker.new_plot.
        """
        tod = data.get('time', 0.0)
        if tod > 0:
            self._current_tod = tod

    # ================================================================
    # RESETEO DE SESIÓN
    # ================================================================

    @pyqtSlot()
    def reset_session(self):
        """Resetea toda la UI para una nueva carga de PCAP."""
        self._current_tod = 0.0
        self._playing = False
        self.btn_play.setText("▶")
        self.btn_play.setEnabled(False)  # FASE 1: Play deshabilitado hasta decodificar
        self.btn_decode.setEnabled(False)  # Se habilitará tras escaneo
        self.lbl_clock.setText("00:00:00")
        self.time_slider.setValue(0)
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(False)
        self.lbl_progress.setText("Cargando...")
        self.lbl_targets.setText("Ploteos: 0")
        self.lbl_sensors.setText("Sensores detectados: 0")
        self.lbl_cat_counts.setText("⬜ 01: 0 | ◯ 48: 0 | △ 21: 0 | ⬡ 62: 0")
        self.set_warning_message("")

        # Limpiar controles de sensores dinámicos
        for widget in self.sensor_widgets.values():
            widget.deleteLater()
        self.sensor_widgets.clear()
        self.sensor_checkboxes.clear()
        self.sensor_center_radios.clear()
        # QButtonGroup se limpia solo al borrar los botones

    # ================================================================
    # RELOJ DIGITAL
    # ================================================================

    def _update_clock(self):
        """Actualiza el display del reloj ToD."""
        tod = self._current_tod
        h = int(tod // 3600) % 24
        m = int((tod % 3600) // 60)
        s = int(tod % 60)
        self.lbl_clock.setText(f"{h:02d}:{m:02d}:{s:02d}")

    # ================================================================
    # FILTROS
    # ================================================================

    @pyqtSlot(QAbstractButton)
    def _on_center_changed(self, clicked_button: QAbstractButton):
        """Emite la señal cuando se selecciona un nuevo sensor como centro."""
        for key, radio_button in self.sensor_center_radios.items():
            if radio_button == clicked_button:
                self.center_sensor_changed.emit(key)
                break

    def _on_filters_changed(self):
        """Recolecta estado de filtros y emite señal."""
        active: Set[Tuple[int, int]] = set()
        for (sac, sic), cb in self.sensor_checkboxes.items():
            if cb.isChecked():
                active.add((sac, sic))

        squawk_text = self.squawk_input.text().strip()
        self.filters_changed.emit(active, squawk_text)

    def _on_udp_connect(self):
        """Maneja el clic en 'Conectar a Stream UDP'."""
        ip = self.ip_input.text().strip()
        port_str = self.port_input.text().strip()
        try:
            port = int(port_str)
            if ip and 0 < port < 65536:
                self.udp_connect_requested.emit(ip, port)
        except ValueError:
            self.set_warning_message(f"Error: Puerto UDP inválido '{port_str}'")

    def get_active_sensors(self) -> Set[Tuple[int, int]]:
        """Retorna sensores activos (útil para inicialización)."""
        active: Set[Tuple[int, int]] = set()
        for (sac, sic), cb in self.sensor_checkboxes.items():
            if cb.isChecked():
                active.add((sac, sic))
        return active

    def get_squawk_filter(self) -> str:
        """Retorna el texto del filtro Squawk."""
        return self.squawk_input.text().strip()

    # ================================================================
    # CONTROL DE REPRODUCCIÓN
    # ================================================================

    def _on_decode_clicked(self):
        """FASE 1: El usuario presiona 'Decodificar Archivo'."""
        self.btn_decode.setEnabled(False)
        self.btn_decode.setText("⚙  Decodificando...")
        self.decode_requested.emit()

    def _toggle_play(self):
        """Toggle Play/Pausa."""
        self._playing = not self._playing
        self.btn_play.setText("❚❚" if self._playing else "▶")
        self.play_toggle.emit()

    @pyqtSlot()
    def set_play_state(self, playing: bool):
        """Actualiza el estado visual del botón Play desde fuera."""
        self._playing = playing
        self.btn_play.setText("❚❚" if playing else "▶")

    def _on_sweep_toggle(self):
        """FASE 3: Toggle del barrido.
        OFF: Se oculta el haz verde, los ploteos se actualizan de inmediato.
        ON: Se dibuja la línea giratoria con persistencia síncrona.
        """
        visible = self.btn_sweep.isChecked()
        self.btn_sweep.setText("Línea de Barrido ON" if visible else "Línea de Barrido OFF")
        self.sweep_toggled.emit(visible)

    def _on_centrar_mendoza(self):
        """FASE 2/3: Emite señal para centrar la vista en Mendoza (-32.89, -69.95)."""
        self.centrar_mendoza_requested.emit()

    def _on_stop(self):
        """Maneja el botón Stop."""
        self._playing = False
        self.btn_play.setText("▶")
        self.time_slider.setValue(0)
        self.lbl_clock.setText("00:00:00")
        self.stop_requested.emit()

    def _on_slider_pressed(self):
        """Slider presionado: pausa la reproducción."""
        if self._playing:
            self._playing = False
            self.btn_play.setText("▶")
            self.play_toggle.emit()  # Pauses if it was playing

    def _on_slider_released(self):
        """Slider liberado: envía seek al ToD correspondiente y reanuda."""
        if self.time_slider.maximum() > 0:
            # El valor del slider está en milisegundos. Se emite el offset en segundos.
            seek_offset_seconds = self.time_slider.value() / 1000.0
            self.seek_requested.emit(seek_offset_seconds)

            # Reanudar reproducción automáticamente
            if not self._playing:
                self._playing = True
                self.btn_play.setText("❚❚")
                self.play_toggle.emit()

    # ================================================================
    # MÉTODOS ADICIONALES
    # ================================================================
    
    def add_sensor_control(self, sac: int, sic: int, name: str):
        """Añade un checkbox de sensor dinámicamente (detectado en runtime)."""
        key = (sac, sic)
        if key not in self.sensor_checkboxes:
            # Widget contenedor para la fila
            row_widget = QWidget()
            row_layout = QHBoxLayout(row_widget)
            row_layout.setContentsMargins(2, 2, 2, 2)
            row_layout.setSpacing(6)

            cb = QCheckBox(f"{name} ({sac}/{sic})")
            cb.setChecked(True)
            cb.stateChanged.connect(self._on_filters_changed)

            rb = QRadioButton("Centro")
            rb.setFixedWidth(60)

            row_layout.addWidget(cb)
            row_layout.addStretch()
            row_layout.addWidget(rb)

            self.scroll_inner_layout.insertWidget(self.scroll_inner_layout.count() - 1, row_widget)

            self.sensor_widgets[key] = row_widget
            self.sensor_checkboxes[key] = cb
            self.sensor_center_radios[key] = rb
            self.center_button_group.addButton(rb)