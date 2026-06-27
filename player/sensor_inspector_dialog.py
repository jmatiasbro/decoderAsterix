"""Inspector multi-sensor: muestra qué radares detectan actualmente una aeronave
y con qué separación, para diagnosticar duplicados por fallo de fusión.
"""
import math
import json
import os

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLineEdit, QPushButton, QLabel,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QFont


_SQUAWKS_GENERICOS = {"1200", "7000", "7600", "7700", "2000", "0000"}
_SENSOR_PARAMS_DIR = os.path.join(os.path.dirname(__file__), "..", "default-site-params")


def _cargar_nombres_sensores() -> dict:
    """SAC_SIC → nombre legible desde los JSON de configuración."""
    nombres = {}
    try:
        for fn in os.listdir(_SENSOR_PARAMS_DIR):
            if not fn.endswith(".json"):
                continue
            key = fn.replace(".json", "")  # "226_210"
            try:
                with open(os.path.join(_SENSOR_PARAMS_DIR, fn), encoding="utf-8") as f:
                    d = json.load(f)
                nombres[key] = d.get("name", key)
            except Exception:
                pass
    except Exception:
        pass
    return nombres


_NOMBRES_SENSORES: dict = _cargar_nombres_sensores()


def _sq_str(mode3a) -> str:
    if mode3a is None or mode3a == "" or mode3a == "----":
        return ""
    return f"{int(mode3a):04o}" if isinstance(mode3a, int) else str(mode3a).strip().upper()


def _dist_nm(t1, t2) -> float:
    dx = t1.x - t2.x
    dy = t1.y - t2.y
    return math.sqrt(dx * dx + dy * dy) / 1852.0


def _nombre_sensor(sac_sic: str) -> str:
    key = sac_sic.replace("/", "_")
    return _NOMBRES_SENSORES.get(key, sac_sic)


class SensorInspectorDialog(QDialog):
    """Ventana flotante que lista los radares que ven a la aeronave buscada."""

    localizar = pyqtSignal(float, float, str, str)

    _COL_SENSOR   = 0
    _COL_SAC_SIC  = 1
    _COL_ESTADO   = 2
    _COL_RANGO    = 3
    _COL_AZIMUT   = 4
    _COL_LAT      = 5
    _COL_LON      = 6
    _COL_DELTA    = 7
    _COL_TOD      = 8
    _NCOLS        = 9

    def __init__(self, radar_widget, parent=None):
        super().__init__(parent)
        self.radar = radar_widget
        self._query = ""

        self.setWindowFlags(Qt.WindowType.Tool | Qt.WindowType.WindowStaysOnTopHint)
        self.setWindowTitle("Inspector Multi-sensor")
        self.resize(820, 320)
        self._init_ui()

        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._refresh)

    # ------------------------------------------------------------------ UI --
    def _init_ui(self):
        self.setStyleSheet(
            "QDialog { background-color: #0a0f18; color: #ffffff; font-family: 'Consolas'; }"
            "QLabel  { color: #8fa0bc; font-size: 9px; font-weight: bold; }"
            "QTableWidget { background-color: #0d1520; color: #c8d8f0; "
            "               gridline-color: #1a2a3d; font-size: 10px; }"
            "QHeaderView::section { background-color: #0f1e30; color: #8fa0bc; "
            "                       border: 1px solid #1a2a3d; padding: 2px; font-size: 9px; }"
            "QLineEdit { background-color: #101724; border: 1px solid #23334d; "
            "            border-radius: 4px; padding: 5px; color: #00ff66; "
            "            font-size: 12px; font-weight: bold; }"
            "QPushButton { background-color: #162338; border: 1px solid #2d456e; "
            "              border-radius: 4px; padding: 5px 10px; font-weight: bold; color: #c8d8f0; }"
            "QPushButton:hover { background-color: #213454; border-color: #00ff66; }"
        )
        layout = QVBoxLayout(self)
        layout.setSpacing(6)

        lbl = QLabel("INSPECCIÓN MULTI-SENSOR  —  CALLSIGN | SSR Mode 3/A")
        layout.addWidget(lbl)

        row = QHBoxLayout()
        self.txt_query = QLineEdit()
        self.txt_query.setPlaceholderText("Ej: ARG1340  ó  2023")
        self.txt_query.returnPressed.connect(self._on_buscar)
        row.addWidget(self.txt_query)

        btn = QPushButton("Inspeccionar")
        btn.clicked.connect(self._on_buscar)
        row.addWidget(btn)

        self.lbl_estado = QLabel("")
        self.lbl_estado.setStyleSheet("color: #00ff66; font-size: 9px; font-weight: bold;")
        row.addWidget(self.lbl_estado)
        layout.addLayout(row)

        self.tabla = QTableWidget(0, self._NCOLS)
        self.tabla.setHorizontalHeaderLabels([
            "Sensor", "SAC/SIC", "Estado", "Rango (NM)", "Azimut (°)",
            "Lat", "Lon", "Δ (NM)", "ToD (s)",
        ])
        self.tabla.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tabla.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tabla.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.tabla.horizontalHeader().setStretchLastSection(True)
        self.tabla.verticalHeader().setVisible(False)
        layout.addWidget(self.tabla)

    # --------------------------------------------------------------- lógica --
    def _on_buscar(self):
        q = self.txt_query.text().strip().upper()
        if not q:
            return
        self._query = q
        self._refresh()
        self._timer.start()

    def _buscar_tracks(self, query: str) -> list:
        fuentes = [
            (self.radar.tracks, "Prom"),
            (self.radar.pending_tracks, "Pend"),
        ]
        resultados = []
        for d, estado in fuentes:
            for t in d.values():
                cs = (t.callsign or "").upper()
                sq = _sq_str(t.mode3a)
                if (cs and cs == query) or (sq and sq == query):
                    resultados.append((t, estado))
        return resultados

    def _refresh(self):
        if not self._query:
            return

        matches = self._buscar_tracks(self._query)

        # referencia = primer track promovido (tracks dict), para calcular Δ
        ref = next((t for t, st in matches if st == "Prom"), None)
        if ref is None and matches:
            ref = matches[0][0]

        # ordenar por distancia al ref (primero el propio ref con Δ=0)
        def sort_key(item):
            t, _ = item
            return _dist_nm(t, ref) if ref else 0.0

        matches.sort(key=sort_key)

        n = len(matches)
        self.lbl_estado.setText(f"{n} sensor{'es' if n != 1 else ''} detectando '{self._query}'")

        self.tabla.setRowCount(n)
        font_bold = QFont("Consolas", 10)
        font_bold.setBold(True)

        for row, (t, estado) in enumerate(matches):
            delta_nm = _dist_nm(t, ref) if ref else 0.0

            lat = t.raw_dict.get("lat") or t.raw_dict.get("lat_render")
            lon = t.raw_dict.get("lon") or t.raw_dict.get("lon_render")

            valores = [
                _nombre_sensor(t.sac_sic),
                t.sac_sic,
                estado,
                f"{t.raw_range:.2f}" if t.raw_range is not None else "—",
                f"{t.raw_azimuth:.2f}" if t.raw_azimuth is not None else "—",
                f"{lat:.5f}" if lat is not None else "—",
                f"{lon:.5f}" if lon is not None else "—",
                f"{delta_nm:.2f}",
                f"{t.timestamp:.1f}" if t.timestamp else "—",
            ]

            for col, val in enumerate(valores):
                item = QTableWidgetItem(str(val))
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.tabla.setItem(row, col, item)

            # Color de fila según separación
            if delta_nm < 0.01:
                color = QColor("#0d2b14")   # verde oscuro → track de referencia
            elif delta_nm > 5.0:
                color = QColor("#2b1010")   # rojo → separación crítica
            elif delta_nm > 1.0:
                color = QColor("#2b2010")   # naranja → separación notable
            else:
                color = QColor("#0d1520")   # normal

            for col in range(self._NCOLS):
                it = self.tabla.item(row, col)
                if it:
                    it.setBackground(color)
                    if col == self._COL_DELTA and delta_nm > 5.0:
                        it.setFont(font_bold)
                        it.setForeground(QColor("#ff4040"))

    def closeEvent(self, event):
        self._timer.stop()
        super().closeEvent(event)
