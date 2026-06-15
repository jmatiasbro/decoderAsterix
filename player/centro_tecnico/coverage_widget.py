"""Pestaña Cobertura: contorno real por FL en vista polar + mapa, con exportación."""
import numpy as np
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QComboBox, QSpinBox, QPushButton,
    QLabel, QMenu, QFileDialog,
)
from matplotlib.figure import Figure
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas

from analysis.coverage import compute_coverage, level_polygon_latlon, FL_BANDS


class CoverageWidget(QWidget):
    def __init__(self, source_provider, db_path="pass_analytics.duckdb", parent=None):
        super().__init__(parent)
        self._source_provider = source_provider
        self._db_path = db_path
        self.result = None

        root = QVBoxLayout(self)
        ctrl = QHBoxLayout()
        self.cmb_radar = QComboBox()
        self.spin_pctl = QSpinBox(); self.spin_pctl.setRange(50, 99); self.spin_pctl.setValue(95)
        self.btn_calc = QPushButton("Calcular")
        self.btn_export = QPushButton("⤓ Exportar ▼")
        self.lbl_info = QLabel("—")
        ctrl_items = [QLabel("Radar"), self.cmb_radar, QLabel("Pctil"),
                      self.spin_pctl, self.btn_calc, self.btn_export, self.lbl_info]
        for it in ctrl_items:
            ctrl.addWidget(it)
        ctrl.addStretch(1)
        root.addLayout(ctrl)

        views = QHBoxLayout()
        self.fig_map = Figure(figsize=(5, 5)); self.canvas_map = FigureCanvas(self.fig_map)
        self.fig_polar = Figure(figsize=(5, 5)); self.canvas_polar = FigureCanvas(self.fig_polar)
        views.addWidget(self.canvas_map, 1)
        views.addWidget(self.canvas_polar, 1)
        root.addLayout(views, 1)

        self.btn_calc.clicked.connect(self.calculate)
        self.btn_export.clicked.connect(self._show_export_menu)
        self.on_source_changed()

    def set_radar(self, sac_sic):
        i = self.cmb_radar.findText(sac_sic)
        if i < 0:
            self.cmb_radar.addItem(sac_sic); i = self.cmb_radar.findText(sac_sic)
        self.cmb_radar.setCurrentIndex(i)

    def on_source_changed(self):
        try:
            radars = self._source_provider().radars()
        except Exception:
            radars = []
        cur = self.cmb_radar.currentText()
        self.cmb_radar.clear(); self.cmb_radar.addItems(radars)
        if cur:
            self.set_radar(cur)

    def _radar_latlon(self, sac_sic):
        """Lat/lon del radar desde default-site-params. (lat, lon) o (None, None)."""
        from utils.geo import cargar_sensores
        try:
            sac, sic = (int(x) for x in sac_sic.split("/"))
        except Exception:
            return (None, None)
        info = cargar_sensores("default-site-params").get((sac, sic))
        if not info:
            return (None, None)
        return (info["lat"], info["lon"])

    def calculate(self):
        sac_sic = self.cmb_radar.currentText()
        rlat, rlon = self._radar_latlon(sac_sic)
        if rlat is None:
            self.lbl_info.setText(f"Sin parámetros de sitio para {sac_sic}")
            return
        rows = self._source_provider().load(radars=[sac_sic])
        plots = [(r["lat"], r["lon"], r.get("flight_level")) for r in rows
                 if r.get("lat") and r.get("lon")]
        self.result = compute_coverage(plots, rlat, rlon, percentile=self.spin_pctl.value())
        self.lbl_info.setText(f"Plots: {self.result.plot_count}")
        self._draw()

    def _draw(self):
        res = self.result
        # Polar
        self.fig_polar.clear()
        axp = self.fig_polar.add_subplot(111, projection="polar")
        axp.set_theta_zero_location("N"); axp.set_theta_direction(-1)
        for fl in FL_BANDS:
            ranges = res.levels.get(fl) or []
            if any(r > 0 for r in ranges):
                theta = np.deg2rad(np.arange(360))
                axp.plot(theta, ranges, linewidth=1, label=f"FL{fl}")
        axp.legend(fontsize=6, loc="upper right")
        self.canvas_polar.draw_idle()
        # Mapa
        self.fig_map.clear()
        axm = self.fig_map.add_subplot(111)
        axm.plot([res.radar_lon], [res.radar_lat], marker="*", color="cyan")
        for fl in FL_BANDS:
            ring = level_polygon_latlon(res, fl)
            if ring:
                lons = [p[1] for p in ring]; lats = [p[0] for p in ring]
                axm.plot(lons, lats, linewidth=1, label=f"FL{fl}")
                axm.fill(lons, lats, alpha=0.10)
        axm.set_xlabel("lon"); axm.set_ylabel("lat"); axm.legend(fontsize=6)
        axm.set_aspect("equal", adjustable="datalim")
        self.canvas_map.draw_idle()

    def _show_export_menu(self):
        menu = QMenu(self)
        menu.addAction("KMZ (Google Earth)", self._export_kmz)
        menu.addAction("Heatmap QGIS (CSV)", self._export_csv)
        menu.addAction("Imagen PNG (mapa)", self._export_png)
        menu.addAction("Polígonos GeoJSON", self._export_geojson)
        menu.exec(self.btn_export.mapToGlobal(self.btn_export.rect().bottomLeft()))

    def _export_kmz(self):
        from analysis.exporters import PassExporter
        path, _ = QFileDialog.getSaveFileName(self, "KMZ", "cobertura.kmz", "KMZ (*.kmz)")
        if path:
            PassExporter(db_path=self._db_path).export_coverage_map_kmz(
                self.cmb_radar.currentText(), output_file=path)

    def _export_csv(self):
        from analysis.exporters import PassExporter
        path, _ = QFileDialog.getSaveFileName(self, "CSV", "heatmap.csv", "CSV (*.csv)")
        if path:
            PassExporter(db_path=self._db_path).export_heatmap_qgis(output_file=path)

    def _export_png(self):
        path, _ = QFileDialog.getSaveFileName(self, "PNG", "cobertura.png", "PNG (*.png)")
        if path:
            self.fig_map.savefig(path, dpi=150)

    def _export_geojson(self):
        import json
        if not self.result:
            return
        path, _ = QFileDialog.getSaveFileName(self, "GeoJSON", "cobertura.geojson",
                                              "GeoJSON (*.geojson)")
        if not path:
            return
        feats = []
        for fl in FL_BANDS:
            ring = level_polygon_latlon(self.result, fl)
            if ring:
                feats.append({"type": "Feature",
                              "properties": {"FL": fl},
                              "geometry": {"type": "Polygon",
                                           "coordinates": [[[p[1], p[0]] for p in ring]]}})
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"type": "FeatureCollection", "features": feats}, f, indent=2)
