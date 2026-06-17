"""Pestaña Cobertura: contorno real por FL en vista polar + mapa, con exportación."""
import math
import numpy as np
import matplotlib.cm as cm
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QComboBox, QSpinBox, QDoubleSpinBox,
    QPushButton, QLabel, QMenu, QFileDialog, QCheckBox,
)
from matplotlib.colors import to_hex
from matplotlib.figure import Figure
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas

from analysis.coverage import compute_coverage, level_polygon_latlon, FL_BANDS

# Color fijo por banda FL, consistente entre mapa y polar (turbo: bajo=frío, alto=cálido).
_FL_COLORS = {fl: cm.turbo(i / (len(FL_BANDS) - 1))
              for i, fl in enumerate(FL_BANDS)}
_BG = "#0E131F"
_FG = "#D8DEE9"
_GRID = "#2A3344"


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
        self.spin_pctl.setToolTip(
            "Percentil del alcance por azimut: P95 = el radar cubre hasta ese rango "
            "el 95% de las veces en esa dirección. Más bajo = más conservador "
            "(filtra ecos lejanos aislados); más alto = alcance máximo.")
        self.spin_theo = QDoubleSpinBox(); self.spin_theo.setRange(0.0, 600.0)
        self.spin_theo.setSuffix(" NM"); self.spin_theo.setDecimals(0)
        self.spin_theo.setValue(250.0)
        self.spin_theo.setToolTip("Alcance teórico (nominal) del radar, autocompletado "
                                  "desde default-site-params. Editable.")
        self.btn_calc = QPushButton("Calcular")
        self.btn_export = QPushButton("⤓ Exportar ▼")
        self.lbl_info = QLabel("—")
        ctrl_items = [QLabel("Radar"), self.cmb_radar, QLabel("Pctil"),
                      self.spin_pctl, QLabel("Teórica"), self.spin_theo,
                      self.btn_calc, self.btn_export, self.lbl_info]
        for it in ctrl_items:
            ctrl.addWidget(it)
        ctrl.addStretch(1)
        root.addLayout(ctrl)

        # Fila de selección de niveles FL: "Todos" + uno por banda. Filtran qué
        # bandas se dibujan (sin recalcular la cobertura).
        niv = QHBoxLayout()
        niv.addWidget(QLabel("Niveles:"))
        self.chk_todos = QCheckBox("Todos"); self.chk_todos.setChecked(True)
        self.chk_todos.toggled.connect(self._on_todos_toggled)
        niv.addWidget(self.chk_todos)
        self.fl_checks = {}
        for fl in FL_BANDS:
            cb = QCheckBox(f"FL{fl}"); cb.setChecked(True)
            cb.setStyleSheet(f"color: {to_hex(_FL_COLORS[fl])}; font-weight: bold;")
            cb.toggled.connect(self._on_fl_toggled)
            self.fl_checks[fl] = cb
            niv.addWidget(cb)
        niv.addStretch(1)
        root.addLayout(niv)

        views = QHBoxLayout()
        self.fig_map = Figure(figsize=(5, 5)); self.canvas_map = FigureCanvas(self.fig_map)
        self.fig_polar = Figure(figsize=(5, 5)); self.canvas_polar = FigureCanvas(self.fig_polar)
        views.addWidget(self.canvas_map, 1)
        views.addWidget(self.canvas_polar, 1)
        root.addLayout(views, 2)

        # Panel vertical (rango x altitud): envolvente geométrica de alcance por
        # altura. Es información distinta del Pd que muestra la pestaña PASS.
        self.fig_vert = Figure(figsize=(8, 2.4)); self.canvas_vert = FigureCanvas(self.fig_vert)
        root.addWidget(self.canvas_vert, 1)

        self.btn_calc.clicked.connect(self.calculate)
        self.btn_export.clicked.connect(self._show_export_menu)
        # Recalcular al cambiar el percentil (sólo si ya hubo un cálculo previo).
        self.spin_pctl.valueChanged.connect(self._on_pctl_changed)
        # Cambiar la teórica solo re-dibuja (no recalcula la cobertura real).
        self.spin_theo.valueChanged.connect(self._on_theo_changed)
        self.on_source_changed()

    def _on_theo_changed(self, _v):
        if self.result is not None:
            self._draw()

    def _selected_fls(self):
        return [fl for fl, cb in self.fl_checks.items() if cb.isChecked()]

    def _on_todos_toggled(self, checked):
        # Marcar/desmarcar todas las bandas; un solo redraw al final.
        for cb in self.fl_checks.values():
            cb.blockSignals(True); cb.setChecked(checked); cb.blockSignals(False)
        if self.result is not None:
            self._draw()

    def _on_fl_toggled(self, _checked):
        # Sincronizar el estado de "Todos" sin disparar su handler.
        todos = all(cb.isChecked() for cb in self.fl_checks.values())
        self.chk_todos.blockSignals(True); self.chk_todos.setChecked(todos)
        self.chk_todos.blockSignals(False)
        if self.result is not None:
            self._draw()

    def _on_pctl_changed(self, _v):
        if self.result is not None and self.cmb_radar.currentText():
            self.calculate()

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
        elif radars:
            self.cmb_radar.setCurrentIndex(0)
            self.calculate()

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

    def _radar_theo_range(self, sac_sic):
        """Alcance teórico (NM) del radar desde site-params, o None."""
        from utils.geo import cargar_sensores
        try:
            sac, sic = (int(x) for x in sac_sic.split("/"))
        except Exception:
            return None
        info = cargar_sensores("default-site-params").get((sac, sic)) or {}
        r = info.get("range")
        return float(r) if r else None

    def calculate(self):
        sac_sic = self.cmb_radar.currentText()
        rlat, rlon = self._radar_latlon(sac_sic)
        if rlat is None:
            self.lbl_info.setText(f"Sin parámetros de sitio para {sac_sic}")
            return
        # Autocompletar la teórica desde site-params (sin disparar redraw).
        theo = self._radar_theo_range(sac_sic)
        if theo:
            self.spin_theo.blockSignals(True)
            self.spin_theo.setValue(theo)
            self.spin_theo.blockSignals(False)
        rows = self._source_provider().load(radars=[sac_sic])
        plots = [(r["lat"], r["lon"], r.get("flight_level")) for r in rows
                 if r.get("lat") and r.get("lon")]
        self.result = compute_coverage(plots, rlat, rlon, percentile=self.spin_pctl.value())
        self.lbl_info.setText(f"Plots: {self.result.plot_count}")
        self._draw()

    def _draw(self):
        res = self.result
        theo = self.spin_theo.value()
        # Bandas FL seleccionadas y con datos (para escalar y anillos de rango).
        sel = set(self._selected_fls())
        bandas = [fl for fl in FL_BANDS
                  if fl in sel and any(r > 0 for r in (res.levels.get(fl) or []))]
        rmax = max((max(res.levels.get(fl) or [0]) for fl in bandas), default=100.0)
        rmax = max(50.0, rmax * 1.05, theo * 1.05)
        # Dibujar de mayor a menor cobertura para que las chicas queden encima.
        orden = sorted(bandas, key=lambda fl: max(res.levels.get(fl) or [0]), reverse=True)

        # Envolvente externa por azimut (máx sobre FL) -> % área real vs teórica.
        outer = np.zeros(360)
        for fl in bandas:
            outer = np.maximum(outer, np.array(res.levels.get(fl), dtype=float))
        real_area = float(np.sum(0.5 * outer ** 2 * np.deg2rad(1.0)))
        theo_area = math.pi * theo ** 2 if theo > 0 else 0.0
        pct = (100.0 * real_area / theo_area) if theo_area > 0 else 0.0
        self.lbl_info.setText(
            f"Plots: {res.plot_count}   ·   Real vs teórica: {pct:.0f}%")

        # ---- POLAR ----
        self.fig_polar.clear()
        self.fig_polar.set_facecolor(_BG)
        axp = self.fig_polar.add_subplot(111, projection="polar", facecolor=_BG)
        axp.set_theta_zero_location("N"); axp.set_theta_direction(-1)
        theta = np.deg2rad(np.arange(360))
        for fl in orden:
            r = np.array(res.levels.get(fl), dtype=float)
            color = _FL_COLORS[fl]
            axp.fill(theta, np.where(r > 0, r, 0.0), color=color, alpha=0.22)
            # Línea de contorno con los ceros enmascarados (no colapsa al centro).
            axp.plot(theta, np.where(r > 0, r, np.nan), color=color, linewidth=1.6,
                     label=f"FL{fl}")
        if theo > 0:
            axp.plot(theta, np.full(360, theo), color="#FF3366", linewidth=1.2,
                     linestyle="--", label=f"Teórica {theo:.0f}NM")
        axp.set_ylim(0, rmax)
        rticks = [t for t in (50, 100, 150, 200, 250, 300) if t <= rmax]
        axp.set_rticks(rticks)
        axp.set_yticklabels([f"{t} NM" for t in rticks], color=_FG, fontsize=7)
        axp.tick_params(colors=_FG, labelsize=8)
        axp.grid(color=_GRID, alpha=0.7)
        axp.set_title("Alcance por azimut (NM)", color=_FG, fontsize=9, pad=12)
        if orden:
            axp.legend(fontsize=7, loc="lower left", bbox_to_anchor=(-0.12, -0.12),
                       facecolor=_BG, edgecolor=_GRID, labelcolor=_FG)
        self.canvas_polar.draw_idle()

        # ---- MAPA ----
        self.fig_map.clear()
        self.fig_map.set_facecolor(_BG)
        axm = self.fig_map.add_subplot(111, facecolor=_BG)
        # Anillos de rango de referencia (círculos geodésicos).
        for nm in rticks:
            rlat, rlon = self._range_ring(res.radar_lat, res.radar_lon, nm)
            axm.plot(rlon, rlat, color=_GRID, linewidth=0.7, linestyle=":")
            axm.text(res.radar_lon, res.radar_lat + nm / 60.0, f"{nm}NM",
                     color=_GRID, fontsize=6, ha="center", va="bottom")
        for fl in orden:
            ring = level_polygon_latlon(res, fl)
            if ring:
                lons = [p[1] for p in ring]; lats = [p[0] for p in ring]
                color = _FL_COLORS[fl]
                axm.fill(lons, lats, color=color, alpha=0.18)
                axm.plot(lons, lats, color=color, linewidth=1.4, label=f"FL{fl}")
        if theo > 0:
            tlat, tlon = self._range_ring(res.radar_lat, res.radar_lon, theo)
            axm.plot(tlon, tlat, color="#FF3366", linewidth=1.3, linestyle="--",
                     label=f"Teórica {theo:.0f}NM")
        axm.plot([res.radar_lon], [res.radar_lat], marker="*", color="#00E5FF",
                 markersize=13, markeredgecolor="white", zorder=5)
        axm.set_xlabel("lon", color=_FG, fontsize=8)
        axm.set_ylabel("lat", color=_FG, fontsize=8)
        axm.tick_params(colors=_FG, labelsize=7)
        for spine in axm.spines.values():
            spine.set_color(_GRID)
        axm.grid(color=_GRID, alpha=0.3)
        # Corrección de aspecto lat/lon (1° lon < 1° lat según la latitud).
        axm.set_aspect(1.0 / max(0.1, math.cos(math.radians(res.radar_lat))))
        if orden:
            axm.legend(fontsize=7, facecolor=_BG, edgecolor=_GRID, labelcolor=_FG)
        self.canvas_map.draw_idle()

        # ---- VERTICAL (rango x altitud): envolvente de alcance por altura ----
        self._draw_vertical(orden, rmax, theo)

    def _draw_vertical(self, orden, rmax, theo):
        """Perfil vertical: para cada banda FL, hasta qué rango llega la cobertura.

        Es la envolvente geométrica (alcance por altura), distinta del Pd que ya
        muestra la pestaña PASS. Da el 'lóbulo vertical' del sensor.
        """
        res = self.result
        self.fig_vert.clear()
        self.fig_vert.set_facecolor(_BG)
        axv = self.fig_vert.add_subplot(111, facecolor=_BG)
        # Alcance representativo por banda = percentil 90 de los azimuts con dato.
        sel = set(self._selected_fls())
        ys, xs = [], []
        for fl in FL_BANDS:
            if fl not in sel:
                continue
            r = np.array(res.levels.get(fl) or [], dtype=float)
            r = r[r > 0]
            reach = float(np.percentile(r, 90)) if r.size else 0.0
            ys.append(fl); xs.append(reach)
        # Relleno del lóbulo (de 0 al alcance de cada banda) + línea de borde.
        axv.fill_betweenx(ys, 0, xs, color="#00E5FF", alpha=0.18, step="mid")
        axv.plot(xs, ys, color="#00E5FF", marker="o", linewidth=1.6)
        for fl, reach in zip(ys, xs):
            if reach > 0:
                axv.plot([reach], [fl], marker="o", color=_FL_COLORS[fl], markersize=6)
        if theo > 0:
            axv.axvline(theo, color="#FF3366", linestyle="--", linewidth=1.2,
                        label=f"Teórica {theo:.0f}NM")
            axv.legend(fontsize=7, facecolor=_BG, edgecolor=_GRID, labelcolor=_FG)
        axv.set_xlim(0, rmax); axv.set_ylim(0, max(FL_BANDS) + 50)
        axv.set_xlabel("Rango (NM)", color=_FG, fontsize=8)
        axv.set_ylabel("Nivel de vuelo (FL)", color=_FG, fontsize=8)
        axv.set_title("Cobertura vertical — alcance por altura", color=_FG, fontsize=9)
        axv.tick_params(colors=_FG, labelsize=7)
        for spine in axv.spines.values():
            spine.set_color(_GRID)
        axv.grid(color=_GRID, alpha=0.3)
        self.fig_vert.tight_layout()
        self.canvas_vert.draw_idle()

    @staticmethod
    def _range_ring(radar_lat, radar_lon, nm):
        """Círculo geodésico (lat[], lon[]) a `nm` millas náuticas del radar."""
        from utils.geo import GeoTools
        lats, lons = [], []
        d_m = GeoTools.nm_to_meters(nm)
        for az in range(0, 361, 5):
            la, lo = GeoTools.vincenty_forward(radar_lat, radar_lon, float(az % 360), d_m)
            lats.append(la); lons.append(lo)
        return lats, lons

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
