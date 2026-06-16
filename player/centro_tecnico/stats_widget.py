"""Constructor configurable de estadísticas: métrica × dimensión × gráfico."""
from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QFormLayout, QComboBox, QPushButton,
    QLabel, QFileDialog,
)
from matplotlib.figure import Figure
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas

from player.stats.metric_registry import METRICS, DIMENSIONS, aggregate, metric_by_id
from player.stats.chart_renderer import render, CHART_TYPES


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


class StatsWidget(QWidget):
    def __init__(self, source_provider, parent=None):
        super().__init__(parent)
        self._source_provider = source_provider
        root = QHBoxLayout(self)

        cfg = QWidget(); form = QFormLayout(cfg); cfg.setMaximumWidth(320)
        self.cmb_metric = QComboBox()
        for m in METRICS:
            self.cmb_metric.addItem(m.label, m.id)
        self.cmb_dim = QComboBox()
        for d in DIMENSIONS:
            label = DIMENSION_LABELS.get(d, d)
            self.cmb_dim.addItem(label, d)
        self.cmb_chart = QComboBox()
        for c in CHART_TYPES:
            self.cmb_chart.addItem(c, c)
        self.btn_gen = QPushButton("Generar")
        self.btn_png = QPushButton("⤓ PNG")
        self.lbl_rows = QLabel("Filas: 0")
        form.addRow("Métrica", self.cmb_metric)
        form.addRow("Dimensión", self.cmb_dim)
        form.addRow("Gráfico", self.cmb_chart)
        form.addRow(self.btn_gen)
        form.addRow(self.btn_png)
        form.addRow(self.lbl_rows)

        self.figure = Figure(figsize=(6, 4))
        self.canvas = FigureCanvas(self.figure)

        root.addWidget(cfg)
        root.addWidget(self.canvas, 1)

        self.btn_gen.clicked.connect(self.generate)
        self.btn_png.clicked.connect(self._export_png)

    # API para tests
    def set_metric(self, mid): self.cmb_metric.setCurrentIndex(self.cmb_metric.findData(mid))
    def set_dimension(self, d): self.cmb_dim.setCurrentIndex(self.cmb_dim.findData(d))
    def set_chart(self, c): self.cmb_chart.setCurrentIndex(self.cmb_chart.findData(c))

    def on_source_changed(self):
        pass   # placeholder para refrescar filtros de radar (Task 15 opcional)

    def generate(self):
        src = self._source_provider()
        rows = src.load()
        metric = metric_by_id(self.cmb_metric.currentData())
        dim = self.cmb_dim.currentData()
        chart = self.cmb_chart.currentData()
        data = aggregate(rows, metric, dim)
        self.lbl_rows.setText(f"Filas: {len(data)}")
        try:
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
