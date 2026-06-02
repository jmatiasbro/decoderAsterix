"""
radar_widget.py — Widget PPI (Plan Position Indicator) para ASTERIX Radar Decoder
==================================================================================
Implementación profesional con:
  - Fondo oscuro #0B0E14, anillos concéntricos, barrido verde neón
  - Símbolos dinámicos por categoría (CAT48 círculo, CAT21 triángulo, CAT62 cuadrado)
  - Data blocks: Line1=Callsign/Squawk, Line2=FL, coloreados por SAC/SIC
  - Vector de tendencia (1 minuto) para CAT 21/62 con velocidad y rumbo

  FASE BARRIDO:
    - Los plots llegan a un buffer pending_plots[]
    - Solo se actualizan y refrescan cuando la línea de barrido (sweep) cruza su azimut
    - Esto sincroniza la aparición de blancos con la rotación de la antena

  FASE HISTORIAL:
    - Cada blanco guarda los últimos 5 puntos de trayectoria (history[])
    - Los puntos antiguos se dibujan sin etiqueta, con opacidad degradada

  FASE 2 - HARD RESET GEOGRÁFICO:
    - reset_origin_for_new_file() recrea el proyector y reproyecta el mapa DXF
      usando coordenadas geográficas (lat/lon) para que el mapa se recentre
      automáticamente en el nuevo radar.

  ESTABILIDAD:
    - Zoom clamp, safe_divide(), is_valid_coord(), try-except en todo bloque
    - MAX_PLOTS_RENDERED, poda de viejos, DXF estático cacheado

  PROHIBICIÓN ABSOLUTA:
    - self.history almacena EXCLUSIVAMENTE objetos HistoryPoint ligeros.
    - NUNCA almacenar diccionarios ASTERIX completos. El historial es mudo.
    - Simulación de tiempo vía Singleton SimulationTime para evitar saltos.
"""

import math
import time as time_module
from typing import Dict, List, Optional, Set, Tuple, Any
from collections import deque, defaultdict
from threading import Lock, RLock
from dataclasses import dataclass

from PyQt6.QtCore import Qt, QTimer, QPointF, QRectF, pyqtSlot, pyqtSignal
from PyQt6.QtGui import QPainter, QColor, QPen, QBrush, QPainterPath, QFont, QFontMetrics, QPalette
from PyQt6.QtWidgets import (
    QWidget, QDialog, QVBoxLayout, QTableWidget, QTableWidgetItem,
    QHeaderView, QDialogButtonBox, QHBoxLayout, QLabel, QToolTip
)

from geo_utils import METERS_PER_NM, StereographicLocal, WGS84_GEOD


# ============================================================
# FASE 3: SINGLETON DE TIEMPO (PROHIBICIÓN DE SALTOS ERRÁTICOS)
# ============================================================
class SimulationTime:
    """
    Singleton thread-safe que proporciona una base temporal unificada
    para toda la simulación. Reemplaza todas las llamadas a time.time()
    dentro del contexto del radar.

    Propósito:
      - Evitar que time.time() genere saltos erráticos (Time Jumps)
        cuando múltiples hilos/timers consultan la hora del sistema
        en momentos de recarga del timer.
      - Proveer un punto único de referencia temporal para toda la
        cadena de envejecimiento de plots (age, alpha, is_alive).
      - Soportar un modo de congelación (freeze) que permita pausar
        el envejecimiento de los blancos cuando el timer está detenido.
    """
    _instance: Optional['SimulationTime'] = None
    _lock: Lock = Lock()

    def __init__(self):
        self._sim_clock: float = time_module.time()
        self._frozen: bool = False
        self._rwlock = RLock()
        self._origin: float = self._sim_clock

    @classmethod
    def instance(cls) -> 'SimulationTime':
        """Retorna la instancia singleton, creándola si es necesario."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def now(self) -> float:
        """
        Retorna el tiempo actual de simulación.
        Congela el reloj si _frozen está activo (timer detenido).
        """
        with self._rwlock:
            if self._frozen:
                return self._sim_clock
            self._sim_clock = time_module.time()
            return self._sim_clock

    def freeze(self):
        """Congela el tiempo de simulación (no avanza)."""
        with self._rwlock:
            if not self._frozen:
                self._sim_clock = time_module.time()
                self._frozen = True

    def unfreeze(self):
        """Descongela el tiempo de simulación."""
        with self._rwlock:
            if self._frozen:
                self._frozen = False
                self._sim_clock = time_module.time()

    @property
    def is_frozen(self) -> bool:
        return self._frozen

    @classmethod
    def time(cls) -> float:
        """
        Método de clase de acceso directo.
        Reemplaza globalmente a time.time() dentro del módulo.
        """
        return cls.instance().now()


# ============================================================
# FASE 1: ESTRUCTURA LIGERA DE HISTORIAL (LIGHTWEIGHT HISTORY)
# ============================================================
@dataclass
class HistoryPoint:
    """
    Punto de historial ligero para trayectoria de blancos.

    PROHIBICIÓN ABSOLUTA: No almacena el diccionario ASTERIX completo.
    Solo contiene datos geométricos y de identificación mínimos:
      - x, y: Coordenadas proyectadas (metros)
      - tod:  Hora formateada HH:MM:SS.sss
      - squawk: Modo 3/A (código SSR)
      - fl:    Flight Level (string, ej. "FL350")
      - rho:   Distancia radial desde el radar (NM)
      - theta: Azimut desde el radar (grados)
    """
    x: float
    y: float
    cat: int
    tod: str = ""
    squawk: str = ""
    fl: Optional[str] = None
    rho: Optional[float] = None
    theta: Optional[float] = None
    lat: Optional[float] = None
    lon: Optional[float] = None



# ============================================================
# COLORES
# ============================================================
COLOR_BG          = QColor("#0B0E14")
COLOR_CYAN        = QColor("#00FFFF")
COLOR_CYAN_DIM    = QColor(0, 255, 255, 80)
COLOR_GREEN_NEON  = QColor("#39FF14")
COLOR_GREEN_DIM   = QColor(57, 255, 20, 40)
COLOR_MAP_LINE    = QColor(52, 73, 94, 100)
COLOR_RING        = QColor(40, 60, 40, 80)
COLOR_RING_LABEL  = QColor(60, 80, 60, 150)
COLOR_ACCENT_GREEN = QColor("#00FF00")
COLOR_PALETTE = [
    QColor("#00FFFF"), QColor("#00FF00"), QColor("#FFFF00"),
    QColor("#FF00FF"), QColor("#FF6347"), QColor("#7B68EE"),
    QColor("#FFA500"), QColor("#FFFFFF"),
]

# Persistencia
MAX_AGE_PLOT = 30.0
MAX_AGE_TRACK = 60.0

# Zoom seguro
MIN_ZOOM = 1e-5
MAX_ZOOM = 1e6
DEFAULT_NM_RANGE = 250

# Límite de plots renderizados
MAX_PLOTS_RENDERED = 2000

# Historial
HISTORY_LENGTH = 7  # Últimos 7 puntos de trayectoria

# Ángulo de tolerancia del barrido (grados) para iluminar plots cercanos
SWEEP_TOLERANCE = 3.0

# Referencia geográfica del DXF (San Luis como origen del mapa)
DXF_REF_LAT = -33.274444
DXF_REF_LON = -66.348611


def safe_divide(value: float, divisor: float, default: float = 1.0) -> float:
    if divisor < MIN_ZOOM or divisor > MAX_ZOOM or divisor == 0.0:
        return default
    result = value / divisor
    if not math.isfinite(result) or abs(result) > 1e7:
        return default
    return result


def is_valid_coord(x: float, y: float) -> bool:
    if not math.isfinite(x) or not math.isfinite(y):
        return False
    if abs(x) > 1e7 or abs(y) > 1e7:
        return False
    return True


class RadarPlot:
    """
    Representa un blanco individual con su historial de trayectoria.
    
    Atributos clave:
      - x, y: posición actual proyectada (metros)
      - raw_azimuth: ángulo del blanco respecto al norte del radar (para correlación barrido)
      - history: deque de hasta HISTORY_LENGTH HistoryPoints
                 SOLO ALMACENA HistoryPoint. NUNCA diccionarios ASTERIX completos.
      - is_illuminated: True cuando el barrido ha pasado sobre este blanco

    REGLA ABSOLUTA DE ARQUITECTURA (FASE 1):
      self.history solo puede contener objetos HistoryPoint ligeros.
      Está terminantemente prohibido almacenar diccionarios ASTERIX.
    """
    __slots__ = ('x', 'y', 'sac_sic', 'sac', 'sic', 'category', 'timestamp',
                 'mode3a', 'callsign', 'flight_level', 'is_track',
                 '_last_seen', '_highlight_filter', 'mode_s', 'track_angle', 'ground_speed',
                 'altitude_ft', 'raw_azimuth', 'is_illuminated', 'id', 'track_number',
                 'raw_range', 'bds_data', 'raw_dict', 'reporting_sensors')

    def __init__(self, x: float, y: float, sac_sic: str, category: int,
                 timestamp: float, mode3a: str, callsign: str,
                 flight_level: Optional[float], is_track: bool, mode_s: Optional[str],
                 track_angle: Optional[float], ground_speed: Optional[float],
                 altitude_ft: Optional[float] = None,
                 raw_azimuth: Optional[float] = None,
                 plot_id: Optional[str] = None,
                 track_number: Optional[int] = None,
                 raw_range: Optional[float] = None,
                 bds_data: Optional[Dict] = None,
                 raw_dict: Optional[Dict] = None,
                 reporting_sensors: Optional[Set] = None):
        self.x = x
        self.y = y
        self.id = plot_id or f"{sac_sic}_{timestamp}"
        self.sac_sic = sac_sic
        self.sac = 0
        self.sic = 0
        try:
            parts = sac_sic.split('/')
            self.sac = int(parts[0])
            self.sic = int(parts[1])
        except (ValueError, IndexError):
            pass
        self.category = category
        self.timestamp = timestamp
        self.mode3a = mode3a
        self.callsign = callsign
        self.flight_level = flight_level
        self.is_track = is_track
        # FASE 3: Usar SimulationTime en lugar de time.time()
        self._last_seen = SimulationTime.time()
        self._highlight_filter = ""
        self.mode_s = mode_s
        self.track_angle = track_angle
        self.ground_speed = ground_speed
        self.altitude_ft = altitude_ft
        self.raw_azimuth = raw_azimuth
        self.is_illuminated = False
        self.track_number = track_number
        self.raw_range = raw_range
        self.bds_data = bds_data or {}
        self.raw_dict = raw_dict or {}
        self.reporting_sensors = reporting_sensors or set()

    def set_highlight_filter(self, filtro: str):
        self._highlight_filter = filtro

    @property
    def highlighted(self) -> bool:
        if not self._highlight_filter:
            return False
        return (self._highlight_filter in self.mode3a or
                self._highlight_filter.lower() in self.callsign.lower())

    def illuminate(self):
        """Marca el blanco como iluminado por el barrido y resetea su alpha."""
        self.is_illuminated = True
        # FASE 3: SimulationTime en lugar de time.time()
        self._last_seen = SimulationTime.time()

    @property
    def age(self) -> float:
        """
        Retorna la edad del plot usando el singleton SimulationTime.
        
        FASE 3: Esto elimina los saltos erráticos (Time Jumps) causados
        por timers paralelos consultando time.time() de forma inconsistente.
        """
        return SimulationTime.time() - self._last_seen

    @property
    def alpha(self) -> int:
        max_age = MAX_AGE_TRACK if self.is_track else MAX_AGE_PLOT
        age = self.age
        if age >= max_age:
            return 0
        ratio = age / max_age
        return max(30, int(255 * (1.0 - ratio * ratio)))

    def is_alive(self) -> bool:
        max_age = MAX_AGE_TRACK if self.is_track else MAX_AGE_PLOT
        return self.age < max_age


# ================================================================
# VENTANA DE INSPECCIÓN DE BLANCO (FASE 3 - Doble Clic)
# ================================================================
class TargetInspectionDialog(QDialog):
    """
    Ventana modal de inspección detallada de un blanco ASTERIX.
    Se abre al hacer doble clic sobre un blanco activo en el PPI.

    Muestra una tabla con todos los campos decodificados disponibles,
    mapeados según el estándar ASTERIX (I048/xxx, I021/xxx, I062/xxx)
    desde I048/010 hasta I048/260, incluyendo datos BDS del registro 250.
    """

    def __init__(self, plot: 'RadarPlot', sensor_info: Dict, history: Optional[deque] = None, parent=None, proy: 'StereographicLocal' = None, asterix_version: str = ""):
        super().__init__(parent)
        self.setObjectName("TargetInspectionDialog")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._proy = proy
        self._radar_ref: Optional['RadarWidget'] = None
        self.history = history or deque()

        if parent is not None:
            p = parent
            while p is not None:
                if isinstance(p, RadarWidget):
                    self._radar_ref = p
                    break
                try:
                    p = p.parent()
                except Exception:
                    break

        self.asterix_version = asterix_version
        callsign = plot.callsign if plot.callsign else plot.mode3a
        self.setWindowTitle(f"Detalle de Blanco ASTERIX - {callsign}")
        self.resize(680, 520)
        # Forzar fondo claro vía QPalette (compatible VNC, no depende de stylesheet)
        self.setAutoFillBackground(True)
        pal = self.palette()
        pal.setColor(QPalette.ColorRole.Window, QColor("#e8e8e8"))
        self.setPalette(pal)
        self.setStyleSheet("""
            QTableWidget::item { padding: 3px; }
        """)

        layout = QVBoxLayout(self)
        layout.setSpacing(8)
        layout.setContentsMargins(12, 12, 12, 12)

        title_text = f"Blanco: {callsign}"
        if plot.track_number is not None:
            title_text += f"  |  Track #: {plot.track_number}"
        lbl_title = QLabel(title_text)
        layout.addWidget(lbl_title)

        self.table = QTableWidget()
        self.table.setColumnCount(2)
        self.table.setHorizontalHeaderLabels(["Campo ASTERIX", "Valor Decodificado"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.verticalHeader().setVisible(False)

        self._populate_all_fields(plot, sensor_info)
        layout.addWidget(self.table)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        btn_close = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        btn_close.rejected.connect(self.reject)
        btn_layout.addWidget(btn_close)
        layout.addLayout(btn_layout)

    def _add_field(self, asterix_id: str, label: str, value: Any):
        row = self.table.rowCount()
        self.table.insertRow(row)
        campo = f"{asterix_id} {label}"
        item_campo = QTableWidgetItem(campo)
        item_campo.setForeground(QColor("#0066CC"))
        self.table.setItem(row, 0, item_campo)
        if value is None or value == "" or value is False:
            valor_str = "—"
        elif isinstance(value, float):
            valor_str = f"{value:.4f}"
        elif isinstance(value, bool):
            valor_str = "Sí" if value else "No"
        else:
            valor_str = str(value)
        item_valor = QTableWidgetItem(valor_str)
        item_valor.setForeground(QColor("#222222"))
        self.table.setItem(row, 1, item_valor)

    def _populate_all_fields(self, plot: 'RadarPlot', sensor_info: Dict):
        sensor_name = sensor_info.get((plot.sac, plot.sic), {}).get('name', f"Radar {plot.sac}/{plot.sic}")

        fields = [
            ("I048/010", "SAC", lambda p: p.sac, True),
            ("I048/010", "SIC", lambda p: p.sic, True),
            ("I048/010", "Sensor", lambda p: f"{sensor_name} ({p.sac}/{p.sic})", True),
            ("I048/040", "RHO (NM)", lambda p: f"{p.raw_range:.2f} NM", plot.raw_range is not None),
            ("I048/040", "THETA (°)", lambda p: f"{p.raw_azimuth:.2f}°", plot.raw_azimuth is not None),
            ("I048/042", "X (m)", lambda p: f"{p.x:.1f}", True),
            ("I048/042", "Y (m)", lambda p: f"{p.y:.1f}", True),
            ("I048/070", "Mode 3/A", lambda p: p.mode3a if p.mode3a != "----" else None, True),
            ("I048/090", "FL", lambda p: f"FL{int(p.flight_level)}", plot.flight_level is not None),
            ("I048/090", "Alt (ft)", lambda p: f"{int(p.altitude_ft)} ft", plot.altitude_ft is not None),
            ("I048/161", "Track #", lambda p: p.track_number, True),
            ("I048/170", "Track Status", lambda p: p.is_track, True),
            ("I048/200", "GS (kt)", lambda p: f"{int(p.ground_speed)} kt", plot.ground_speed is not None),
            ("I048/200", "Rumbo (°)", lambda p: f"{plot.track_angle:.1f}°", plot.track_angle is not None),
            ("I048/220", "Mode S", lambda p: p.mode_s, True),
            ("I048/240", "Callsign", lambda p: p.callsign if p.callsign else None, True),
            ("I048/140", "ToD", lambda p: time_module.strftime("%H:%M:%S", time_module.gmtime(p.timestamp)) + f".{int((p.timestamp % 1) * 1000):03d}", plot.timestamp > 0),
            ("I048/140", "ToD (s)", lambda p: f"{p.timestamp:.3f} s", plot.timestamp > 0),
        ]

        for f_id, f_label, f_val_func, f_cond in fields:
            if f_cond:
                self._add_field(f_id, f_label, f_val_func(plot))

        if self._proy is not None and hasattr(self._proy, 'activo') and self._proy.activo:
            try:
                lat, lon = self._proy.xy_to_latlon(plot.x, plot.y)
                self._add_field("I048/042", "Lat WGS84", f"{lat:.6f}°")
                self._add_field("I048/042", "Lon WGS84", f"{lon:.6f}°")
            except Exception:
                pass

        if plot.bds_data and any(v is not None for k, v in plot.bds_data.items() if 'i048_030' not in k):
            self._add_field("I048/250", "BDS Presentes", "Sí")
            bds_fields = [
                ('roll_angle', "Roll Angle (°)", lambda b: f"{b['roll_angle']:.1f}°"),
                ('ground_speed_bds', "GS BDS (kt)", lambda b: f"{int(b['ground_speed_bds'])} kt"),
                ('mag_heading', "Mag Heading (°)", lambda b: f"{b['mag_heading']:.1f}°"),
                ('ias', "IAS (kt)", lambda b: f"{int(b['ias'])} kt"),
                ('mach', "Mach", lambda b: f"{b['mach']:.3f}"),
            ]
            for key, label, val_func in bds_fields:
                if key in plot.bds_data:
                    self._add_field("I048/250", label, val_func(plot.bds_data))
        else:
            self._add_field("I048/250", "BDS (ACAS)", "No presentes")

        cat_names = {48: "CAT048 (PSR/SSR)", 21: "CAT021 (ADS-B)", 62: "CAT062 (System Track)",
                     1: "CAT001", 2: "CAT002", 34: "CAT034"}
        self._add_field("Metadatos", "Categoría", cat_names.get(plot.category, f"CAT{plot.category}"))
        version_str = f"{self.asterix_version}" if self.asterix_version else "1.21"
        self._add_field("Metadatos", "Versión CAT048", version_str)

        # Historial points
        if self.history:
            self._add_field("---", f"--- HISTORIAL ({len(self.history)} pts) ---", "---")
            for i, hp in enumerate(self.history):
                label = f"Punto {i+1}: {hp.tod}"
                details = f"({hp.x:.1f}, {hp.y:.1f})"
                if hp.squawk:
                    details += f" SQK={hp.squawk}"
                if hp.fl:
                    details += f" {hp.fl}"
                if hp.rho is not None:
                    details += f" RHO={hp.rho:.1f}NM"
                if hp.theta is not None:
                    details += f" THETA={hp.theta:.1f}°"
                self._add_field("HIST", label, details)

        if hasattr(plot, 'raw_dict') and plot.raw_dict:
            self._add_field("---", "--- RAW ---", "---")
            for k, v in plot.raw_dict.items():
                if k not in ('extra_data', 'bds_data', 'plots'):
                    self._add_field("RAW", str(k), v)
            if 'extra_data' in plot.raw_dict and isinstance(plot.raw_dict['extra_data'], dict):
                self._add_field("---", "--- EXTRA ---", "---")
                for k, v in plot.raw_dict['extra_data'].items():
                    self._add_field("EXTRA", str(k), v)

        self._add_field("Resumen", "Total Campos", f"{self.table.rowCount()} ítems")


class RadarWidget(QWidget):
    """
    Widget PPI con sincronización de barrido e historial de trayectoria.

    Flujo de actualización:
      1. on_new_plot / on_new_plot_batch → _process_plot_data()
      2. El plot se guarda en pending_plots (no se muestra aún)
      3. En _on_timer(), cuando el sweep cruza el raw_azimuth del plot,
         se promueve a _plots (se ilumina y refresca)
      4. El paintEvent dibuja: datos activos + historial + vectores + data blocks
    """

    category_counts_updated = pyqtSignal(dict)

    def __init__(self, parent=None, sensores: Dict = None):
        super().__init__(parent)

        self.sensor_info = sensores or {}
        self.proy = StereographicLocal()
        self.projection_set = False
        self.center_key: Optional[Tuple[int, int]] = None

        # FASE 1: Factor de escala píxeles/unidad para calcular_xy_pantalla.
        # Representa cuántos píxeles equivalen a 1 Milla Náutica.
        # Ej: 2.0 significa que 50 NM ocupan 100 píxeles.
        self.escala = 2.0
        # Centro geográfico de referencia (ACC Córdoba / Taravella)
        self.centro_lat = -31.31
        self.centro_lon = -64.21

        # FASE 2: Bloqueo de señales
        self._command_lock = Lock()
        self._is_playing = False

        # FASE 2: Estado de arrastre (pan)
        self.is_panning = False
        self.last_mouse_pos = None

        # Plots activos
        self.tracks: Dict[str, RadarPlot] = {}
        self.pending_tracks: Dict[str, RadarPlot] = {}

        # FASE 3: Historial de trazas, mapeado por plot_id
        self.history: Dict[str, deque] = defaultdict(lambda: deque(maxlen=500))
        self.history_limit = 500
        self.history_mode = "Tracking"

        # Mapa DXF
        self._raw_dxf_segments: List[Tuple] = []
        self._dxf_has_data = False
        self._dxf_raw_min_x = 0.0
        self._dxf_raw_min_y = 0.0
        self._dxf_raw_max_x = 1.0
        self._dxf_raw_max_y = 1.0
        self.map_path = QPainterPath()
        self.map_path_borders = QPainterPath()
        self.map_path_airways = QPainterPath()
        self.map_path_runways = QPainterPath()
        self.map_path_other = QPainterPath()
        self.map_has_data = False
        self.map_min_x = self.map_min_y = 0.0
        self.map_max_x = self.map_max_y = 1.0

        # Filtros
        self.active_sensors: Set[Tuple[int, int]] = set()
        self.squawk_filter = ""
        self.filter_enabled = False

        # Zoom/pan
        self.zoom_factor = 1.0
        self.pan_x = 0.0
        self.pan_y = 0.0

        # Colores
        self.sensor_colors: Dict[Tuple[int, int], QColor] = {}
        self.color_palette_index = 0
        self._setup_default_colors()

        # Barrido
        self.sweep_angle = 0.0
        self.sweep_rpm = 12.0
        self.sweep_visible = True
        self.sweep_enabled = True

        # Etiqueta sensor
        self._active_sensor_label = ""
        self.asterix_version = ""
        self._last_tod = 0.0

        # FASE 3: Singleton tiempo
        SimulationTime.instance()

        # Timer 20 FPS
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._on_timer)
        self.timer.start(50)

        # Enable mouse tracking for tooltip on history points
        self.setMouseTracking(True)

        # FASE 2: Diccionario de hitboxes de labels para doble clic
        # Mapa: track_id → QRectF en coordenadas de viewport (píxeles)
        self.label_hitboxes: Dict[str, QRectF] = {}

        # FASE 4: Punto de historial seleccionado por clic simple (estilo INVAP)
        # Tupla: (plot, HistoryPoint, index) o None
        self.selected_history_point: Optional[Tuple['RadarPlot', 'HistoryPoint', int]] = None

        # FASE 1: Auto-centrado geográfico forzado para CAT 62
        self.cat62_centrado_automatico = False

        # FASE 4: Selección múltiple con botón derecho (Rubber Band)
        self.is_selecting = False
        self.selection_rect = QRectF()
        self.selected_history_points: list = []
        self.setMinimumSize(600, 600)
        self.plot_count = 0

        # FASE 3: Lista plana de plots crudos con coordenadas de pantalla
        # Usado por agregar_plot_individual como ruta directa de renderizado
        self.plots_raw: List[Dict[str, Any]] = []

    # ================================================================
    # CONFIGURACIÓN
    # ================================================================

    def _setup_default_colors(self):
        self._get_sensor_color(226, 210)
        self._get_sensor_color(1, 44)
        self._get_sensor_color(226, 110)

    def _get_sensor_color(self, sac: int, sic: int) -> QColor:
        key = (sac, sic)
        if key not in self.sensor_colors:
            color = COLOR_PALETTE[self.color_palette_index % len(COLOR_PALETTE)]
            self.sensor_colors[key] = color
            self.color_palette_index += 1
        return self.sensor_colors.get(key, COLOR_CYAN)

    def set_sweep_speed(self, rpm: float):
        if rpm > 0:
            self.sweep_rpm = rpm

    def reset_sweep_angle(self):
        self.sweep_angle = 0.0

    def set_sweep_visible(self, visible: bool):
        self.sweep_visible = visible
        if not visible:
            self._promote_all_pending()
        self.update()

    def set_sweep_enabled(self, enabled: bool):
        self.sweep_enabled = enabled
        if not enabled:
            self._promote_all_pending()
        self.update()

    def _promote_all_pending(self):
        for pid, plot in list(self.pending_tracks.items()):
            plot.illuminate()
            self.tracks[pid] = plot
        self.pending_tracks.clear()

    @pyqtSlot()
    def play(self):
        acquired = self._command_lock.acquire(blocking=False)
        if not acquired:
            return
        try:
            sim_time = SimulationTime.instance()
            sim_time.unfreeze()
            self.timer.stop()
            self.timer.start(50)
            self.sweep_visible = True
            self._is_playing = True
        finally:
            self._command_lock.release()

    def stop_sweep(self):
        acquired = self._command_lock.acquire(blocking=False)
        if not acquired:
            return
        try:
            sim_time = SimulationTime.instance()
            sim_time.freeze()
            self.timer.stop()
            self._last_tod = 0.0
            self.sweep_angle = 0.0
            self.sweep_visible = False
            self._is_playing = False
            self.tracks.clear()
            self.pending_tracks.clear()
            self.history.clear()
            self.selected_history_points.clear()
            self.plot_count = 0
            self.update()
        finally:
            self._command_lock.release()

    @pyqtSlot()
    def clear_all_plots(self):
        self.stop_sweep()

    def limpiar_pantalla(self):
        """Vacía las estructuras de datos y fuerza un repintado en blanco."""
        if hasattr(self, 'plots'):
            self.plots = []
        if hasattr(self, 'plots_raw'):
            self.plots_raw = []
        if hasattr(self, 'tracks'):
            self.tracks = {}
        if hasattr(self, 'pending_tracks'):
            self.pending_tracks = {}
        self.update()

    # ================================================================
    # MAPA DXF
    # ================================================================

    # ================================================================
    # MAPA DXF
    # ================================================================

    def _nm_offset_to_latlon(self, x_nm: float, y_nm: float) -> Tuple[float, float]:
        if abs(x_nm) < 1e-9 and abs(y_nm) < 1e-9:
            return DXF_REF_LAT, DXF_REF_LON
        range_m = math.sqrt(x_nm * x_nm + y_nm * y_nm) * METERS_PER_NM
        azimuth_deg = math.degrees(math.atan2(x_nm, y_nm))
        if azimuth_deg < 0:
            azimuth_deg += 360.0
        try:
            lon_dest, lat_dest, _ = WGS84_GEOD.fwd(DXF_REF_LON, DXF_REF_LAT, azimuth_deg, range_m)
            return float(lat_dest), float(lon_dest)
        except Exception:
            return DXF_REF_LAT, DXF_REF_LON

    def _reproject_dxf_to_current_proy(self):
        if not self._dxf_has_data or not self.proy.activo:
            return
        
        self.map_path = QPainterPath()
        self.map_path_borders = QPainterPath()
        self.map_path_airways = QPainterPath()
        self.map_path_runways = QPainterPath()
        self.map_path_other = QPainterPath()
        
        new_min_x = new_min_y = float('inf')
        new_max_x = new_max_y = float('-inf')
        
        for seg in self._raw_dxf_segments:
            if len(seg) < 2:
                continue
            t = seg[0]
            layer = seg[1]
            coords = seg[2:]
            
            # Clasificar path por nombre de capa
            layer_upper = str(layer).upper()
            if "LINEAS_DE_MAPA" in layer_upper or "MAPA" in layer_upper or "LIMITES" in layer_upper or "FRONTERA" in layer_upper:
                path = self.map_path_borders
            elif "AEROVIAS" in layer_upper or "AIRWAYS" in layer_upper or "RUTAS" in layer_upper:
                path = self.map_path_airways
            elif "PISTAS" in layer_upper or "RUNWAYS" in layer_upper:
                path = self.map_path_runways
            else:
                path = self.map_path_other

            if t == 'C':
                path.closeSubpath()
                continue
                
            pts_converted = []
            for i in range(0, len(coords), 2):
                x_nm = coords[i]
                y_nm = coords[i + 1]
                lat, lon = self._nm_offset_to_latlon(x_nm, y_nm)
                try:
                    px, py = self.proy.latlon_to_xy(lat, lon)
                    if not is_valid_coord(px, py):
                        px, py = 0.0, 0.0
                except Exception:
                    px, py = 0.0, 0.0
                pts_converted.append((px, py))
                new_min_x = min(new_min_x, px)
                new_max_x = max(new_max_x, px)
                new_min_y = min(new_min_y, py)
                new_max_y = max(new_max_y, py)
                
            for j, (px, py) in enumerate(pts_converted):
                if j == 0 and t == 'M':
                    path.moveTo(px, py)
                else:
                    path.lineTo(px, py)
                    
        if new_min_x == float('inf'):
            return
            
        self.map_min_x, self.map_min_y = new_min_x, new_min_y
        self.map_max_x, self.map_max_y = new_max_x, new_max_y
        self.map_has_data = True

    def set_raw_map_segments(self, raw_segments: list, min_x: float, min_y: float,
                              max_x: float, max_y: float):
        self._raw_dxf_segments = raw_segments
        self._dxf_has_data = bool(raw_segments)
        self._dxf_raw_min_x = min_x
        self._dxf_raw_min_y = min_y
        self._dxf_raw_max_x = max_x
        self._dxf_raw_max_y = max_y
        self._reproject_dxf_to_current_proy()

    # ================================================================
    # HARD RESET GEOGRÁFICO
    # ================================================================

    def reset_origin_for_new_file(self, lat: float, lon: float, sac: int, sic: int, 
                                   sensor_name: str = "", asterix_version: str = ""):
        # FASE 1: Resetear bandera de auto-centrado CAT 62
        self.cat62_centrado_automatico = False
        # Limpiar la bandera de debug para que se imprima de nuevo con el nuevo archivo
        if hasattr(self, 'cat62_debug_impreso'):
            del self.cat62_debug_impreso

        self.proy = StereographicLocal(lat, lon)
        self.projection_set = True
        self.center_key = (sac, sic)
        self.asterix_version = asterix_version
        self.history.clear() # Limpiar historial de trazas
        self.tracks.clear()
        self.pending_tracks.clear()
        self.plot_count = 0
        self.pan_x = 0.0
        self.pan_y = 0.0
        widget_radius_px = min(self.width(), self.height()) / 2.0
        if widget_radius_px > 0:
            self.zoom_factor = widget_radius_px / (DEFAULT_NM_RANGE * METERS_PER_NM)
            self._clamp_zoom()
        self.sweep_angle = 0.0
        self.sweep_rpm = 12.0
        self.sweep_visible = False
        self._is_playing = False
        name = sensor_name or f"Radar {sac}/{sic}"
        version_str = f" - CAT 48 {asterix_version}" if asterix_version else ""
        self._active_sensor_label = f"SENSOR ACTIVO: {name} ({sac}/{sic}){version_str}"
        self.sensor_colors.clear()
        self.color_palette_index = 0
        self._setup_default_colors()
        self._reproject_dxf_to_current_proy()
        print(f"[GEODESIA] Centro: [{name}] (Lat: {lat:.5f}, Lon: {lon:.5f}){version_str}")
        print(f"[GEODESIA] Mapa DXF reproyectado: {len(self._raw_dxf_segments)} segmentos")
        self.update()

    def set_projection_center(self, lat: float, lon: float, sensor_key: Optional[Tuple[int, int]] = None):
        if self.proy.center_lat != lat or self.proy.center_lon != lon:
            self.proy.set_center(lat, lon)
            self.projection_set = True
            self.center_key = sensor_key
            self._reproject_dxf_to_current_proy()
            self.update()

    def reproject_all_coordinates(self):
        """
        Recalcula las posiciones x, y de todas las pistas y de sus estelas históricas
        usando el proyector actual (tras recentrar en un nuevo sensor).
        """
        if not self.proy or not self.proy.activo:
            return

        # 1. Reproyectar tracks activos
        for track in self.tracks.values():
            lat = track.raw_dict.get('lat') or track.raw_dict.get('lat_render')
            lon = track.raw_dict.get('lon') or track.raw_dict.get('lon_render')
            if lat is not None and lon is not None:
                try:
                    track.x, track.y = self.proy.latlon_to_xy(lat, lon)
                except Exception:
                    pass
            else:
                try:
                    track.x, track.y = self.calcular_xy_pantalla(track.raw_dict)
                except Exception:
                    pass

        # 2. Reproyectar pending tracks (blancos pendientes)
        for track in self.pending_tracks.values():
            lat = track.raw_dict.get('lat') or track.raw_dict.get('lat_render')
            lon = track.raw_dict.get('lon') or track.raw_dict.get('lon_render')
            if lat is not None and lon is not None:
                try:
                    track.x, track.y = self.proy.latlon_to_xy(lat, lon)
                except Exception:
                    pass
            else:
                try:
                    track.x, track.y = self.calcular_xy_pantalla(track.raw_dict)
                except Exception:
                    pass

        # 3. Reproyectar todo el historial de estelas de puntos
        for plot_id, history_deque in self.history.items():
            for hp in history_deque:
                if hp.lat is not None and hp.lon is not None:
                    try:
                        hp.x, hp.y = self.proy.latlon_to_xy(hp.lat, hp.lon)
                    except Exception:
                        pass

        self.update()


    def centrar_en_coordenadas(self, target_lat: float, target_lon: float):
        """
        FASE 2: Fuerza el centro de la vista (geográfico + paneo) a las coordenadas
        especificadas. Actualiza el centro de proyección y resetea el paneo manual,
        de modo que el punto (target_lat, target_lon) quede exactamente en el centro
        de la pantalla del PPI.

        Args:
            target_lat: Latitud destino en grados decimales
            target_lon: Longitud destino en grados decimales
        """
        # 1) Actualizar el centro de proyección geográfica
        self.proy.set_center(target_lat, target_lon)
        self.projection_set = True

        # 2) Resetear todo desplazamiento manual de paneo
        self.pan_x = 0.0
        self.pan_y = 0.0

        # 3) Reproyectar el mapa DXF al nuevo centro
        self._reproject_dxf_to_current_proy()

        # 4) Forzar actualización visual
        self.update()
        print(f"🗺️ Vista centrada en Lat: {target_lat:.5f}, Lon: {target_lon:.5f}")

    def set_map_path(self, path: QPainterPath, min_x: float, min_y: float,
                     max_x: float, max_y: float):
        self.map_path = path
        self.map_min_x, self.map_min_y = min_x, min_y
        self.map_max_x, self.map_max_y = max_x, max_y
        self.map_has_data = True
        self.update()

    def _set_default_view(self):
        self.pan_x, self.pan_y = 0.0, 0.0
        widget_radius_px = min(self.width(), self.height()) / 2.0
        if widget_radius_px > 0:
            self.zoom_factor = widget_radius_px / (DEFAULT_NM_RANGE * METERS_PER_NM)
            self._clamp_zoom()
        self.update()

    def _clamp_zoom(self):
        if not math.isfinite(self.zoom_factor):
            self.zoom_factor = MIN_ZOOM
        self.zoom_factor = max(MIN_ZOOM, min(self.zoom_factor, MAX_ZOOM))

    # ================================================================
    # FASE 1: MOTOR MATEMÁTICO — Conversión Bimodal a Píxeles de Pantalla
    # ================================================================

    def calcular_xy_pantalla(self, plot: Dict[str, Any]) -> Tuple[Optional[float], Optional[float]]:
        """
        Convierte coordenadas Geográficas (Lat/Lon) o Polares (Rho/Theta) a PÍXELES
        de pantalla (x, y) DIRECTAMENTE en coordenadas del widget Qt.

        REGLA DE PROYECCIÓN Y ESCALA:
          - La escala (self.escala) define cuántos píxeles representa 1 Milla Náutica.
            Ej: 2.0 significa que 50 NM ocupan 100 píxeles.
          - El centro de la pantalla es self.width()/2, self.height()/2.
          - Las coordenadas retornadas están en PÍXELES (no en metros proyectados).

        REGLA BIMODAL ESTRICTA:
          1. Si existen lat_render/lon_render → proyección equirectangular (CAT 21, CAT 62)
             con centro default ACC Córdoba (-31.31, -64.21).
          2. Si no, si existen rho_render/theta_render → conversión polar a cartesiana
             (CAT 01, CAT 48).

        Args:
            plot: Diccionario del plot con claves estandarizadas.

        Returns:
            Tupla (x, y) en PÍXELES de pantalla, o (None, None) si no se pudo convertir.
        """
        centro_x = self.width() / 2
        centro_y = self.height() / 2

        # Escala: píxeles por Milla Náutica
        escala = getattr(self, 'escala', 2.0)

        # 1. Proyección WGS-84 (ADS-B CAT 21, CAT 62)
        lat = plot.get('lat_render')
        lon = plot.get('lon_render')
        if lat is not None and lon is not None:
            # Centro por defecto: ACC Córdoba / Taravella
            centro_lat = getattr(self, 'centro_lat', -31.31)
            centro_lon = getattr(self, 'centro_lon', -64.21)

            # 1 grado de latitud ≈ 60 Millas Náuticas
            dist_y_mn = (centro_lat - lat) * 60.0
            dist_x_mn = (lon - centro_lon) * 60.0 * math.cos(math.radians(centro_lat))

            x = centro_x + (dist_x_mn * escala)
            y = centro_y + (dist_y_mn * escala)
            return x, y

        # 2. Proyección Polar (Radares CAT 01, CAT 48)
        rho = plot.get('rho_render')       # Distancia
        theta = plot.get('theta_render')   # Azimut (grados, 0 = Norte, sentido horario)

        if rho is not None and theta is not None:
            # Si rho viene en metros (>1000), convertir a NM
            if rho > 1000:
                rho = rho / 1852.0

            theta_rad = math.radians(theta)
            x = centro_x + (rho * escala * math.sin(theta_rad))
            y = centro_y - (rho * escala * math.cos(theta_rad))
            return x, y

        return None, None

    # ================================================================
    # RECEPCIÓN DE PLOTS
    # ================================================================

    def _compute_azimuth(self, x: float, y: float) -> Optional[float]:
        if abs(x) < 1e-6 and abs(y) < 1e-6:
            return None
        angle = math.degrees(math.atan2(x, y))
        if angle < 0:
            angle += 360.0
        return angle

    def _process_plot_data(self, data: Dict[str, Any]) -> Optional[str]:
        try:
            # 1. Extraer o calcular coordenadas cartesianas primero (para poder usar distancia en correlación)
            x = y = None
            x_m = data.get('x_meters')
            y_m = data.get('y_meters')
            if x_m is not None and y_m is not None:
                x, y = x_m, y_m
            else:
                # Prioridad 1: lat/lon clásicas (worker normalizadas)
                lat, lon = data.get('lat'), data.get('lon')
                if lat is not None and lon is not None:
                    try:
                        x, y = self.proy.latlon_to_xy(lat, lon)
                    except Exception:
                        pass
                # Prioridad 2: claves estandarizadas lat_render/lon_render (ADS-B CAT 21/62)
                if (x is None or y is None or not is_valid_coord(x, y)):
                    lat_r = data.get('lat_render')
                    lon_r = data.get('lon_render')
                    if lat_r is not None and lon_r is not None:
                        try:
                            x2, y2 = self.proy.latlon_to_xy(lat_r, lon_r)
                            if is_valid_coord(x2, y2):
                                x, y = x2, y2
                        except Exception:
                            pass
                # Prioridad 3: convertidor bimodal (rho_render/theta_render para CAT 01/48)
                if (x is None or y is None or not is_valid_coord(x, y)):
                    x2, y2 = self.calcular_xy_pantalla(data)
                    if x2 is not None and y2 is not None and is_valid_coord(x2, y2):
                        x, y = x2, y2
            
            if x is None or y is None or not is_valid_coord(x, y):
                return None

            # Extraer el sensor que lo reporta y validar que esté en los filtros activos
            sensor_id = data.get('sac_sic', 'UNK')
            if hasattr(self, 'sensores_visibles') and self.sensores_visibles is not None and sensor_id not in self.sensores_visibles:
                return None

            if not self.projection_set:
                return None

            raw_az = data.get('raw_azimuth')
            if raw_az is None:
                raw_az = self._compute_azimuth(x, y)

            # 2. Correlación inteligente multi-sensor para evitar duplicados
            # Buscar si ya existe una pista activa para esta misma aeronave
            matched_track_id = None
            mode_s_addr = (data.get('mode_s') or "").strip().upper()
            
            # A. Búsqueda por dirección Mode S (ICAO) - Máxima prioridad
            if mode_s_addr and mode_s_addr != '----':
                for tid, track in list(self.tracks.items()) + list(self.pending_tracks.items()):
                    t_mode_s = (track.mode_s or "").strip().upper()
                    if t_mode_s == mode_s_addr:
                        matched_track_id = tid
                        break

            # B. Búsqueda por código Squawk (Mode 3/A) con ventana de distancia
            if not matched_track_id:
                mode3a = data.get('mode3a')
                mode3a_str = ""
                if mode3a is not None:
                    if isinstance(mode3a, int):
                        mode3a_str = f"{mode3a:04o}"
                    else:
                        mode3a_str = str(mode3a).strip()
                
                if mode3a_str and mode3a_str != "----" and mode3a_str != "0000":
                    is_generic = mode3a_str in ("1200", "2000", "7000", "0000")
                    for tid, track in list(self.tracks.items()) + list(self.pending_tracks.items()):
                        t_sq = track.mode3a
                        t_sq_str = f"{t_sq:04o}" if isinstance(t_sq, int) else str(t_sq).strip()
                        if t_sq_str == mode3a_str:
                            t_mode_s = (track.mode_s or "").strip().upper()
                            if not mode_s_addr or not t_mode_s or t_mode_s == mode_s_addr:
                                dx = track.x - x
                                dy = track.y - y
                                dist_m = math.sqrt(dx*dx + dy*dy)
                                # Límite de 10 NM si es genérico, 30 NM para otros códigos
                                max_dist = 18520.0 if is_generic else 55560.0
                                if dist_m < max_dist:
                                    matched_track_id = tid
                                    break

            # C. Búsqueda por número de pista
            if not matched_track_id:
                track_num = data.get('track_number')
                if track_num is not None:
                    for tid, track in list(self.tracks.items()) + list(self.pending_tracks.items()):
                        if track.track_number == track_num:
                            dx = track.x - x
                            dy = track.y - y
                            dist_m = math.sqrt(dx*dx + dy*dy)
                            if dist_m < 55560.0:  # 30 NM
                                matched_track_id = tid
                                break

            # 3. Establecer target_id final
            if matched_track_id:
                target_id = matched_track_id
            else:
                # Si es una pista nueva, generar un ID estable
                if mode_s_addr and mode_s_addr != '----':
                    target_id = mode_s_addr
                elif 'mode3a' in data and data['mode3a'] and data['mode3a'] != '----' and data['mode3a'] != '0000':
                    mode3a = data['mode3a']
                    target_id = f"{mode3a:04o}" if isinstance(mode3a, int) else str(mode3a).strip()
                elif data.get('track_number') is not None:
                    target_id = f"TRK_{data['track_number']}"
                else:
                    return None

            # 4. Correlación / Actualización del Diccionario de Pistas
            def update_track(track: RadarPlot):
                hp = HistoryPoint(
                    x=track.x, y=track.y, cat=track.category,
                    tod=time_module.strftime("%H:%M:%S", time_module.gmtime(track.timestamp)),
                    squawk=track.mode3a,
                    fl=(f"FL{int(track.flight_level)}" if track.flight_level is not None else None),
                    rho=track.raw_range, theta=track.raw_azimuth,
                    lat=track.raw_dict.get('lat') or track.raw_dict.get('lat_render'),
                    lon=track.raw_dict.get('lon') or track.raw_dict.get('lon_render')
                )
                self.history[target_id].append(hp)

                # Si el nuevo dato es de categoría superior (CAT 21 o 62), adoptamos su posición directamente
                # para evitar que la menor precisión de radares antiguos distorsione la traza.
                if data.get('category') in (21, 62) and track.category not in (21, 62):
                    track.x = x
                    track.y = y
                    track.category = data.get('category')
                else:
                    track.x = (track.x + x) / 2
                    track.y = (track.y + y) / 2
                
                track.timestamp = data.get('time', track.timestamp)
                track.raw_azimuth = raw_az
                if data.get('mode3a') is not None and data.get('mode3a') not in ('', '----'):
                    track.mode3a = data.get('mode3a')
                if data.get('callsign'):
                    track.callsign = data.get('callsign')
                if data.get('flight_level') is not None:
                    track.flight_level = data.get('flight_level')
                if data.get('ground_speed') is not None:
                    track.ground_speed = data.get('ground_speed')
                if data.get('track_angle') is not None:
                    track.track_angle = data.get('track_angle')
                if data.get('mode_s'):
                    track.mode_s = data.get('mode_s')
                
                track.reporting_sensors.add(sensor_id)
                track.illuminate()

            if target_id in self.tracks:
                update_track(self.tracks[target_id])
                return target_id
            
            if target_id in self.pending_tracks:
                update_track(self.pending_tracks[target_id])
                return target_id

            # Pista nueva
            try:
                plot = RadarPlot(
                    x=x, y=y,
                    sac_sic=data['sac_sic'],
                    category=data.get('category', 0),
                    timestamp=data.get('time', 0.0),
                    mode3a=data.get('mode3a', ''),
                    callsign=data.get('callsign', ''),
                    flight_level=data.get('flight_level'),
                    is_track=data.get('is_track', False),
                    mode_s=data.get('mode_s'),
                    track_angle=data.get('track_angle'),
                    ground_speed=data.get('ground_speed'),
                    altitude_ft=data.get('altitude_ft'),
                    raw_azimuth=raw_az,
                    plot_id=target_id,
                    track_number=data.get('track_number'),
                    raw_range=data.get('raw_range'),
                    bds_data=data.get('bds_data', {}),
                    raw_dict=data,
                    reporting_sensors={sensor_id}
                )
                plot.set_highlight_filter(self.squawk_filter)
                self.pending_tracks[target_id] = plot
            except Exception:
                return None

            self.plot_count = len(self.tracks) + len(self.pending_tracks)
            self._last_tod = data.get('time', self._last_tod)
            return target_id
        except Exception:
            return None

    @pyqtSlot(object)
    def on_new_plot(self, data: Dict[str, Any]):
        self._process_plot_data(data)
        self.update()

    def normalizar_coordenadas_wgs84(self, plot: Dict[str, Any]):
        """
        Garantiza que todos los plots tengan lat_render y lon_render.
        Convierte polares (CAT 48/01) a WGS-84 usando el cabezal del radar como centro.
        """
        # Si ya tiene WGS-84 (ADS-B CAT 21), no hacemos nada
        if plot.get('lat_render') is not None and plot.get('lon_render') is not None:
            return

        # Si tiene Polares (Radares CAT 48), calculamos su Lat/Lon absoluto
        rho = plot.get('rho_render')     # Distancia en MN
        theta = plot.get('theta_render') # Azimut en grados respecto al norte verdadero

        if rho is not None and theta is not None:
            # Extraer las coordenadas del cabezal del radar (Variables del módulo GEODESIA del usuario)
            radar_lat = getattr(self, 'centro_lat', -26.75055) # Default Saenz Peña
            radar_lon = getattr(self, 'centro_lon', -60.48167)

            # 1 Grado de Latitud = 60 MN. 
            # Delta Latitud (Norte/Sur) = (Rho * Cos(Theta)) / 60
            theta_rad = math.radians(theta)
            delta_lat = (rho * math.cos(theta_rad)) / 60.0
            
            # Delta Longitud (Este/Oeste) = (Rho * Sin(Theta)) / (60 * Cos(Latitud_Radar))
            lat_rad = math.radians(radar_lat)
            delta_lon = (rho * math.sin(theta_rad)) / (60.0 * math.cos(lat_rad))

            plot['lat_render'] = radar_lat + delta_lat
            plot['lon_render'] = radar_lon + delta_lon

    def agregar_plot_individual(self, plot: Dict[str, Any], trigger_update: bool = True):
        """
        FASE 2: Método de ingestión unificado.
        """
        # 1. Aplicar trigonometría si es un radar
        self.normalizar_coordenadas_wgs84(plot)
        
        lat = plot.get('lat_render')
        lon = plot.get('lon_render')

        # 2. Validar que tengamos WGS-84
        if lat is None or lon is None:
            return # Descartar si es un paquete sin posición
            
        # 3. Validar Filtros de UI
        sensor_id = plot.get('sac_sic', 'UNK')
        if hasattr(self, 'sensores_visibles') and self.sensores_visibles is not None:
            if sensor_id not in self.sensores_visibles and plot.get('category') != 62:
                return

        # 3b. CONVERSIÓN A PÍXELES/PROYECCIÓN (CRÍTICO)
        # Se calcula x_pantalla e y_pantalla en metros proyectados, porque el 
        # paintEvent utiliza un QTransform (scale/translate) que dibuja en este espacio.
        try:
            if hasattr(self, 'proy') and self.proy.activo:
                x, y = self.proy.latlon_to_xy(lat, lon)
            elif hasattr(self, 'calcular_xy_pantalla'):
                x, y = self.calcular_xy_pantalla(plot)
            else:
                escala = getattr(self, 'escala', 2.0)
                c_lat = getattr(self, 'centro_lat', -26.75)
                c_lon = getattr(self, 'centro_lon', -60.48)
                dx = (lon - c_lon) * 60.0 * math.cos(math.radians(c_lat))
                dy = (c_lat - lat) * 60.0 
                x = (self.width() / 2) + (dx * escala)
                y = (self.height() / 2) + (dy * escala)

            if not is_valid_coord(x, y):
                return

            plot['x_pantalla'] = x
            plot['y_pantalla'] = y
            plot['x_meters'] = x
            plot['y_meters'] = y
        except Exception as e:
            print(f"Error proyectando a píxeles: {e}")
            return

        # 4. Delegar al sistema de tracks y forzar repintado si corresponde
        # NOTA: NO se agrega a plots_raw — el renderizado FASE 2 (tracks/pending_tracks)
        # ya dibuja cada blanco con su símbolo y etiqueta correctamente.
        self._process_plot_data(plot)
        if trigger_update:
            self.update()

    @pyqtSlot(list)
    def on_new_plot_batch(self, batch: List[Dict[str, Any]]):
        if not batch:
            return
        for data in batch:
            self._process_plot_data(data)
        self.update()

    # ================================================================
    # FILTROS
    # ================================================================

    def set_filters(self, active_sensors: Set[Tuple[int, int]], squawk_filter: str):
        self.active_sensors = active_sensors
        self.squawk_filter = squawk_filter
        self.filter_enabled = bool(active_sensors) or bool(squawk_filter)
        self.update()

    def _plot_passes_filter(self, data: dict) -> bool:
        # REGLA DE BYPASS PARA CAT 62:
        # Los plots de CAT 62 (System Track) no se filtran por SAC/SIC,
        # ya que representan trazas fusionadas del sistema y no están
        # atadas a un sensor físico específico que el usuario pueda filtrar.
        
        # Nuevo filtro unificado basado en QListWidget (sensores_visibles)
        if hasattr(self, 'sensores_visibles') and self.sensores_visibles is not None:
            if data.get('category') != 62:
                sensor_id = data.get('sac_sic', f"UNK_CAT{data.get('category', 'XX')}")
                if sensor_id not in self.sensores_visibles:
                    return False
        return True

    # ================================================================
    # AJUSTE DE VISTA
    # ================================================================

    def _adjust_view(self):
        all_pts = []
        if self.map_has_data:
            all_pts.extend([
                (self.map_min_x, self.map_min_y),
                (self.map_max_x, self.map_max_y)
            ])
        for plot in self._plots.values():
            if plot.is_alive():
                all_pts.append((plot.x, plot.y))
        if not all_pts:
            return
        try:
            min_x = min(p[0] for p in all_pts)
            max_x = max(p[0] for p in all_pts)
            min_y = min(p[1] for p in all_pts)
            max_y = max(p[1] for p in all_pts)
            w, h = self.width(), self.height()
            if w > 0 and h > 0 and (max_x - min_x) > 1e-6 and (max_y - min_y) > 1e-6:
                self.zoom_factor = 0.9 * min(w / (max_x - min_x), h / (max_y - min_y))
                self._clamp_zoom()
                self.pan_x = (min_x + max_x) / 2.0
                self.pan_y = (min_y + max_y) / 2.0
                self.update()
        except Exception:
            pass

    # ================================================================
    # TIMER
    # ================================================================

    def _on_timer(self):
        try:
            sim_time = SimulationTime.instance()
            if sim_time.is_frozen and self._is_playing:
                sim_time.unfreeze()
            sweep_active = self.sweep_visible and self.sweep_enabled
            if sweep_active:
                now = time_module.time()
                if not hasattr(self, '_last_sweep_tick_time') or self._last_sweep_tick_time is None:
                    self._last_sweep_tick_time = now
                dt = now - self._last_sweep_tick_time
                self._last_sweep_tick_time = now
                
                # Limitar dt para evitar saltos gigantescos si el hilo UI se congela
                dt = min(0.5, max(0.0, dt))
                
                # 1 RPM = 6 grados por segundo
                increment = self.sweep_rpm * 6.0 * dt
                
                prev_sweep = self.sweep_angle
                self.sweep_angle = (self.sweep_angle + increment) % 360.0
                curr_sweep = self.sweep_angle
            else:
                self._last_sweep_tick_time = None

            if sweep_active:
                sweep_center = self.sweep_angle
                to_promote = []
                for pid, plot in self.pending_tracks.items():
                    if plot.raw_azimuth is not None:
                        diff = abs(plot.raw_azimuth - sweep_center)
                        if diff > 180.0:
                            diff = 360.0 - diff
                        if diff <= SWEEP_TOLERANCE:
                            to_promote.append(pid)
                    else:
                        if plot.age > 0.5:
                            to_promote.append(pid)
            else:
                to_promote = list(self.pending_tracks.keys())

            for pid in to_promote:
                plot = self.pending_tracks.pop(pid, None)
                if plot:
                    plot.illuminate()
                    self.tracks[pid] = plot

            # ---- PROCESAMIENTO PESADO TEMPORIZADO (Poda y Telemetría) ----
            # Ejecutar solo una vez cada 1.0 segundo (20 ticks a 50ms de intervalo)
            self._timer_tick_count = getattr(self, '_timer_tick_count', 0) + 1
            if self._timer_tick_count >= 20:
                self._timer_tick_count = 0

                # 1. Poda de blancos muertos
                for d in (self.tracks, self.pending_tracks):
                    muertos = [pid for pid, plot in d.items() if not plot.is_alive()]
                    for pid in muertos:
                        if pid in self.history:
                            del self.history[pid]
                        del d[pid]

                # 2. Control de exceso de capacidad
                total_plots = len(self.tracks) + len(self.pending_tracks)
                if total_plots > MAX_PLOTS_RENDERED * 2:
                    excess = total_plots - MAX_PLOTS_RENDERED
                    pids = list(self.pending_tracks.keys())[:excess]
                    for pid in pids:
                        del self.pending_tracks[pid]
                    if len(self.tracks) > MAX_PLOTS_RENDERED:
                        sorted_plots = sorted(self.tracks.items(), key=lambda item: item[1]._last_seen)
                        to_remove = len(self.tracks) - MAX_PLOTS_RENDERED
                        for pid, _ in sorted_plots[:to_remove]:
                            del self.tracks[pid]

                # 3. FASE 4: Contar plots vivos por categoría y emitir señal de telemetría
                counts = {1: 0, 21: 0, 48: 0, 62: 0}
                for plot in self.tracks.values():
                    if plot.is_alive() and plot.category in counts:
                        counts[plot.category] += 1
                self.category_counts_updated.emit(counts)

            self.plot_count = len(self.tracks) + len(self.pending_tracks)
            self.update()
        except Exception:
            pass

    # ================================================================
    # PAINT EVENT
    # ================================================================

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        try:
            painter.fillRect(self.rect(), COLOR_BG)
            w, h = self.width(), self.height()

            self._clamp_zoom()
            z = self.zoom_factor
            inv_z = safe_divide(1.0, z, 1.0)

            painter.save()

            # Centro del widget en píxeles (preserva relación de aspecto 1:1)
            center_x = w / 2.0 + self.pan_x
            center_y = h / 2.0 + self.pan_y

            painter.translate(center_x, center_y)
            painter.scale(z, -z)

            # ---- 1. MAPA DXF ----
            if self.map_has_data:
                try:
                    painter.setBrush(QBrush(Qt.BrushStyle.NoBrush))
                    
                    # A. Líneas de Fronteras y Provincias (Layer: LINEAS_DE_MAPA)
                    # Color cian táctico semi-transparente bien definido
                    pen_borders = QPen(QColor(0, 229, 255, 130))
                    pen_borders.setWidthF(max(1.0, inv_z * 1.0))
                    painter.setPen(pen_borders)
                    painter.drawPath(self.map_path_borders)
                    
                    # B. Aerovías (Layer: AEROVIAS)
                    # Línea punteada muy sutil para que no ensucie la pantalla ni tape las fronteras
                    pen_airways = QPen(QColor(80, 110, 150, 45))
                    pen_airways.setWidthF(max(0.4, inv_z * 0.4))
                    pen_airways.setStyle(Qt.PenStyle.DotLine)
                    painter.setPen(pen_airways)
                    painter.drawPath(self.map_path_airways)
                    
                    # C. Pistas de aeropuertos (Layer: PISTAS)
                    pen_runways = QPen(COLOR_GREEN_NEON)
                    pen_runways.setWidthF(max(1.8, inv_z * 1.8))
                    painter.setPen(pen_runways)
                    painter.drawPath(self.map_path_runways)
                    
                    # D. Otras capas auxiliares del DXF
                    pen_other = QPen(COLOR_MAP_LINE)
                    pen_other.setWidthF(max(0.4, inv_z * 0.5))
                    painter.setPen(pen_other)
                    painter.drawPath(self.map_path_other)
                    
                except Exception:
                    pass

            # ---- 2. ANILLOS ----
            try:
                pen_ring = QPen(COLOR_RING)
                pen_ring.setWidthF(inv_z)
                painter.setPen(pen_ring)
                for dist_nm in [50, 100, 200]:
                    r = dist_nm * METERS_PER_NM
                    painter.drawEllipse(QPointF(0.0, 0.0), r, r)
                font_label = QFont("Monospace", 8)
                painter.setFont(font_label)
                painter.setPen(COLOR_RING_LABEL)
                for dist_nm in [50, 100, 200]:
                    r = dist_nm * METERS_PER_NM
                    painter.save()
                    painter.translate(0.0 + r, 0.0)
                    painter.scale(inv_z, -inv_z)
                    painter.drawText(QPointF(4, 12), f"{dist_nm} NM")
                    painter.restore()
            except Exception:
                pass

            # ---- 3. BARRIDO ----
            if self.sweep_visible and self.sweep_enabled:
                try:
                    painter.save()
                    painter.translate(0.0, 0.0)
                    painter.rotate(-self.sweep_angle)
                    sweep_len = 350 * METERS_PER_NM
                    pen_sweep = QPen(COLOR_GREEN_NEON)
                    pen_sweep.setWidthF(safe_divide(2.0, z, 0.5))
                    painter.setPen(pen_sweep)
                    painter.drawLine(QPointF(0, 0), QPointF(0, sweep_len))
                    painter.setPen(Qt.PenStyle.NoPen)
                    painter.setBrush(COLOR_GREEN_DIM)
                    painter.drawPolygon([
                        QPointF(0, 0), QPointF(0, sweep_len),
                        QPointF(-sweep_len * 0.12, sweep_len * 0.88),
                    ])
                    painter.restore()
                except Exception:
                    painter.restore()

            # ---- 4. SENSOR CENTRAL ----
            if self.projection_set:
                try:
                    painter.setPen(QPen(COLOR_ACCENT_GREEN, safe_divide(2.0, z, 0.5)))
                    painter.setBrush(COLOR_ACCENT_GREEN)
                    s_size = safe_divide(15.0, z, 1.0)
                    s_path = QPainterPath()
                    s_path.moveTo(0, s_size)
                    s_path.lineTo(-s_size * 0.866, -s_size * 0.5)
                    s_path.lineTo(s_size * 0.866, -s_size * 0.5)
                    s_path.closeSubpath()
                    painter.drawPath(s_path)
                except Exception:
                    pass

            # ---- 5. DIBUJO DE PLOTS ----
            font_sq = QFont("Monospace", 9)

            # --- FASE 1: HISTORIAL (ESTELA LIGERA) ---
            if self.history_limit > 0:
                for track_id, history_points in list(self.history.items()):
                    plot = self.tracks.get(track_id) or self.pending_tracks.get(track_id)
                    if not plot or not plot.is_alive():
                        continue

                    try:
                        alpha = plot.alpha
                        if alpha <= 0:
                            continue
                        plot_color = self._get_sensor_color(plot.sac, plot.sic)
                        base_color = QColor(plot_color)

                        limit = self.history_limit
                        points_to_draw = list(history_points)[-limit:]
                        if self.history_mode == "Tracking":
                            # Draw connected trajectory (polyline)
                            if len(points_to_draw) >= 2:
                                path = QPainterPath()
                                first_pt = points_to_draw[0]
                                path.moveTo(first_pt.x, first_pt.y)
                                for pt in points_to_draw[1:]:
                                    path.lineTo(pt.x, pt.y)
                                pen = QPen(base_color, safe_divide(2.0, z, 0.5))
                                pen.setStyle(Qt.PenStyle.SolidLine)
                                painter.setPen(pen)
                                painter.setBrush(Qt.BrushStyle.NoBrush)
                                painter.drawPath(path)
                        else:
                            # Historic mode – original fading dots
                            history_alpha_values = [max(20, alpha // (i + 2)) for i in range(limit)]
                            for i, h_point in enumerate(reversed(points_to_draw)):
                                hx, hy = h_point.x, h_point.y
                                if not is_valid_coord(hx, hy):
                                    continue
                                ha = history_alpha_values[i] if i < len(history_alpha_values) else 20
                                h_color = QColor(base_color)
                                h_color.setAlpha(ha)
                                painter.setPen(QPen(h_color, safe_divide(1.5, z, 0.3)))
                                painter.setBrush(h_color)
                                h_size = safe_divide(3.0, z, 0.5) * (1.0 - i / (limit * 1.5))
                                painter.drawEllipse(QPointF(hx, hy), h_size, h_size)
                    except Exception:
                        continue

            # FASE 4: Feedback visual para punto de historial seleccionado
            if getattr(self, 'selected_history_point', None) is not None:
                try:
                    sel_plot, sel_hp, sel_idx = self.selected_history_point
                    # Verificar que el punto siga existiendo en el historial
                    history_list = list(self.history.get(sel_plot.id, []))
                    if sel_idx < len(history_list) and history_list[sel_idx] == sel_hp:
                        hx, hy = sel_hp.x, sel_hp.y
                        if is_valid_coord(hx, hy):
                            # Cuadro punteado verde alrededor del punto
                            box_size = safe_divide(8.0, z, 1.0)
                            pen_dashed = QPen(QColor("#00FF00"))
                            pen_dashed.setWidthF(safe_divide(1.5, z, 0.5))
                            pen_dashed.setStyle(Qt.PenStyle.DashLine)
                            painter.setPen(pen_dashed)
                            painter.setBrush(QBrush(Qt.BrushStyle.NoBrush))
                            painter.drawRect(QRectF(hx - box_size, hy - box_size,
                                                     box_size * 2, box_size * 2))
                except Exception:
                    pass

            # FASE 4: Feedback visual para puntos de historial seleccionados (múltiple)
            if self.selected_history_points:
                pen_dashed = QPen(QColor("#00FF00"))
                pen_dashed.setWidthF(safe_divide(1.5, z, 0.5))
                pen_dashed.setStyle(Qt.PenStyle.DashLine)
                painter.setPen(pen_dashed)
                painter.setBrush(QBrush(Qt.BrushStyle.NoBrush))
                box_size = safe_divide(8.0, z, 1.0)

                for sel_plot, sel_hp, sel_idx in self.selected_history_points:
                    try:
                        history_list = list(self.history.get(sel_plot.id, []))
                        if sel_idx < len(history_list) and history_list[sel_idx] == sel_hp:
                            hx, hy = sel_hp.x, sel_hp.y
                            if is_valid_coord(hx, hy):
                                painter.drawRect(QRectF(hx - box_size, hy - box_size,
                                                         box_size * 2, box_size * 2))
                                # FASE 2: Tooltip para historial seleccionado
                                painter.save()
                                painter.translate(hx, hy)
                                painter.scale(inv_z, -inv_z)

                                cat_str = f"CAT {sel_hp.cat}"
                                tod_str = sel_hp.tod
                                sqk_str = f"A: {sel_hp.squawk}" if sel_hp.squawk else "A: ----"
                                fl_str = f"C: {sel_hp.fl}" if sel_hp.fl else "C: ---"
                                rho_str = f"@ {sel_hp.rho:.1f}NM" if sel_hp.rho is not None else ""
                                theta_str = f" {sel_hp.theta:.1f}°" if sel_hp.theta is not None else ""
                                
                                tooltip_text = f"[{cat_str}] [{tod_str}] [{sqk_str}, {fl_str} {rho_str}{theta_str}]"
                                
                                painter.setPen(QColor("#00FF00"))
                                painter.setFont(QFont("Monospace", 8))
                                painter.drawText(QPointF(10, -10), tooltip_text)
                                painter.restore()

                    except Exception:
                        continue

            # FASE 1 (Opacidad Heredada): Resetear opacidad antes de dibujar plots vivos
            # para evitar que la transparencia del historial afecte a los plots activos.
            painter.setOpacity(1.0)

            # --- FASE 2: CABEZAS DE TRACK ---
            all_active_plots = list(self.tracks.items()) + list(self.pending_tracks.items())
            for track_id, plot in all_active_plots:
                try:
                    # FASE 2: INMUNIDAD ABSOLUTA PARA CAT 62
                    # Los System Tracks (CAT 62) NO se filtran por sensor visible.
                    # El bypass ya está en _plot_passes_filter() y se refuerza aquí.
                    if plot.category == 62:
                        self._draw_cat62_plot(painter, plot, z, inv_z)
                        continue  # No pasa por filtro de sensores ni lógica PSR/SSR/ADS-B

                    # 🔓 FILTRO DE SENSORES MÚLTIPLES ACTIVADO:
                    # El normalizador universal inyecta el ID del sensor.
                    # Comprobamos si está en el set de sensores visibles.
                    sensor_id = getattr(plot, 'sac_sic', f"UNK_CAT{plot.category}")
                    visibles = getattr(self, 'sensores_visibles', None)
                    if visibles is not None and sensor_id not in visibles:
                        continue

                    # Lógica original e intacta para el resto de categorías
                    if not plot.is_alive():
                        continue
                    alpha = plot.alpha
                    if alpha <= 0:
                        continue
                    x, y = plot.x, plot.y
                    if not is_valid_coord(x, y):
                        continue

                    # FASE 2: Clasificar tipo de blanco y definir color/estilo de símbolo
                    painter.setBrush(QBrush(Qt.BrushStyle.NoBrush))
                    sensor_info = self.sensor_info.get((plot.sac, plot.sic))
                    sensor_type = str(sensor_info.get('type', '')).upper() if sensor_info else ''

                    is_psr = False
                    is_ssr = False
                    is_combined = False
                    is_adsb = False
                    is_mlat = False

                    if plot.category == 21:
                        is_adsb = True
                    elif sensor_type == 'MLAT':
                        is_mlat = True
                    elif plot.category == 1:
                        is_psr = True
                    elif plot.category == 48:
                        has_ssr_info = bool(plot.mode3a or plot.mode_s)
                        if sensor_type == 'SSR/PSR' and has_ssr_info:
                            is_combined = True
                        elif not has_ssr_info:
                            is_psr = True
                        else:
                            is_ssr = True
                    else:
                        if 'PSR' in sensor_type and 'SSR' in sensor_type:
                            is_combined = True
                        elif 'PSR' in sensor_type:
                            is_psr = True
                        elif 'SSR' in sensor_type:
                            is_ssr = True
                        elif 'ADS-B' in sensor_type:
                            is_adsb = True
                        else:
                            if plot.mode3a or plot.mode_s:
                                is_ssr = True
                            else:
                                is_psr = True

                    # Colores específicos curados para tema cyber-radar
                    if is_psr:
                        plot_color = QColor(204, 85, 0)  # Dark Orange (PSR)
                    elif is_ssr:
                        plot_color = COLOR_GREEN_NEON  # Verde Neón (SSR)
                    elif is_combined:
                        plot_color = COLOR_GREEN_NEON  # Verde Neón para combinado
                    elif is_adsb:
                        plot_color = QColor("#FFFF00")  # Yellow (ADS-B)
                    elif is_mlat:
                        plot_color = QColor(255, 0, 255)  # Magenta (MLAT)
                    else:
                        plot_color = self._get_sensor_color(plot.sac, plot.sic)

                    if plot.highlighted:
                        base_color = QColor(255, 255, 0, alpha)
                    else:
                        base_color = QColor(plot_color)
                        base_color.setAlpha(alpha)

                    # Símbolo
                    painter.save()
                    try:
                        painter.translate(x, y)
                        if is_adsb and plot.track_angle is not None:
                            painter.rotate(plot.track_angle)

                        sym_size = safe_divide(8.0, z, 1.0)

                        if is_psr:
                            # Radar Primario (PSR): Cruz pequeña (+)
                            pen_psr = QPen(base_color, safe_divide(2.0, z, 0.5))
                            painter.setPen(pen_psr)
                            s_r = sym_size * 0.5
                            painter.drawLine(QPointF(-s_r, 0), QPointF(s_r, 0))
                            painter.drawLine(QPointF(0, -s_r), QPointF(0, s_r))
                        elif is_combined:
                            # Combinado PSR + SSR: Cuadrado con cruz adentro (⊞)
                            pen_c = QPen(base_color, safe_divide(2.0, z, 0.5))
                            painter.setPen(pen_c)
                            painter.setBrush(QBrush(Qt.BrushStyle.NoBrush))
                            painter.drawRect(QRectF(-sym_size / 2, -sym_size / 2, sym_size, sym_size))
                            s_r = sym_size * 0.5
                            painter.drawLine(QPointF(-s_r, 0), QPointF(s_r, 0))
                            painter.drawLine(QPointF(0, -s_r), QPointF(0, s_r))
                        elif is_ssr:
                            # Radar Secundario (SSR): Cuadrado hueco (□)
                            painter.setPen(QPen(base_color, safe_divide(2.0, z, 0.5)))
                            painter.setBrush(QBrush(Qt.BrushStyle.NoBrush))
                            painter.drawRect(QRectF(-sym_size / 2, -sym_size / 2, sym_size, sym_size))
                        elif is_adsb:
                            # ADS-B (CAT 21): Triángulo apuntando hacia arriba (△) o Diamante (♢)
                            painter.setPen(QPen(base_color, safe_divide(2.0, z, 0.5)))
                            painter.setBrush(QBrush(Qt.BrushStyle.NoBrush))
                            if plot.track_angle is not None:
                                t = QPainterPath()
                                t.moveTo(0, -sym_size * 0.66)
                                t.lineTo(-sym_size * 0.5, sym_size * 0.33)
                                t.lineTo(sym_size * 0.5, sym_size * 0.33)
                                t.closeSubpath()
                                painter.drawPath(t)
                            else:
                                t = QPainterPath()
                                t.moveTo(0, -sym_size * 0.5)
                                t.lineTo(sym_size * 0.5, 0)
                                t.lineTo(0, sym_size * 0.5)
                                t.lineTo(-sym_size * 0.5, 0)
                                t.closeSubpath()
                                painter.drawPath(t)
                        elif is_mlat:
                            # Multilateración (MLAT): Triángulo apuntando hacia abajo (▽)
                            painter.setPen(QPen(base_color, safe_divide(2.0, z, 0.5)))
                            painter.setBrush(QBrush(Qt.BrushStyle.NoBrush))
                            t = QPainterPath()
                            t.moveTo(0, sym_size * 0.66)
                            t.lineTo(-sym_size * 0.5, -sym_size * 0.33)
                            t.lineTo(sym_size * 0.5, -sym_size * 0.33)
                            t.closeSubpath()
                            painter.drawPath(t)
                        else:
                            # Fallback por defecto: Círculo hueco (○)
                            painter.setPen(QPen(base_color, safe_divide(2.0, z, 0.5)))
                            painter.setBrush(QBrush(Qt.BrushStyle.NoBrush))
                            painter.drawEllipse(QPointF(0, 0), sym_size / 2, sym_size / 2)
                    finally:
                        painter.restore()

                    # Vector de tendencia
                    if (plot.is_track and plot.ground_speed is not None and
                            plot.track_angle is not None and plot.ground_speed > 10):
                        try:
                            speed_mps = plot.ground_speed * (METERS_PER_NM / 3600.0)
                            v_len = speed_mps * 60.0
                            a_rad = math.radians(plot.track_angle)
                            ex = x + v_len * math.sin(a_rad)
                            ey = y + v_len * math.cos(a_rad)
                            if is_valid_coord(ex, ey):
                                pen_v = QPen(base_color)
                                pen_v.setWidthF(safe_divide(1.0, z, 0.3))
                                painter.setPen(pen_v)
                                painter.drawLine(QPointF(x, y), QPointF(ex, ey))
                        except Exception:
                            pass

                    # DATA BLOCK (TEXTO) — FASE 3: ADAPTATIVO
                    lines = self._build_plot_label_lines(plot)

                    if lines:
                        painter.save()
                        try:
                            painter.translate(x, y)
                            painter.scale(inv_z, -inv_z)
                            painter.setFont(font_sq)
                            lc = QColor(plot_color)
                            lc.setAlpha(alpha)
                            painter.setPen(lc)

                            # Dibujar la línea guía (Leader Line)
                            pen_leader = QPen(base_color)
                            pen_leader.setWidthF(max(0.4, safe_divide(0.6, z, 0.2)))
                            # Línea delgada y translúcida
                            leader_alpha = min(alpha, 80)
                            pen_leader.setColor(QColor(base_color.red(), base_color.green(), base_color.blue(), leader_alpha))
                            painter.setPen(pen_leader)
                            painter.drawLine(QPointF(0, 0), QPointF(10, -10))

                            # Restaurar color de texto
                            painter.setPen(lc)

                            fm = QFontMetrics(font_sq)

                            # Dibujar texto y calcular hitbox exacto con QFontMetrics.boundingRect
                            total_hitbox = None  # QRectF en viewport coords para todas las líneas
                            yo = -10
                            for i, line in enumerate(lines):
                                # Posición del texto en coordenadas de painter (inversa de escala)
                                text_pos = QPointF(10, yo + (i * 14))

                                # boundingRect en coordenadas del painter (texto)
                                br = fm.boundingRect(int(text_pos.x()), int(text_pos.y()),
                                                      int(1e6), int(1e6),
                                                      Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop,
                                                      str(line))

                                # Convertir boundingRect del painter a coordenadas de viewport
                                mapped_rect = painter.transform().mapRect(br)

                                # Acumular en el hitbox combinado
                                if total_hitbox is None:
                                    total_hitbox = QRectF(mapped_rect)
                                else:
                                    total_hitbox = total_hitbox.united(QRectF(mapped_rect))

                                # Dibujar texto
                                painter.drawText(text_pos, str(line))
                        finally:
                            painter.restore()

                        # Guardar hitbox en viewport coords referenciado por plot.id
                        if total_hitbox is not None:
                            self.label_hitboxes[plot.id] = total_hitbox
                except Exception as e:
                    # NOTA: Las capas FASE 3 (plots_raw) y BLINDAJE fueron eliminadas.
                    # El renderizado FASE 2 (tracks + pending_tracks) ya dibuja
                    # cada blanco correctamente con su símbolo y etiqueta.
                    # Mantener esas capas adicionales causaba doble/triple dibujado.
                    print(f"[RENDER WARNING] Error al dibujar target {track_id}: {e}")
                    continue


            # ---- 6. CARTEL DE SENSOR ACTIVO ----
            if self._active_sensor_label:
                try:
                    painter.save()
                    painter.resetTransform()
                    font_label = QFont("Monospace", 12, QFont.Weight.Bold)
                    painter.setFont(font_label)
                    fm = painter.fontMetrics()
                    label_w = fm.horizontalAdvance(self._active_sensor_label) + 16
                    label_h = fm.height() + 8
                    label_x = self.width() - label_w - 10
                    label_y = 12
                    painter.fillRect(label_x, label_y, label_w, label_h, QColor(0, 0, 0, 140))
                    painter.setPen(QColor(0, 255, 255, 255))
                    painter.drawText(label_x + 8, label_y + fm.ascent() + 4, self._active_sensor_label)
                    painter.restore()
                except Exception:
                    painter.restore()

            # ---- 7. LEYENDA DE SENSORES ----
            try:
                painter.save()
                font_legend = QFont("Monospace", 9)
                painter.setFont(font_legend)
                yp = 20
                for sac, sic in sorted(list(self.active_sensors)):
                    key = (sac, sic)
                    color = self._get_sensor_color(sac, sic)
                    name = self.sensor_info.get(key, {}).get('name', f'{sac}/{sic}')
                    painter.setBrush(color)
                    painter.setPen(Qt.PenStyle.NoPen)
                    painter.drawRect(15, yp, 10, 10)
                    painter.setPen(QColor("white"))
                    painter.drawText(QPointF(30, yp + 10), name)
                    yp += 18
                painter.restore()
            except Exception:
                pass

            painter.restore()

        except Exception as e:
            print(f"[RadarWidget] Error en paintEvent: {e}")
            painter.restore()
        finally:
            painter.end()

    # ================================================================
    # WHEEL — ZOOM
    # ================================================================

    def wheelEvent(self, event):
        try:
            delta = event.angleDelta().y()
            if delta > 0:
                self.zoom_factor *= 1.2
            elif delta < 0:
                self.zoom_factor /= 1.2
            self._clamp_zoom()
            self.update()
        except Exception:
            pass

    # ================================================================
    # MOUSE — DRAG PAN
    # ================================================================

    def mousePressEvent(self, event):
        try:
            if event.button() == Qt.MouseButton.LeftButton:
                # FASE 4: Detectar clic en un punto del historial (distancia <= 5px)
                clicked_history = self._get_history_point_at(event.pos(), radius_px=5.0)
                if clicked_history is not None:
                    self.selected_history_point = clicked_history
                    self.update()
                    # No iniciar pan si se seleccionó un punto de historial
                    return

                # Si no hay hit en historial, iniciar pan
                self.is_panning = True
                self.last_mouse_pos = event.pos()
                self.setCursor(Qt.CursorShape.ClosedHandCursor)
                self.selected_history_point = None  # Limpiar selección al hacer pan
                self.update()
            elif event.button() == Qt.MouseButton.RightButton:
                self.is_selecting = True
                self.selection_start_point = event.position()
                self.selection_rect = QRectF(self.selection_start_point, self.selection_start_point)
                self.selected_history_points.clear()
                self.update()
        except Exception:
            pass

    def mouseMoveEvent(self, event):
        try:
            if self.is_selecting:
                self.selection_rect.setBottomRight(event.position())
                self.update()
                return
            if getattr(self, 'is_panning', False) and self.last_mouse_pos is not None:
                dx = event.pos().x() - self.last_mouse_pos.x()
                dy = event.pos().y() - self.last_mouse_pos.y()
                self.pan_x += dx
                self.pan_y += dy
                self.last_mouse_pos = event.pos()
                self.update()
                return

            # NOTA: No se usa QToolTip.showText() porque en algunos sistemas Linux
            # las tooltips heredan el tema oscuro del sistema y no se ven los textos.
            # Para información sobre puntos de historial, usar doble clic.
        except Exception:
            pass

    def mouseReleaseEvent(self, event):
        try:
            if event.button() == Qt.MouseButton.LeftButton:
                self.is_panning = False
                self.last_mouse_pos = None
                self.setCursor(Qt.CursorShape.ArrowCursor)
            elif event.button() == Qt.MouseButton.RightButton and self.is_selecting:
                self.is_selecting = False
                selection_area = self.selection_rect.normalized()

                self.selected_history_points.clear()

                for plot_id, history_deque in self.history.items():
                    plot = self._plots.get(plot_id)
                    if not plot or not plot.is_alive():
                        continue
                    for i, hp in enumerate(history_deque):
                        screen_pos = self._world_to_screen(hp.x, hp.y)
                        if screen_pos and selection_area.contains(screen_pos):
                            self.selected_history_points.append((plot, hp, i))
                self.selection_rect = QRectF()
                self.update()
        except Exception:
            pass

    # ================================================================
    # DOUBLE CLICK — INSPECCIÓN POR DATA BLOCK (HITBOX EN TEXTO)
    # ================================================================

    def _build_plot_label_lines(self, plot: 'RadarPlot') -> List[str]:
        lines = []
        
        # 1. Identificador de llamada (Callsign)
        if plot.callsign and plot.callsign.strip() and plot.callsign != '----':
            lines.append(f"CS: {plot.callsign.strip()}")
            
        # 2. Código SSR (Mode 3/A - Squawk)
        if plot.mode3a and plot.mode3a != '----' and plot.mode3a != '0000':
            lines.append(f"SSR: {plot.mode3a}")
            
        # 3. Nivel de Vuelo (FL) o Altitud
        # Calcular tendencia de nivel (ascenso / descenso) dinámicamente
        trend_arrow = ""
        if plot.id in self.history:
            hist = list(self.history[plot.id])
            if len(hist) >= 3:
                past_pt = hist[-3]
                if plot.flight_level is not None and past_pt.fl:
                    try:
                        if past_pt.fl.startswith("FL"):
                            past_fl = float(past_pt.fl[2:])
                            diff = plot.flight_level - past_fl
                            if diff >= 1.5:
                                trend_arrow = " ↑"
                            elif diff <= -1.5:
                                trend_arrow = " ↓"
                    except Exception:
                        pass
        
        if plot.flight_level is not None:
            lines.append(f"FL{int(plot.flight_level)}{trend_arrow}")
        elif plot.altitude_ft is not None:
            lines.append(f"ALT: {int(plot.altitude_ft)}ft{trend_arrow}")
            
        # 4. Dirección Mode S / ICAO Address
        if plot.mode_s and plot.mode_s != '----':
            lines.append(f"ICAO: {plot.mode_s.upper()}")
            
        # 5. Coordenadas polares (Rho & Theta)
        rho = plot.raw_range
        theta = plot.raw_azimuth
        if plot.category in (1, 48, 21, 62):
            if (rho is None or theta is None) and plot.x is not None and plot.y is not None:
                try:
                    if rho is None:
                        rho = math.sqrt(plot.x**2 + plot.y**2) / 1852.0
                    if theta is None:
                        if not (abs(plot.x) < 1e-6 and abs(plot.y) < 1e-6):
                            angle = math.degrees(math.atan2(plot.x, plot.y))
                            if angle < 0:
                                angle += 360.0
                            theta = angle
                except Exception:
                    pass

        if rho is not None and theta is not None:
            lines.append(f"R/A: {rho:.1f}NM {theta:.1f}°")
            
        # 6. Información complementaria (Velocidad y Rumbo)
        comp = []
        if plot.ground_speed is not None:
            comp.append(f"{int(plot.ground_speed)}kt")
        if plot.track_angle is not None:
            comp.append(f"{plot.track_angle:.1f}°")
        if comp:
            lines.append(" ".join(comp))
            
        # Anteponer la categoría al principio
        if not lines:
            lines.append(f"CAT {plot.category:02d}")
        else:
            lines[0] = f"[{plot.category:02d}] {lines[0]}"
            
        return lines

    def _get_label_rect(self, plot: 'RadarPlot', z: float, inv_z: float,
                        vp_cx: float, vp_cy: float, side: float) -> Optional[QRectF]:
        """
        Calcula el rectángulo del data block label en coordenadas de viewport
        para poder hacer hit-test con el clic del mouse.

        Retorna QRectF en coordenadas del viewport (píxeles) o None si no hay label.
        """
        lines = self._build_plot_label_lines(plot)

        if not lines:
            return None

        # Calcular posición en viewport del símbolo
        # paintEvent: translate(vp_cx + pan_x, vp_cy + pan_y) → scale(z, -z)
        # El símbolo está en (plot.x, plot.y) en mundo
        # En viewport: screen_x = vp_cx + pan_x + plot.x * z
        #              screen_y = vp_cy + pan_y - plot.y * z
        sx = vp_cx + self.pan_x + plot.x * z
        sy = vp_cy + self.pan_y - plot.y * z

        # El label se dibuja en inv_z (texto no escalado)
        # offset: QPointF(10, yo + i*14) donde yo = -10 (en espacio escalado inv_z)
        # En viewport: (sx + 10, sy + yo + i*14)
        font = QFont("Monospace", 9)
        fm = QFontMetrics(font)

        max_width = 0
        total_height = len(lines) * 14
        for line in lines:
            w = fm.horizontalAdvance(line)
            if w > max_width:
                max_width = w

        # Rect que cubre todas las líneas
        label_x = sx + 10
        label_y = sy - 10  # yo = -10 for first line
        return QRectF(label_x, label_y, max_width + 4, total_height + 4)

    def mouseDoubleClickEvent(self, event):
        """
        Inspección detallada del blanco por doble clic en su etiqueta (DATA BLOCK).

        FASE 3: La detección se realiza EXCLUSIVAMENTE por bounding box
        (rect.contains(event.pos()) sobre self.label_hitboxes):
          Itera sobre self.label_hitboxes (pre-calculadas en paintEvent mediante
          QFontMetrics.boundingRect() + painter.transform().mapRect()).
          Si rect.contains(event.pos()), abre TargetInspectionDialog.

        REGLAS:
          - NO usa distancia al centro del plot.
          - NO usa fallback al símbolo geométrico.
          - Solo se activa si el clic cae DENTRO del área de texto del label.
        """
        try:
            if not self.projection_set or not self.tracks:
                return

            click_pos = event.position()

            # Única búsqueda: bounding box del texto (label hitbox)
            for pid, hitbox in self.label_hitboxes.items():
                if pid not in self.tracks:
                    continue
                plot = self.tracks[pid]
                if not plot.is_alive():
                    continue

                if hitbox.contains(click_pos):
                    # Hit exacto dentro del área del label → abrir inspección
                    plot_history = self.history.get(plot.id, deque())
                    dialog = TargetInspectionDialog(
                        plot, self.sensor_info,
                        history=plot_history,
                        parent=self.window(), proy=self.proy,
                        asterix_version=self.asterix_version
                    )
                    dialog.exec()
                    return

            # Si ningún rect contiene el clic, no se hace nada

        except Exception as e:
            print(f"[RadarWidget] Error en doble clic: {e}")

    # ================================================================
    # MOUSE MOVE — TOOLTIP SOBRE HISTORIAL
    # ================================================================
    def _world_to_screen(self, x: float, y: float) -> Optional[QPointF]:
        w, h = self.width(), self.height()
        z = self.zoom_factor
        if z < MIN_ZOOM:
            return None
        side = min(w, h)
        vp_cx, vp_cy = side / 2.0, side / 2.0
        sx = vp_cx + self.pan_x + x * z
        sy = vp_cy + self.pan_y - y * z
        return QPointF(sx, sy)

    def _get_history_point_at(self, pos, radius_px: float = 8.0) -> Optional[Tuple['RadarPlot', 'HistoryPoint', int]]:
        """
        Busca si la posición del mouse/press está sobre algún punto del historial.
        Retorna (plot, history_point, index verdadero en historia) o None.

        Parámetros:
          pos: QPoint con coordenadas del evento.
          radius_px: radio de tolerancia en píxeles para considerar un hit.
        """
        for plot_id, history_deque in self.history.items():
            plot = self.tracks.get(plot_id)
            if not plot or not plot.is_alive():
                continue

            for i, hp in enumerate(reversed(list(history_deque))):
                hx, hy = hp.x, hp.y
                if not is_valid_coord(hx, hy):
                    continue
                # Convert world coords to screen coords
                screen_pos = self._world_to_screen(hx, hy)
                if not screen_pos:
                    continue
                px = pos.x()
                py = pos.y()
                dist_px = math.sqrt((screen_pos.x() - px) ** 2 + (screen_pos.y() - py) ** 2)
                if dist_px < radius_px:
                    # Índice verdadero (desde el inicio de la cola)
                    true_idx = len(history_deque) - 1 - i
                    return (plot, hp, true_idx)

        return None

    def _draw_cat62_plot(self, painter: QPainter, plot: 'RadarPlot', z: float, inv_z: float):
        """
        FASE 2/3: Dibuja un plot de CAT 62 de forma completamente aislada.
        
        Pipeline de renderizado para CAT 62 (System Track):
          1. Símbolo: cuadrado sólido CYAN (#00FFFF) con alta visibilidad
          2. Data Block: texto BLANCO (callsign / FL / GS)
          3. Vector de tendencia: línea proporcional a ground_speed segun track_angle
        
        CLAVES ACOPLADAS al esquema del decodificador:
          - plot.callsign     → Identificador de vuelo (I062/380)
          - plot.flight_level → Nivel de vuelo FL (I062/210)
          - plot.ground_speed → Velocidad en nudos GS (I062/185)
          - plot.track_angle  → Rumbo en grados (I062/202)
        
        REGLA ABSOLUTA:
          - Usar EXCLUSIVAMENTE plot.x / plot.y (ya proyectadas en _process_plot_data)
          - NO re-proyectar desde raw_dict
        """
        try:
            # ================================================================
            # 1. COORDENADAS (FASE 3: Filtros de validez desactivados para depuración)
            # ================================================================
            x, y = plot.x, plot.y

            # Coordenadas en pantalla para depuración
            w, h = self.width(), self.height()
            side = min(w, h)
            vp_cx, vp_cy = side / 2.0, side / 2.0
            cx = vp_cx + self.pan_x
            cy = vp_cy + self.pan_y
            screen_x = cx + x * self.zoom_factor
            screen_y = cy - y * self.zoom_factor

            alpha = plot.alpha

            # Símbolo: CYAN fijo (#00FFFF) — máxima visibilidad sobre fondo #0B0E14
            symbol_color = QColor(COLOR_CYAN)  # #00FFFF
            if plot.highlighted:
                symbol_color = QColor(255, 255, 0, alpha)
            else:
                # FASE 3: Asegurar que alpha no sea negativo si la validación se desactiva
                symbol_color.setAlpha(max(0, alpha))

            # ================================================================
            # 3. SÍMBOLO: CUADRADO SÓLIDO CYAN
            # ================================================================
            painter.save()
            try:
                painter.translate(x, y)
                painter.setPen(QPen(symbol_color, max(0.0, safe_divide(2.0, z, 0.5))))
                painter.setBrush(QBrush(symbol_color, Qt.BrushStyle.SolidPattern))
                sym_size = max(0.0, safe_divide(8.0, z, 1.0))

                painter.drawRect(QRectF(-sym_size / 2, -sym_size / 2, sym_size, sym_size))
            finally:
                painter.restore()

            # ================================================================
            # 4. VECTOR DE TENDENCIA (track_angle + ground_speed)
            # ================================================================
            hdg = plot.track_angle     # I062/202: Track Angle (grados, 0=Norte)
            gs = plot.ground_speed     # I062/185: Ground Speed (nudos)
            if (plot.is_track and gs is not None and hdg is not None and gs > 10):
                try:
                    # Velocidad en metros/segundo (1 NM = 1852 m, 1 h = 3600 s)
                    speed_mps = gs * (METERS_PER_NM / 3600.0)
                    # Vector de 60 segundos (1 minuto de trayectoria proyectada)
                    v_len = speed_mps * 60.0
                    # track_angle: 0° = Norte, crece en sentido horario
                    a_rad = math.radians(hdg)
                    ex = x + v_len * math.sin(a_rad)
                    ey = y + v_len * math.cos(a_rad)
                    if is_valid_coord(ex, ey):
                        pen_v = QPen(symbol_color)
                        pen_v.setWidthF(max(0.0, safe_divide(1.0, z, 0.3)))
                        painter.setPen(pen_v)
                        painter.drawLine(QPointF(x, y), QPointF(ex, ey))
                except Exception:
                    pass

            # ================================================================
            # 5. DATA BLOCK (Etiqueta BLANCA)
            # ================================================================
            lines = self._build_plot_label_lines(plot)

            if not lines:
                return

            # REGLA DE RENDERIZADO VISUAL (FASE 2)
            # Etiqueta en BLANCO puro (#FFFFFF) para máximo contraste
            label_color = QColor("#FFFFFF")
            label_color.setAlpha(alpha if alpha > 0 else 255)

            painter.save()
            try:
                painter.translate(x, y)
                painter.scale(inv_z, -inv_z)

                font_sq = QFont("Monospace", 9)
                painter.setFont(font_sq)
                painter.setPen(label_color)

                # Dibujar la línea guía (Leader Line)
                pen_leader = QPen(symbol_color)
                pen_leader.setWidthF(max(0.4, safe_divide(0.6, z, 0.2)))
                # Línea delgada y translúcida
                leader_alpha = min(alpha, 80)
                pen_leader.setColor(QColor(symbol_color.red(), symbol_color.green(), symbol_color.blue(), leader_alpha))
                painter.setPen(pen_leader)
                painter.drawLine(QPointF(0, 0), QPointF(10, -10))

                # Restaurar color de texto
                painter.setPen(label_color)

                fm = QFontMetrics(font_sq)
                total_hitbox = None
                yo = -10
                for i, line in enumerate(lines):
                    text_pos = QPointF(10, yo + (i * 14))
                    br = fm.boundingRect(int(text_pos.x()), int(text_pos.y()), int(1e6), int(1e6),
                                          Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop, str(line))
                    mapped_rect = painter.transform().mapRect(br)
                    if total_hitbox is None:
                        total_hitbox = QRectF(mapped_rect)
                    else:
                        total_hitbox = total_hitbox.united(QRectF(mapped_rect))
                    painter.drawText(text_pos, str(line))
            finally:
                painter.restore()

            if total_hitbox is not None:
                self.label_hitboxes[plot.id] = total_hitbox

        except Exception as e:
            print(f"[RENDER WARNING] Error al dibujar target CAT 62 {plot.id}: {e}")
