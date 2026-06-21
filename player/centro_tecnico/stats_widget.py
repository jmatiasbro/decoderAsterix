"""Constructor configurable de estadísticas.

Dos modos:
- Agregado: métrica × dimensión × gráfico (bar/line/pie/box/…).
- Dispersión (X vs Y): dos campos numéricos cruzados, con color por radar/categoría/…

Selector de sensores multi-radar: individual, varios o todos.
"""
import random

from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QFormLayout, QComboBox, QPushButton,
    QLabel, QFileDialog,
)
from matplotlib.figure import Figure
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas

from player.stats.metric_registry import METRICS, DIMENSIONS, aggregate, metric_by_id
from player.stats.chart_renderer import render, CHART_TYPES
from player.pass_dashboard import CheckableComboBox


DIMENSION_LABELS = {
    "radar": "SIC/SAC",
    "hour": "Tiempo (Hora)",
    "mode3a": "Modo A / SSR",
    "fl_band": "Nivel (FL50, FL150, FL200, FL300)",
    "category": "Categoría ASTERIX",
    "callsign": "Callsign",
    "mode_s": "Aircraft Address (Mode S)",
    "garbled": "Garbling (Interferencia)",
}

# Campos numéricos para los ejes del gráfico de dispersión (X vs Y).
NUMERIC_FIELDS = [
    ("raw_range", "Rango (NM)"),
    ("raw_azimuth", "Azimut (°)"),
    ("altitude_ft", "Altitud (ft)"),
    ("flight_level", "Nivel (FL)"),
    ("ground_speed", "Velocidad (kt)"),
    ("track_angle", "Rumbo (°)"),
    ("vertical_rate", "Régimen vertical"),
    ("lat", "Latitud (°)"),
    ("lon", "Longitud (°)"),
    ("timestamp", "Tiempo (s)"),
    ("pd", "Pd (%)"),
]

# Agrupación por color en el scatter (claves que existen en DIMENSIONS).
COLOR_BY = [
    (None, "(ninguno)"),
    ("radar", "Radar (SAC/SIC)"),
    ("category", "Categoría"),
    ("mode3a", "Modo A / SSR"),
    ("fl_band", "Nivel (FL)"),
]

MAX_SCATTER_POINTS = 20000   # tope para que el scatter no se vuelva pesado


def _num(x):
    if x is None:
        return None
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


class StatsWidget(QWidget):
    def __init__(self, source_provider, parent=None):
        super().__init__(parent)
        self._source_provider = source_provider
        root = QHBoxLayout(self)

        cfg = QWidget(); cfg.setMaximumWidth(340)
        col = QVBoxLayout(cfg)

        # --- Sensores (multi-radar) + tipo de gráfico ---
        form_top = QFormLayout()
        self.cmb_sensors = CheckableComboBox()
        self.cmb_chart = QComboBox()
        for c in CHART_TYPES:
            self.cmb_chart.addItem(c, c)
        self.cmb_chart.currentIndexChanged.connect(self._on_chart_changed)
        form_top.addRow("Sensores", self.cmb_sensors)
        form_top.addRow("Gráfico", self.cmb_chart)
        col.addLayout(form_top)

        # --- Modo Agregado: métrica × dimensión ---
        self.box_agg = QWidget()
        f_agg = QFormLayout(self.box_agg)
        f_agg.setContentsMargins(0, 0, 0, 0)
        self.cmb_metric = QComboBox()
        for m in METRICS:
            self.cmb_metric.addItem(m.label, m.id)
        self.cmb_dim = QComboBox()
        for d in DIMENSIONS:
            self.cmb_dim.addItem(DIMENSION_LABELS.get(d, d), d)
        f_agg.addRow("Métrica", self.cmb_metric)
        f_agg.addRow("Dimensión", self.cmb_dim)
        col.addWidget(self.box_agg)

        # --- Modo Dispersión: Eje X × Eje Y × color ---
        self.box_xy = QWidget()
        f_xy = QFormLayout(self.box_xy)
        f_xy.setContentsMargins(0, 0, 0, 0)
        self.cmb_x = QComboBox()
        self.cmb_y = QComboBox()
        for key, lbl in NUMERIC_FIELDS:
            self.cmb_x.addItem(lbl, key)
            self.cmb_y.addItem(lbl, key)
        self.cmb_x.setCurrentIndex(0)               # Rango
        self.cmb_y.setCurrentIndex(2)               # Altitud
        self.cmb_color = QComboBox()
        for key, lbl in COLOR_BY:
            self.cmb_color.addItem(lbl, key)
        self.cmb_color.setCurrentIndex(1)           # Radar
        f_xy.addRow("Eje X", self.cmb_x)
        f_xy.addRow("Eje Y", self.cmb_y)
        f_xy.addRow("Color por", self.cmb_color)
        col.addWidget(self.box_xy)

        # --- Acciones ---
        self.btn_gen = QPushButton("Generar")
        self.btn_png = QPushButton("⤓ PNG")
        self.lbl_rows = QLabel("Filas: 0")
        col.addWidget(self.btn_gen)
        col.addWidget(self.btn_png)
        col.addWidget(self.lbl_rows)
        col.addStretch(1)

        self.figure = Figure(figsize=(6, 4))
        self.canvas = FigureCanvas(self.figure)
        root.addWidget(cfg)
        root.addWidget(self.canvas, 1)

        self.btn_gen.clicked.connect(self.generate)
        self.btn_png.clicked.connect(self._export_png)
        self._on_chart_changed()
        self._populate_sensors()

    # ---- API para tests / control externo ----
    def set_metric(self, mid): self.cmb_metric.setCurrentIndex(self.cmb_metric.findData(mid))
    def set_dimension(self, d): self.cmb_dim.setCurrentIndex(self.cmb_dim.findData(d))
    def set_chart(self, c): self.cmb_chart.setCurrentIndex(self.cmb_chart.findData(c))

    def on_source_changed(self):
        """Repuebla el selector de sensores cuando cambia la fuente (nuevo archivo)."""
        self._populate_sensors()

    # ---- Helpers internos ----
    def _on_chart_changed(self):
        es_scatter = (self.cmb_chart.currentData() == "scatter")
        self.box_xy.setVisible(es_scatter)
        self.box_agg.setVisible(not es_scatter)

    def _populate_sensors(self):
        try:
            disponibles = self._source_provider().radars()
        except Exception:
            disponibles = []
        previos = set(self._selected_radars())
        self.cmb_sensors.model.clear()
        for sac_sic in disponibles:
            checked = (not previos) or (sac_sic in previos)
            self.cmb_sensors.add_checkable_item(sac_sic, sac_sic, checked=checked)

    def _selected_radars(self):
        return [d for d in self.cmb_sensors.get_checked_data() if d]

    def _scatter_data(self, rows):
        xf = self.cmb_x.currentData()
        yf = self.cmb_y.currentData()
        color = self.cmb_color.currentData()
        keyfn = DIMENSIONS[color] if color else None
        series = {}
        for r in rows:
            x = _num(r.get(xf)); y = _num(r.get(yf))
            if x is None or y is None:
                continue
            g = keyfn(r) if keyfn else ""
            series.setdefault(g, []).append((x, y))
        # Tope de puntos: muestreo proporcional para no congelar la UI.
        total = sum(len(v) for v in series.values())
        if total > MAX_SCATTER_POINTS and total > 0:
            frac = MAX_SCATTER_POINTS / total
            series = {g: random.sample(v, max(1, int(len(v) * frac)))
                      for g, v in series.items()}
        return sorted(series.items(), key=lambda kv: str(kv[0])), total

    # ---- Render ----
    def generate(self):
        src = self._source_provider()
        rows = src.load(radars=self._selected_radars() or None)
        chart = self.cmb_chart.currentData()
        try:
            if chart == "scatter":
                data, total = self._scatter_data(rows)
                self.lbl_rows.setText(f"Puntos: {total}")
                xl = dict(NUMERIC_FIELDS).get(self.cmb_x.currentData(), "X")
                yl = dict(NUMERIC_FIELDS).get(self.cmb_y.currentData(), "Y")
                render(self.figure, data, "scatter", title=f"{yl} vs {xl}",
                       xlabel=xl, ylabel=yl)
            else:
                metric = metric_by_id(self.cmb_metric.currentData())
                dim = self.cmb_dim.currentData()
                data = aggregate(rows, metric, dim)
                self.lbl_rows.setText(f"Filas: {len(data)}")
                render(self.figure, data, chart, title=metric.label,
                       xlabel=DIMENSION_LABELS.get(dim, dim), ylabel=metric.label)
        except Exception as e:
            self.figure.clear()
            ax = self.figure.add_subplot(111)
            ax.text(0.5, 0.5, f"No se pudo graficar:\n{e}", ha="center", va="center")
        self.canvas.draw_idle()

    def _export_png(self):
        path, _ = QFileDialog.getSaveFileName(self, "Guardar PNG", "estadistica.png",
                                              "PNG (*.png)")
        if path:
            self.figure.savefig(path, dpi=150)
