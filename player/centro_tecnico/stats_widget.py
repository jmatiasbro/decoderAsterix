"""Constructor de estadísticas orientado a análisis radar.

Selector de **Vista**:
- Presets de dominio (1 click): Cobertura PPI, Pd vs Rango, Rosa de azimut,
  Cobertura vertical, Histograma de rango.
- Avanzado: constructor genérico métrica × dimensión, y dispersión X vs Y.

Selector de sensores multi-radar: individual, varios o todos.
"""
import random

import numpy as np
from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QFormLayout, QComboBox, QPushButton,
    QLabel, QFileDialog,
)
from matplotlib.figure import Figure
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas

from player.stats.metric_registry import METRICS, DIMENSIONS, aggregate, metric_by_id
from player.stats.chart_renderer import render
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

# Vistas del panel: presets de dominio + modos avanzados.
VIEWS = [
    ("ppi_cov",    "Cobertura PPI (rango × azimut)"),
    ("geo_cov",    "Cobertura geográfica (lon × lat)"),
    ("pd_azimuth", "Pd vs Azimut"),
    ("rose_az",    "Rosa de azimut (sectores)"),
    ("vert_cov",   "Cobertura vertical (alt × rango)"),
    ("range_hist", "Histograma de rango"),
    ("adv_agg",    "Avanzado: métrica × dimensión"),
    ("adv_xy",     "Avanzado: dispersión X / Y"),
]

# Tipos de gráfico válidos en el modo agregado (los engañosos fueron podados).
AGG_CHARTS = [("bar", "Barras"), ("line", "Línea")]

# Campos numéricos para los ejes del gráfico de dispersión avanzado (X vs Y).
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

# Agrupación por color en el scatter avanzado (claves que existen en DIMENSIONS).
COLOR_BY = [
    (None, "(ninguno)"),
    ("radar", "Radar (SAC/SIC)"),
    ("category", "Categoría"),
    ("mode3a", "Modo A / SSR"),
    ("fl_band", "Nivel (FL)"),
]

MAX_SCATTER_POINTS = 20000   # tope para que el scatter/PPI no se vuelva pesado
RANGE_BIN_NM = 10.0          # ancho de anillo para histograma / Pd vs rango
AZ_SECTOR_DEG = 10.0         # ancho de sector para la rosa de azimut


def _num(x):
    if x is None:
        return None
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


class StatsWidget(QWidget):
    def __init__(self, source_provider, sensores_provider=None,
                 rpms_provider=None, parent=None):
        super().__init__(parent)
        self._source_provider = source_provider
        self._sensores_provider = sensores_provider
        self._rpms_provider = rpms_provider
        root = QHBoxLayout(self)

        cfg = QWidget(); cfg.setMaximumWidth(340)
        col = QVBoxLayout(cfg)

        # --- Sensores (multi-radar) + Vista ---
        form_top = QFormLayout()
        self.cmb_sensors = CheckableComboBox()
        self.cmb_view = QComboBox()
        for vid, lbl in VIEWS:
            self.cmb_view.addItem(lbl, vid)
        self.cmb_view.insertSeparator(6)   # separa presets de los modos avanzados
        self.cmb_view.currentIndexChanged.connect(self._on_view_changed)
        form_top.addRow("Sensores", self.cmb_sensors)
        form_top.addRow("Vista", self.cmb_view)
        col.addLayout(form_top)

        # --- Modo Avanzado Agregado: métrica × dimensión × gráfico ---
        self.box_agg = QWidget()
        f_agg = QFormLayout(self.box_agg)
        f_agg.setContentsMargins(0, 0, 0, 0)
        self.cmb_metric = QComboBox()
        for m in METRICS:
            self.cmb_metric.addItem(m.label, m.id)
        self.cmb_dim = QComboBox()
        for d in DIMENSIONS:
            self.cmb_dim.addItem(DIMENSION_LABELS.get(d, d), d)
        self.cmb_aggchart = QComboBox()
        for c, lbl in AGG_CHARTS:
            self.cmb_aggchart.addItem(lbl, c)
        f_agg.addRow("Métrica", self.cmb_metric)
        f_agg.addRow("Dimensión", self.cmb_dim)
        f_agg.addRow("Gráfico", self.cmb_aggchart)
        col.addWidget(self.box_agg)

        # --- Modo Avanzado Dispersión: Eje X × Eje Y × color ---
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
        self._on_view_changed()
        self._populate_sensors()

    # ---- API para tests / control externo ----
    def set_metric(self, mid): self.cmb_metric.setCurrentIndex(self.cmb_metric.findData(mid))
    def set_dimension(self, d): self.cmb_dim.setCurrentIndex(self.cmb_dim.findData(d))

    def set_chart(self, c):
        """Selecciona el modo agregado y su tipo de gráfico (bar/line)."""
        self.cmb_view.setCurrentIndex(self.cmb_view.findData("adv_agg"))
        i = self.cmb_aggchart.findData(c)
        if i >= 0:
            self.cmb_aggchart.setCurrentIndex(i)

    def on_source_changed(self):
        """Repuebla el selector de sensores cuando cambia la fuente (nuevo archivo)."""
        self._populate_sensors()

    # ---- Helpers internos ----
    def _on_view_changed(self):
        view = self.cmb_view.currentData()
        self.box_agg.setVisible(view == "adv_agg")
        self.box_xy.setVisible(view == "adv_xy")

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

    def _xy_series(self, rows, xf, yf, keyfn):
        """Series (x, y) por grupo, con muestreo proporcional bajo MAX_SCATTER_POINTS."""
        series = {}
        for r in rows:
            x = _num(r.get(xf)); y = _num(r.get(yf))
            if x is None or y is None:
                continue
            g = keyfn(r) if keyfn else ""
            series.setdefault(g, []).append((x, y))
        total = sum(len(v) for v in series.values())
        if total > MAX_SCATTER_POINTS and total > 0:
            frac = MAX_SCATTER_POINTS / total
            series = {g: random.sample(v, max(1, int(len(v) * frac)))
                      for g, v in series.items()}
        return sorted(series.items(), key=lambda kv: str(kv[0])), total

    def _pd_vs_azimuth(self, rows):
        """Pd real por sector de azimut, una curva por sensor.

        El Pd no es un valor por-plot: es detecciones observadas / esperadas por
        bin contra trazas de referencia geodésicas. Se reusa el motor PASS (el
        mismo de la pestaña PASS/SASS-C), que devuelve `pd_vs_azimuth` por sensor.
        """
        from analysis.pass_analyzer import PASSAnalyticsEngine
        sensores = self._sensores_provider() if self._sensores_provider else {}
        rpms = self._rpms_provider() if self._rpms_provider else {}
        engine = PASSAnalyticsEngine(sensores=sensores)
        results = engine.analyze_data(rows, rpms)
        out = []
        for sac_sic, res in sorted(results.items(), key=lambda kv: str(kv[0])):
            if not isinstance(res, dict):
                continue                      # claves globales (overlap_pairwise…)
            pts = [(float(az), float(pd)) for az, pd in res.get("pd_vs_azimuth", [])]
            if pts:
                out.append((res.get("name") or sac_sic, pts))
        return out

    def _range_hist(self, rows):
        """Conteo de detecciones por anillo de rango (orden natural)."""
        counts = {}
        for r in rows:
            rng = _num(r.get("raw_range"))
            if rng is None:
                continue
            b = int(rng // RANGE_BIN_NM) * int(RANGE_BIN_NM)
            counts[b] = counts.get(b, 0) + 1
        return [(str(b), c) for b, c in sorted(counts.items())]

    def _azimuth_rose(self, rows):
        """Conteo de detecciones por sector de azimut (todos los radares juntos)."""
        n = int(round(360.0 / AZ_SECTOR_DEG))
        counts = [0] * n
        for r in rows:
            az = _num(r.get("raw_azimuth"))
            if az is None:
                continue
            counts[int((az % 360.0) // AZ_SECTOR_DEG) % n] += 1
        pts = [((i + 0.5) * AZ_SECTOR_DEG, c) for i, c in enumerate(counts)]
        return [("", pts)]

    def _with_polar(self, rows):
        """Deriva raw_range (NM) / raw_azimuth (°) desde lat/lon cuando faltan.

        CAT021 (ADS-B) y CAT062 traen posición GPS, no polares de radar. Si se
        conoce la posición de la estación (sensores), se computa el rango/azimut
        del blanco respecto a ella — así PPI/Rosa/Histograma/Cobertura vertical
        funcionan para ADS-B (cobertura desde el receptor). Sin posición de
        sensor configurada, las filas quedan igual (presets vacíos, honesto).
        """
        sensores = self._sensores_provider() if self._sensores_provider else {}
        pos = {k: (v.get("lat"), v.get("lon")) for k, v in (sensores or {}).items()
               if isinstance(v, dict) and v.get("lat") is not None
               and v.get("lon") is not None}
        if not pos:
            return rows
        from utils.geo import _calculate_distance_and_azimuth_jit as _geo
        out = []
        for r in rows:
            if r.get("raw_range") is not None and r.get("raw_azimuth") is not None:
                out.append(r); continue
            sp = pos.get(r.get("sac_sic"))
            lat = _num(r.get("lat")); lon = _num(r.get("lon"))
            if sp is None or lat is None or lon is None or (lat == 0.0 and lon == 0.0):
                out.append(r); continue
            d_m, az = _geo(sp[0], sp[1], lat, lon)
            out.append({**r, "raw_range": d_m / 1852.0, "raw_azimuth": az})
        return out

    def _with_alt_ft(self, rows):
        """Rellena altitude_ft desde flight_level (FL×100) cuando falta.

        En CAT048/001 suele venir solo el Mode C como flight_level; sin esto la
        cobertura vertical queda vacía aunque haya nivel reportado.
        """
        out = []
        for r in rows:
            if r.get("altitude_ft") is not None:
                out.append(r); continue
            fl = _num(r.get("flight_level"))
            out.append(r if fl is None else {**r, "altitude_ft": fl * 100.0})
        return out

    def _scatter_data(self, rows):
        """Datos del scatter avanzado, con color por la dimensión elegida."""
        color = self.cmb_color.currentData()
        keyfn = DIMENSIONS[color] if color else None
        return self._xy_series(rows, self.cmb_x.currentData(),
                               self.cmb_y.currentData(), keyfn)

    # ---- Render ----
    def generate(self):
        src = self._source_provider()
        rows = src.load(radars=self._selected_radars() or None)
        view = self.cmb_view.currentData()
        radar_dim = DIMENSIONS["radar"]
        try:
            if view == "ppi_cov":
                data, total = self._xy_series(self._with_polar(rows),
                                              "raw_range", "raw_azimuth", radar_dim)
                self.lbl_rows.setText(f"Puntos: {total}")
                render(self.figure, data, "ppi", title="Cobertura PPI (rango × azimut)")
            elif view == "geo_cov":
                geo = [r for r in rows if not (_num(r.get("lat")) in (None, 0.0)
                                               and _num(r.get("lon")) in (None, 0.0))]
                data, total = self._xy_series(geo, "lon", "lat", radar_dim)
                self.lbl_rows.setText(f"Puntos: {total}")
                render(self.figure, data, "scatter", title="Cobertura geográfica",
                       xlabel="Longitud (°)", ylabel="Latitud (°)")
            elif view == "vert_cov":
                data, total = self._xy_series(self._with_alt_ft(self._with_polar(rows)),
                                              "raw_range", "altitude_ft", radar_dim)
                self.lbl_rows.setText(f"Puntos: {total}")
                render(self.figure, data, "scatter", title="Cobertura vertical",
                       xlabel="Rango (NM)", ylabel="Altitud (ft)")
            elif view == "pd_azimuth":
                data = self._pd_vs_azimuth(rows)
                self.lbl_rows.setText(f"Bins: {sum(len(p) for _, p in data)}")
                render(self.figure, data, "curves", title="Pd vs Azimut",
                       xlabel="Azimut (°)", ylabel="Pd (%)")
            elif view == "rose_az":
                data = self._azimuth_rose(self._with_polar(rows))
                self.lbl_rows.setText(f"Sectores: {len(data[0][1])}")
                render(self.figure, data, "rose",
                       title="Rosa de azimut (detecciones por sector)")
            elif view == "range_hist":
                data = self._range_hist(self._with_polar(rows))
                self.lbl_rows.setText(f"Bins: {len(data)}")
                render(self.figure, data, "bar", title="Histograma de rango",
                       xlabel="Rango (NM)", ylabel="Detecciones")
            elif view == "adv_xy":
                data, total = self._scatter_data(rows)
                self.lbl_rows.setText(f"Puntos: {total}")
                xl = dict(NUMERIC_FIELDS).get(self.cmb_x.currentData(), "X")
                yl = dict(NUMERIC_FIELDS).get(self.cmb_y.currentData(), "Y")
                render(self.figure, data, "scatter", title=f"{yl} vs {xl}",
                       xlabel=xl, ylabel=yl)
            else:  # adv_agg
                metric = metric_by_id(self.cmb_metric.currentData())
                dim = self.cmb_dim.currentData()
                data = aggregate(rows, metric, dim)
                self.lbl_rows.setText(f"Filas: {len(data)}")
                render(self.figure, data, self.cmb_aggchart.currentData(),
                       title=metric.label, xlabel=DIMENSION_LABELS.get(dim, dim),
                       ylabel=metric.label)
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
