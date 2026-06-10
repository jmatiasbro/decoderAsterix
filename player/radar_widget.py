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
import os
import re
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

from utils.geo import METERS_PER_NM, StereographicLocal, WGS84_GEOD
from decoder.altimetry import AltimetryManager


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
        self._use_pcap_time: bool = False
        self._playback_speed: float = 1.0
        self._last_wall_time: float = time_module.time()

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
            
            if self._use_pcap_time:
                now_wall = time_module.time()
                dt_wall = now_wall - self._last_wall_time
                if dt_wall > 1.0:
                    dt_wall = 1.0
                elif dt_wall < 0.0:
                    dt_wall = 0.0
                
                self._sim_clock += dt_wall * self._playback_speed
                self._last_wall_time = now_wall
                return self._sim_clock
            else:
                self._sim_clock = time_module.time()
                return self._sim_clock

    def set_time(self, t: float):
        """Fuerza el reloj de simulación al tiempo indicado (típicamente del PCAP)."""
        with self._rwlock:
            self._sim_clock = t
            self._last_wall_time = time_module.time()
            self._use_pcap_time = True

    def set_speed(self, speed: float):
        """Establece la velocidad de reproducción de la simulación."""
        with self._rwlock:
            if not self._frozen and self._use_pcap_time:
                now_wall = time_module.time()
                dt_wall = now_wall - self._last_wall_time
                if 0.0 <= dt_wall <= 1.0:
                    self._sim_clock += dt_wall * self._playback_speed
                self._last_wall_time = now_wall
            self._playback_speed = speed

    def reset(self):
        """Restablece el singleton de tiempo al tiempo del sistema y desactiva el modo PCAP."""
        with self._rwlock:
            self._sim_clock = time_module.time()
            self._frozen = False
            self._use_pcap_time = False
            self._playback_speed = 1.0
            self._last_wall_time = time_module.time()

    def freeze(self):
        """Congela el tiempo de simulación (no avanza)."""
        with self._rwlock:
            if not self._frozen:
                if self._use_pcap_time:
                    now_wall = time_module.time()
                    dt_wall = now_wall - self._last_wall_time
                    if 0.0 <= dt_wall <= 1.0:
                        self._sim_clock += dt_wall * self._playback_speed
                else:
                    self._sim_clock = time_module.time()
                self._frozen = True

    def unfreeze(self):
        """Descongela el tiempo de simulación."""
        with self._rwlock:
            if self._frozen:
                self._frozen = False
                self._last_wall_time = time_module.time()

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
    timestamp: float = 0.0
    sac: Optional[int] = None
    sic: Optional[int] = None
    raw_x: Optional[float] = None
    raw_y: Optional[float] = None



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
    QColor("#00F5FF"),  # Turquesa Neón
    QColor("#FF007F"),  # Rosa Fucsia
    QColor("#FF8C00"),  # Naranja Coral
    QColor("#A020F0"),  # Violeta Neón
    QColor("#7FFF00"),  # Verde Lima
    QColor("#FFD700"),  # Oro brillante
    QColor("#38B0DE"),  # Celeste
    QColor("#00FFC4"),  # Verde Menta
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
HISTORY_LENGTH = 15  # Últimos 15 puntos de trayectoria (estela de puntos)

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


def is_angle_between(target: float, start: float, end: float) -> bool:
    """Retorna True si el ángulo target está entre start y end en sentido horario."""
    target = target % 360.0
    start = start % 360.0
    end = end % 360.0
    if start <= end:
        return start <= target < end
    else:
        return start <= target or target < end


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
                 'raw_range', 'bds_data', 'raw_dict', 'reporting_sensors',
                 'is_reflection', 'linked_real_id', 'has_reflection', 'ab_filter',
                 'garbled', 'degradada', 'dqf_razon', '_update_count', '_first_seen',
                 'en_jurisdiccion', 'label_offset', 'is_dragging', 'label_rect',
                 'widget_ref',
                 '_update_period',
                 # Suavizado de velocidad y filtros de plausibilidad (antes ausentes
                 # de __slots__: el AttributeError silencioso deshabilitaba el
                 # cross-fill de identidad y la acumulación de reporting_sensors).
                 '_smooth_vx', '_smooth_vy', '_vel_prev_x', '_vel_prev_y', '_vel_prev_t',
                 '_last_fl_time', '_last_gs_time')

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
        self.is_reflection = False
        self.linked_real_id = None
        self.has_reflection = False
        self.ab_filter = None
        self.garbled = False
        self.degradada = False
        self.dqf_razon = ""
        self._update_count = 0
        self._first_seen = SimulationTime.time()  # Momento de creación (no se resetea)
        self.en_jurisdiccion = False
        self.label_offset = QPointF(30, -30)
        self.is_dragging = False
        self.label_rect = QRectF()
        self.widget_ref = None
        self._update_period = 4.0

    def set_highlight_filter(self, filtro: str):
        self._highlight_filter = filtro

    @property
    def highlighted(self) -> bool:
        if not self._highlight_filter:
            return False
        return (self._highlight_filter in self.mode3a or
                self._highlight_filter.lower() in self.callsign.lower())

    def illuminate(self):
        self.is_illuminated = True
        self._last_seen = SimulationTime.time()

    @property
    def age(self) -> float:
        """
        Retorna la edad del plot/track.
        CAT62: pista consolidada del SDP — sin barrido de antena, sin sensor_time.
        Se mide contra el reloj de simulación directamente.
        Otras categorías: contra el reloj del sensor (get_sensor_time) para evitar
        que relojes desincronizados de otros sensores afecten su vigencia.
        """
        if self.category == 62:
            return SimulationTime.time() - self._last_seen
        # Pistas multi-sensor (modo integrado): usar SimulationTime directamente
        # para evitar que el reloj de un solo sensor afecte la vigencia de una pista
        # que puede seguir siendo actualizada por otro sensor.
        if len(getattr(self, 'reporting_sensors', [])) > 1:
            return SimulationTime.time() - self._last_seen
        if getattr(self, 'widget_ref', None) is not None:
            return self.widget_ref.get_sensor_time(self.sac, self.sic) - self._last_seen
        return SimulationTime.time() - self._last_seen

    @property
    def alpha(self) -> int:
        return self.get_alpha(None)

    def get_alpha(self, max_age: Optional[float] = None) -> int:
        if max_age is None:
            max_age = MAX_AGE_TRACK if self.is_track else MAX_AGE_PLOT
        age = self.age
        if age >= max_age:
            return 0
        ratio = age / max_age
        return max(30, int(255 * (1.0 - ratio * ratio)))

    def is_alive(self, max_age: Optional[float] = None) -> bool:
        if max_age is None:
            max_age = MAX_AGE_TRACK if self.is_track else MAX_AGE_PLOT
        return self.age < max_age

    @property
    def lat(self) -> Optional[float]:
        if self.raw_dict:
            return self.raw_dict.get('lat') or self.raw_dict.get('lat_render')
        return None

    @property
    def lon(self) -> Optional[float]:
        if self.raw_dict:
            return self.raw_dict.get('lon') or self.raw_dict.get('lon_render')
        return None


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
        self.setStyleSheet("""
            QDialog {
                background-color: #0E131F;
                border: 2px solid #00E5FF;
                border-radius: 8px;
            }
            QLabel {
                color: #FFFFFF;
                font-family: 'Segoe UI', sans-serif;
                font-size: 11pt;
                font-weight: bold;
            }
            QTableWidget {
                background-color: #121824;
                color: #E0E6ED;
                gridline-color: #2D3548;
                border: 1px solid #2D3548;
                border-radius: 6px;
                font-family: 'Monospace';
                font-size: 9pt;
            }
            QTableWidget::item {
                padding: 6px;
                border-bottom: 1px solid #1B2232;
            }
            QTableWidget::item:selected {
                background-color: rgba(0, 229, 255, 30);
                color: #00E5FF;
            }
            QHeaderView::section {
                background-color: #1A2233;
                color: #00E5FF;
                padding: 6px;
                border: 1px solid #2D3548;
                font-weight: bold;
                font-size: 9pt;
            }
            QPushButton {
                background-color: rgba(45, 49, 60, 200);
                border: 1px solid #4B5263;
                border-radius: 4px;
                padding: 6px 12px;
                color: #FFFFFF;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #3E4451;
                border: 1px solid #00E5FF;
                color: #00E5FF;
            }
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


def _filter_mode3a(value):
    """Devuelve el squawk sólo si es válido (no None, vacío, '----' ó '0000'/0)."""
    if value is None or value == '' or value == '----':
        return ''
    m3a_str = f"{value:04o}" if isinstance(value, int) else str(value).strip()
    if m3a_str == '0000':
        return ''
    return value


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

    def __init__(self, parent=None, sensores: Dict = None, declinacion_magnetica: float = 0.0):
        super().__init__(parent)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        self.sensor_info = sensores or {}
        self.declinacion_magnetica = declinacion_magnetica
        # Compensador magnético dinámico (WMM); usa la declinación estática como fallback
        from player.magnetic_compensator import MagneticCompensator
        self.magnetic_compensator = MagneticCompensator(fallback_deg=declinacion_magnetica)
        # Núcleo de correlación multisensor headless (compartido con la herramienta
        # de calibración offline). El TTL de la asociación usa el reloj de simulación.
        from fusion.correlator import Correlator
        self.correlator = Correlator(now_fn=SimulationTime.time)
        self.plot_filter_fn = None
        self.proy = StereographicLocal()
        self.projection_set = False
        self.center_key: Optional[Tuple[int, int]] = None

        # Variables de estado RBL (Range & Bearing Line)
        # rbl_activo / rbl_origen_anchor / rbl_destino_anchor → RBL en construcción (aun no persistente)
        self.rbl_activo = False
        self.rbl_origen_anchor = None
        self.rbl_destino_anchor = None
        # Lista de RBLs persistentes. Cada elemento es un dict:
        # { 'origen': anchor, 'destino': anchor,
        #   'label_hitbox': QRectF|None, 'p_origen': QPointF|None, 'p_destino': QPointF|None,
        #   'color': QColor }
        self.rbl_lines = []
        self._rbl_color = QColor("#FFD700")  # Color único para todos los RBLs
        self.focused_target_id = None
        self.rbl_drag_origin_anchor = None
        self.mouse_press_pos = None
        self.hovered_target_id = None

        # FASE 1: Factor de escala píxeles/unidad para calcular_xy_pantalla.
        # Representa cuántos píxeles equivalen a 1 Milla Náutica.
        # Ej: 2.0 significa que 50 NM ocupan 100 píxeles.
        self.escala = 2.0
        # Centro geográfico de referencia (ACC Córdoba / Taravella)
        self.centro_lat = -31.31
        self.centro_lon = -64.21

        # Jurisdicción operativa: volumen = radio (NM) x techo (FL)
        self.techo_incumbencia = 95
        self.radio_incumbencia = 50.0
        # Vista de incumbencia (Fase C): dibuja el anillo de jurisdicción y atenúa
        # el tráfico fuera del radio o sobre el techo FL. En controlador va implícita.
        self.mostrar_incumbencia = False
        # Vista limpia para rol controlador (sin coberturas/símbolo radar/sweep/anillos de rango)
        self.vista_controlador = False
        # Gestor de altimetría (impulsado por perfil; QNH manual desde HMI)
        self.altimetry = AltimetryManager()
        self.aeropuerto_lat = -31.31548
        self.aeropuerto_lon = -64.21545

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
        self.history_visible = True
        self.mtr_visible = True

        from player.map_manager import MapManager
        self.map_manager = MapManager()
        self.map_manager.cargar_cartografia_base()

        # FASE 1 (OACI DOC 4444): Temporizador de Parpadeo (Blink Timer) para alertas visuales
        self.blink_flag = False
        self.blink_timer = QTimer(self)
        self.blink_timer.timeout.connect(self._toggle_blink)
        self.blink_timer.start(500)  # Parpadeo cada 500ms

        # Filtros
        self.active_sensors: Set[Tuple[int, int]] = set()
        self.squawk_filter = ""
        self.filter_enabled = False
        
        # Configuración de Filtro de Etiquetas (Fase 9)
        self.label_filter_config = {
            "codigo_a": True, "numero_mensaje": False, "codigo_c": True,
            "direccion_aeronave": True, "numero_respuestas": False, "velocidad": True,
            "hora_utc": False, "numero_pista": True, "identific_aeronave": True,
            "altitud_adsb": True, "cat_emisor_adsb": False, "veloc_vertic_adsb": False,
            "rho_theta": False, "rumbo_verdadero": False, "rumbo_magnetico": False,
            "orientacion": "NE", "sel_por_codigo_a": True, "sel_por_posicion": False
        }

        # Zoom/pan
        self.zoom_factor = 1.0
        self.pan_x = 0.0
        self.pan_y = 0.0
        self.vector_tiempo_minutos = 2

        # Colores
        self.sensor_colors: Dict[Tuple[int, int], QColor] = {}
        self.color_palette_index = 0
        self._setup_default_colors()

        # Barrido
        self.sweep_angle = 0.0
        self.target_sweep_angle = 0.0
        self.sweep_rpm = 12.0
        self.playback_speed = 1.0
        self.sensor_rpms: Dict[Tuple[int, int], float] = {}
        self.sensor_times: Dict[Tuple[int, int], float] = {}
        self.sweep_visible = True
        self.sweep_enabled = False
        self.show_silence_cone = False

        # Coberturas de radar (Fase 16)
        self.radar_coverages = []
        self._load_radar_coverages()

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

        # Almacén de reflectores calculados dinámicamente
        # Mapa: (azimuth_bin, range_bin) -> { 'hits': count, 'azimuth': float, 'range_nm': float }
        self.detected_reflectors: Dict[Tuple[int, int], Dict[str, Any]] = {}

        # FASE 3: Lista plana de plots crudos con coordenadas de pantalla
        # Usado por agregar_plot_individual como ruta directa de renderizado
        self.plots_raw: List[Dict[str, Any]] = []

        # Inicializar STCA Engine, Diálogo y QualityManager (DQF)
        from analysis.stca_analyzer import STCA_Engine
        from player.stca_dialog import STCADialog
        from analysis.quality_manager import QualityManager
        self.stca_engine = STCA_Engine()
        self.stca_dialog = STCADialog(self)
        self.stca_habilitado = True
        self.quality_manager = QualityManager()
        # Silenciar el logger interno del QM: registra en cada ciclo y satura el
        # archivo. El registro de eventos de calidad ahora es deduplicado y vive
        # en quality_events.log vía _log_quality_event().
        try:
            self.quality_manager.logger.handlers.clear()
            self.quality_manager.logger.disabled = True
        except Exception:
            pass
        # Dedup de eventos de calidad ya registrados: keys (track_id, razon) para
        # DQF y reflector_key para reflexiones. Evita repetir la misma línea.
        self._logged_quality_events: Set = set()
        # Cache de velocidad estimada por pista para el campo N: { plot_id: (gs_kt, timestamp) }.
        # Evita recalcular en cada repintado y permite suavizar (EMA) entre scans.
        self._gs_est_map: Dict[str, Tuple[float, float]] = {}
        self.modo_integrado = True
        self.tracks_en_alerta = set()
        self.conflictos_activos = []
        self.logged_conflicts = {}
        
        # Activar seguimiento de cursor y HUD geodésico (FASE 4)
        self.setMouseTracking(True)
        self.cursor_geo_text = "LAT: --.----° | LON: --.----°"

    def set_label_filter_config(self, config: dict):
        """Actualiza la configuración de filtros de etiquetas."""
        self.label_filter_config = config
        self.update()

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

    def get_sensor_time(self, sac: int, sic: int) -> float:
        return self.sensor_times.get((sac, sic), SimulationTime.time())

    def reset_sweep_angle(self):
        self.sweep_angle = 0.0

    def set_sweep_visible(self, visible: bool):
        self.sweep_visible = visible
        if not visible:
            self._promote_all_pending()
        self.update()

    def set_history_visible(self, visible: bool):
        self.history_visible = visible
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
    def _toggle_blink(self):
        self.blink_flag = not self.blink_flag
        self.update()

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

    @pyqtSlot()
    def pause(self):
        acquired = self._command_lock.acquire(blocking=False)
        if not acquired:
            return
        try:
            sim_time = SimulationTime.instance()
            sim_time.freeze()
            self._is_playing = False
            self._last_sweep_tick_time = None
        finally:
            self._command_lock.release()

    def stop_sweep(self):
        acquired = self._command_lock.acquire(blocking=False)
        if not acquired:
            return
        try:
            sim_time = SimulationTime.instance()
            sim_time.reset()
            self.timer.stop()
            self._last_tod = 0.0
            self.sweep_angle = 0.0
            self.sweep_visible = False
            self._is_playing = False
            self.tracks.clear()
            self.pending_tracks.clear()
            self.history.clear()
            self.selected_history_points.clear()
            self.detected_reflectors.clear()
            self.plot_count = 0
            
            # Reset Hibrido STCA
            if hasattr(self, 'stca_dialog') and self.stca_dialog:
                self.stca_dialog.hide()
            self.tracks_en_alerta = set()
            self.conflictos_activos = []
            self.logged_conflicts = {}
            
            self.update()
        finally:
            self._command_lock.release()

    @pyqtSlot()
    def clear_all_plots(self):
        self.stop_sweep()

    def limpiar_pantalla(self):
        """Vacía las estructuras de datos y fuerza un repintado en blanco."""
        try:
            SimulationTime.instance().reset()
        except Exception:
            pass

        if hasattr(self, 'plots'):
            self.plots = []
        if hasattr(self, 'plots_raw'):
            self.plots_raw = []
        if hasattr(self, 'tracks'):
            self.tracks = {}
        if hasattr(self, 'pending_tracks'):
            self.pending_tracks = {}
        if hasattr(self, 'history'):
            self.history.clear()
        if hasattr(self, 'sensor_rpms'):
            self.sensor_rpms.clear()
        if hasattr(self, 'sensor_times'):
            self.sensor_times.clear()
            
        self.sweep_angle = 0.0
        self.target_sweep_angle = 0.0
        self._last_tod = 0.0
        self._last_plot_azimuth = None
        self._last_wrap_time = None
        if hasattr(self, 'detected_reflectors'):
            self.detected_reflectors.clear()
            
        # Reset Hibrido STCA
        if hasattr(self, 'stca_dialog') and self.stca_dialog:
            self.stca_dialog.hide()
        self.tracks_en_alerta = set()
        self.conflictos_activos = []
        self.logged_conflicts = {}
        
        self.update()

    # ================================================================
    # MAPA DXF
    # ================================================================

    # ================================================================
    # MAPA DXF
    # ================================================================

    @property
    def map_has_data(self):
        if not hasattr(self, 'map_manager'): return False
        return bool(self.map_manager.get_visible_layers())

    @property
    def map_min_x(self):
        return self.map_manager.get_bounds()[0] if hasattr(self, 'map_manager') else 0.0

    @property
    def map_min_y(self):
        return self.map_manager.get_bounds()[1] if hasattr(self, 'map_manager') else 0.0

    @property
    def map_max_x(self):
        return self.map_manager.get_bounds()[2] if hasattr(self, 'map_manager') else 1.0

    @property
    def map_max_y(self):
        return self.map_manager.get_bounds()[3] if hasattr(self, 'map_manager') else 1.0

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
        if not self.proy or not self.proy.activo:
            return
        self.map_manager.reproject_all(self.proy)


    def set_raw_map_segments(self, raw_segments: list, min_x: float, min_y: float,
                              max_x: float, max_y: float, name: str = "Mapa Táctico"):
        self.map_manager.add_layer(name, raw_segments, "TACTICO")
        self._reproject_dxf_to_current_proy()
        self.update()

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
        self.centro_lat = lat
        self.centro_lon = lon
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
        # Preservar el estado de reproducción si ya estábamos reproduciendo
        # (ej. si se auto-centró la proyección sobre la marcha)
        if not getattr(self, '_is_playing', False):
            self.sweep_visible = False
            self._is_playing = False
        else:
            self.sweep_visible = True
            self._is_playing = True
        name = sensor_name or f"Radar {sac}/{sic}"
        version_str = f" - CAT 48 {asterix_version}" if asterix_version else ""
        self._active_sensor_label = f"SENSOR ACTIVO: {name} ({sac}/{sic}){version_str}"
        self.sensor_colors.clear()
        self.color_palette_index = 0
        self._setup_default_colors()
        self._reproject_dxf_to_current_proy()
        print(f"[GEODESIA] Centro: [{name}] (Lat: {lat:.5f}, Lon: {lon:.5f}){version_str}")
        print(f"[GEODESIA] Mapas reproyectados: {len(self.map_manager.layers)} capas activas")
        self.update()

    def set_projection_center(self, lat: float, lon: float, sensor_key: Optional[Tuple[int, int]] = None):
        if self.proy.center_lat != lat or self.proy.center_lon != lon:
            self.proy.set_center(lat, lon)
            self.projection_set = True
            self.center_key = sensor_key
            self.centro_lat = lat
            self.centro_lon = lon
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

        # 3.b) Reproyectar TODAS las tracks/pending/estelas al nuevo centro.
        # Sin esto, las pistas existentes quedan en el marco de proyección anterior
        # mientras los plots entrantes usan el nuevo: el emparejado de fusión (MRT)
        # falla y aparecen duplicados al cambiar de rol/perfil.
        self.reproject_all_coordinates()

        # 4) Forzar actualización visual
        self.update()
        print(f"[GEODESIA] Vista centrada en Lat: {target_lat:.5f}, Lon: {target_lon:.5f}")

    def configurar_vista_perfil(self, lat: float, lon: float):
        """
        Ancla y zoom geográfico del PPI al aeródromo de trabajo,
        recalculando el factor de escala de píxeles por milla náutica.
        """
        # 1) Desplazar el centro al aeródromo
        self.centrar_en_coordenadas(lat, lon)

        # 2) Zoom para enmarcar el área de control (radio de incumbencia + margen del 30%)
        radio = float(getattr(self, 'radio_incumbencia', 50.0))
        rango_vista_nm = max(radio * 1.3, 10.0)
        widget_radius_px = min(self.width(), self.height()) / 2.0
        if widget_radius_px > 0:
            self.zoom_factor = widget_radius_px / (rango_vista_nm * 1852.0)
            self._clamp_zoom()
        self.update()
        print(f"[RADAR VIEW] Perfil configurado: Centro Lat={lat:.5f}, Lon={lon:.5f}, Zoom={self.zoom_factor:.6f}")

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
            # Sincronizar el reloj de simulación con el timestamp del plot procesado (usar TOD del mensaje ASTERIX)
            plot_time = data.get('time')
            if plot_time is not None:
                SimulationTime.instance().set_time(plot_time)

            # Filtrar pistas de prueba genéricas (ADSB1, ADSB2, 0AD5B1, etc.)
            mode_s_upper = (data.get('mode_s') or "").strip().upper()
            callsign_upper = (data.get('callsign') or "").strip().upper()
            if mode_s_upper.startswith("0AD5B") or callsign_upper.startswith("ADSB"):
                return None

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
                # Prioridad 3: convertidor polar a metros (para CAT 01/48)
                if (x is None or y is None or not is_valid_coord(x, y)):
                    rho = data.get('rho_render') or data.get('raw_range')
                    theta = data.get('theta_render') or data.get('raw_azimuth')
                    if rho is not None and theta is not None:
                        # Si es menor a 1000, asumimos Millas Náuticas y convertimos a metros
                        rho_m = rho * 1852.0 if rho < 1000.0 else rho
                        theta_rad = math.radians(theta)
                        # Calcular cartesianas locales en metros respecto al origen del sensor
                        x2 = rho_m * math.sin(theta_rad)
                        y2 = rho_m * math.cos(theta_rad)
                        if is_valid_coord(x2, y2):
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

            # Determinar si debemos omitir el búfer de pendientes para una promoción instantánea (ADS-B, MLAT y System Tracks se muestran inmediatamente)
            plot_sac, plot_sic = 0, 0
            try:
                parts = sensor_id.split('/')
                plot_sac, plot_sic = int(parts[0]), int(parts[1])
            except (ValueError, IndexError):
                pass
            
            # Registrar el tiempo de actualización de este sensor
            if plot_time is not None:
                self.sensor_times[(plot_sac, plot_sic)] = plot_time
            sensor_info = self.sensor_info.get((plot_sac, plot_sic)) if hasattr(self, 'sensor_info') else None
            sensor_type = str(sensor_info.get('type', '')).upper() if sensor_info else ''
            is_async = (data.get('category') in (21, 62)) or (sensor_type == 'MLAT') or data.get('is_track', False)
            bypass_pending = is_async

            # 2. Correlación inteligente multi-sensor para evitar duplicados
            # Buscar si ya existe una pista activa para esta misma aeronave
            matched_track_id = None
            mode_s_addr = (data.get('mode_s') or "").strip().upper()

            # CAT62: System Track consolidado — omitir correlación A-E.
            # El track_number asignado por el SDP es la clave definitiva; no hay nada que correlacionar.
            _is_cat62 = data.get('category') == 62
            if _is_cat62:
                tn62 = data.get('track_number')
                if tn62 is None:
                    return None
                _cat62_id = f"TRK_{tn62}_{sensor_id}"
                if _cat62_id in self.tracks or _cat62_id in self.pending_tracks:
                    matched_track_id = _cat62_id
                else:
                    # El SDP reasigna TN para la misma aeronave (renumeración frecuente).
                    # Buscar por squawk+sensor+proximidad: si existe → actualizar esa pista
                    # en lugar de crear una nueva (garantiza 1 pista por aeronave por sensor).
                    sq62 = str(data.get('mode3a') or '----').strip()
                    if sq62 not in ('----', '0000'):
                        for _eid, _etrack in list(self.tracks.items()) + list(self.pending_tracks.items()):
                            if _etrack.category == 62 and _etrack.sac_sic == sensor_id:
                                _esq = str(_etrack.mode3a or '----').strip()
                                if _esq == sq62:
                                    _edx = _etrack.x - x
                                    _edy = _etrack.y - y
                                    if math.sqrt(_edx*_edx + _edy*_edy) < 9260.0:
                                        matched_track_id = _eid
                                        break
                    if not matched_track_id:
                        target_id = _cat62_id

            # A. Búsqueda por dirección Mode S (ICAO) - Máxima prioridad
            # Detectar si es una dirección Mode S de receptor genérico / mock (ej: 0AD5B1 o callsign ADSB)
            is_mock_mode_s = mode_s_addr.startswith("0AD5B") or (data.get('callsign') or "").strip().upper().startswith("ADSB")
            if not _is_cat62 and mode_s_addr and mode_s_addr != '----' and not is_mock_mode_s:
                for tid, track in list(self.tracks.items()) + list(self.pending_tracks.items()):
                    if not getattr(self, 'modo_integrado', True) and track.sac_sic != sensor_id:
                        continue
                    t_mode_s = (track.mode_s or "").strip().upper()
                    if t_mode_s == mode_s_addr:
                        matched_track_id = tid
                        break

            # B. Búsqueda por código Squawk (Mode 3/A) con ventana de distancia
            if not _is_cat62 and not matched_track_id:
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
                        if not getattr(self, 'modo_integrado', True) and track.sac_sic != sensor_id:
                            continue
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

            # C. Búsqueda por número de pista (prefiere track con identidad SSR/Mode-S sobre TRK_)
            if not _is_cat62 and not matched_track_id:
                track_num = data.get('track_number')
                if track_num is not None:
                    trk_fallback = None
                    for tid, track in list(self.tracks.items()) + list(self.pending_tracks.items()):
                        if not getattr(self, 'modo_integrado', True) and track.sac_sic != sensor_id:
                            continue
                        if track.track_number == track_num:
                            dx = track.x - x
                            dy = track.y - y
                            dist_m = math.sqrt(dx*dx + dy*dy)
                            if dist_m < 55560.0:  # 30 NM
                                if tid.startswith('TRK_'):
                                    if trk_fallback is None:
                                        trk_fallback = tid
                                else:
                                    matched_track_id = tid
                                    break
                    if not matched_track_id and trk_fallback:
                        matched_track_id = trk_fallback

            # D. Mismo sensor + mismas coordenadas polares → mismo eco físico (sin gate modo_integrado)
            if not _is_cat62 and not matched_track_id:
                curr_rho = data.get('rho_render') or data.get('raw_range')
                curr_theta = data.get('theta_render') or data.get('raw_azimuth')
                if curr_rho is not None and curr_theta is not None:
                    for tid, track in list(self.tracks.items()) + list(self.pending_tracks.items()):
                        if track.sac_sic != sensor_id:
                            continue
                        t_rho = track.raw_range
                        t_theta = track.raw_azimuth
                        if t_rho is None or t_theta is None:
                            continue
                        # Tolerancia: 0.15 NM en rango y 0.5° en azimut
                        if abs(curr_rho - t_rho) < 0.15 and abs(curr_theta - t_theta) < 0.5:
                            matched_track_id = tid
                            break

            # E. Búsqueda por proximidad cartesiana 3D (siempre disponible, no requiere lat/lon)
            if not _is_cat62 and not matched_track_id and getattr(self, 'modo_integrado', True):
                fl_curr = data.get('flight_level')
                alt_curr = data.get('altitude_ft')
                alt_curr_val = fl_curr * 100.0 if fl_curr is not None else alt_curr
                has_alt = alt_curr_val is not None
                # Sin altitud: 1 NM (estricto); con altitud: 3 NM + verificación vertical
                max_dist_m = (3.0 if has_alt else 1.0) * 1852.0
                t_plot = plot_time if plot_time is not None else data.get('time')
                best_dist_m = float('inf')
                best_tid = None
                for tid, track in list(self.tracks.items()) + list(self.pending_tracks.items()):
                    fl_t = track.flight_level
                    alt_t = track.altitude_ft
                    alt_t_val = fl_t * 100.0 if fl_t is not None else alt_t
                    if has_alt and alt_t_val is not None:
                        if abs(alt_curr_val - alt_t_val) >= 1500.0:
                            continue
                    # (b) Extrapolar la pista a la hora del plot antes de medir distancia,
                    # para no penalizar el desfase de barrido entre sensores.
                    tx, ty = self._extrapolar_xy(track, t_plot)
                    dx = tx - x
                    dy = ty - y
                    dist_m = math.sqrt(dx*dx + dy*dy)
                    if dist_m < max_dist_m and dist_m < best_dist_m:
                        best_dist_m = dist_m
                        best_tid = tid
                if best_tid:
                    matched_track_id = best_tid

            # 3. Establecer target_id final
            if matched_track_id:
                target_id = matched_track_id
                matched_track = self.tracks.get(target_id) or self.pending_tracks.get(target_id)
                if matched_track:
                    if sensor_id not in matched_track.reporting_sensors or len(matched_track.reporting_sensors) > 1:
                        is_async = True
                        bypass_pending = True
                    # Limpiar TRK_ huérfana del mismo sensor si es la misma aeronave (< 5 NM)
                    tn = data.get('track_number')
                    if tn is not None and not target_id.startswith('TRK_'):
                        trk_orphan = f"TRK_{tn}_{sensor_id}"
                        orphan = self.tracks.get(trk_orphan) or self.pending_tracks.get(trk_orphan)
                        if orphan is not None:
                            dx = orphan.x - x
                            dy = orphan.y - y
                            if math.sqrt(dx*dx + dy*dy) < 9260.0:  # 5 NM
                                self.tracks.pop(trk_orphan, None)
                                self.pending_tracks.pop(trk_orphan, None)
            elif data.get('category') == 62:
                # target_id ya fue asignado en el bloque CAT62 de arriba; solo forzar bypass
                is_async = True
                bypass_pending = True
            else:
                is_mock_mode_s = mode_s_addr.startswith("0AD5B") or (data.get('callsign') or "").strip().upper().startswith("ADSB")
                suffix = f"_{sensor_id}"
                if mode_s_addr and mode_s_addr != '----' and not is_mock_mode_s:
                    target_id = f"{mode_s_addr}"
                elif mode_s_addr and is_mock_mode_s:
                    target_id = f"{mode_s_addr}{suffix}"
                elif 'mode3a' in data and data['mode3a'] and data['mode3a'] != '----' and data['mode3a'] != '0000':
                    mode3a = data['mode3a']
                    tgt = f"{mode3a:04o}" if isinstance(mode3a, int) else str(mode3a).strip()
                    target_id = f"{tgt}{suffix}"
                elif data.get('track_number') is not None:
                    target_id = f"TRK_{data['track_number']}{suffix}"
                elif (data.get('id') or '').startswith('PSR_'):
                    target_id = data['id']
                else:
                    return None

            # 4. Correlación / Actualización del Diccionario de Pistas
            def update_track(track: RadarPlot):
                track.widget_ref = self
                prev_last_seen = track._last_seen  # guardar para EMA de _update_period
                track._last_seen = SimulationTime.time()  # resetear edad en cada actualización
                # 0. Actualizar el timestamp del track primero para que los filtros y el historial usen el tiempo correcto
                track.timestamp = data.get('time', track.timestamp)

                # 1. Adoptar la nueva posición física con suavizado alpha-beta.
                # Se aplica en AMBOS modos (Integrado y Crudo): la diferencia entre modos
                # es la fusión de identidad y los filtros, no el suavizado.
                if (len(track.reporting_sensors) > 1 or track.category == 62 or track.is_track):
                    if track.ab_filter is None:
                        from analysis.filters import AlphaBetaFilter
                        track.ab_filter = AlphaBetaFilter(track.x, track.y, alpha=0.3, beta=0.005)
                        track.ab_filter.last_update = track.timestamp
                    
                    smooth_x, smooth_y = track.ab_filter.update(x, y, current_time=track.timestamp)
                    track.x = smooth_x
                    track.y = smooth_y

                    # Velocidad suavizada derivada de la trayectoria suavizada (m/s en
                    # coords proyectadas). Alimenta el rumbo del vector de tendencia para
                    # que no oscile entre los track_angle dispares de cada radar.
                    prev_t = getattr(track, '_vel_prev_t', None)
                    if prev_t is not None:
                        dt_v = track.timestamp - prev_t
                        if 0.1 < dt_v < 30.0:
                            inst_vx = (track.x - track._vel_prev_x) / dt_v
                            inst_vy = (track.y - track._vel_prev_y) / dt_v
                            # Guarda de plausibilidad: un plot del siguiente sensor con
                            # offset de registración produce un salto que implica
                            # velocidades absurdas (>700 kt). Se descarta la muestra
                            # para no envenenar la velocidad suavizada ni el vector de
                            # tendencia (evita el artefacto "N740" y la mala extrapolación).
                            MAX_VEL_MPS = 700.0 * (METERS_PER_NM / 3600.0)  # ~360 m/s
                            if math.hypot(inst_vx, inst_vy) <= MAX_VEL_MPS:
                                if getattr(track, '_smooth_vx', None) is None:
                                    track._smooth_vx, track._smooth_vy = inst_vx, inst_vy
                                else:
                                    k = 0.25  # EMA: 25% medición nueva, 75% histórico
                                    track._smooth_vx = (1 - k) * track._smooth_vx + k * inst_vx
                                    track._smooth_vy = (1 - k) * track._smooth_vy + k * inst_vy
                    track._vel_prev_x = track.x
                    track._vel_prev_y = track.y
                    track._vel_prev_t = track.timestamp
                else:
                    track.x = x
                    track.y = y

                # 2. Ahora que las coordenadas están suavizadas, creamos el punto de historial
                plot_sac, plot_sic = 0, 0
                try:
                    parts = sensor_id.split('/')
                    plot_sac = int(parts[0])
                    plot_sic = int(parts[1])
                except (ValueError, IndexError):
                    pass

                hp = HistoryPoint(
                    x=track.x, y=track.y, cat=track.category,
                    tod=time_module.strftime("%H:%M:%S", time_module.gmtime(track.timestamp)),
                    squawk=track.mode3a,
                    fl=(f"FL{int(track.flight_level)}" if track.flight_level is not None else None),
                    rho=track.raw_range, theta=track.raw_azimuth,
                    lat=track.raw_dict.get('lat') or track.raw_dict.get('lat_render'),
                    lon=track.raw_dict.get('lon') or track.raw_dict.get('lon_render'),
                    timestamp=track.timestamp,
                    sac=plot_sac,  # Asignar SAC del sensor real que reportó este plot
                    sic=plot_sic,  # Asignar SIC del sensor real que reportó este plot
                    raw_x=x,
                    raw_y=y
                )
                # Evitar ráfagas o respuestas raw duplicadas en el historial durante el mismo barrido (PLL temporal)
                # Si el último punto de historial fue hace menos de 1.5 segundos, reemplazamos el último punto con
                # el nuevo para conservar únicamente la coordenada consolidada final y evitar estelas con grupos de puntos.
                # (A menos que estemos en modo crudo, en cuyo caso guardamos todo)
                hist_queue = self.history[target_id]
                
                # Si el tiempo retrocedió (ej. seek hacia atrás), podamos los puntos del "futuro"
                while hist_queue and hist_queue[-1].timestamp > track.timestamp:
                    hist_queue.pop()
                    
                if hist_queue and (0 <= track.timestamp - hist_queue[-1].timestamp < 1.5) and not getattr(self, 'modo_crudo', False):
                    hist_queue[-1] = hp
                else:
                    hist_queue.append(hp)
                
                # Evitar parpadeos de símbolos en fusión priorizando categorías de mayor calidad
                best_cat = track.category
                new_cat = data.get('category')
                if new_cat is not None:
                    if 62 in (best_cat, new_cat):
                        track.category = 62
                    elif 21 in (best_cat, new_cat):
                        track.category = 21
                    else:
                        track.category = new_cat
                else:
                    track.category = best_cat
                
                # Mantener el diccionario crudo de datos actualizado con los metadatos más recientes
                track.raw_dict = data
                
                # Actualizar campos individuales del track para mantener coherencia en las estelas e inspecciones
                track.raw_azimuth = raw_az
                track.raw_range = data.get('raw_range') or data.get('rho_render') or track.raw_range
                track.altitude_ft = data.get('altitude_ft', track.altitude_ft)
                track.bds_data = data.get('bds_data') or track.bds_data
                # CAT62: actualizar track_number si el SDP renumeró la pista
                if data.get('category') == 62 and data.get('track_number') is not None:
                    track.track_number = data.get('track_number')

                # Matriz de Detección: Si hay Garbling activo, ignorar cambios en Squawk (mode3a) y Flight Level,
                # manteniendo los del paquete anterior (Coast/extrapolación).
                if not track.garbled:
                    m3a = data.get('mode3a')
                    # Rechazar squawk inválido: 0 (int) ó "0000" son equivalentes a "sin transponder"
                    m3a_str = f"{m3a:04o}" if isinstance(m3a, int) else str(m3a).strip()
                    if m3a is not None and m3a not in ('', '----') and m3a_str != '0000':
                        track.mode3a = m3a
                    
                    try:
                        if data.get('flight_level') is not None:
                            new_fl = data.get('flight_level')
                            # Filtro de plausibilidad: rechazar saltos de FL físicamente imposibles.
                            if track.flight_level is not None:
                                dt_fl = track.timestamp - getattr(track, '_last_fl_time', track.timestamp)
                                max_fl_change = max(3.0, (6000.0 / 60.0 / 100.0) * max(dt_fl, 1.0))  # FL por segundo
                                fl_diff = abs(float(new_fl) - float(track.flight_level))
                                if fl_diff <= max_fl_change:
                                    track.flight_level = float(new_fl)
                                    track._last_fl_time = track.timestamp
                            else:
                                track.flight_level = float(new_fl)
                                track._last_fl_time = track.timestamp
                    except (ValueError, TypeError):
                        pass
                
                if data.get('callsign'):
                    track.callsign = data.get('callsign')
                
                try:
                    if data.get('ground_speed') is not None:
                        new_gs = data.get('ground_speed')
                        # Filtro de plausibilidad: rechazar saltos de velocidad físicamente imposibles.
                        if track.ground_speed is not None:
                            dt_gs = track.timestamp - getattr(track, '_last_gs_time', track.timestamp)
                            max_gs_change = max(5.0, 3.0 * max(dt_gs, 1.0))  # kt
                            gs_diff = abs(float(new_gs) - float(track.ground_speed))
                            if gs_diff <= max_gs_change:
                                track.ground_speed = float(new_gs)
                                track._last_gs_time = track.timestamp
                        else:
                            track.ground_speed = float(new_gs)
                            track._last_gs_time = track.timestamp
                except (ValueError, TypeError):
                    pass

                if data.get('track_angle') is not None:
                    try:
                        track.track_angle = float(data.get('track_angle'))
                    except (ValueError, TypeError):
                        pass
                if data.get('mode_s'):
                    track.mode_s = data.get('mode_s')
                if data.get('track_number') is not None:
                    track.track_number = data.get('track_number')

                track.garbled = data.get('garbled', False)
                track._update_count += 1  # Contador monotónico independiente del historial
                
                try:
                    # Evaluar DQF (Data Quality Filter)
                    track_age = SimulationTime.time() - track._first_seen
                    degradada, razon = self.quality_manager.evaluar_pista(
                        track.id,
                        {'garbled': track.garbled, 'update_count': track._update_count, 'age': track_age}
                    )
                    track.degradada = degradada
                    track.dqf_razon = razon
                    # Registrar (deduplicado) solo FRUIT y GARBLING; INMADURA es
                    # transitorio y no se loguea.
                    if razon == 'FRUIT':
                        self._log_quality_event(
                            (track.id, 'FRUIT'), 'FRUIT',
                            f"Track {track.id} | Edad:{track_age:.1f}s Updates:{track._update_count}")
                    elif razon == 'GARBLING':
                        self._log_quality_event(
                            (track.id, 'GARBLING'), 'GARBLING',
                            f"Track {track.id} | SSR garbled (CAT048 bit G)")
                except Exception:
                    pass
                
                track.reporting_sensors.add(sensor_id)

                # Actualizar período de actualización estimado (EMA) para CAT21 y CAT62
                if track.category in (21, 62) and plot_time is not None and prev_last_seen > 0:
                    tod_delta = plot_time - prev_last_seen
                    if tod_delta < 0:
                        tod_delta += 86400  # rollover medianoche
                    if 0.3 < tod_delta < 120.0:
                        track._update_period = track._update_period * 0.7 + tod_delta * 0.3

                track.illuminate()
                
                # --- JURISDICTION CHECK ---
                track_lat = data.get('latitude') or data.get('lat') or data.get('lat_render')
                track_lon = data.get('longitude') or data.get('lon') or data.get('lon_render')
                
                dist_nm = None
                if track_lat is not None and track_lon is not None and getattr(self, 'aeropuerto_lat', None) is not None and getattr(self, 'aeropuerto_lon', None) is not None:
                    try:
                        from analysis.stca_analyzer import STCA_Engine
                        dist_nm = STCA_Engine.haversine_nm(self.aeropuerto_lat, self.aeropuerto_lon, track_lat, track_lon)
                    except Exception:
                        pass
                if dist_nm is None:
                    dist_nm = math.sqrt(track.x**2 + track.y**2) / 1852.0
                
                fl_val = track.flight_level if track.flight_level is not None else 0.0
                radio = getattr(self, 'radio_incumbencia', 50.0)
                track.en_jurisdiccion = (dist_nm <= radio) and (fl_val <= getattr(self, 'techo_incumbencia', 95))
                data['en_jurisdiccion'] = track.en_jurisdiccion

            if bypass_pending:
                if target_id in self.pending_tracks:
                    self.tracks[target_id] = self.pending_tracks.pop(target_id)
                if target_id in self.tracks:
                    update_track(self.tracks[target_id])
                    return target_id
            else:
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
                    mode3a=_filter_mode3a(data.get('mode3a', '')),
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
                    raw_range=data.get('raw_range') or data.get('rho_render'),
                    bds_data=data.get('bds_data', {}),
                    raw_dict=data,
                    reporting_sensors={sensor_id}
                )
                plot.widget_ref = self
                plot.set_highlight_filter(self.squawk_filter)
                if bypass_pending:
                    self.tracks[target_id] = plot
                else:
                    self.pending_tracks[target_id] = plot
                update_track(plot)
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
        Convierte polares (CAT 48/01) a WGS-84 usando el cabezal del radar físico como centro.
        """
        # Si ya tiene WGS-84 (ADS-B CAT 21), no hacemos nada
        if plot.get('lat_render') is not None and plot.get('lon_render') is not None:
            return

        # Si tiene Polares (Radares CAT 48), calculamos su Lat/Lon absoluto
        rho = plot.get('rho_render')     # Distancia en MN
        theta = plot.get('theta_render') # Azimut en grados respecto al norte verdadero

        if rho is not None and theta is not None:
            # Obtener el sensor físico específico del plot para usar sus coordenadas correctas
            sac = plot.get('sac')
            sic = plot.get('sic')
            if sac is None or sic is None:
                sid = plot.get('sac_sic', '')
                if '/' in sid:
                    try:
                        sac, sic = map(int, sid.split('/'))
                    except ValueError:
                        pass

            sensor_pos = None
            if sac is not None and sic is not None:
                sensor_pos = self.sensor_info.get((sac, sic))

            if sensor_pos and sensor_pos.get('lat') and sensor_pos.get('lon'):
                radar_lat = sensor_pos['lat']
                radar_lon = sensor_pos['lon']
            else:
                # Fallback al centro actual de proyección
                radar_lat = getattr(self, 'centro_lat', -26.75055)
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
        # ya dibuja cada blanco con su símbolo y etiqueta. Agregar a plots_raw causaría
        # renderizado doble (o triple si BLINDAJE también está activo).
        self._process_plot_data(plot)
        self._reconciliar_pistas()
        self.evaluar_stca()
        if trigger_update:
            self.update()

    @pyqtSlot(list)
    def on_new_plot_batch(self, batch: List[Dict[str, Any]]):
        if not batch:
            return
        for data in batch:
            self._process_plot_data(data)
        self._reconciliar_pistas()
        self.evaluar_stca()
        self.update()

    # ================================================================
    # FUSIÓN MULTISENSOR: extrapolación cinemática y reconciliación de
    # pistas duplicadas (mismo avión visto por fuentes con identidad
    # disjunta: Mode S/ADS-B sin squawk vs. SSR con squawk sin Mode S).
    # ================================================================
    # Delegaciones al núcleo headless fusion.correlator.Correlator (Fase 1).
    def _velocidad_track(self, track) -> tuple:
        return self.correlator.velocidad(track)

    def _extrapolar_xy(self, track, t_target) -> tuple:
        return self.correlator.extrapolar(track, t_target)

    def _claves_identidad(self, t) -> list:
        return self.correlator.claves_identidad(t)

    def _son_misma_aeronave(self, a, b) -> bool:
        return self.correlator.son_misma_aeronave(a, b)

    def _reconciliar_pistas(self):
        """Fusiona pistas promovidas que son el mismo avión. Throttle ~0.3s
        para cerrar la ventana en que una pista recién promovida queda visible
        al STCA antes de fusionarse (re-disparo de alarma al perder/recuperar)."""
        if not getattr(self, 'modo_integrado', True):
            return
        ahora = SimulationTime.time()
        if ahora - getattr(self, '_last_reconcile', 0.0) < 0.3:
            return
        self._last_reconcile = ahora

        items = list(self.tracks.items())
        n = len(items)
        if n < 2:
            return
        fusionados = set()
        for i in range(n):
            tid_a, a = items[i]
            if tid_a in fusionados:
                continue
            for j in range(i + 1, n):
                tid_b, b = items[j]
                if tid_b in fusionados:
                    continue
                if not self._son_misma_aeronave(a, b):
                    continue
                # Ganador: más sensores, luego is_track (62/21), luego más historial.
                def rank(tid, t):
                    return (len(getattr(t, 'reporting_sensors', ())),
                            1 if t.is_track else 0,
                            len(self.history.get(tid, ())))
                if rank(tid_b, b) > rank(tid_a, a):
                    wid, win, lid, los = tid_b, b, tid_a, a
                else:
                    wid, win, lid, los = tid_a, a, tid_b, b
                self._fusionar_pistas(wid, win, lid, los)
                fusionados.add(lid)
                if lid == tid_a:
                    break  # a se fusionó; pasar al siguiente i

    def _fusionar_pistas(self, wid, win, lid, los):
        """Une identidad, sensores e historial de la pista perdedora en la ganadora
        y elimina la perdedora de tracks/pending/history/STCA."""
        try:
            win.reporting_sensors = set(getattr(win, 'reporting_sensors', set())) | \
                                    set(getattr(los, 'reporting_sensors', set()))
            if not (win.mode_s or "").strip() and (los.mode_s or "").strip():
                win.mode_s = los.mode_s
            def sq_valido(m):
                s = f"{m:04o}" if isinstance(m, int) else str(m or "").strip()
                return s and s not in ("----", "0000")
            if not sq_valido(win.mode3a) and sq_valido(los.mode3a):
                win.mode3a = los.mode3a
            # Registrar/refrescar la asociación de identidad aprendida (squawk<->Mode S)
            # para mantener la fusión estable ante separación por registración y
            # readquisición tras pérdida de pista.
            self.correlator.registrar_asociacion(win, los)
            if not (win.callsign or "").strip() and (los.callsign or "").strip():
                win.callsign = los.callsign
            if win.track_number is None and los.track_number is not None:
                win.track_number = los.track_number
            if los.bds_data:
                merged = dict(los.bds_data); merged.update(win.bds_data or {})
                win.bds_data = merged
            # Categoría de mayor calidad (62 > 21 > resto)
            if 62 in (win.category, los.category):
                win.category = 62
            elif 21 in (win.category, los.category):
                win.category = 21
            # Si la perdedora es más reciente, adoptar su posición/tiempo
            if (los.timestamp or 0.0) > (win.timestamp or 0.0):
                win.x, win.y = los.x, los.y
                win.timestamp = los.timestamp
                win._last_seen = max(getattr(win, '_last_seen', 0.0), getattr(los, '_last_seen', 0.0))
            # Fusionar historial conservando orden temporal
            hist_w = self.history.get(wid)
            hist_l = self.history.pop(lid, None)
            if hist_l:
                if hist_w is None:
                    hist_w = self.history[wid]
                combinado = sorted(list(hist_w) + list(hist_l), key=lambda hp: hp.timestamp)
                hist_w.clear()
                hist_w.extend(combinado[-hist_w.maxlen:] if hist_w.maxlen else combinado)
            # Eliminar la perdedora de todas las estructuras
            self.tracks.pop(lid, None)
            self.pending_tracks.pop(lid, None)
            vp = getattr(self, '_stca_vel_prev', None)
            if isinstance(vp, dict):
                vp.pop(lid, None)
        except Exception:
            pass

    def evaluar_stca(self):
        """
        Evalúa conflictos STCA con lógica de inhibición multisensor (Regla de Oro de la FASE 3).
        """
        if not hasattr(self, 'stca_engine') or not hasattr(self, 'stca_dialog'):
            return

        # Seguridad Operativa: Desactivar procesamiento si stca_habilitado es False
        if not getattr(self, 'stca_habilitado', True):
            self.tracks_en_alerta = set()
            self.conflictos_activos = []
            if hasattr(self, 'stca_dialog') and self.stca_dialog:
                self.stca_dialog.actualizar_alertas([])
            return

        # 1. LÓGICA DE INHIBICIÓN MULTISENSOR
        sensores_activos = set(t.sac_sic for t in self.tracks.values() if getattr(t, 'sac_sic', None))
        
        conflictos = []
        self.conflictos_activos = []
        
        # Evaluar solo si es Monosensor o si está activa la Fusión (Modo Integrado)
        if len(sensores_activos) <= 1 or getattr(self, 'modo_integrado', True):
            # Preparar pistas para STCA
            tracks_for_stca = {}
            for tid, track in self.tracks.items():
                if not track.is_alive():
                    continue
                # DQF / Multipath: Excluir pistas degradadas o reflejos fantasmas de la evaluación STCA
                if getattr(track, 'degradada', False) or getattr(track, 'is_reflection', False):
                    continue
                # PSR-only: sin identidad confiable → excluir del STCA
                if tid.startswith('PSR_'):
                    continue
                
                # Obtener coordenadas
                lat = track.raw_dict.get('lat_render') or track.raw_dict.get('lat') if track.raw_dict else None
                lon = track.raw_dict.get('lon_render') or track.raw_dict.get('lon') if track.raw_dict else None
                
                # Flight Level como string de dígito entero
                fl_str = ""
                if track.flight_level is not None:
                    try:
                        fl_str = str(int(float(track.flight_level)))
                    except Exception:
                        pass
                
                # CPA Kinematics: vx, vy calculation
                vx = vy = None
                if track.ground_speed is not None and track.track_angle is not None:
                    speed_mps = track.ground_speed * (METERS_PER_NM / 3600.0)
                    if 1.0 <= speed_mps <= 600.0:
                        angle_rad = math.radians(track.track_angle)
                        vx = speed_mps * math.sin(angle_rad)
                        vy = speed_mps * math.cos(angle_rad)
                
                # Si no se dispone de velocidad directa, estimar mediante regresión
                # lineal por mínimos cuadrados sobre la ventana de historial (A).
                # Promedia el ruido de N muestras en lugar de fiarse de 2 puntos,
                # reduciendo el jitter del CPA. Tras estimar, un gate de confianza
                # (D) descarta el vector para predicción si saltó respecto al tick
                # previo (maniobra/ruido): en ese caso el STCA solo evalúa VIOLATION.
                if vx is None or vy is None:
                    hist = self.history.get(tid)
                    if hist and len(hist) >= 2:
                        # Recolectar muestras (t, x, y) dentro de la ventana temporal
                        samples = [
                            (pt.timestamp, pt.x, pt.y)
                            for pt in hist
                            if 1.0 <= (track.timestamp - pt.timestamp) <= 25.0
                        ]
                        # Incluir el punto actual como muestra más reciente
                        samples.append((track.timestamp, track.x, track.y))

                        est_vx = est_vy = None
                        if len(samples) >= 3:
                            # Regresión lineal: pendiente temporal = componente de velocidad
                            n = len(samples)
                            t_mean = sum(s[0] for s in samples) / n
                            x_mean = sum(s[1] for s in samples) / n
                            y_mean = sum(s[2] for s in samples) / n
                            var_t = sum((s[0] - t_mean) ** 2 for s in samples)
                            if var_t > 1e-6:
                                est_vx = sum((s[0] - t_mean) * (s[1] - x_mean) for s in samples) / var_t
                                est_vy = sum((s[0] - t_mean) * (s[2] - y_mean) for s in samples) / var_t
                        elif len(samples) >= 2:
                            # Fallback de 2 puntos si la ventana es demasiado corta
                            (t0, x0, y0), (t1, x1, y1) = samples[0], samples[-1]
                            dt = t1 - t0
                            if dt >= 1.0:
                                est_vx = (x1 - x0) / dt
                                est_vy = (y1 - y0) / dt

                        # Validar que la velocidad estimada sea realista (5–600 m/s)
                        if est_vx is not None and est_vy is not None:
                            speed = math.sqrt(est_vx ** 2 + est_vy ** 2)
                            if 5.0 <= speed <= 600.0:
                                vx = est_vx
                                vy = est_vy

                        # --- Gate de confianza (D) ---
                        # Solo aplica al vector ESTIMADO. Si el rumbo cambió > 25°
                        # o la magnitud salió del rango 0.5x–2x respecto al tick
                        # anterior, el vector no es confiable para predicción:
                        # se descarta (vx,vy=None) y el STCA evaluará solo VIOLATION.
                        if vx is not None and vy is not None:
                            vel_prev_map = getattr(self, '_stca_vel_prev', None)
                            if vel_prev_map is None:
                                vel_prev_map = self._stca_vel_prev = {}
                            prev = vel_prev_map.get(tid)
                            if prev is not None:
                                pvx, pvy = prev
                                prev_mag = math.hypot(pvx, pvy)
                                cur_mag = math.hypot(vx, vy)
                                if prev_mag > 1e-3 and cur_mag > 1e-3:
                                    dot = max(-1.0, min(1.0, (pvx * vx + pvy * vy) / (prev_mag * cur_mag)))
                                    heading_change = math.degrees(math.acos(dot))
                                    mag_ratio = cur_mag / prev_mag
                                    if heading_change > 25.0 or mag_ratio < 0.5 or mag_ratio > 2.0:
                                        vx = vy = None  # inestable: no confiable para predicción
                            # Guardar para el próximo tick solo si quedó vector válido
                            if vx is not None and vy is not None:
                                vel_prev_map[tid] = (vx, vy)
                
                # Obtener velocidad en nudos (knots) para filtrar blancos estáticos (ruido/obstáculos MTR/transpondedores de calibración)
                speed_kt = track.ground_speed
                if speed_kt is None and vx is not None and vy is not None:
                    # Convertir m/s a nudos (1 m/s = 1.94384 knots)
                    speed_kt = math.sqrt(vx**2 + vy**2) * 1.94384

                m3a = track.mode3a
                m3a_str = f"{m3a:04o}" if isinstance(m3a, int) else str(m3a).strip()
                tracks_for_stca[tid] = {
                    'flight_level': fl_str,
                    'lat_render': lat,
                    'lon_render': lon,
                    'sac_sic': track.sac_sic,
                    'x': track.x,
                    'y': track.y,
                    'vx': vx,
                    'vy': vy,
                    'speed_kt': speed_kt,
                    'mode3a': m3a_str,
                    'mode_s': (track.mode_s or '').strip().upper(),
                }
            
            try:
                raw_conflictos = self.stca_engine.evaluar_conflictos(tracks_for_stca)
                
                # Convertir a etiquetas legibles (Callsigns) para el diálogo
                for t1_id, t2_id, estado, tiempo, dist_h, dist_v in raw_conflictos:
                    t1 = self.tracks.get(t1_id)
                    t2 = self.tracks.get(t2_id)
                    lbl1 = (t1.callsign or t1_id) if t1 else t1_id
                    lbl2 = (t2.callsign or t2_id) if t2 else t2_id
                    conflictos.append((lbl1, lbl2, estado, tiempo, dist_h, dist_v))
                    self.conflictos_activos.append((t1_id, t2_id, estado, tiempo))
                
                self.tracks_en_alerta = set(id for t1, t2, est, t, dh, dv in raw_conflictos for id in (t1, t2))
                
                # --- SISTEMA DE LOGS DE CONFLICTOS STCA ---
                current_active_keys = set()
                for t1_id, t2_id, estado, tiempo, dist_h, dist_v in raw_conflictos:
                    pair_key = tuple(sorted([t1_id, t2_id]))
                    current_active_keys.add(pair_key)
                    
                    t1 = self.tracks.get(t1_id)
                    t2 = self.tracks.get(t2_id)
                    lbl1 = (t1.callsign or t1_id) if t1 else t1_id
                    lbl2 = (t2.callsign or t2_id) if t2 else t2_id
                    
                    if pair_key not in self.logged_conflicts:
                        # Conflicto nuevo!
                        self.logged_conflicts[pair_key] = (estado, tiempo)
                        msg = f"NUEVO CONFLICTO detectado entre {lbl1} y {lbl2} - Estado: {estado}"
                        if estado == 'PREDICTION':
                            msg += f" (CPA estimado en {tiempo}s)"
                        self._log_stca_event(msg)
                    else:
                        prev_estado, prev_tiempo = self.logged_conflicts[pair_key]
                        # Escalación de predicción a violación
                        if prev_estado == 'PREDICTION' and estado == 'VIOLATION':
                            self.logged_conflicts[pair_key] = (estado, tiempo)
                            self._log_stca_event(f"ESCALACIÓN: Conflicto entre {lbl1} y {lbl2} evolucionó de PREDICCIÓN a VIOLACIÓN DE SEPARACIÓN")
                        # Actualización de tiempo CPA en predicción
                        elif estado == 'PREDICTION' and abs(prev_tiempo - tiempo) >= 10:
                            self.logged_conflicts[pair_key] = (estado, tiempo)
                            self._log_stca_event(f"ACTUALIZACIÓN: Conflicto predictivo entre {lbl1} y {lbl2} - CPA en {tiempo}s")

                # Detectar conflictos resueltos
                resolved_keys = set(self.logged_conflicts.keys()) - current_active_keys
                for pair_key in resolved_keys:
                    prev_estado, _ = self.logged_conflicts[pair_key]
                    t1_id, t2_id = pair_key
                    t1 = self.tracks.get(t1_id)
                    t2 = self.tracks.get(t2_id)
                    lbl1 = (t1.callsign or t1_id) if t1 else t1_id
                    lbl2 = (t2.callsign or t2_id) if t2 else t2_id
                    
                    self._log_stca_event(f"RESOLVIDO: Conflicto entre {lbl1} y {lbl2} finalizado (Separación segura restablecida)")
                    del self.logged_conflicts[pair_key]

            except Exception as e:
                print(f"[STCA] Error: {e}")
                self.tracks_en_alerta = set()
                self.conflictos_activos = []
        else:
            # Inhibición activa por multisensor sin modo integrado
            self.tracks_en_alerta = set()
            self.conflictos_activos = []

        # 2. Actualizar la UI flotante
        if hasattr(self, 'stca_dialog') and self.stca_dialog:
            self.stca_dialog.actualizar_alertas(conflictos)

    def _log_stca_event(self, message: str):
        """
        Registra eventos de alerta de separación STCA en un archivo de auditoría local.
        """
        try:
            import datetime
            log_path = "c:/documentos/decode_asterix/stca_conflicts.log"
            os.makedirs(os.path.dirname(log_path), exist_ok=True)
            timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(f"[{timestamp}] {message}\n")
        except Exception as e:
            print(f"[STCA LOG ERROR] {e}")

    def _log_quality_event(self, event_key, event_type: str, message: str):
        """
        Registra eventos de calidad (FRUIT / GARBLING / REFLEXION) en un archivo
        de auditoría, deduplicado: cada event_key se escribe una sola vez.
        """
        if event_key in self._logged_quality_events:
            return
        self._logged_quality_events.add(event_key)
        try:
            import datetime
            log_path = "c:/documentos/decode_asterix/quality_events.log"
            os.makedirs(os.path.dirname(log_path), exist_ok=True)
            timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(f"[{timestamp}] {event_type:<9} | {message}\n")
        except Exception as e:
            print(f"[QUALITY LOG ERROR] {e}")

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

    def recenter_to_fit_map(self):
        """Recentra la cámara (paneo y zoom) para ajustar perfectamente la extensión del mapa en pantalla."""
        if not self.map_has_data:
            self.pan_x, self.pan_y = 0.0, 0.0
            self.zoom_factor = 1.0
            self.update()
            return

        w, h = self.width(), self.height()
        if w <= 0 or h <= 0:
            return

        width_m = self.map_max_x - self.map_min_x
        height_m = self.map_max_y - self.map_min_y

        if width_m > 1e-3 and height_m > 1e-3:
            z_w = (w * 0.9) / width_m
            z_h = (h * 0.9) / height_m
            self.zoom_factor = min(z_w, z_h)
            self._clamp_zoom()

            z = self.zoom_factor
            center_m_x = (self.map_min_x + self.map_max_x) / 2.0
            center_m_y = (self.map_min_y + self.map_max_y) / 2.0

            self.pan_x = -center_m_x * z
            self.pan_y = center_m_y * z
            self.update()
            print(f"[RADAR VIEW] Vista adaptada: zoom={self.zoom_factor:.4f}, pan=({self.pan_x:.1f}, {self.pan_y:.1f})")

    def _load_radar_coverages(self):
        """Busca y procesa secuencialmente todas las coberturas *.map en la carpeta mapa/."""
        self.radar_coverages = []
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        map_dir = os.path.join(base_dir, "mapa")
        if not os.path.exists(map_dir):
            return

        def parse_coord_helper(coord_str: str) -> Optional[Tuple[float, float]]:
            m = re.match(r'^(\d{2})(\d{2})(\d{2}(?:\.\d+)?)([NS])(\d{3})(\d{2})(\d{2}(?:\.\d+)?)([EW])$', coord_str.strip())
            if not m:
                return None
            lat_deg, lat_min, lat_sec, lat_hem, lon_deg, lon_min, lon_sec, lon_hem = m.groups()
            lat = float(lat_deg) + float(lat_min) / 60.0 + float(lat_sec) / 3600.0
            if lat_hem == 'S': lat = -lat
            lon = float(lon_deg) + float(lon_min) / 60.0 + float(lon_sec) / 3600.0
            if lon_hem == 'W': lon = -lon
            return lat, lon

        try:
            for fname in os.listdir(map_dir):
                if fname.endswith(".map") and fname != "boundary.map":
                    fpath = os.path.join(map_dir, fname)
                    # Extraer el nombre corto (ej: CBA, PAR, PSP)
                    name_match = re.match(r'^\d*([A-Z_]+)_RADAR\.map$', fname)
                    short_name = name_match.group(1) if name_match else fname.replace(".map", "")
                    
                    with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                        lines = f.readlines()
                    
                    for line in lines:
                        line = line.strip()
                        if line.startswith("Circumference"):
                            parts = line.split()
                            if len(parts) >= 3:
                                coord_str = parts[1]
                                try:
                                    radius_nm = float(parts[2])
                                except ValueError:
                                    radius_nm = 200.0
                                    
                                res = parse_coord_helper(coord_str)
                                if res:
                                    lat, lon = res
                                    self.radar_coverages.append({
                                        'filename': fname,
                                        'short_name': short_name,
                                        'lat': lat,
                                        'lon': lon,
                                        'radius_nm': radius_nm
                                    })
                                    break  # Encontrada la cobertura, pasar al siguiente archivo
            print(f"[RADAR COVERAGES] Cargadas {len(self.radar_coverages)} coberturas de radar exitosamente.")
        except Exception as e:
            print(f"[RADAR COVERAGES] Error cargando coberturas: {e}")

    # ================================================================
    # TIMER
    # ================================================================

    def _on_timer(self):
        try:
            sim_time = SimulationTime.instance()
            if sim_time.is_frozen and self._is_playing:
                sim_time.unfreeze()
            sweep_active = self.sweep_visible and self.sweep_enabled and self._is_playing
            if sweep_active:
                sim_clock = sim_time.now()
                target_angle = (sim_clock * 6.0 * self.sweep_rpm) % 360.0
                
                # En caso de un salto grande (seek, pausa larga, etc.), sincronizar de inmediato
                playback_speed = getattr(self, 'playback_speed', 1.0)
                is_jump = False
                if not hasattr(self, '_last_sim_time') or self._last_sim_time is None:
                    is_jump = True
                else:
                    dt_sim = sim_clock - self._last_sim_time
                    if dt_sim < 0.0 or dt_sim > 5.0 * max(1.0, playback_speed):
                        is_jump = True
                self._last_sim_time = sim_clock
                
                prev_sweep = self.sweep_angle
                if is_jump:
                    self.sweep_angle = target_angle
                    prev_sweep = target_angle
                else:
                    self.sweep_angle = target_angle
                curr_sweep = self.sweep_angle
            else:
                self._last_sim_time = None

            if sweep_active:
                to_promote = []
                for pid, plot in self.pending_tracks.items():
                    sensor_info = self.sensor_info.get((plot.sac, plot.sic)) if hasattr(self, 'sensor_info') else None
                    sensor_type = str(sensor_info.get('type', '')).upper() if sensor_info else ''
                    is_async = (plot.category in (21, 62)) or (sensor_type == 'MLAT') or plot.is_track or (len(getattr(plot, 'reporting_sensors', [])) > 1)
                    
                    if is_async:
                        to_promote.append(pid)
                        continue
                        
                    if plot.raw_azimuth is not None:
                        az = plot.raw_azimuth
                        
                        # Comprobar robustamente si la línea de barrido cruzó por el acimut del blanco
                        # Considera tanto el paso directo por el sector del incremento como la ventana de SWEEP_TOLERANCE
                        crossed = False
                        if curr_sweep >= prev_sweep:
                            crossed = (prev_sweep - SWEEP_TOLERANCE <= az <= curr_sweep + SWEEP_TOLERANCE)
                        else:
                            # Cruce del norte (wraparound)
                            crossed = (az >= prev_sweep - SWEEP_TOLERANCE or az <= curr_sweep + SWEEP_TOLERANCE)
                            
                        if crossed:
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

            # ---- PROCESAMIENTO PESADO TEMPORIZADO (Poda, MTR y Telemetría) ----
            # Ejecutar solo una vez cada 1.0 segundo (20 ticks a 50ms de intervalo)
            self._timer_tick_count = getattr(self, '_timer_tick_count', 0) + 1
            if self._timer_tick_count >= 20:
                self._timer_tick_count = 0

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

                # 3. DETECTOR DE REFLEXIONES MTR (Heavy $O(N^2)$ calculations)
                tracks_by_sqk = defaultdict(list)
                for track in list(self.tracks.values()) + list(self.pending_tracks.values()):
                    track.is_reflection = False
                    track.linked_real_id = None
                    track.has_reflection = False
                    
                    sq = track.mode3a
                    sq_str = f"{sq:04o}" if isinstance(sq, int) else str(sq).strip()
                    if sq_str and sq_str not in ("", "----", "0000", "1200", "2000", "7000"):
                        tracks_by_sqk[sq_str].append(track)
                        
                for sq_str, group in tracks_by_sqk.items():
                    if len(group) >= 2:
                        group.sort(key=lambda t: t.raw_range if t.raw_range is not None else 0.0)
                        real_track = group[0]
                        real_track.has_reflection = True
                        for ghost in group[1:]:
                            ghost.is_reflection = True
                            ghost.linked_real_id = real_track.id
                            
                            d_OA = real_track.raw_range
                            d_F = ghost.raw_range
                            az_real = real_track.raw_azimuth
                            az_ghost = ghost.raw_azimuth
                            if d_OA is not None and d_F is not None and az_real is not None and az_ghost is not None:
                                try:
                                    alpha_rad = math.radians(abs(az_real - az_ghost))
                                    denominator = 2.0 * (d_F - d_OA * math.cos(alpha_rad))
                                    if denominator != 0:
                                        d_ref = (d_F**2 - d_OA**2) / denominator
                                        if 0.1 <= d_ref <= 30.0:
                                            # Búsqueda de coincidencia/agrupación espacial
                                            matched_key = None
                                            for k, ref in self.detected_reflectors.items():
                                                if abs(ref['range_nm'] - d_ref) < 1.5 and abs(ref['azimuth'] - az_ghost) < 5.0:
                                                    matched_key = k
                                                    break
                                            
                                            current_tod = getattr(self, '_last_tod', 0.0)
                                            if matched_key:
                                                ref = self.detected_reflectors[matched_key]
                                                ref['hits'] += 1
                                                ref['azimuth'] = (ref['azimuth'] * 4.0 + az_ghost) / 5.0
                                                ref['range_nm'] = (ref['range_nm'] * 4.0 + d_ref) / 5.0
                                                ref['last_seen_tod'] = current_tod
                                                ref['ghost_sq'] = sq_str
                                                ref['real_id'] = real_track.id
                                                # Registrar (deduplicado) al confirmar el reflector
                                                if ref['hits'] >= 4:
                                                    self._log_quality_event(
                                                        ('REFLEX', matched_key), 'REFLEXION',
                                                        f"Ghost {sq_str} (id {ghost.id}) ← Real {real_track.id} | "
                                                        f"Reflector R:{ref['range_nm']:.1f}NM Az:{ref['azimuth']:.0f}° ({ref['hits']}H)")
                                            else:
                                                key = (int(az_ghost * 2), int(d_ref * 10))
                                                self.detected_reflectors[key] = {
                                                    'hits': 1,
                                                    'azimuth': az_ghost,
                                                    'range_nm': d_ref,
                                                    'last_seen_tod': current_tod,
                                                    'ghost_sq': sq_str,
                                                    'real_id': real_track.id,
                                                }
                                except Exception:
                                    pass

                # 3b. Envejecimiento de reflectores (MTR timeout)
                if hasattr(self, 'detected_reflectors') and self.detected_reflectors:
                    current_tod = getattr(self, '_last_tod', 0.0)
                    expired = [
                        k for k, r in self.detected_reflectors.items()
                        if current_tod - r.get('last_seen_tod', 0.0) > 45.0
                    ]
                    for k in expired:
                        del self.detected_reflectors[k]
                        # Permitir re-loguear el reflector si reaparece tras expirar
                        self._logged_quality_events.discard(('REFLEX', k))

                # 4. FASE 4: Contar plots vivos por categoría y emitir señal de telemetría
                counts = {1: 0, 21: 0, 48: 0, 62: 0}
                for plot in self.tracks.values():
                    if plot.is_alive() and plot.category in counts:
                        if self.plot_filter_fn and not self.plot_filter_fn(plot):
                            continue
                        counts[plot.category] += 1
                self.category_counts_updated.emit(counts)

                # 5. Re-evaluar STCA localmente en el timer
                self.evaluar_stca()

            self.plot_count = len(self.tracks) + len(self.pending_tracks)
            self.update()
        except Exception:
            pass

    def _draw_video_maps(self, painter: QPainter, inv_z: float, tipo: str):
        if not hasattr(self, 'map_manager'):
            return
            
        visibles = self.map_manager.get_visible_layers(tipo)
        if not visibles:
            return
            
        try:
            painter.setBrush(QBrush(Qt.BrushStyle.NoBrush))
            
            for layer in visibles:
                # Estilos visuales: TACTICO usa el color guardado por el usuario; ESTRUCTURAL usa colores semánticos fijos
                alpha_base = 255 if tipo == "TACTICO" else 150
                
                if tipo == "TACTICO":
                    # Color dinámico guardado en la capa
                    layer_color = QColor(getattr(layer, 'color', '#00E5FF'))
                    layer_color.setAlpha(alpha_base)
                    
                    # A. Fronteras / geometría principal → color del usuario
                    pen_borders = QPen(layer_color)
                    pen_borders.setWidthF(max(1.5, inv_z * 1.5))
                    painter.setPen(pen_borders)
                    painter.drawPath(layer.path_borders)
                    
                    # B. Aerovías → mismo color, línea discontinua
                    pen_airways = QPen(layer_color)
                    pen_airways.setWidthF(max(1.2, inv_z * 1.5))
                    pen_airways.setStyle(Qt.PenStyle.DashLine)
                    painter.setPen(pen_airways)
                    painter.drawPath(layer.path_airways)
                    
                    # C. Pistas → mismo color
                    pen_runways = QPen(layer_color)
                    pen_runways.setWidthF(max(1.8, inv_z * 1.8))
                    painter.setPen(pen_runways)
                    painter.drawPath(layer.path_runways)
                    
                    # D. Otros → mismo color
                    pen_other = QPen(layer_color)
                    pen_other.setWidthF(max(1.0, inv_z * 1.2))
                    painter.setPen(pen_other)
                    painter.drawPath(layer.path_other)
                    
                    # E. Símbolos
                    if layer.map_symbols:
                        painter.save()
                        pen_symbol = QPen(layer_color)
                        pen_symbol.setWidthF(max(1.0, inv_z * 1.0))
                        painter.setPen(pen_symbol)
                        sz = 4.0 * inv_z
                        for px, py, text in layer.map_symbols:
                            painter.drawPolygon([
                                QPointF(px, py + sz),
                                QPointF(px - sz, py - sz),
                                QPointF(px + sz, py - sz),
                            ])
                        painter.restore()
                        
                    # F. Textos
                    if layer.map_labels or layer.map_symbols:
                        font = painter.font()
                        font.setPointSizeF(7.5)
                        font.setBold(True)
                        pen_text = QPen(layer_color)
                        
                        for px, py, text in (layer.map_labels + layer.map_symbols):
                            if text:
                                painter.save()
                                painter.translate(px, py)
                                painter.scale(inv_z, -inv_z)
                                painter.setFont(font)
                                fm = QFontMetrics(font)
                                tw = fm.horizontalAdvance(text)
                                th = fm.height()
                                tx = 7
                                ty = th / 2 - 2
                                
                                painter.setPen(Qt.PenStyle.NoPen)
                                painter.setBrush(QBrush(QColor(0, 0, 0, min(180, alpha_base))))
                                painter.drawRect(QRectF(tx - 2, ty - fm.ascent() - 1, tw + 4, th + 2))
                                
                                painter.setPen(pen_text)
                                painter.drawText(QPointF(tx, ty), text)
                                painter.restore()
                else:
                    # ESTRUCTURAL: colores semánticos fijos (cartografía base)
                    # A. Fronteras
                    pen_borders = QPen(QColor(0, 229, 255, alpha_base))
                    pen_borders.setWidthF(max(1.0, inv_z * 1.2))
                    painter.setPen(pen_borders)
                    painter.drawPath(layer.path_borders)
                    
                    # B. Aerovías
                    pen_airways = QPen(QColor(0, 180, 255, alpha_base))
                    pen_airways.setWidthF(max(1.2, inv_z * 1.5))
                    pen_airways.setStyle(Qt.PenStyle.DashLine)
                    painter.setPen(pen_airways)
                    painter.drawPath(layer.path_airways)
                    
                    # C. Pistas
                    pen_runways = QPen(QColor(57, 255, 20, alpha_base)) # Neon green
                    pen_runways.setWidthF(max(1.8, inv_z * 1.8))
                    painter.setPen(pen_runways)
                    painter.drawPath(layer.path_runways)
                    
                    # D. Otros
                    pen_other = QPen(QColor(52, 73, 94, min(100, alpha_base)))
                    pen_other.setWidthF(max(0.4, inv_z * 0.5))
                    painter.setPen(pen_other)
                    painter.drawPath(layer.path_other)
                    
                    # E. Símbolos
                    if layer.map_symbols:
                        painter.save()
                        pen_symbol = QPen(QColor(0, 229, 255, alpha_base))
                        pen_symbol.setWidthF(max(1.0, inv_z * 1.0))
                        painter.setPen(pen_symbol)
                        sz = 4.0 * inv_z
                        for px, py, text in layer.map_symbols:
                            painter.drawPolygon([
                                QPointF(px, py + sz),
                                QPointF(px - sz, py - sz),
                                QPointF(px + sz, py - sz),
                            ])
                        painter.restore()
                        
                    # F. Textos
                    if layer.map_labels or layer.map_symbols:
                        font = painter.font()
                        font.setPointSizeF(7.5)
                        font.setBold(True)
                        pen_text = QPen(QColor(0, 229, 255, alpha_base))
                        
                        for px, py, text in (layer.map_labels + layer.map_symbols):
                            if text:
                                painter.save()
                                painter.translate(px, py)
                                painter.scale(inv_z, -inv_z)
                                painter.setFont(font)
                                fm = QFontMetrics(font)
                                tw = fm.horizontalAdvance(text)
                                th = fm.height()
                                tx = 7
                                ty = th / 2 - 2
                                
                                # Fondo del texto oscuro
                                painter.setPen(Qt.PenStyle.NoPen)
                                painter.setBrush(QBrush(QColor(0, 0, 0, min(180, alpha_base))))
                                painter.drawRect(QRectF(tx - 2, ty - fm.ascent() - 1, tw + 4, th + 2))
                                
                                painter.setPen(pen_text)
                                painter.drawText(QPointF(tx, ty), text)
                                painter.restore()
        except Exception as e:
            print(f"[RadarWidget] Error renderizando mapa de video {tipo}: {e}")

    # ================================================================
    # PAINT EVENT
    # ================================================================

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        try:
            self.label_hitboxes.clear()
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

            # ---- 1. MAPA ESTRUCTURAL (FONDO) ----
            self._draw_video_maps(painter, inv_z, "ESTRUCTURAL")

            # ---- 1.5. COBERTURAS DE RADAR (Fase 16) — oculto en vista controlador ----
            if (not self.vista_controlador) and getattr(self, 'radar_coverages', None) and self.projection_set and self.proy.activo:
                try:
                    for cov in self.radar_coverages:
                        lat = cov['lat']
                        lon = cov['lon']
                        radius_nm = cov['radius_nm']
                        short_name = cov['short_name']
                        
                        cx, cy = self.proy.latlon_to_xy(lat, lon)
                        if not is_valid_coord(cx, cy):
                            continue
                            
                        # Si está en el origen (es el active projection center)
                        is_active = (cx * cx + cy * cy) < 1000.0 * 1000.0
                        
                        if is_active:
                            # Highlighted active radar coverage
                            pen_active = QPen(QColor(0, 229, 255, 100))
                            pen_active.setWidthF(inv_z * 1.2)
                            pen_active.setStyle(Qt.PenStyle.DashLine)
                            painter.setPen(pen_active)
                            painter.setBrush(QBrush(QColor(0, 229, 255, 8))) # opacidad 3%
                            
                            r = radius_nm * METERS_PER_NM
                            painter.drawEllipse(QPointF(cx, cy), r, r)
                            
                            # Centro del radar activo
                            pen_center = QPen(QColor(0, 229, 255, 200))
                            pen_center.setWidthF(inv_z * 1.5)
                            painter.setPen(pen_center)
                            painter.setBrush(QBrush(QColor(0, 229, 255, 120)))
                            painter.drawEllipse(QPointF(cx, cy), inv_z * 4.0, inv_z * 4.0)
                            
                            # Etiqueta
                            painter.setFont(QFont("Monospace", 8))
                            painter.setPen(QColor(0, 229, 255, 220))
                            painter.save()
                            painter.translate(cx, cy)
                            painter.scale(inv_z, -inv_z)
                            painter.drawText(QPointF(6, 12), f"{short_name} (ACTIVE)")
                            painter.restore()
                        else:
                            # Subtle background radar coverage
                            pen_bg = QPen(QColor(0, 229, 255, 22)) # opacidad muy sutil
                            pen_bg.setWidthF(inv_z * 0.8)
                            pen_bg.setStyle(Qt.PenStyle.DotLine)
                            painter.setPen(pen_bg)
                            painter.setBrush(QBrush(Qt.BrushStyle.NoBrush))
                            
                            r = radius_nm * METERS_PER_NM
                            painter.drawEllipse(QPointF(cx, cy), r, r)
                            
                            # Centro del radar secundario
                            pen_center = QPen(QColor(0, 229, 255, 45))
                            pen_center.setWidthF(inv_z * 0.8)
                            painter.setPen(pen_center)
                            painter.setBrush(QBrush(Qt.BrushStyle.NoBrush))
                            painter.drawEllipse(QPointF(cx, cy), inv_z * 2.5, inv_z * 2.5)
                            
                            # Etiqueta
                            painter.setFont(QFont("Monospace", 8))
                            painter.setPen(QColor(0, 229, 255, 40))
                            painter.save()
                            painter.translate(cx, cy)
                            painter.scale(inv_z, -inv_z)
                            painter.drawText(QPointF(6, 12), short_name)
                            painter.restore()
                except Exception:
                    pass

            # ---- 2. ANILLOS DE RANGO (sensor-céntricos) — ocultos en vista controlador ----
            if not self.vista_controlador:
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

            # ---- 2.b ANILLO DE ÁREA DE CONTROL (controlador o toggle de incumbencia) ----
            if (self.vista_controlador or getattr(self, 'mostrar_incumbencia', False)) \
                    and self.projection_set and self.proy.activo \
                    and getattr(self, 'aeropuerto_lat', None) is not None \
                    and getattr(self, 'aeropuerto_lon', None) is not None:
                try:
                    acx, acy = self.proy.latlon_to_xy(self.aeropuerto_lat, self.aeropuerto_lon)
                    if is_valid_coord(acx, acy):
                        r_ctrl = float(getattr(self, 'radio_incumbencia', 50.0)) * METERS_PER_NM
                        pen_ctrl = QPen(QColor(0, 229, 255, 180))
                        pen_ctrl.setWidthF(inv_z * 1.5)
                        painter.setPen(pen_ctrl)
                        painter.setBrush(QBrush(QColor(0, 229, 255, 10)))
                        painter.drawEllipse(QPointF(acx, acy), r_ctrl, r_ctrl)
                        # Etiqueta del área
                        painter.save()
                        painter.translate(acx, acy + r_ctrl)
                        painter.scale(inv_z, -inv_z)
                        painter.setPen(QColor(0, 229, 255, 210))
                        painter.setFont(QFont("Monospace", 8, QFont.Weight.Bold))
                        painter.drawText(QPointF(4, -4), f"ÁREA DE CONTROL ({int(self.radio_incumbencia)} NM)")
                        painter.restore()
                except Exception:
                    pass

            # ---- 2.5. CONO DE SILENCIO DINÁMICO (oculto en vista controlador) ----
            if (not self.vista_controlador) and getattr(self, 'show_silence_cone', True):
                try:
                    # Determinar altitud de referencia: seleccionada o FL300
                    selected_fl = 300.0
                    if getattr(self, 'selected_history_point', None) is not None:
                        _, sel_hp, _ = self.selected_history_point
                        if sel_hp.fl and sel_hp.fl.startswith("FL"):
                            try:
                                selected_fl = float(sel_hp.fl[2:])
                            except ValueError:
                                pass
                    elif self.tracks:
                        # Si hay pistas, podemos tomar el FL máximo activo como referencia dinámica
                        fls = [t.flight_level for t in self.tracks.values() if t.flight_level is not None]
                        if fls:
                            selected_fl = max(fls)
                            
                    # R_silence = Altitud_pies / tan(36°)
                    # Calibración operativa real: Aunque el haz de las antenas LVA teóricamente llega a 45°,
                    # en condiciones operativas reales y grabaciones de tráfico monopulso (MSSR), el límite de
                    # atenuación o STC provoca la pérdida del blanco a una elevación práctica de 36°.
                    # tan(36°) ≈ 0.7265425
                    # Radio en metros = (FL * 100 * 0.3048) / tan(36°)
                    alt_ft = selected_fl * 100.0
                    r_silence_m = (alt_ft * 0.3048) / 0.726542528
                    
                    painter.save()
                    pen_silence = QPen(QColor(255, 51, 102, 60))  # Rojo/rosa suave translúcido
                    pen_silence.setWidthF(safe_divide(1.5, z, 0.5))
                    pen_silence.setStyle(Qt.PenStyle.DashDotLine)
                    painter.setPen(pen_silence)
                    painter.setBrush(QBrush(QColor(255, 51, 102, 12)))  # Relleno muy suave
                    painter.drawEllipse(QPointF(0.0, 0.0), r_silence_m, r_silence_m)
                    
                    # Dibujar etiqueta de texto al borde del cono
                    painter.translate(r_silence_m * 0.7071, -r_silence_m * 0.7071)
                    painter.scale(inv_z, -inv_z)
                    painter.setPen(QColor(255, 51, 102, 140))
                    painter.setFont(QFont("Monospace", 8, QFont.Weight.Bold))
                    painter.drawText(QPointF(5, 5), f"CONO SILENCIO (FL{int(selected_fl)} @ 36° MSSR: {r_silence_m / 1852.0:.1f} NM)")
                    painter.restore()
                except Exception:
                    pass

            # ---- 3. BARRIDO (oculto en vista controlador) ----
            if (not self.vista_controlador) and self.sweep_visible and self.sweep_enabled:
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

            # ---- 4. SENSOR CENTRAL (símbolo de radar — oculto en vista controlador) ----
            if self.projection_set and not self.vista_controlador:
                try:
                    painter.save()
                    # Dibujar un símbolo tipo 'Y' para representar el origen del radar
                    pen_y = QPen(COLOR_ACCENT_GREEN, safe_divide(3.0, z, 1.0))
                    pen_y.setCapStyle(Qt.PenCapStyle.RoundCap)
                    painter.setPen(pen_y)
                    s_size = safe_divide(12.0, z, 1.0)
                    
                    # Segmento vertical inferior
                    painter.drawLine(QPointF(0, 0), QPointF(0, -s_size))
                    # Segmento superior izquierdo (a 120 grados de separación)
                    painter.drawLine(QPointF(0, 0), QPointF(-s_size * 0.866, s_size * 0.5))
                    # Segmento superior derecho (a 120 grados de separación)
                    painter.drawLine(QPointF(0, 0), QPointF(s_size * 0.866, s_size * 0.5))
                    
                    painter.restore()
                except Exception:
                    try:
                        painter.restore()
                    except Exception:
                        pass

            # ---- 5. DIBUJO DE PLOTS ----
            font_sq = QFont("Monospace", 9)

            # --- FASE 1: HISTORIAL (ESTELA DE PUNTOS MEJORADA) ---
            if getattr(self, 'history_visible', True) and self.history_limit > 0:
                for track_id, history_points in list(self.history.items()):
                    plot = self.tracks.get(track_id) or self.pending_tracks.get(track_id)
                    if not plot or not plot.is_alive():
                        continue

                    # Filtro de datos personalizado
                    if self.plot_filter_fn and not self.plot_filter_fn(plot):
                        continue

                    # Filtro de sensores múltiples para historial
                    if plot.category != 62:
                        sensor_id = getattr(plot, 'sac_sic', f"UNK_CAT{plot.category}")
                        visibles = getattr(self, 'sensores_visibles', None)
                        if visibles is not None and sensor_id not in visibles:
                            continue

                    try:
                        rpm = self.sensor_rpms.get((plot.sac, plot.sic), self.sweep_rpm)
                        scan_time = 60.0 / rpm if rpm > 0 else 5.0
                        max_age = 3.2 * scan_time
                        alpha = plot.get_alpha(max_age)
                        if alpha <= 0:
                            continue

                        # Determinar color base según tipo de blanco (igual que cabeza)
                        sensor_info_h = self.sensor_info.get((plot.sac, plot.sic))
                        sensor_type_h = str(sensor_info_h.get('type', '')).upper() if sensor_info_h else ''
                        if getattr(plot, 'degradada', False):
                            _dqf_r = getattr(plot, 'dqf_razon', '')
                            if _dqf_r == 'GARBLING':
                                trail_base = QColor("#FF00FF")
                            elif _dqf_r == 'FRUIT':
                                trail_base = QColor("#FFA500")
                            elif _dqf_r == 'PISTA INMADURA':
                                trail_base = QColor("#FFD700")
                            else:
                                trail_base = QColor("#FFA500")
                        else:
                            trail_base = COLOR_GREEN_NEON

                        limit = self.history_limit
                        points_to_draw = list(history_points)[-limit:]
                        n_pts = len(points_to_draw)
                        if n_pts == 0:
                            continue
                        
                        pts_reversed = list(reversed(points_to_draw))

                        if self.history_mode == "Tracking":
                            # Modo Tracking: líneas conectoras por segmento para coloreado por radar y fade suave
                            if n_pts >= 2:
                                painter.setBrush(Qt.BrushStyle.NoBrush)
                                for i in range(n_pts - 1):
                                    pt1 = points_to_draw[i]
                                    pt2 = points_to_draw[i+1]
                                    if not is_valid_coord(pt1.x, pt1.y) or not is_valid_coord(pt2.x, pt2.y):
                                        continue
                                    # Evitar dibujar líneas conectoras al origen (0,0) que ensucian la pantalla táctica
                                    if (abs(pt1.x) < 1.0 and abs(pt1.y) < 1.0) or (abs(pt2.x) < 1.0 and abs(pt2.y) < 1.0):
                                        continue
                                    if getattr(plot, 'degradada', False):
                                        _dqf_r = getattr(plot, 'dqf_razon', '')
                                        if _dqf_r == 'GARBLING':
                                            segment_color = QColor("#FF00FF")
                                        elif _dqf_r == 'FRUIT':
                                            segment_color = QColor("#FFA500")
                                        elif _dqf_r == 'PISTA INMADURA':
                                            segment_color = QColor("#FFD700")
                                        else:
                                            segment_color = QColor("#FFA500")
                                    else:
                                        segment_color = trail_base
                                    
                                    # Fade de opacidad (más reciente = más opaco)
                                    t = (n_pts - 1 - i) / max(1, n_pts - 1)
                                    seg_alpha = int(alpha * max(0.20, (1.0 - t * 0.80)))
                                    color_seg = QColor(segment_color)
                                    color_seg.setAlpha(seg_alpha)
                                    
                                    pen_track = QPen(color_seg, safe_divide(2.0, z, 0.5))
                                    painter.setPen(pen_track)
                                    painter.drawLine(QPointF(pt1.x, pt1.y), QPointF(pt2.x, pt2.y))
                        else:
                            # Modo Historic: solo puntos individuales con fade y color por radar
                            dot_max_size = safe_divide(3.5, z, 0.6)
                            dot_min_size = safe_divide(1.2, z, 0.2)
                            for i, h_point in enumerate(pts_reversed):
                                hx, hy = h_point.x, h_point.y
                                if not is_valid_coord(hx, hy):
                                    continue
                                # Evitar dibujar puntos de historial en el origen (0,0) que ensucian la pantalla táctica
                                if abs(hx) < 1.0 and abs(hy) < 1.0:
                                    continue
                                t = i / max(1, n_pts - 1)
                                dot_alpha = int(alpha * max(0.10, (1.0 - t * 0.85)))
                                dot_size = dot_max_size * (1.0 - t * 0.65) + dot_min_size * t
                                
                                if getattr(plot, 'degradada', False):
                                    _dqf_r = getattr(plot, 'dqf_razon', '')
                                    if _dqf_r == 'GARBLING':
                                        pt_color = QColor("#FF00FF")
                                    elif _dqf_r == 'FRUIT':
                                        pt_color = QColor("#FFA500")
                                    elif _dqf_r == 'PISTA INMADURA':
                                        pt_color = QColor("#FFD700")
                                    else:
                                        pt_color = QColor("#FFA500")
                                else:
                                    pt_color = trail_base
                                
                                dot_color = QColor(pt_color)
                                dot_color.setAlpha(dot_alpha)
                                painter.setPen(Qt.PenStyle.NoPen)
                                painter.setBrush(dot_color)
                                painter.drawEllipse(QPointF(hx, hy), dot_size, dot_size)

                        # Dibujar los plots individuales crudos que componen la track en Modo Integrado
                        if getattr(self, 'modo_integrado', True) and n_pts > 0:
                            for idx, pt in enumerate(points_to_draw):
                                if pt.raw_x is not None and pt.raw_y is not None and is_valid_coord(pt.raw_x, pt.raw_y):
                                    if pt.sac is not None and pt.sic is not None:
                                        sensor_id_pt = f"{pt.sac}/{pt.sic}"
                                        visibles = getattr(self, 'sensores_visibles', None)
                                        if visibles is not None and sensor_id_pt not in visibles:
                                            continue
                                        raw_color = self._get_sensor_color(pt.sac, pt.sic)
                                    else:
                                        raw_color = trail_base
                                    
                                    # Fade de opacidad (más reciente = más brillante)
                                    t_idx = (n_pts - 1 - idx) / max(1, n_pts - 1)
                                    pt_alpha = int(alpha * max(0.20, (1.0 - t_idx * 0.75)))
                                    color = QColor(raw_color)
                                    color.setAlpha(pt_alpha)
                                    
                                    # Dibujar una pequeña cruz '+' fina en la coordenada cruda original
                                    pen_raw = QPen(color, safe_divide(1.5, z, 0.4))
                                    painter.setPen(pen_raw)
                                    r_size = safe_divide(3.0, z, 0.5)
                                    painter.drawLine(QPointF(pt.raw_x - r_size, pt.raw_y), QPointF(pt.raw_x + r_size, pt.raw_y))
                                    painter.drawLine(QPointF(pt.raw_x, pt.raw_y - r_size), QPointF(pt.raw_x, pt.raw_y + r_size))
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

            # FASE 1 (Opacidad Heredada): Resetear opacidad y brush antes de dibujar plots vivos
            # para evitar que la transparencia/relleno del historial o sensor central
            # afecte a los plots activos.
            painter.setOpacity(1.0)
            painter.setBrush(QBrush(Qt.BrushStyle.NoBrush))  # RESET DEFENSIVO: evitar brush leak

            # --- FASE 2: CABEZAS DE TRACK ---
            alertas_dict = {}  # { track_id : (estado, tiempo, par_id) }
            for t1, t2, estado, tiempo in getattr(self, 'conflictos_activos', []):
                alertas_dict[t1] = (estado, tiempo, t2)
                alertas_dict[t2] = (estado, tiempo, t1)

            all_active_plots = list(self.tracks.items()) + list(self.pending_tracks.items())

            # --- FASE 3: ALGORITMO ANTI-SOLAPAMIENTO VISUAL DE ETIQUETAS ---
            label_shifts = {} # { track_id: [shift_x, shift_y] }
            for track_id, plot in all_active_plots:
                label_shifts[track_id] = [0.0, 0.0]
                
            if len(all_active_plots) > 1:
                default_centers = {}
                for track_id, plot in all_active_plots:
                    if not plot.is_alive():
                        continue
                    
                    # Comprobar filtros de visualización para ver si realmente se dibujará la etiqueta
                    if self.plot_filter_fn and not self.plot_filter_fn(plot):
                        continue
                    sensor_id = getattr(plot, 'sac_sic', f"UNK_CAT{plot.category}")
                    visibles = getattr(self, 'sensores_visibles', None)
                    if visibles is not None and sensor_id not in visibles and plot.category != 62:
                        continue
                        
                    sx_sy = self._world_to_screen(plot.x, plot.y)
                    if sx_sy is None:
                        continue
                    
                    lines = self._build_plot_label_lines(plot)
                    if not lines:
                        continue
                        
                    # Estimación rápida del ancho máximo de texto (aprox. 6.5px por carácter)
                    max_w = max(len(str(line)) * 6.5 for line in lines)
                    
                    cfg_or = self.label_filter_config.get("orientacion", "NE")
                    if cfg_or == "NE":
                        dx, dy = 15.0, -15.0
                    elif cfg_or == "NO":
                        dx, dy = -15.0 - max_w/2.0, -15.0
                    elif cfg_or == "SE":
                        dx, dy = 15.0, 15.0
                    elif cfg_or == "SO":
                        dx, dy = -15.0 - max_w/2.0, 15.0
                    else:
                        dx, dy = 15.0, -15.0
                        
                    default_centers[track_id] = (sx_sy.x() + dx, sx_sy.y() + dy, max_w)
                
                # Relajación iterativa de colisiones (2 pasadas de repulsión de fuerzas)
                for _ in range(2):
                    active_tids = list(default_centers.keys())
                    for i in range(len(active_tids)):
                        tid1 = active_tids[i]
                        c1_x, c1_y, w1 = default_centers[tid1]
                        s1_x, s1_y = label_shifts[tid1]
                        curr1_x = c1_x + s1_x
                        curr1_y = c1_y + s1_y
                        
                        for j in range(i + 1, len(active_tids)):
                            tid2 = active_tids[j]
                            c2_x, c2_y, w2 = default_centers[tid2]
                            s2_x, s2_y = label_shifts[tid2]
                            curr2_x = c2_x + s2_x
                            curr2_y = c2_y + s2_y
                            
                            # Distancia en píxeles
                            dx_px = curr1_x - curr2_x
                            dy_px = curr1_y - curr2_y
                            dist_px = math.sqrt(dx_px**2 + dy_px**2)
                            
                            # Umbral de legibilidad de 50 píxeles
                            if dist_px < 50.0:
                                if dist_px < 1.0:
                                    dist_px = 1.0
                                angle = math.atan2(dy_px, dx_px)
                                force = (50.0 - dist_px) * 0.5
                                rep_x = force * math.cos(angle)
                                rep_y = force * math.sin(angle)
                                
                                # Aplicar desplazamientos opuestos
                                label_shifts[tid1][0] += rep_x
                                label_shifts[tid1][1] += rep_y
                                label_shifts[tid2][0] -= rep_x
                                label_shifts[tid2][1] -= rep_y

            # Store label shifts in cache for use in drawing methods
            self._label_shifts_cache = label_shifts

            for track_id, plot in all_active_plots:
                try:
                    # Filtro de datos personalizado
                    if self.plot_filter_fn and not self.plot_filter_fn(plot):
                        continue
                    # FASE 2: INMUNIDAD ABSOLUTA PARA CAT 62
                    # Los System Tracks (CAT 62) NO se filtran por sensor visible.
                    if plot.category == 62:
                        self._draw_cat62_plot(painter, plot, z, inv_z)
                        continue  # No pasa por filtro de sensores ni lógica PSR/SSR/ADS-B

                    # 🔓 FILTRO DE SENSORES MÚLTIPLES ACTIVADO:
                    sensor_id = getattr(plot, 'sac_sic', f"UNK_CAT{plot.category}")
                    visibles = getattr(self, 'sensores_visibles', None)
                    if visibles is not None and sensor_id not in visibles:
                        continue

                    if not plot.is_alive():
                        continue

                    # Draw target using OACI Doc 4444 standards
                    self._draw_oaci_track(painter, plot, z, inv_z, alertas_dict)

                except Exception as e:
                    # Si un plot está corrupto, lo informamos en consola pero NO CORTAMOS EL BUCLE
                    print(f"[RENDER WARNING] Error al dibujar target {track_id}: {e}")
                    continue

            # NOTA: Las capas FASE 3 (plots_raw) y BLINDAJE fueron eliminadas.
            # El renderizado FASE 2 (tracks + pending_tracks, líneas ~1615) ya dibuja
            # cada blanco correctamente con su símbolo y etiqueta. Mantener esas capas
            # adicionales causaba que cada blanco se dibujara 2-3 veces.

            # --- DIBUJADO DE LÍNEAS DE CONFLICTO Y TEXTO DE PREDICCIÓN/VIOLACIÓN ---
            try:
                for t1_id, t2_id, estado, tiempo in getattr(self, 'conflictos_activos', []):
                    t1 = self.tracks.get(t1_id) or self.pending_tracks.get(t1_id)
                    t2 = self.tracks.get(t2_id) or self.pending_tracks.get(t2_id)
                    if not t1 or not t2:
                        continue
                    if not t1.is_alive() or not t2.is_alive():
                        continue
                    
                    color_alerta = QColor("#FF0000") if estado == 'VIOLATION' else QColor("#FFFF00")
                    
                    # Dibujar línea punteada
                    pen_line = QPen(color_alerta, safe_divide(1.5, z, 0.5), Qt.PenStyle.DashLine)
                    painter.setPen(pen_line)
                    painter.drawLine(QPointF(t1.x, t1.y), QPointF(t2.x, t2.y))
            except Exception as e:
                print(f"[RENDER WARNING] Error al dibujar línea de conflicto STCA: {e}")

            # ---- 5.5. OBSTÁCULOS MTR DETECTADOS (marcador mínimo) ----
            # Solo un triángulo pequeño y estático. El detalle (squawk, rango,
            # plot real reflejado) se registra en quality_events.log, no en pantalla.
            if getattr(self, 'mtr_visible', True) and hasattr(self, 'detected_reflectors') and self.detected_reflectors:
                try:
                    for key, ref in self.detected_reflectors.items():
                        if ref['hits'] < 4:
                            continue

                        az_rad = math.radians(ref['azimuth'])
                        dist_m = ref['range_nm'] * METERS_PER_NM
                        rx = dist_m * math.sin(az_rad)
                        ry = dist_m * math.cos(az_rad)

                        if is_valid_coord(rx, ry):
                            painter.save()
                            painter.translate(rx, ry)
                            painter.scale(inv_z, -inv_z)

                            tri_size = 5
                            t_path = QPainterPath()
                            t_path.moveTo(0, -tri_size)
                            t_path.lineTo(-tri_size * 0.866, tri_size * 0.5)
                            t_path.lineTo(tri_size * 0.866, tri_size * 0.5)
                            t_path.closeSubpath()

                            painter.setPen(QPen(QColor(255, 51, 102, 200), 1.0))
                            painter.setBrush(QBrush(QColor(255, 51, 102, 40)))
                            painter.drawPath(t_path)

                            painter.restore()
                except Exception as e:
                    print(f"[RENDER WARNING] Error drawing reflectors: {e}")

            # ---- MAPA TÁCTICO (FRENTE) ----
            self._draw_video_maps(painter, inv_z, "TACTICO")

            # ---- 6. CARTEL DE SENSOR ACTIVO (oculto en vista controlador) ----
            if (not self.vista_controlador) and self._active_sensor_label:
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

            # ---- DIBUJAR SELECCIÓN DE RECUADRO DE ZOOM (RUBBER BAND) ----
            if self.is_selecting and not self.selection_rect.isNull():
                painter.save()
                painter.setPen(QPen(QColor(0, 255, 255), 1.5, Qt.PenStyle.DashLine))
                painter.setBrush(QBrush(QColor(0, 255, 255, 30))) # 12% opacidad
                painter.drawRect(self.selection_rect.normalized())
                painter.restore()

            # ---- 8. SEGUIMIENTO DEL CURSOR EN VIVO (HUD SUPERIOR DERECHO) ----
            try:
                painter.save()
                ancho_widget = self.width()
                # Esquina superior derecha; el reloj flotante UTC se ubica justo debajo
                rect_destino = QRectF(ancho_widget - 260, 45, 250, 28)
                
                painter.setBrush(QBrush(QColor(11, 14, 20, 220)))
                painter.setPen(QPen(QColor("#00FF00"), 1.0))
                painter.drawRect(rect_destino)
                
                painter.setPen(QColor("#00FF00")) # Verde Radar aeronáutico
                painter.setFont(QFont("Monospace", 9, QFont.Weight.Bold))
                painter.drawText(rect_destino, Qt.AlignmentFlag.AlignCenter, self.cursor_geo_text)
                painter.restore()
            except Exception:
                pass

            # ---- 9. RENDERIZADO DE LA HERRAMIENTA RBL (RANGE & BEARING LINE) ----
            try:
                # Pintar encuadre de etiqueta enfocada o hovereada
                for tid, color_val in [
                    (self.focused_target_id, QColor("#FFD700")),
                    (getattr(self, 'hovered_target_id', None), QColor("#00FFFF"))
                ]:
                    if tid and tid in self.label_hitboxes:
                        hitbox = self.label_hitboxes[tid]
                        painter.save()
                        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
                        frame_rect = hitbox.adjusted(-3.0, -3.0, 3.0, 3.0)
                        pen_frame = QPen(color_val, 1.2, Qt.PenStyle.DashLine)
                        painter.setPen(pen_frame)
                        painter.setBrush(QBrush(Qt.BrushStyle.NoBrush))
                        painter.drawRoundedRect(frame_rect, 3.0, 3.0)
                        painter.restore()

                from analysis.geo_math import calcular_distancia_nm, calcular_rumbo_magnetico

                def _render_single_rbl(o_anchor, d_anchor, rbl_color, rbl_entry=None):
                    """Dibuja un único segmento RBL y devuelve (label_hitbox, p_origen, p_destino)."""
                    olat, olon, orig_lbl = self._resolve_anchor_latlon(o_anchor)
                    dlat, dlon, dest_lbl = self._resolve_anchor_latlon(d_anchor)
                    ox, oy = self.proy.latlon_to_xy(olat, olon)
                    dx, dy = self.proy.latlon_to_xy(dlat, dlon)
                    p_origen = self._world_to_screen(ox, oy)
                    p_destino = self._world_to_screen(dx, dy)
                    if not p_origen or not p_destino:
                        return None, None, None

                    painter.save()
                    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

                    # Línea de trazos con el color del RBL
                    pen = QPen(rbl_color, 2, Qt.PenStyle.DashLine)
                    painter.setPen(pen)
                    painter.drawLine(p_origen, p_destino)

                    # Círculos en los extremos
                    painter.setPen(QPen(rbl_color, 1.5))
                    painter.setBrush(QBrush(rbl_color))
                    painter.drawEllipse(p_origen, 4, 4)
                    painter.drawEllipse(p_destino, 4, 4)

                    # Encuadre de etiquetas de aeronave vinculadas
                    for anchor in [o_anchor, d_anchor]:
                        if anchor and anchor.get("type") == "aircraft":
                            pid = anchor.get("plot_id")
                            if pid in self.label_hitboxes:
                                hitbox = self.label_hitboxes[pid]
                                painter.save()
                                frame_rect = hitbox.adjusted(-3.0, -3.0, 3.0, 3.0)
                                pen_frame = QPen(rbl_color, 1.5, Qt.PenStyle.SolidLine)
                                painter.setPen(pen_frame)
                                painter.setBrush(QBrush(Qt.BrushStyle.NoBrush))
                                painter.drawRoundedRect(frame_rect, 3.0, 3.0)
                                tag_rect = QRectF(frame_rect.right() - 25, frame_rect.top() - 10, 25, 10)
                                painter.setPen(rbl_color)
                                painter.setBrush(QBrush(rbl_color))
                                painter.drawRect(tag_rect)
                                painter.setPen(QColor("#000000"))
                                font_tag = QFont("Monospace", 7, QFont.Weight.Bold)
                                painter.setFont(font_tag)
                                painter.drawText(tag_rect, Qt.AlignmentFlag.AlignCenter, "RBL")
                                painter.restore()

                    # Calcular métricas — declinación magnética dinámica (WMM) en el
                    # centroide de la línea, cacheada por celda para no recalcular por frame.
                    dist = calcular_distancia_nm(olat, olon, dlat, dlon)
                    decl = self.magnetic_compensator.obtener_declinacion(
                        (olat + dlat) / 2.0, (olon + dlon) / 2.0
                    )
                    rumbo = calcular_rumbo_magnetico(olat, olon, dlat, dlon, decl)
                    info_text = f"{rumbo:03.0f}\u00b0 M | {dist:.1f} NM"
                    if orig_lbl and dest_lbl:
                        label_text = f"{orig_lbl} -> {dest_lbl}\n{info_text}"
                    elif orig_lbl:
                        label_text = f"{orig_lbl} -> {info_text}"
                    elif dest_lbl:
                        label_text = f"{info_text} -> {dest_lbl}"
                    else:
                        label_text = info_text

                    mid_x = (p_origen.x() + p_destino.x()) / 2.0
                    mid_y = (p_origen.y() + p_destino.y()) / 2.0

                    font = QFont("Consolas", 9, QFont.Weight.Bold)
                    painter.setFont(font)
                    lines_t = label_text.split('\n')
                    fm = painter.fontMetrics()
                    rect_w = max(fm.horizontalAdvance(line) for line in lines_t) + 16
                    rect_h = fm.height() * len(lines_t) + 8
                    text_rect = QRectF(mid_x - rect_w / 2.0, mid_y - rect_h / 2.0, rect_w, rect_h)

                    # Borde del color del RBL, fondo negro
                    painter.setPen(QPen(rbl_color, 1.5))
                    painter.setBrush(QBrush(QColor("#000000")))
                    painter.drawRoundedRect(text_rect, 4, 4)

                    painter.setPen(QColor("#FFFFFF"))
                    for i, line in enumerate(lines_t):
                        line_y = text_rect.top() + fm.ascent() + 4 + i * fm.height()
                        line_w = fm.horizontalAdvance(line)
                        line_x = text_rect.left() + (rect_w - line_w) / 2.0
                        painter.drawText(QPointF(line_x, line_y), line)

                    painter.restore()
                    return text_rect, p_origen, p_destino

                # --- Renderizar RBL persistentes ---
                for rbl_entry in self.rbl_lines:
                    lhb, po, pd = _render_single_rbl(
                        rbl_entry['origen'], rbl_entry['destino'], rbl_entry['color'], rbl_entry
                    )
                    rbl_entry['label_hitbox'] = lhb
                    rbl_entry['p_origen'] = po
                    rbl_entry['p_destino'] = pd

                # --- Renderizar RBL activo (en construcción, semitransparente) ---
                if getattr(self, 'rbl_activo', False) and self.rbl_origen_anchor and self.rbl_destino_anchor:
                    active_color = QColor("#FFD700")
                    active_color.setAlpha(180)
                    _render_single_rbl(self.rbl_origen_anchor, self.rbl_destino_anchor, active_color)

            except Exception as e:
                print(f"[RadarWidget] Error renderizando RBL: {e}")

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

    def _rbl_point_near_segment(self, p, a, b, tol=10.0):
        """Devuelve True si el punto p está a menos de tol píxeles del segmento a-b."""
        if a is None or b is None:
            return False
        ab = b - a
        ap = p - a
        ab_len_sq = ab.x()**2 + ab.y()**2
        if ab_len_sq > 0:
            t = (ap.x()*ab.x() + ap.y()*ab.y()) / ab_len_sq
            t = max(0.0, min(1.0, t))
            proj = a + t * ab
            return math.hypot(p.x() - proj.x(), p.y() - proj.y()) < tol
        return math.hypot(p.x() - a.x(), p.y() - a.y()) < tol

    def mousePressEvent(self, event):
        try:
            # Hit-Testing for dragging labels (FASE 2)
            is_shift = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
            if event.button() == Qt.MouseButton.LeftButton and not is_shift:
                click_pos_f = event.position()
                click_pos = event.pos()
                label_dragged = False
                all_plots = list(self.tracks.values()) + list(self.pending_tracks.values())
                for target in all_plots:
                    if target.is_alive() and target.label_rect.contains(click_pos_f):
                        target.is_dragging = True
                        self.mouse_press_pos = click_pos_f
                        self.last_mouse_pos = click_pos
                        label_dragged = True
                        break
                if label_dragged:
                    self.update()
                    return

            # ── Comprobar si el clic elimina algún RBL persistente ──
            clic = event.position()
            idx_to_remove = None
            for i, rbl in enumerate(self.rbl_lines):
                hit_label = rbl.get('label_hitbox') and rbl['label_hitbox'].contains(clic)
                hit_line  = self._rbl_point_near_segment(clic, rbl.get('p_origen'), rbl.get('p_destino'))
                if hit_label or hit_line:
                    idx_to_remove = i
                    break
            if idx_to_remove is not None:
                self.rbl_lines.pop(idx_to_remove)
                self.update()
                return

            # Activación de herramienta RBL: Shift + Clic Izquierdo O Clic Central (Middle Button)
            is_shift = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
            is_left = event.button() == Qt.MouseButton.LeftButton
            is_middle = event.button() == Qt.MouseButton.MiddleButton
            
            if (is_left and is_shift) or is_middle:
                self.rbl_activo = True
                lat, lon, label, anchor = self._snap_to_target(event.position())

                # Si tenemos un blanco enfocado, úsalo como origen
                if getattr(self, 'focused_target_id', None):
                    focused_plot = self.tracks.get(self.focused_target_id)
                    if focused_plot and focused_plot.is_alive():
                        f_lat = focused_plot.lat
                        f_lon = focused_plot.lon
                        f_lbl = getattr(focused_plot, 'callsign', None) or getattr(focused_plot, 'mode3a', None) or f"Trk {getattr(focused_plot, 'track_number', '')}"
                        self.rbl_origen_anchor = {
                            "type": "aircraft",
                            "plot_id": self.focused_target_id,
                            "last_lat": f_lat,
                            "last_lon": f_lon,
                            "last_label": f_lbl
                        }
                        self.rbl_destino_anchor = anchor
                    else:
                        self.rbl_origen_anchor = anchor
                        self.rbl_destino_anchor = anchor
                else:
                    self.rbl_origen_anchor = anchor
                    self.rbl_destino_anchor = anchor
                self.update()
                return

            if event.button() == Qt.MouseButton.LeftButton:
                click_pos = event.position()
                self.mouse_press_pos = click_pos
                target_plot = None
                target_anchor = None
                
                # 0. PRIORIDAD MÁXIMA: Si el hover ya detectó un blanco, usarlo directamente
                hovered_id = getattr(self, 'hovered_target_id', None)
                if hovered_id:
                    plot = self.tracks.get(hovered_id) or self.pending_tracks.get(hovered_id)
                    if plot and plot.is_alive():
                        target_plot = plot
                        plat, plon = self.proy.xy_to_latlon(plot.x, plot.y)
                        target_anchor = {
                            "type": "aircraft",
                            "plot_id": hovered_id,
                            "last_lat": plat,
                            "last_lon": plon,
                            "last_label": getattr(plot, 'callsign', None) or getattr(plot, 'mode3a', None) or f"Trk {getattr(plot, 'track_number', '')}"
                        }

                # 1. Búsqueda: bounding box del texto (label hitbox) de plots activos para foco
                if target_plot is None:
                    for pid, hitbox in list(self.label_hitboxes.items()):
                        plot = self.tracks.get(pid) or self.pending_tracks.get(pid)
                        if not plot or not plot.is_alive():
                            continue
                        buffered_hitbox = hitbox.adjusted(-15.0, -15.0, 15.0, 15.0)
                        if buffered_hitbox.contains(click_pos):
                            target_plot = plot
                            plat, plon = self.proy.xy_to_latlon(plot.x, plot.y)
                            target_anchor = {
                                "type": "aircraft",
                                "plot_id": pid,
                                "last_lat": plat,
                                "last_lon": plon,
                                "last_label": getattr(plot, 'callsign', None) or getattr(plot, 'mode3a', None) or f"Trk {getattr(plot, 'track_number', '')}"
                            }
                            break
                
                # 2. Si no dio en etiqueta, buscar por distancia al símbolo físico de la aeronave
                if target_plot is None:
                    best_dist = 25.0  # 25px de tolerancia
                    all_plots = list(self.tracks.items()) + list(self.pending_tracks.items())
                    for pid, plot in all_plots:
                        if not plot.is_alive():
                            continue
                        plat, plon = self.proy.xy_to_latlon(plot.x, plot.y)
                        if plat is not None and plon is not None:
                            x_val, y_val = self.proy.latlon_to_xy(plat, plon)
                            p_screen = self._world_to_screen(x_val, y_val)
                            if p_screen:
                                dist = math.hypot(click_pos.x() - p_screen.x(), click_pos.y() - p_screen.y())
                                if dist < best_dist:
                                    best_dist = dist
                                    target_plot = plot
                                    target_anchor = {
                                        "type": "aircraft",
                                        "plot_id": pid,
                                        "last_lat": plat,
                                        "last_lon": plon,
                                        "last_label": getattr(plot, 'callsign', None) or getattr(plot, 'mode3a', None) or f"Trk {getattr(plot, 'track_number', '')}"
                                    }
                                    
                if target_plot is not None:
                    # Si ya teníamos un blanco seleccionado y es diferente, crear RBL persistente entre ambos
                    if self.focused_target_id and self.focused_target_id != target_plot.id:
                        focused_plot = self.tracks.get(self.focused_target_id) or self.pending_tracks.get(self.focused_target_id)
                        if focused_plot and focused_plot.is_alive():
                            f_lat = focused_plot.lat
                            f_lon = focused_plot.lon
                            f_lbl = getattr(focused_plot, 'callsign', None) or getattr(focused_plot, 'mode3a', None) or f"Trk {getattr(focused_plot, 'track_number', '')}"
                            o_anchor = {
                                "type": "aircraft",
                                "plot_id": self.focused_target_id,
                                "last_lat": f_lat,
                                "last_lon": f_lon,
                                "last_label": f_lbl
                            }
                            rbl_color = self._rbl_color
                            self.rbl_lines.append({
                                'origen': o_anchor,
                                'destino': target_anchor,
                                'color': rbl_color,
                                'label_hitbox': None,
                                'p_origen': None,
                                'p_destino': None,
                            })
                            self.rbl_activo = False
                            self.update()
                            return
                    
                    self.focused_target_id = target_plot.id
                    self.selected_history_point = None
                    self.rbl_drag_origin_anchor = target_anchor
                    self.update()
                    return
                else:
                    self.focused_target_id = None
                    self.rbl_drag_origin_anchor = None

                # FASE 4: Detectar clic en un punto del historial (distancia <= 5px)
                clicked_history = self._get_history_point_at(event.pos(), radius_px=5.0)
                if clicked_history is not None:
                    self.selected_history_point = clicked_history
                    self.update()
                    # No iniciar pan si se seleccionó un punto de historial
                    return

                # Si no hay hit en historial ni etiqueta, iniciar pan
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
            # Dragging label logic (FASE 2)
            all_plots = list(self.tracks.values()) + list(self.pending_tracks.values())
            dragging_plot = None
            for target in all_plots:
                if getattr(target, 'is_dragging', False):
                    dragging_plot = target
                    break
            
            if dragging_plot is not None:
                curr_pos = event.position()
                last_pos = getattr(self, 'mouse_press_pos', curr_pos)
                dx = curr_pos.x() - last_pos.x()
                dy = curr_pos.y() - last_pos.y()
                dragging_plot.label_offset += QPointF(dx, dy)
                self.mouse_press_pos = curr_pos
                self.update()
                return

            # Si el RBL está activo, actualizar destino (con snap) y retornar
            if getattr(self, 'rbl_activo', False):
                lat, lon, label, anchor = self._snap_to_target(event.position())
                self.rbl_destino_anchor = anchor
                self.cursor_geo_text = f"LAT: {lat:.4f}° | LON: {lon:.4f}°"
                self.update()
                return

            # Si se arrastra desde un blanco previamente presionado, activar RBL sin Shift
            if event.buttons() & Qt.MouseButton.LeftButton and getattr(self, 'rbl_drag_origin_anchor', None) is not None:
                press_pos = getattr(self, 'mouse_press_pos', None)
                if press_pos is not None:
                    dist = math.hypot(event.position().x() - press_pos.x(), event.position().y() - press_pos.y())
                    if dist > 5.0:  # Umbral de 5 píxeles
                        self.rbl_activo = True
                        self.rbl_origen_anchor = self.rbl_drag_origin_anchor
                        self.rbl_drag_origin_anchor = None  # Limpiar para no reentrar
                        
                        lat, lon, label, anchor = self._snap_to_target(event.position())
                        self.rbl_destino_anchor = anchor
                        self.cursor_geo_text = f"LAT: {lat:.4f}° | LON: {lon:.4f}°"
                        self.update()
                        return

            # Capturar coordenadas del cursor en vivo y convertirlas a geográficas (FASE 4)
            pos = event.position()
            world_coords = self._screen_to_world(pos.x(), pos.y())
            if world_coords:
                wx, wy = world_coords
                lat, lon = self.proy.xy_to_latlon(wx, wy)
                self.cursor_geo_text = f"LAT: {lat:.4f}° | LON: {lon:.4f}°"
            else:
                self.cursor_geo_text = "LAT: --.----° | LON: --.----°"
            self.update() # Fuerza el repintado para actualizar la etiqueta de texto en el HUD

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

            # Buscar si el cursor pasa por encima (hover) de alguna etiqueta de texto o símbolo
            hover_pos = event.position()
            hover_target = None
            
            # A. Buscar en las hitboxes de las etiquetas
            for pid, hitbox in list(self.label_hitboxes.items()):
                plot = self.tracks.get(pid) or self.pending_tracks.get(pid)
                if not plot or not plot.is_alive():
                    continue
                buffered_hitbox = hitbox.adjusted(-15.0, -15.0, 15.0, 15.0)
                if buffered_hitbox.contains(hover_pos):
                    hover_target = pid
                    break
                    
            # B. Si no dio en etiqueta, buscar cerca del símbolo físico
            if hover_target is None:
                best_dist = 25.0  # 25px de tolerancia para hover
                all_plots = list(self.tracks.items()) + list(self.pending_tracks.items())
                for pid, plot in all_plots:
                    if not plot.is_alive():
                        continue
                    plat, plon = self.proy.xy_to_latlon(plot.x, plot.y)
                    if plat is not None and plon is not None:
                        x_val, y_val = self.proy.latlon_to_xy(plat, plon)
                        p_screen = self._world_to_screen(x_val, y_val)
                        if p_screen:
                            dist = math.hypot(hover_pos.x() - p_screen.x(), hover_pos.y() - p_screen.y())
                            if dist < best_dist:
                                    best_dist = dist
                                    hover_target = pid
                                
            if getattr(self, 'hovered_target_id', None) != hover_target:
                self.hovered_target_id = hover_target
                self.update()

            # NOTA: No se usa QToolTip.showText() porque en algunos sistemas Linux
            # las tooltips heredan el tema oscuro del sistema y no se ven los textos.
            # Para información sobre puntos de historial, usar doble clic.
        except Exception:
            pass

    def mouseReleaseEvent(self, event):
        try:
            # Release label drag state (FASE 2)
            all_plots = list(self.tracks.values()) + list(self.pending_tracks.values())
            released_any = False
            for target in all_plots:
                if getattr(target, 'is_dragging', False):
                    target.is_dragging = False
                    released_any = True
            if released_any:
                self.update()
                return

            # Finalizar RBL activo → guardarlo en la lista de persistentes
            if getattr(self, 'rbl_activo', False):
                self.rbl_activo = False
                if self.rbl_origen_anchor and self.rbl_destino_anchor:
                    rbl_color = self._rbl_color
                    self.rbl_lines.append({
                        'origen': self.rbl_origen_anchor,
                        'destino': self.rbl_destino_anchor,
                        'color': rbl_color,
                        'label_hitbox': None,
                        'p_origen': None,
                        'p_destino': None,
                    })
                self.rbl_origen_anchor = None
                self.rbl_destino_anchor = None
                self.update()
                return

            if event.button() == Qt.MouseButton.LeftButton:
                self.is_panning = False
                self.last_mouse_pos = None
                self.setCursor(Qt.CursorShape.ArrowCursor)
                self.rbl_drag_origin_anchor = None
            elif event.button() == Qt.MouseButton.RightButton and self.is_selecting:
                self.is_selecting = False
                selection_area = self.selection_rect.normalized()

                sw = selection_area.width()
                sh = selection_area.height()
                if sw > 10 and sh > 10:
                    w, h = self.width(), self.height()
                    side = min(w, h)
                    vp_cx, vp_cy = w / 2.0, h / 2.0
                    
                    # 1. Encontrar el centro de la selección en coordenadas de pantalla
                    scx = selection_area.center().x()
                    scy = selection_area.center().y()
                    
                    # 2. Convertir ese centro de pantalla a coordenadas del mundo (world coordinates)
                    cx = (scx - vp_cx - self.pan_x) / self.zoom_factor
                    cy = (vp_cy + self.pan_y - scy) / self.zoom_factor
                    
                    # 3. Calcular el nuevo factor de zoom para ajustar la selección al viewport
                    z_new = self.zoom_factor * (side / max(sw, sh))
                    self.zoom_factor = max(MIN_ZOOM, min(MAX_ZOOM, z_new))
                    
                    # 4. Calcular nuevos desplazamientos (pan) para centrar en (cx, cy)
                    self.pan_x = -cx * self.zoom_factor
                    self.pan_y = cy * self.zoom_factor

                self.selected_history_points.clear()
                self.selection_rect = QRectF()
                self.update()
        except Exception:
            pass

    def keyPressEvent(self, event):
        try:
            step = 30.0  # Cantidad de píxeles a desplazar en cada pulsación
            key = event.key()
            if key == Qt.Key.Key_Left:
                self.pan_x += step
                self.update()
            elif key == Qt.Key.Key_Right:
                self.pan_x -= step
                self.update()
            elif key == Qt.Key.Key_Up:
                self.pan_y += step
                self.update()
            elif key == Qt.Key.Key_Down:
                self.pan_y -= step
                self.update()
            else:
                super().keyPressEvent(event)
        except Exception:
            pass

    # ================================================================
    # DOUBLE CLICK — INSPECCIÓN POR DATA BLOCK (HITBOX EN TEXTO)
    # ================================================================

    def _build_plot_label_lines(self, plot: 'RadarPlot') -> List[str]:
        cfg = getattr(self, 'label_filter_config', {})
        # Rol controlador: datablock operacional fijo (callsign, SSR, FL, N, ADR);
        # rol técnico: todos los campos disponibles según el filtro de etiquetas.
        es_ctrl = getattr(self, 'vista_controlador', False)

        # 1. Line 1: Identity
        show_id = True if es_ctrl else cfg.get("identific_aeronave", True)
        show_squawk = True if es_ctrl else cfg.get("codigo_a", True)
        
        line1_parts = []
        
        # Callsign
        callsign_str = ""
        if show_id and plot.callsign and plot.callsign.strip() and plot.callsign != '----':
            callsign_str = plot.callsign.strip()
            
        # Squawk
        squawk_str = ""
        if show_squawk:
            ssr_code = "----"
            if plot.mode3a is not None:
                if isinstance(plot.mode3a, int):
                    ssr_code = f"{plot.mode3a:04o}"
                else:
                    ssr_code = str(plot.mode3a).strip()
            if ssr_code not in ("----", "0000"):
                squawk_str = ssr_code
                
        if callsign_str and squawk_str:
            line1_parts.append(f"{callsign_str}/{squawk_str}")
        elif callsign_str:
            line1_parts.append(callsign_str)
        elif squawk_str:
            line1_parts.append(squawk_str)
            
        line1 = " ".join(line1_parts) if line1_parts else ""

        # 2. Line 2: Altitude & Speed
        show_altitude = True if es_ctrl else (cfg.get("codigo_c", True) or cfg.get("altitud_adsb", True))
        show_speed = True if es_ctrl else cfg.get("velocidad", True)
        
        alt_str = ""
        if show_altitude:
            fl_for_label = plot.flight_level
            if fl_for_label is None and plot.altitude_ft is not None:
                fl_for_label = plot.altitude_ft / 100.0
            # Toggle A/F dinámico segun TA del perfil y QNH manual (ENR 1.7)
            alt_str = self.altimetry.formatear_altitud(fl_for_label)

        trend_arrow = " "
        if show_altitude:
            rate_of_climb = None
            if plot.raw_dict:
                rate_of_climb = plot.raw_dict.get('vertical_rate_ftmin')
                if rate_of_climb is None and 'extra_data' in plot.raw_dict:
                    rate_of_climb = plot.raw_dict['extra_data'].get('vertical_rate_ftmin')
            if rate_of_climb is None:
                rate_of_climb = 0.0
                if plot.id in self.history:
                    hist = list(self.history[plot.id])
                    curr_fl = plot.flight_level
                    curr_time = plot.timestamp
                    if curr_fl is not None:
                        past_pt = None
                        for pt in reversed(hist):
                            if pt.timestamp > 0 and pt.fl and pt.timestamp < curr_time - 2.0:
                                past_pt = pt
                                if pt.timestamp < curr_time - 5.0:
                                    break
                        if past_pt is not None:
                            try:
                                if past_pt.fl.startswith("FL"):
                                    past_fl = float(past_pt.fl[2:])
                                    fl_diff = curr_fl - past_fl
                                    time_diff = curr_time - past_pt.timestamp
                                    if time_diff > 0:
                                        rate_of_climb = (fl_diff * 100.0 / time_diff) * 60.0
                            except Exception:
                                pass

            if rate_of_climb > 300.0:
                trend_arrow = "▲"
            elif rate_of_climb < -300.0:
                trend_arrow = "▼"

        speed_str = ""
        if show_speed:
            gs_val = plot.ground_speed
            if gs_val is None:
                # Velocidad estimada y SUAVIZADA por pista. Se recalcula solo cuando
                # llega un nuevo scan (cambia el timestamp), no en cada repintado, y se
                # filtra para evitar la fluctuación irreal del campo N.
                cached = self._gs_est_map.get(plot.id)
                curr_time = plot.timestamp
                if cached is not None and curr_time is not None and abs(curr_time - cached[1]) < 0.05:
                    # Mismo scan ya calculado → reusar (sin parpadeo entre frames)
                    gs_val = cached[0]
                elif plot.id in self.history and curr_time is not None:
                    hist = self.history[plot.id]
                    # Muestras (t, x, y) en la ventana 0–30s + el punto actual
                    samples = [
                        (pt.timestamp, pt.x, pt.y)
                        for pt in hist
                        if pt.timestamp > 0 and 0.0 <= (curr_time - pt.timestamp) <= 30.0
                    ]
                    samples.append((curr_time, plot.x, plot.y))

                    est = None
                    if len(samples) >= 3:
                        # Regresión lineal por mínimos cuadrados: |pendiente| = velocidad
                        n = len(samples)
                        t_mean = sum(s[0] for s in samples) / n
                        x_mean = sum(s[1] for s in samples) / n
                        y_mean = sum(s[2] for s in samples) / n
                        var_t = sum((s[0] - t_mean) ** 2 for s in samples)
                        if var_t > 1e-6:
                            vx = sum((s[0] - t_mean) * (s[1] - x_mean) for s in samples) / var_t
                            vy = sum((s[0] - t_mean) * (s[2] - y_mean) for s in samples) / var_t
                            est = math.hypot(vx, vy) * 3600.0 / 1852.0  # m/s → kt

                    if est is not None and 0.0 <= est <= 1200.0:
                        prev = cached[0] if cached is not None else None
                        gs_val = est if prev is None else (0.6 * prev + 0.4 * est)  # EMA
                        self._gs_est_map[plot.id] = (gs_val, curr_time)
                    elif cached is not None:
                        gs_val = cached[0]  # mantener último valor válido

            if gs_val is not None:
                gs_disp = int(round(gs_val / 5.0) * 5)  # redondeo a 5 kt para estabilidad visual
                speed_str = f"N{gs_disp:03d}"
            else:
                speed_str = "N---"

        line2 = ""
        if alt_str and speed_str:
            line2 = f"{alt_str}{trend_arrow}{speed_str}"
        elif alt_str:
            line2 = alt_str
        elif speed_str:
            line2 = speed_str

        # Build list of lines
        lines = []
        if line1:
            lines.append(line1)
        if line2:
            lines.append(line2)
            
        # 3. Extra fields/lines
        # Mode S Address (aircraft address): controlador lo ve si está disponible;
        # técnico según el filtro de etiquetas.
        if plot.mode_s and plot.mode_s.strip() and (es_ctrl or cfg.get("direccion_aeronave", False)):
            lines.append(f"ADR:{plot.mode_s.strip().upper()}")

        # Resto de campos de diagnóstico: SOLO rol técnico.
        if not es_ctrl:
            # Track Number
            if cfg.get("numero_pista", False) and plot.track_number is not None:
                lines.append(f"TRK:{plot.track_number}")

            # UTC Time (TOD)
            if cfg.get("hora_utc", False) and plot.timestamp is not None:
                tod = plot.timestamp
                hours = int(tod // 3600) % 24
                minutes = int((tod % 3600) // 60)
                seconds = int(tod % 60)
                lines.append(f"UTC:{hours:02d}:{minutes:02d}:{seconds:02d}")

            # Vertical Rate
            if cfg.get("veloc_vertic_adsb", False):
                rate_val = None
                if plot.raw_dict:
                    rate_val = plot.raw_dict.get('vertical_rate_ftmin')
                    if rate_val is None and 'extra_data' in plot.raw_dict:
                        rate_val = plot.raw_dict['extra_data'].get('vertical_rate_ftmin')
                if rate_val is not None:
                    sign = "+" if rate_val >= 0 else ""
                    lines.append(f"V/S:{sign}{int(rate_val)}")

            # Emitter Category
            if cfg.get("cat_emisor_adsb", False):
                ecat = None
                if plot.raw_dict:
                    ecat = plot.raw_dict.get('emitter_category')
                    if ecat is None and 'extra_data' in plot.raw_dict:
                        ecat = plot.raw_dict['extra_data'].get('emitter_category')
                if ecat is not None:
                    lines.append(f"ECAT:{ecat}")

            # Message Number
            if cfg.get("numero_mensaje", False):
                msg_no = None
                if plot.raw_dict:
                    msg_no = plot.raw_dict.get('message_number') or plot.raw_dict.get('msg_number')
                if msg_no is not None:
                    lines.append(f"MSG:{msg_no}")

            # Number of Replies
            if cfg.get("numero_respuestas", False):
                replies = None
                if plot.raw_dict:
                    replies = plot.raw_dict.get('num_replies') or plot.raw_dict.get('number_of_replies')
                if replies is not None:
                    lines.append(f"REP:{replies}")

            # Rumbo verdadero (°V) y/o magnético (°M) por posición del blanco (WMM).
            # Solo cambia el TEXTO; la geometría del vector de tendencia usa el rumbo verdadero.
            if plot.track_angle is not None and (cfg.get("rumbo_verdadero", False) or cfg.get("rumbo_magnetico", False)):
                partes_hdg = []
                if cfg.get("rumbo_verdadero", False):
                    partes_hdg.append(f"{plot.track_angle % 360.0:03.0f}°V")
                if cfg.get("rumbo_magnetico", False):
                    tlat, tlon = self.proy.xy_to_latlon(plot.x, plot.y)
                    if tlat is not None and tlon is not None:
                        decl = self.magnetic_compensator.obtener_declinacion(tlat, tlon)
                        partes_hdg.append(f"{(plot.track_angle - decl) % 360.0:03.0f}°M")
                if partes_hdg:
                    lines.append("HDG:" + " ".join(partes_hdg))

            # RHO / THETA (diagnóstico de cabezal de radar): solo técnico
            if plot.category in (1, 48) and plot.raw_range is not None and plot.raw_azimuth is not None:
                lines.append(f"R:{plot.raw_range:.1f}NM A:{plot.raw_azimuth:.1f}°")
            elif cfg.get("rho_theta", False) and plot.raw_range is not None and plot.raw_azimuth is not None:
                lines.append(f"R:{plot.raw_range:.1f}NM A:{plot.raw_azimuth:.1f}°")

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
            if not self.projection_set or (not self.tracks and not self.pending_tracks):
                return

            click_pos = event.position()

            # Única búsqueda: bounding box del texto (label hitbox)
            for pid, hitbox in self.label_hitboxes.items():
                plot = self.tracks.get(pid) or self.pending_tracks.get(pid)
                if not plot:
                    continue
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
    @property
    def pixeles_por_milla(self) -> float:
        return self.zoom_factor * 1852.0

    @property
    def píxeles_por_milla(self) -> float:
        return self.zoom_factor * 1852.0

    def _world_to_screen(self, x: float, y: float) -> Optional[QPointF]:
        w, h = self.width(), self.height()
        z = self.zoom_factor
        if z < MIN_ZOOM:
            return None
        vp_cx, vp_cy = w / 2.0, h / 2.0
        sx = vp_cx + self.pan_x + x * z
        sy = vp_cy + self.pan_y - y * z
        return QPointF(sx, sy)

    def _screen_to_world(self, sx: float, sy: float) -> Optional[Tuple[float, float]]:
        """Convierte coordenadas de pantalla (píxeles) a coordenadas del mundo (metros)."""
        w, h = self.width(), self.height()
        z = self.zoom_factor
        if z < MIN_ZOOM:
            return None
        vp_cx, vp_cy = w / 2.0, h / 2.0
        x = (sx - vp_cx - self.pan_x) / z
        y = (vp_cy + self.pan_y - sy) / z
        return x, y

    def _snap_to_target(self, mouse_pos) -> Tuple[float, float, Optional[str], dict]:
        """
        Busca si la posición del mouse en pantalla está cerca de algún radar o aeronave (o sus etiquetas).
        Retorna (lat, lon, label_name, anchor_dict).
        
        PRIORIDAD DE DETECCIÓN:
          0. hovered_target_id (ya calculado por mouseMoveEvent con lógica robusta)
          1. Hitbox de etiqueta de texto (label_hitboxes) con buffer generoso
          2. Sensores/radares por distancia en pantalla
          3. Símbolo físico de aeronave por distancia en pantalla
        """
        px = mouse_pos.x()
        py = mouse_pos.y()
        
        # Obtener coordenadas del puntero por defecto
        world_coords = self._screen_to_world(px, py)
        if not world_coords:
            return 0.0, 0.0, None, {"type": "point", "lat": 0.0, "lon": 0.0}
        default_lat, default_lon = self.proy.xy_to_latlon(world_coords[0], world_coords[1])

        # --- PRIORIDAD 0: Si mouseMoveEvent ya detectó un hover, usarlo directamente ---
        hovered_id = getattr(self, 'hovered_target_id', None)
        if hovered_id:
            plot = self.tracks.get(hovered_id)
            if plot and getattr(plot, 'is_alive', lambda: True)():
                plat, plon = self.proy.xy_to_latlon(plot.x, plot.y)
                if plat is not None and plon is not None:
                    label = getattr(plot, 'callsign', None) or getattr(plot, 'mode3a', None) or f"Trk {getattr(plot, 'track_number', '')}"
                    anchor = {
                        "type": "aircraft",
                        "plot_id": hovered_id,
                        "last_lat": plat,
                        "last_lon": plon,
                        "last_label": label
                    }
                    return plat, plon, label, anchor
        
        snap_radius = 25.0  # Radio generoso para facilitar la selección
        best_dist = float('inf')
        best_coord = (default_lat, default_lon)
        best_label = None
        best_anchor = {"type": "point", "lat": default_lat, "lon": default_lon, "label": None}

        # 1. Verificar si el mouse está dentro de la etiqueta de texto de una aeronave (máxima prioridad)
        for plot_id, hitbox in list(self.label_hitboxes.items()):
            plot = self.tracks.get(plot_id)
            if not plot or not getattr(plot, 'is_alive', lambda: True)():
                continue
            plat, plon = self.proy.xy_to_latlon(plot.x, plot.y)
            if plat is not None and plon is not None:
                buffered_hitbox = hitbox.adjusted(-15.0, -15.0, 15.0, 15.0)
                if buffered_hitbox.contains(mouse_pos):
                    best_coord = (plat, plon)
                    best_label = getattr(plot, 'callsign', None) or getattr(plot, 'mode3a', None) or f"Trk {getattr(plot, 'track_number', '')}"
                    best_anchor = {
                        "type": "aircraft",
                        "plot_id": plot_id,
                        "last_lat": plat,
                        "last_lon": plon,
                        "last_label": best_label
                    }
                    return best_coord[0], best_coord[1], best_label, best_anchor

        # 2. Verificar radares (snapping por distancia física de píxeles)
        for (sac, sic), s_info in self.sensor_info.items():
            slat = s_info.get('lat')
            slon = s_info.get('lon')
            sname = s_info.get('name', f"Radar {sac}/{sic}")
            if slat is not None and slon is not None:
                wx, wy = self.proy.latlon_to_xy(slat, slon)
                spos = self._world_to_screen(wx, wy)
                if spos:
                    dist = math.hypot(spos.x() - px, spos.y() - py)
                    if dist < snap_radius and dist < best_dist:
                        best_dist = dist
                        best_coord = (slat, slon)
                        best_label = sname
                        best_anchor = {"type": "sensor", "sac_sic": (sac, sic)}

        # 3. Verificar símbolos físicos de aeronaves (snapping por distancia física de píxeles)
        for plot_id, plot in self.tracks.items():
            if not getattr(plot, 'is_alive', lambda: True)():
                continue
            plat, plon = self.proy.xy_to_latlon(plot.x, plot.y)
            if plat is not None and plon is not None:
                wx, wy = self.proy.latlon_to_xy(plat, plon)
                spos = self._world_to_screen(wx, wy)
                if spos:
                    dist = math.hypot(spos.x() - px, spos.y() - py)
                    if dist < snap_radius and dist < best_dist:
                        best_dist = dist
                        best_coord = (plat, plon)
                        best_label = getattr(plot, 'callsign', None) or getattr(plot, 'mode3a', None) or f"Trk {getattr(plot, 'track_number', '')}"
                        best_anchor = {
                            "type": "aircraft",
                            "plot_id": plot_id,
                            "last_lat": plat,
                            "last_lon": plon,
                            "last_label": best_label
                        }

        return best_coord[0], best_coord[1], best_label, best_anchor

    def _resolve_anchor_latlon(self, anchor: dict) -> Tuple[float, float, Optional[str]]:
        if not anchor:
            return 0.0, 0.0, None
        
        atype = anchor.get("type")
        if atype == "aircraft":
            plot_id = anchor.get("plot_id")
            plot = self.tracks.get(plot_id)
            if plot and getattr(plot, 'is_alive', lambda: True)():
                plat, plon = self.proy.xy_to_latlon(plot.x, plot.y)
                if plat is not None and plon is not None:
                    label = getattr(plot, 'callsign', None) or getattr(plot, 'mode3a', None) or f"Trk {getattr(plot, 'track_number', '')}"
                    anchor["last_lat"] = plat
                    anchor["last_lon"] = plon
                    anchor["last_label"] = label
                    return plat, plon, label
            return anchor.get("last_lat", 0.0), anchor.get("last_lon", 0.0), anchor.get("last_label")
            
        elif atype == "sensor":
            sac_sic = anchor.get("sac_sic")
            s_info = self.sensor_info.get(sac_sic)
            if s_info:
                slat = s_info.get('lat')
                slon = s_info.get('lon')
                sname = s_info.get('name', f"Radar {sac_sic[0]}/{sac_sic[1]}")
                if slat is not None and slon is not None:
                    return slat, slon, sname
                    
        return anchor.get("lat", 0.0), anchor.get("lon", 0.0), anchor.get("label")

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

    def _draw_oaci_track(self, painter: QPainter, plot: 'RadarPlot', z: float, inv_z: float, alertas_dict: dict):
        try:
            # 1. Check emergency (FASE 4)
            ssr_code = ""
            if plot.mode3a is not None:
                if isinstance(plot.mode3a, int):
                    ssr_code = f"{plot.mode3a:04o}"
                else:
                    ssr_code = str(plot.mode3a).strip()
            
            is_emergency = ssr_code in ("7500", "7600", "7700")
            
            # Blink logic for emergency (FASE 4)
            if is_emergency and not self.blink_flag:
                return  # Skip rendering in this frame to create a blinking effect
                
            x, y = plot.x, plot.y
            if not is_valid_coord(x, y):
                return
                
            sensor_info = self.sensor_info.get((plot.sac, plot.sic)) if hasattr(self, 'sensor_info') else None
            sensor_type = str(sensor_info.get('type', '')).upper() if sensor_info else ''
            is_async = (plot.category in (21, 62)) or (sensor_type == 'MLAT') or (plot.is_track and plot.category not in (1, 48)) or (len(getattr(plot, 'reporting_sensors', [])) > 1)

            rpm = self.sensor_rpms.get((plot.sac, plot.sic), self.sweep_rpm)
            scan_time = 60.0 / rpm if rpm > 0 else 5.0

            is_coasting = False
            alpha = 255
            is_alive = plot.age < 25.0

            if not is_alive or alpha <= 0:
                return

            # Fase C — atenuación por incumbencia: si la vista de jurisdicción está
            # activa (controlador siempre, o técnico con el toggle), el tráfico fuera
            # del radio o sobre el techo FL se muestra tenue.
            if (self.vista_controlador or getattr(self, 'mostrar_incumbencia', False)) \
                    and not getattr(plot, 'en_jurisdiccion', True):
                alpha = 70
            
            is_psr = False
            is_ssr = False
            is_combined = False
            is_adsb = False
            is_mlat = False
            is_fused = (plot.category == 62) or (len(getattr(plot, 'reporting_sensors', [])) > 1)

            if plot.category == 21:
                is_adsb = True
            elif sensor_type == 'MLAT':
                is_mlat = True
            elif plot.category == 1:
                has_ssr_info = bool(plot.mode3a and plot.mode3a != "----")
                if has_ssr_info:
                    is_ssr = True
                else:
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
                        
            # Determine color
            if is_emergency:
                plot_color = QColor(Qt.GlobalColor.red)
            elif getattr(plot, 'degradada', False) and not getattr(self, 'modo_crudo', False):
                _dqf_r = getattr(plot, 'dqf_razon', '')
                if _dqf_r == 'GARBLING':
                    plot_color = QColor("#FF00FF")
                elif _dqf_r == 'FRUIT':
                    plot_color = QColor("#FFA500")
                elif _dqf_r == 'PISTA INMADURA':
                    plot_color = QColor("#FFD700")
                else:
                    plot_color = QColor("#FFA500")
            elif plot.id in alertas_dict:
                estado, tiempo, _ = alertas_dict[plot.id]
                plot_color = QColor("#FF0000") if estado == 'VIOLATION' else QColor("#FFFF00")
            elif getattr(plot, 'is_reflection', False) and not getattr(self, 'modo_crudo', False):
                plot_color = QColor(255, 51, 102)
            elif getattr(plot, 'has_reflection', False) and not getattr(self, 'modo_crudo', False):
                plot_color = QColor(255, 128, 0)
            else:
                if is_fused:
                    plot_color = QColor("#FFFFFF")  # Blanco para fusionado/CAT62
                elif is_adsb:
                    plot_color = QColor("#FFFF00")  # Amarillo para ADS-B/CAT21
                elif is_mlat:
                    plot_color = QColor(255, 0, 255)  # Magenta para MLAT
                elif is_psr:
                    plot_color = QColor(204, 85, 0)  # Naranja oscuro para PSR
                elif is_ssr or is_combined:
                    # CAT48/01 sin SSR (squawk) o sin FL → celeste claro (plot inválido/incompleto)
                    has_valid_ssr = ssr_code and ssr_code not in ("----", "0000", "")
                    has_fl = plot.flight_level is not None
                    if plot.category in (1, 48) and (not has_valid_ssr or not has_fl):
                        plot_color = QColor(100, 200, 255)  # Celeste claro = inválido
                    else:
                        plot_color = COLOR_GREEN_NEON  # Verde neón para SSR / combinado
                else:
                    plot_color = self._get_sensor_color(plot.sac, plot.sic)
                
            if plot.highlighted:
                base_color = QColor(255, 255, 0, alpha)
            else:
                base_color = QColor(plot_color)
                base_color.setAlpha(alpha)
            
            # 2. Draw Symbol (FASE 2)
            painter.save()
            try:
                painter.translate(x, y)
                if is_adsb and plot.track_angle is not None:
                    painter.rotate(plot.track_angle)
                    
                sym_size = safe_divide(8.0, z, 1.0)
                
                # Active vs Coasting line style (FASE 2)
                if is_coasting:
                    pen_symbol = QPen(QColor(128, 128, 128), safe_divide(2.0, z, 0.5), Qt.PenStyle.DashLine)
                    brush_symbol = QBrush(Qt.BrushStyle.NoBrush)
                else:
                    pen_symbol = QPen(base_color, safe_divide(2.0, z, 0.5), Qt.PenStyle.SolidLine)
                    brush_symbol = QBrush(Qt.BrushStyle.NoBrush)
                    
                painter.setPen(pen_symbol)
                painter.setBrush(brush_symbol)
                
                if is_adsb:
                    t = QPainterPath()
                    t.moveTo(0, -sym_size * 0.66)
                    t.lineTo(-sym_size * 0.5, sym_size * 0.33)
                    t.lineTo(sym_size * 0.5, sym_size * 0.33)
                    t.closeSubpath()
                    painter.drawPath(t)
                elif is_psr:
                    s_r = sym_size * 0.5
                    painter.drawLine(QPointF(-s_r, 0), QPointF(s_r, 0))
                    painter.drawLine(QPointF(0, -s_r), QPointF(0, s_r))
                else:
                    painter.drawRect(QRectF(-sym_size / 2, -sym_size / 2, sym_size, sym_size))
            finally:
                painter.restore()
                
            # 3. Dibujar encuadre concéntrico de selección o hover en el símbolo
            is_focused = self.focused_target_id and plot.id == self.focused_target_id
            is_hovered = getattr(self, 'hovered_target_id', None) and plot.id == self.hovered_target_id
            if is_focused or is_hovered:
                try:
                    painter.save()
                    painter.translate(x, y)
                    color_val = QColor("#FFD700") if is_focused else QColor("#00FFFF")
                    pen_focused = QPen(color_val, safe_divide(1.5, z, 0.3), Qt.PenStyle.DashLine)
                    painter.setPen(pen_focused)
                    painter.setBrush(QBrush(Qt.BrushStyle.NoBrush))
                    r_val = safe_divide(12.0, z, 2.0)
                    painter.drawEllipse(QPointF(0, 0), r_val, r_val)
                    d_val = safe_divide(10.0, z, 2.0)
                    l_val = safe_divide(4.0, z, 1.0)
                    painter.drawLine(QPointF(-d_val, d_val), QPointF(-d_val + l_val, d_val))
                    painter.drawLine(QPointF(-d_val, d_val), QPointF(-d_val, d_val - l_val))
                    painter.drawLine(QPointF(d_val, d_val), QPointF(d_val - l_val, d_val))
                    painter.drawLine(QPointF(d_val, d_val), QPointF(d_val, d_val - l_val))
                    painter.drawLine(QPointF(-d_val, -d_val), QPointF(-d_val + l_val, -d_val))
                    painter.drawLine(QPointF(-d_val, -d_val), QPointF(-d_val, -d_val + l_val))
                    painter.drawLine(QPointF(d_val, -d_val), QPointF(d_val - l_val, -d_val))
                    painter.drawLine(QPointF(d_val, -d_val), QPointF(d_val, -d_val + l_val))
                    painter.restore()
                except Exception:
                    pass

            # 4. Dibuja la bounding box si está en conflicto
            if plot.id in alertas_dict:
                try:
                    estado, tiempo, _ = alertas_dict[plot.id]
                    color_alerta = QColor("#FF0000") if estado == 'VIOLATION' else QColor("#FFFF00")
                    
                    painter.save()
                    painter.translate(x, y)
                    pen_box = QPen(color_alerta, safe_divide(2.0, z, 0.5))
                    painter.setPen(pen_box)
                    painter.setBrush(QBrush(Qt.BrushStyle.NoBrush))
                    box_size = safe_divide(30.0, z, 1.0)
                    painter.drawRect(QRectF(-box_size / 2, -box_size / 2, box_size, box_size))
                    painter.restore()
                except Exception:
                    pass

            # 5. Vector de tendencia (Predictive speed vector in screen pixels - FASE 1)
            es_pista = plot.is_track or is_fused

            # MÓDULO (largo) = velocidad del blanco; DIRECCIÓN = velocidad suavizada
            # (evita oscilación ~180° entre radares), con fallback al track_angle crudo.
            target_gs = plot.ground_speed
            target_heading = plot.track_angle
            sv_x = getattr(plot, '_smooth_vx', None)
            sv_y = getattr(plot, '_smooth_vy', None)
            if sv_x is not None and sv_y is not None:
                v_mps = math.hypot(sv_x, sv_y)
                if v_mps > 5.0:  # ~10 kt: descartar ruido en blancos lentos/estáticos
                    target_heading = math.degrees(math.atan2(sv_x, sv_y)) % 360.0
                    if target_gs is None:
                        target_gs = v_mps * 1.94384  # m/s -> kt (solo si no hay gs reportado)

            if es_pista and target_gs is not None and target_heading is not None and target_gs > 10:
                try:
                    # Tope anti-inflación: la velocidad estimada puede dispararse por los
                    # saltos de posición entre radares; ningún avión civil supera ~600 kt.
                    gs_clamp = min(float(target_gs), 600.0)

                    painter.save()
                    painter.translate(x, y)
                    painter.scale(inv_z, -inv_z)  # espacio de PÍXELES de pantalla

                    # Largo FIJO en pantalla, proporcional a la velocidad (no escala con el
                    # zoom): así siempre es visible y nunca cruza la pantalla. PX_POR_NM es
                    # una escala visual fija (no representa distancia real en el mapa).
                    PX_POR_NM = 5.0
                    distancia_vector_nm = (gs_clamp / 60.0) * self.vector_tiempo_minutos
                    longitud_px = distancia_vector_nm * PX_POR_NM

                    # 0° apunta al Norte (el scale(-inv_z) ya invierte el eje Y).
                    ang = math.radians(target_heading)
                    dx_vector = longitud_px * math.sin(ang)
                    dy_vector = -longitud_px * math.cos(ang)

                    pen_v = QPen(base_color, 1.5, Qt.PenStyle.SolidLine)
                    painter.setPen(pen_v)
                    painter.drawLine(QPointF(0, 0), QPointF(dx_vector, dy_vector))

                    painter.restore()
                except Exception:
                    pass

            # 6. Dibujar línea de enlace si es una reflexión y el blanco real está visible
            if getattr(plot, 'is_reflection', False) and getattr(plot, 'linked_real_id', None) and not getattr(self, 'modo_crudo', False):
                real_plot = self.tracks.get(plot.linked_real_id) or self.pending_tracks.get(plot.linked_real_id)
                if real_plot and real_plot.is_alive():
                    try:
                        pen_link = QPen(QColor(150, 150, 150, min(alpha, 80)))
                        pen_link.setStyle(Qt.PenStyle.DotLine)
                        pen_link.setWidthF(safe_divide(1.2, z, 0.3))
                        painter.setPen(pen_link)
                        painter.drawLine(QPointF(x, y), QPointF(real_plot.x, real_plot.y))
                    except Exception:
                        pass

            lines = self._build_plot_label_lines(plot)
            if lines:
                painter.save()
                try:
                    painter.translate(x, y)
                    painter.scale(inv_z, -inv_z)
                    
                    font_oaci = QFont("Consolas", 9)
                    painter.setFont(font_oaci)
                    
                    if is_coasting:
                        label_pen_color = QColor(128, 128, 128)
                    elif is_emergency:
                        label_pen_color = QColor(Qt.GlobalColor.red)
                    else:
                        label_pen_color = QColor(plot_color)
                        label_pen_color.setAlpha(alpha)
                        
                    painter.setPen(label_pen_color)
                    fm = QFontMetrics(font_oaci)
                    
                    max_w = max(fm.horizontalAdvance(line) for line in lines)
                    
                    # Position label based on offset (FASE 3)
                    dx = plot.label_offset.x()
                    dy = plot.label_offset.y()
                    
                    # Draw Leader Line (FASE 3)
                    if is_coasting:
                        pen_leader = QPen(QColor(128, 128, 128), 1.0, Qt.PenStyle.DashLine)
                    else:
                        pen_leader = QPen(base_color, 1.0, Qt.PenStyle.SolidLine)
                        
                    leader_alpha = min(alpha, 80)
                    pen_leader.setColor(QColor(pen_leader.color().red(), pen_leader.color().green(), pen_leader.color().blue(), leader_alpha))
                    painter.setPen(pen_leader)
                    
                    # Draw Leader Line from aircraft center (0, 0) to label offset
                    painter.drawLine(QPointF(0, 0), plot.label_offset)
                    
                    # If target is in conflict STCA, draw badge/box
                    if plot.id in alertas_dict:
                        try:
                            estado, tiempo, _ = alertas_dict[plot.id]
                            color_alerta = QColor("#FF0000") if estado == 'VIOLATION' else QColor("#FFFF00")
                            pen_box = QPen(color_alerta, 1.2)
                            painter.setPen(pen_box)
                            painter.setBrush(QBrush(QColor(11, 14, 20, 180)))
                            rect_label = QRectF(dx - 5, dy - 2, max_w + 10, len(lines) * 14 + 3)
                            painter.drawRect(rect_label)
                            
                            if estado == 'PREDICTION':
                                badge_txt = f"T-{tiempo}s"
                                painter.save()
                                painter.setFont(QFont("Consolas", 7, QFont.Weight.Bold))
                                fm_badge = QFontMetrics(painter.font())
                                badge_w = fm_badge.horizontalAdvance(badge_txt) + 6
                                badge_h = 11
                                rect_badge = QRectF(rect_label.right() - badge_w - 4, rect_label.top() - 9, badge_w, badge_h)
                                painter.setPen(Qt.PenStyle.NoPen)
                                painter.setBrush(QBrush(QColor("#FFFF00")))
                                painter.drawRect(rect_badge)
                                painter.setPen(QColor("#000000"))
                                painter.drawText(rect_badge, Qt.AlignmentFlag.AlignCenter, badge_txt)
                                painter.restore()
                            painter.setBrush(QBrush(Qt.BrushStyle.NoBrush))
                        except Exception:
                            pass
                            
                    # Draw text lines
                    painter.setPen(label_pen_color)
                    total_hitbox = None
                    for i, line in enumerate(lines):
                        y_pos = dy + i * 14
                        text_pos = QPointF(dx, y_pos)
                        painter.drawText(text_pos, line)
                        
                        br = fm.boundingRect(int(text_pos.x()), int(text_pos.y()), int(1e6), int(1e6),
                                              Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop, line)
                        mapped_rect = painter.transform().mapRect(br)
                        if total_hitbox is None:
                            total_hitbox = QRectF(mapped_rect)
                        else:
                            total_hitbox = total_hitbox.united(QRectF(mapped_rect))
                            
                finally:
                    painter.restore()
                    
                if total_hitbox is not None:
                    self.label_hitboxes[plot.id] = total_hitbox
                    plot.label_rect = total_hitbox
                    
        except Exception as e:
            print(f"[RENDER WARNING] Error drawing OACI target: {e}")

    def _draw_cat62_plot(self, painter: QPainter, plot: 'RadarPlot', z: float, inv_z: float):
        alertas_dict = {}
        for t1, t2, estado, tiempo in getattr(self, 'conflictos_activos', []):
            alertas_dict[t1] = (estado, tiempo, t2)
            alertas_dict[t2] = (estado, tiempo, t1)
        self._draw_oaci_track(painter, plot, z, inv_z, alertas_dict)
