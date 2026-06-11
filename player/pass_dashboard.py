"""
pass_dashboard.py — Dashboard Premium de Evaluación PASS (PyQt6 & Matplotlib)
==============================================================================
Panel de visualización técnica y gráficos analíticos interactivos.
Estética Cyber Radar con Glassmorphic y alertas neón cian/verde/rojo.
"""

import sys
import os
import csv
import math
from typing import Dict, Tuple, List, Any, Optional

from PyQt6.QtWidgets import (
    QDialog, QWidget, QVBoxLayout, QHBoxLayout, QTableWidget,
    QTableWidgetItem, QTabWidget, QPushButton, QLabel, QGroupBox,
    QFileDialog, QMessageBox, QHeaderView, QComboBox
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QColor

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qtagg import NavigationToolbar2QT as NavigationToolbar
from matplotlib.figure import Figure
import matplotlib.pyplot as plt
import numpy as np

from utils.geo import obtener_centros_control
from analysis.rdqc_thresholds import load_profile, severity

# Intentar importar FPDF para PDF
try:
    from fpdf import FPDF
    HAS_FPDF = True
except ImportError:
    HAS_FPDF = False

# ============================================================
# PARÁMETROS ESTÉTICOS SURVEILLANCE
# ============================================================
COLOR_BG_CYBER = "#0B0E14"
COLOR_GLASS_GROUP = "rgba(20, 24, 33, 140)"
COLOR_ACCENT_CYAN = "#00E5FF"
COLOR_NEON_GREEN = "#39FF14"
COLOR_NEON_RED = "#FF3366"
COLOR_NEON_ORANGE = "#FF9900"

# ============================================================
# COMPONENTE DE SELECCIÓN MULTI-SENSOR
# ============================================================
from PyQt6.QtWidgets import QListView
from PyQt6.QtGui import QStandardItemModel, QStandardItem
from PyQt6.QtCore import QEvent

class CheckableComboBox(QComboBox):
    """QComboBox personalizado que permite selección múltiple usando checkboxes."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setView(QListView(self))
        self.view().viewport().installEventFilter(self)
        self.model = QStandardItemModel(self)
        self.setModel(self.model)
        self.model.dataChanged.connect(self._on_data_changed)
        self._changed = False
        self.setEditable(True)
        self.lineEdit().setReadOnly(True)
        self.lineEdit().setFocusPolicy(Qt.FocusPolicy.NoFocus)
        
    def eventFilter(self, widget, event):
        if widget == self.view().viewport() and event.type() == QEvent.Type.MouseButtonRelease:
            index = self.view().indexAt(event.pos())
            item = self.model.itemFromIndex(index)
            if item:
                state = Qt.CheckState.Unchecked if item.checkState() == Qt.CheckState.Checked else Qt.CheckState.Checked
                item.setCheckState(state)
                self._changed = True
            return True
        return super().eventFilter(widget, event)
        
    def showPopup(self):
        super().showPopup()
        self._changed = False
        
    def hidePopup(self):
        super().hidePopup()
        if self._changed:
            self.currentIndexChanged.emit(self.currentIndex())
            
    def add_checkable_item(self, text, data, checked=True):
        item = QStandardItem(text)
        item.setData(data, Qt.ItemDataRole.UserRole)
        item.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
        item.setCheckState(Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)
        self.model.appendRow(item)
        self._update_text()
        
    def get_checked_data(self) -> List[Any]:
        checked_data = []
        for i in range(self.model.rowCount()):
            item = self.model.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                checked_data.append(item.data(Qt.ItemDataRole.UserRole))
        return checked_data
        
    def _on_data_changed(self, top_left, bottom_right, roles):
        self._update_text()
        
    def _update_text(self):
        checked = []
        for i in range(self.model.rowCount()):
            item = self.model.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                checked.append(item.text())
        if not checked:
            self.setEditText("Ninguno seleccionado")
        elif len(checked) == self.model.rowCount():
            self.setEditText("Todos los sensores")
        elif len(checked) == 1:
            self.setEditText(checked[0])
        else:
            self.setEditText(f"{len(checked)} sensores seleccionados")

class PassDashboardDialog(QDialog):
    """
    Diálogo Dashboard de Evaluación PASS.
    Muestra tablas de calidad de radar y gráficos embebidos de Matplotlib.
    """

    def __init__(self, analysis_results: Dict[Tuple[int, int], Dict[str, Any]], parent=None):
        super().__init__(parent)
        # Extraer 'overlap_pairwise' para evitar errores de ordenación (TypeError de mezcla tuple y str)
        # y de claves faltantes en sumatorias de total_plots
        self.all_results = dict(analysis_results)
        self.overlap_pairwise = self.all_results.pop('overlap_pairwise', {})
        self.results = dict(self.all_results)
        
        self.setWindowTitle("Evaluación de Prestaciones Radar — Sistema PASS (SASS-C)")
        self.resize(1180, 780)
        self.setStyleSheet(self._get_cyber_stylesheet())
        
        self._setup_ui()
        self._load_table_data()

    def _get_cyber_stylesheet(self) -> str:
        return f"""
            QDialog {{
                background-color: {COLOR_BG_CYBER};
                border: 2px solid {COLOR_ACCENT_CYAN};
                border-radius: 10px;
            }}
            QTabWidget::pane {{
                border: 1px solid rgba(0, 229, 255, 60);
                background-color: rgba(14, 18, 27, 240);
                border-radius: 6px;
            }}
            QTabBar::tab {{
                background-color: #121824;
                color: #A0A5B5;
                border: 1px solid rgba(0, 229, 255, 40);
                border-bottom-color: none;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
                padding: 6px 16px;
                font-weight: bold;
                font-family: 'Segoe UI', sans-serif;
            }}
            QTabBar::tab:selected {{
                background-color: rgba(0, 229, 255, 20);
                color: {COLOR_ACCENT_CYAN};
                border: 1px solid {COLOR_ACCENT_CYAN};
                border-bottom-color: none;
            }}
            QTabBar::tab:hover {{
                color: {COLOR_NEON_GREEN};
                background-color: rgba(57, 255, 20, 10);
            }}
            QTableWidget {{
                background-color: #0E131F;
                border: 1px solid rgba(0, 229, 255, 60);
                gridline-color: rgba(0, 229, 255, 30);
                color: #FFFFFF;
                font-family: 'Consolas', 'Monospace';
                font-size: 10pt;
            }}
            QTableWidget::item {{
                padding: 5px;
            }}
            QHeaderView::section {{
                background-color: #161D2B;
                color: {COLOR_ACCENT_CYAN};
                padding: 4px;
                font-weight: bold;
                border: 1px solid rgba(0, 229, 255, 40);
            }}
            QGroupBox {{
                background-color: {COLOR_GLASS_GROUP};
                border: 1px solid rgba(0, 229, 255, 60);
                border-radius: 8px;
                margin-top: 15px;
                font-weight: bold;
                color: {COLOR_ACCENT_CYAN};
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                left: 15px;
                padding: 0 5px;
            }}
            QPushButton {{
                background-color: #121824;
                border: 1px solid {COLOR_ACCENT_CYAN};
                border-radius: 5px;
                color: {COLOR_ACCENT_CYAN};
                font-family: 'Segoe UI', sans-serif;
                font-size: 10pt;
                font-weight: bold;
                padding: 8px 18px;
            }}
            QPushButton:hover {{
                border: 1px solid {COLOR_NEON_GREEN};
                color: {COLOR_NEON_GREEN};
                background-color: rgba(57, 255, 20, 20);
            }}
            QPushButton:pressed {{
                background-color: rgba(57, 255, 20, 50);
            }}
            QLabel {{
                color: #FFFFFF;
                font-family: 'Segoe UI', sans-serif;
            }}
        """

    def _setup_ui(self):
        layout_main = QVBoxLayout(self)
        layout_main.setContentsMargins(15, 15, 15, 15)
        layout_main.setSpacing(10)
        
        # 1. Cabecera Informativa
        group_header = QGroupBox("Métricas Generales del Conjunto de Datos")
        layout_header = QHBoxLayout(group_header)
        layout_header.setContentsMargins(15, 15, 15, 15)
        
        total_plots = sum(r['total_plots'] for r in self.results.values())
        total_sensors = len(self.results)
        profile_label, _ = load_profile()
        profile_txt = profile_label or "perfil ICAO sin definir"

        self.lbl_stats = QLabel(
            f"📡 <b>Sensores Evaluados:</b> {total_sensors} | "
            f"📊 <b>Ploteos Analizados:</b> {total_plots} | "
            f"⚖ <b>Umbrales:</b> {profile_txt} | "
            f"<b>Estándar:</b> Eurocontrol SASS-C / EANA PASS"
        )
        self.lbl_stats.setFont(QFont("Segoe UI", 11))
        self.lbl_stats.setStyleSheet(f"color: {COLOR_ACCENT_CYAN};")
        layout_header.addWidget(self.lbl_stats)
        layout_header.addStretch()
        
        # Combo de filtrado por ACC regional
        lbl_filter = QLabel("<b>Filtrar por ACC:</b>")
        lbl_filter.setFont(QFont("Segoe UI", 10))
        lbl_filter.setStyleSheet("color: #FFFFFF; font-weight: bold;")
        
        self.combo_acc = QComboBox()
        self.combo_acc.addItems([
            "Todos los ACCs",
            "ACC Comodoro",
            "ACC Córdoba",
            "ACC Ezeiza",
            "ACC Mendoza",
            "ACC Resistencia"
        ])
        self.combo_acc.setStyleSheet("""
            QComboBox {
                background-color: #121824;
                color: #00E5FF;
                border: 1px solid #00E5FF;
                border-radius: 4px;
                padding: 4px 10px;
                min-width: 180px;
                font-weight: bold;
            }
            QComboBox QAbstractItemView {
                background-color: #0B0E14;
                color: #FFFFFF;
                selection-background-color: rgba(0, 229, 255, 40);
                selection-color: #00E5FF;
            }
        """)
        self.combo_acc.currentIndexChanged.connect(self._on_acc_filter_changed)
        
        layout_header.addWidget(lbl_filter)
        layout_header.addWidget(self.combo_acc)
        layout_main.addWidget(group_header)
        
        # Selector de Sensor para Gráficos (Evita colgar la app y simplifica la lectura)
        self.layout_selector = QHBoxLayout()
        self.lbl_sel_radar = QLabel("📊 <b>Visualizar Radar en Gráficos:</b>")
        self.lbl_sel_radar.setFont(QFont("Segoe UI", 10))
        self.lbl_sel_radar.setStyleSheet(f"color: {COLOR_NEON_GREEN}; background-color: transparent;")
        
        self.combo_sensor_charts = CheckableComboBox()
        self.combo_sensor_charts.setStyleSheet("""
            QComboBox {
                background-color: #121824;
                color: #00E5FF;
                border: 1px solid #00E5FF;
                border-radius: 4px;
                padding: 4px 10px;
                min-width: 250px;
                font-weight: bold;
            }
            QComboBox QAbstractItemView {
                background-color: #0B0E14;
                color: #FFFFFF;
                selection-background-color: rgba(0, 229, 255, 40);
                selection-color: #00E5FF;
            }
        """)
        self._populate_charts_combo()
        self.combo_sensor_charts.currentIndexChanged.connect(self._on_charts_sensor_changed)
        
        self.layout_selector.addWidget(self.lbl_sel_radar)
        self.layout_selector.addWidget(self.combo_sensor_charts)
        self.layout_selector.addStretch()
        layout_main.addLayout(self.layout_selector)
        
        # 2. Panel de pestañas principal (Tab Widget)
        self.tabs = QTabWidget()
        
        # --- Pestaña 1: Tabla de Métricas de Calidad ---
        self.tab_table = QWidget()
        layout_tab1 = QVBoxLayout(self.tab_table)
        
        # Layout horizontal para las dos tablas acopladas (congelada + desplazable)
        layout_tables = QHBoxLayout()
        layout_tables.setSpacing(0)
        layout_tables.setContentsMargins(0, 0, 0, 0)
        
        self.table_frozen = QTableWidget()
        self.table = QTableWidget()
        
        # Ocultar headers verticales en ambas tablas para alineamiento perfecto de filas
        self.table_frozen.verticalHeader().setVisible(False)
        self.table.verticalHeader().setVisible(False)
        
        # Deshabilitar barras de desplazamiento en la tabla congelada
        self.table_frozen.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.table_frozen.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        
        # Sincronizar scrollbars verticales bidireccionalmente
        self.table.verticalScrollBar().valueChanged.connect(self.table_frozen.verticalScrollBar().setValue)
        self.table_frozen.verticalScrollBar().valueChanged.connect(self.table.verticalScrollBar().setValue)
        
        layout_tables.addWidget(self.table_frozen)
        layout_tables.addWidget(self.table)
        layout_tab1.addLayout(layout_tables)
        
        self.tabs.addTab(self.tab_table, "📋 Tabla de Desempeño")
        
        # --- Pestaña 2: Gráficos de Cobertura Dinámicos ---
        self.tab_pd = QWidget()
        layout_tab2 = QVBoxLayout(self.tab_pd)
        
        # Fila de Selectores Dinámicos de Ejes (Alineado con Eje X y Eje Y)
        layout_axes = QHBoxLayout()
        lbl_x = QLabel("<b>Eje X:</b>")
        lbl_x.setStyleSheet("color: #FFFFFF; font-size: 10pt;")
        self.combo_axis_x = QComboBox()
        self.combo_axis_x.addItems(["Rango (NM)", "Acimut (°)", "Altitud (Miles de Pies)", "Tiempo (HH:MM:SS)"])
        
        lbl_y = QLabel("<b>Eje Y:</b>")
        lbl_y.setStyleSheet("color: #FFFFFF; font-size: 10pt;")
        self.combo_axis_y = QComboBox()
        self.combo_axis_y.addItems([
            "Probabilidad de Detección (Pd %)",
            "Altitud (Miles de Pies)",
            "Modo A (Squawk)",
            "Acimut (°)",
            "Rango (NM)"
        ])
        
        for combo in [self.combo_axis_x, self.combo_axis_y]:
            combo.setStyleSheet("""
                QComboBox {
                    background-color: #121824;
                    color: #00E5FF;
                    border: 1px solid #00E5FF;
                    border-radius: 4px;
                    padding: 3px 8px;
                    font-weight: bold;
                    min-width: 200px;
                    font-size: 9pt;
                }
                QComboBox QAbstractItemView {
                    background-color: #0B0E14;
                    color: #FFFFFF;
                    selection-background-color: rgba(0, 229, 255, 40);
                    selection-color: #00E5FF;
                }
            """)
            
        layout_axes.addWidget(lbl_x)
        layout_axes.addWidget(self.combo_axis_x)
        layout_axes.addWidget(lbl_y)
        layout_axes.addWidget(self.combo_axis_y)
        layout_axes.addStretch()
        layout_tab2.addLayout(layout_axes)
        
        self.canvas_pd = FigureCanvas(Figure(figsize=(8, 4), facecolor='#0B0E14'))
        self.toolbar_pd = NavigationToolbar(self.canvas_pd, self)
        
        layout_tab2.addWidget(self.toolbar_pd)
        layout_tab2.addWidget(self.canvas_pd)
        self.tabs.addTab(self.tab_pd, "📈 Cobertura Dinámica")
        
        # Conectores dinámicos
        self.combo_axis_x.currentIndexChanged.connect(self._plot_dynamic_coverage)
        self.combo_axis_y.currentIndexChanged.connect(self._plot_dynamic_coverage)
        
        # --- Pestaña 3: Residuos Polares / Alineación de Antena ---
        self.tab_residuals = QWidget()
        layout_tab3 = QVBoxLayout(self.tab_residuals)
        self.canvas_res = FigureCanvas(Figure(figsize=(8, 4), facecolor='#0B0E14'))
        self.toolbar_res = NavigationToolbar(self.canvas_res, self)
        layout_tab3.addWidget(self.toolbar_res)
        layout_tab3.addWidget(self.canvas_res)
        self.tabs.addTab(self.tab_residuals, "🎯 Residuos Polares")
        
        # --- Pestaña 4: Distribuciones de Histograma y Ajuste Gaussiano ---
        self.tab_hist = QWidget()
        layout_tab4 = QVBoxLayout(self.tab_hist)
        self.canvas_hist = FigureCanvas(Figure(figsize=(8, 4), facecolor='#0B0E14'))
        self.toolbar_hist = NavigationToolbar(self.canvas_hist, self)
        layout_tab4.addWidget(self.toolbar_hist)
        layout_tab4.addWidget(self.canvas_hist)
        self.tabs.addTab(self.tab_hist, "📊 Histogramas de Jitter")
        
        # --- Pestaña 5: Cobertura Polar y Vertical SASS-C ---
        self.tab_sass_c = QWidget()
        layout_tab5 = QVBoxLayout(self.tab_sass_c)
        self.canvas_sass_c = FigureCanvas(Figure(figsize=(8, 4), facecolor='#0B0E14'))
        self.toolbar_sass_c = NavigationToolbar(self.canvas_sass_c, self)
        layout_tab5.addWidget(self.toolbar_sass_c)
        layout_tab5.addWidget(self.canvas_sass_c)
        self.tabs.addTab(self.tab_sass_c, "🌐 Cobertura SASS-C (Polar/Vertical)")

        # --- Pestaña 6: Parámetros Avanzados (Range Gain, Delays, Reflexiones) ---
        self.tab_advanced = QWidget()
        layout_tab6 = QVBoxLayout(self.tab_advanced)
        self.canvas_adv = FigureCanvas(Figure(figsize=(12, 4), facecolor='#0B0E14'))
        self.toolbar_adv = NavigationToolbar(self.canvas_adv, self)
        layout_tab6.addWidget(self.toolbar_adv)
        layout_tab6.addWidget(self.canvas_adv)
        self.tabs.addTab(self.tab_advanced, "⚡ Parámetros Avanzados")

        # --- Pestaña 7: Comparativa de Solapamiento (Overlap Pd) ---
        self.tab_overlap = QWidget()
        layout_tab7 = QVBoxLayout(self.tab_overlap)
        
        # Fila de control para seleccionar el tipo de gráfico de solapamiento
        layout_ov_controls = QHBoxLayout()
        lbl_ov_type = QLabel("<b>Tipo de Gráfico de Solapamiento:</b>")
        lbl_ov_type.setStyleSheet("color: #FFFFFF; font-size: 10pt; font-weight: bold;")
        
        self.combo_ov_type = QComboBox()
        self.combo_ov_type.addItems([
            "Matriz de Calor (Heatmap 2D)",
            "Curvas de Pd vs. Rango (Transición)",
            "Pd vs. Nivel de Vuelo (FL)"
        ])
        self.combo_ov_type.setStyleSheet("""
            QComboBox {
                background-color: #121824;
                color: #00E5FF;
                border: 1px solid #00E5FF;
                border-radius: 4px;
                padding: 4px 10px;
                min-width: 280px;
                font-weight: bold;
                font-size: 9pt;
            }
            QComboBox QAbstractItemView {
                background-color: #0B0E14;
                color: #FFFFFF;
                selection-background-color: rgba(0, 229, 255, 40);
                selection-color: #00E5FF;
            }
        """)
        self.combo_ov_type.currentIndexChanged.connect(self._plot_overlap_comparison)
        
        layout_ov_controls.addWidget(lbl_ov_type)
        layout_ov_controls.addWidget(self.combo_ov_type)
        layout_ov_controls.addStretch()
        layout_tab7.addLayout(layout_ov_controls)
        
        self.canvas_ov = FigureCanvas(Figure(figsize=(10, 4), facecolor='#0B0E14'))
        self.toolbar_ov = NavigationToolbar(self.canvas_ov, self)
        layout_tab7.addWidget(self.toolbar_ov)
        layout_tab7.addWidget(self.canvas_ov)
        self.tabs.addTab(self.tab_overlap, "🤝 Comparación de Solapamiento")

        layout_main.addWidget(self.tabs)
        
        # 3. Fila de Botones de Acción inferior
        layout_buttons = QHBoxLayout()
        
        self.btn_export_csv = QPushButton("Exportar Tabla (CSV)")
        self.btn_export_pdf = QPushButton("Generar Reporte PASS (PDF)")
        self.btn_close = QPushButton("Cerrar")
        
        layout_buttons.addWidget(self.btn_export_csv)
        layout_buttons.addWidget(self.btn_export_pdf)
        layout_buttons.addStretch()
        layout_buttons.addWidget(self.btn_close)
        
        layout_main.addLayout(layout_buttons)
        
        # Conexiones
        self.btn_close.clicked.connect(self.accept)
        self.btn_export_csv.clicked.connect(self._export_csv)
        self.btn_export_pdf.clicked.connect(self._export_pdf)
        
        self.tabs.currentChanged.connect(self._on_tab_changed)

        # Deshabilitar botones nativos defectuosos de Pan/Zoom que deforman gráficos polares
        self._deshabilitar_pan_zoom_polar(self.toolbar_res)
        self._deshabilitar_pan_zoom_polar(self.toolbar_sass_c)

    def _deshabilitar_pan_zoom_polar(self, toolbar):
        """
        Remueve o deshabilita los botones nativos de Pan y Zoom de la barra de Matplotlib,
        para evitar que el usuario deforme las proyecciones polares, ya que la navegación 
        de Matplotlib por defecto distorsiona los gráficos circulares.
        En su lugar se cuenta con Zoom y Pan interactivo de alta calidad nativo.
        """
        try:
            for action in toolbar.actions():
                text = str(action.text()).lower()
                tooltip = str(action.toolTip()).lower()
                # Ocultar botones de 'pan' (desplazamiento) y 'zoom' (recuadro de zoom) en cualquier idioma
                if any(k in text or k in tooltip for k in ('pan', 'zoom', 'mover', 'arrastrar', 'rectángulo', 'zoom rectangular')):
                    action.setVisible(False)
                    action.setEnabled(False)
        except Exception:
            pass

    def _load_table_data(self):
        """Carga los resultados estadísticos transponiendo la QTableWidget (sensores en cabecera y parámetros en filas)."""
        # 1. Definir los encabezados (uno por cada sensor)
        sensors_list = sorted(self.results.items())
        
        # Tabla Congelada (Parámetro y Referencia)
        self.table_frozen.setColumnCount(2)
        self.table_frozen.setHorizontalHeaderLabels(["PARÁMETRO", "REFER."])
        self.table_frozen.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        self.table_frozen.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        self.table_frozen.setColumnWidth(0, 280)
        self.table_frozen.setColumnWidth(1, 95)
        self.table_frozen.setFixedWidth(377)
        
        # Tabla Desplazable (Radares)
        headers = []
        for sac_sic, data in sensors_list:
            headers.append(f"{data['name']}\n({sac_sic[0]}/{sac_sic[1]})")
            
        self.table.setColumnCount(len(headers))
        self.table.setHorizontalHeaderLabels(headers)
        
        # Ajustar el ancho de las secciones de la cabecera de forma dinámica
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        
        # Si hay demasiados sensores (más de 5), habilitamos el desplazamiento horizontal 
        # dando un ancho mínimo cómodo (130px) para que sean completamente legibles.
        if len(headers) > 5:
            for col_idx in range(len(headers)):
                self.table.horizontalHeader().setSectionResizeMode(col_idx, QHeaderView.ResizeMode.Interactive)
                self.table.setColumnWidth(col_idx, 130)
            self.table.horizontalHeader().setMinimumSectionSize(110)
        else:
            for col_idx in range(len(headers)):
                self.table.horizontalHeader().setSectionResizeMode(col_idx, QHeaderView.ResizeMode.Stretch)

        # 2. Definir los parámetros medidos (filas). Las referencias y el semáforo
        #    provienen de config/rdqc_thresholds.json (ICAO Doc 8071, Tablas 3-1/3-2).
        profile_label, thresholds = load_profile()
        sev_colors = {"ok": COLOR_NEON_GREEN, "warn": COLOR_NEON_ORANGE, "bad": COLOR_NEON_RED}

        # (nombre, clave, formato). El umbral/referencia se resuelve por clave.
        rows_def = [
            ("Muestras (Ploteos)", "total_plots", "{:.0f}"),
            ("Período de Giro (s/vuelta)", "rpm", lambda v: f"{60.0/v:.2f} s" if v > 0 else "0.00 s"),
            ("Prob. Detección SSR", "pd_global", "{:.2f}%"),
            ("Prob. Detección por Solapamiento (Overlap Pd)", "pd_overlap", lambda v: f"{v:.2f}%" if v > 0.0 else "N/A"),
            ("Prob. Detección vs ADS-B (Co-detección)", "pd_vs_adsb", lambda v: f"{v:.2f}%" if v is not None else "N/A"),
            ("Prob. Global de Detección Modo A", "pd_mode_a", "{:.2f}%"),
            ("Prob. Global de Detección Modo C", "pd_mode_c", "{:.2f}%"),
            ("Sesgo en Distancia (m)", "range_bias_m", "{:+.1f}"),
            ("Sesgo en Acimut (°)", "azimuth_bias_deg", "{:+.3f}°"),
            ("Jitter en Distancia (m)", "range_jitter_m", "{:.1f}"),
            ("Jitter en Acimut (°)", "azimuth_jitter_deg", "{:.3f}°"),
            ("% de Split Plots", "split_plots_pct", "{:.2f}%"),
            ("Ganancia en Distancia", "range_gain_slope", "{:+.4f}"),
            ("Delay Medio Transmisión (s)", "delay_mean", "{:.3f}"),
            ("Tasa de Reflexión (%)", "reflection_rate", "{:.2f}%"),
        ]

        self.table_frozen.setRowCount(len(rows_def))
        self.table.setRowCount(len(rows_def))
        
        for row_idx, (param_name, key, fmt) in enumerate(rows_def):
            spec = thresholds.get(key)
            ref_val = spec["ref"] if spec else "-"
            # Col 0: Parámetro
            item_name = self._create_item(param_name)
            item_name.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            font_name = item_name.font()
            font_name.setBold(True)
            item_name.setFont(font_name)
            item_name.setForeground(QColor(COLOR_ACCENT_CYAN))
            self.table_frozen.setItem(row_idx, 0, item_name)
            
            # Col 1: Referencia
            item_ref = self._create_item(ref_val)
            item_ref.setForeground(QColor(COLOR_NEON_GREEN))
            font_ref = item_ref.font()
            font_ref.setBold(True)
            item_ref.setFont(font_ref)
            item_ref.setBackground(QColor("#0E2322")) # Fondo verde/cian oscuro
            self.table_frozen.setItem(row_idx, 1, item_ref)
            
            # Col 0..N-1: Sensores
            for col_idx, (sac_sic, data) in enumerate(sensors_list):
                val = data.get(key, 0.0)
                
                if val is None:
                    text_val = "N/A"
                    color = None
                else:
                    # Formatear el valor
                    if callable(fmt):
                        text_val = fmt(val)
                    else:
                        text_val = fmt.format(val)
                        
                    # Semáforo ICAO: la severidad sale del umbral del perfil activo.
                    # Si el valor no está disponible (N/A) no se colorea.
                    color = None if text_val == "N/A" else sev_colors.get(severity(spec, val))

                item_val = self._create_item(text_val)
                if color:
                    item_val.setForeground(QColor(color))
                    
                self.table.setItem(row_idx, col_idx, item_val)
                
        # Sincronizar perfectamente la altura de las filas
        for r in range(len(rows_def)):
            self.table_frozen.setRowHeight(r, 30)
            self.table.setRowHeight(r, 30)

    def _create_item(self, text: str) -> QTableWidgetItem:
        item = QTableWidgetItem(text)
        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        return item

    def _on_tab_changed(self, index: int):
        """Redibuja los gráficos Matplotlib cuando se selecciona su pestaña."""
        if index == 1:
            self._plot_dynamic_coverage()
        elif index == 2:
            self._plot_polar_residuals()
        elif index == 3:
            self._plot_histograms()
        elif index == 4:
            self._plot_sass_c_diagrams()
        elif index == 5:
            self._plot_advanced_parameters()
        elif index == 6:
            self._plot_overlap_comparison()

    def _populate_charts_combo(self):
        # Desconectar temporalmente para evitar gatillar refrescos múltiples al limpiar
        try:
            self.combo_sensor_charts.currentIndexChanged.disconnect(self._on_charts_sensor_changed)
        except Exception:
            pass
            
        prev_checked = self.combo_sensor_charts.get_checked_data()
        self.combo_sensor_charts.model.clear()
        
        first_time = not prev_checked
        
        for sac_sic, data in sorted(self.results.items()):
            should_check = first_time or (sac_sic in prev_checked)
            self.combo_sensor_charts.add_checkable_item(
                f"[{sac_sic[0]}/{sac_sic[1]}] {data['name']}",
                sac_sic,
                checked=should_check
            )
            
        self.combo_sensor_charts.currentIndexChanged.connect(self._on_charts_sensor_changed)

    def _on_acc_filter_changed(self):
        acc_text = self.combo_acc.currentText()
        
        # Filtrar resultados
        if acc_text == "Todos los ACCs":
            self.results = dict(self.all_results)
        else:
            target_acc = acc_text.replace("ACC ", "")
            filtered = {}
            for sac_sic, data in self.all_results.items():
                accs = obtener_centros_control(data['name'], sac_sic[0], sac_sic[1])
                if target_acc in accs:
                    filtered[sac_sic] = data
            self.results = filtered
            
        # Actualizar tabla
        self._load_table_data()
        
        # Actualizar combo de gráficos
        self._populate_charts_combo()
        
        # Actualizar contadores en la cabecera
        total_plots = sum(r['total_plots'] for r in self.results.values())
        total_sensors = len(self.results)
        self.lbl_stats.setText(
            f"📡 <b>Sensores Evaluados:</b> {total_sensors} | "
            f"📊 <b>Ploteos Analizados:</b> {total_plots} | "
            f"⚖ <b>Estándar de Evaluación:</b> Eurocontrol SASS-C / EANA PASS"
        )
        
        # Refrescar la pestaña actual para actualizar los gráficos
        self._on_tab_changed(self.tabs.currentIndex())

    def _on_charts_sensor_changed(self, index: int):
        self._on_tab_changed(self.tabs.currentIndex())

    # ============================================================
    # RENDERIZADO DE GRÁFICOS MATPLOTLIB
    # ============================================================

    def _plot_sass_c_diagrams(self):
        """Dibuja los diagramas de cobertura Polar y Vertical oficiales de SASS-C."""
        self.canvas_sass_c.figure.clear()
        fig = self.canvas_sass_c.figure
        
        # 1. Configuración de Subplot 1 (Polar)
        ax1 = fig.add_subplot(121, projection='polar')
        ax1.set_facecolor('#0E131F')
        ax1.tick_params(colors='#A0A5B5', labelsize=8)
        ax1.grid(True, color='#ffffff', alpha=0.15, linestyle=':')
        
        # 2. Configuración de Subplot 2 (Vertical)
        ax2 = fig.add_subplot(122)
        ax2.set_facecolor('#0E131F')
        ax2.tick_params(colors='#A0A5B5', labelsize=9)
        ax2.xaxis.label.set_color('#A0A5B5')
        ax2.yaxis.label.set_color('#A0A5B5')
        ax2.grid(True, color='#ffffff', alpha=0.15, linestyle=':')
        
        selected_keys = self.combo_sensor_charts.get_checked_data()
        items_to_plot = [(key, self.results[key]) for key in selected_keys if key in self.results]
        
        # SASS-C Color Mapping Function
        def get_sass_c_color(pd):
            if pd == 100.0:
                return "#2C5A59"  # Teal oscuro premium de SASS-C
            elif pd >= 97.0:
                return "#02C39A"  # Verde brillante / Esmeralda
            elif pd >= 95.0:
                return "#FFD700"  # Amarillo de advertencia
            else:
                return "#FF5A5F"  # Rojo de degradación
                
        has_data = False
        
        # Dibujar diagramas para los sensores seleccionados
        for sac_sic, data in items_to_plot:
            polar_grid = data.get('polar_pd_grid', [])
            vertical_grid = data.get('vertical_pd_grid', [])
            
            # --- RENDERIZADO POLAR (Izquierda) ---
            if polar_grid:
                has_data = True
                width = np.radians(10)
                for bin_data in polar_grid:
                    r = bin_data['r_nm']
                    az_deg = bin_data['az_deg']
                    pd_val = bin_data['pd']
                    
                    theta = np.radians(az_deg + 5) # Centro del bin
                    color = get_sass_c_color(pd_val)
                    
                    # Dibujar sector polar
                    ax1.bar(theta, 20, width=width, bottom=r, color=color, edgecolor='none', alpha=0.85)
                    
            # --- RENDERIZADO VERTICAL (Derecha) ---
            if vertical_grid:
                has_data = True
                
                # Límites del seno para elevaciones de [-0.5°, 20.0°]
                sin_min = math.sin(math.radians(-0.5))
                sin_max = math.sin(math.radians(20.0))
                
                def get_cell_polygon_pts(r1, r2, f1, f2):
                    # Borde inferior: constant f1, range de r1 a r2
                    pts_bottom = []
                    r_vals = np.linspace(r1, r2, 10)
                    for r in r_vals:
                        pts_bottom.append((r, f1 - 0.00662 * (r**2)))
                        
                    # Borde derecho: constant r2, FL de f1 a f2
                    pts_right = []
                    fl_vals = np.linspace(f1, f2, 10)
                    for fl in fl_vals:
                        pts_right.append((r2, fl - 0.00662 * (r2**2)))
                        
                    # Borde superior: constant f2, range de r2 a r1
                    pts_top = []
                    r_vals_rev = np.linspace(r2, r1, 10)
                    for r in r_vals_rev:
                        pts_top.append((r, f2 - 0.00662 * (r**2)))
                        
                    # Borde izquierdo: constant r1, FL de f2 a f1
                    pts_left = []
                    fl_vals_rev = np.linspace(f2, f1, 10)
                    for fl in fl_vals_rev:
                        pts_left.append((r1, fl - 0.00662 * (r1**2)))
                        
                    return pts_bottom + pts_right + pts_top + pts_left

                for bin_data in vertical_grid:
                    r1 = bin_data['r_nm']
                    r2 = r1 + 20
                    h1 = bin_data['alt_kft']
                    h2 = h1 + 5
                    f1 = h1 * 10.0
                    f2 = h2 * 10.0
                    pd_val = bin_data['pd']
                    
                    color = get_sass_c_color(pd_val)
                    poly_pts = get_cell_polygon_pts(r1, r2, f1, f2)
                    
                    from matplotlib.patches import Polygon
                    poly = Polygon(poly_pts, closed=True, facecolor=color, alpha=0.85, edgecolor='none')
                    ax2.add_patch(poly)
                    
        # Configurar límites y ticks del Polar (Subplot 1)
        ax1.set_ylim(0, 240)
        ax1.set_yticks([40, 80, 120, 160, 200, 240])
        ax1.set_yticklabels(["40 NM", "80 NM", "120 NM", "160 NM", "200 NM", "240 NM"], color='#A0A5B5', fontsize=8)
        ax1.set_theta_zero_location('N') # El Norte arriba
        ax1.set_theta_direction(-1)     # Dirección horaria (rotación radar)
        ax1.set_title("Diagrama de Cobertura Polar SASS-C (Pd %)", color=COLOR_ACCENT_CYAN, pad=15, fontsize=10, fontweight='bold')
        
        # Configurar límites y aspecto del Vertical (Subplot 2 - Grilla Cartesiana Curvada SASS-C)
        ax2.axis('off') # Ocultar ejes Cartesianos estándar
        # Rango X: -15 NM a 260 NM para centrar bien la gráfica
        ax2.set_xlim(-15, 260)
        # Rango Y: -420 FL a 530 FL (para acomodar la curvatura de la Tierra a 240 NM)
        ax2.set_ylim(-420, 530)
        ax2.set_title("Diagrama de Cobertura Vertical SASS-C (Pd %)", color=COLOR_ACCENT_CYAN, pad=15, fontsize=10, fontweight='bold')
        
        # 0. Dibujar la línea de curvatura de la Tierra (Horizonte Radar físico de H = 0)
        # H = 0 => y = -0.00662 * x^2
        x_surf = np.linspace(0.0, 240.0, 100)
        y_surf = -0.00662 * (x_surf**2)
        
        # Rellenar la zona de sombra física debajo de la superficie de la Tierra (zona ciega de no detección por curvatura)
        x_fill = [0.0] + list(x_surf) + [240.0, 0.0]
        y_fill = [0.0] + list(y_surf) + [-420.0, -420.0]
        ax2.fill(x_fill, y_fill, facecolor='#1C161D', edgecolor='#D32F2F', 
                 linewidth=1.2, alpha=0.7, hatch='//', label='Curvatura Terrestre')
        
        # Agregar etiqueta descriptiva debajo de la línea de curvatura terrestre
        ax2.text(140, -0.00662 * (140**2) - 15, "Horizonte Radar / Curvatura Terrestre (0° Elev.)", 
                 color='#FF5252', fontsize=7.5, rotation=-8, ha='center', va='top', fontweight='bold')
        
        # Dibujar la zona de sombra cenital (Cono de Silencio del Radar)
        # Angulo máximo de elevación física en radar es de 20.0 grados.
        # En esta proyección, la línea de 20.0° es y = x * 60.76115 * sin(20°)
        # El cono de silencio cubre el espacio a la izquierda de la línea de 20.0° hasta el eje Y (x=0)
        sin_20 = math.sin(math.radians(20.0))
        B_20 = 60.76115 * sin_20
        # Encontrar intersección de la línea de 20.0° con la curva FL 500:
        # 0.00662 * x^2 + B_20 * x - 500 = 0
        x_int = (-B_20 + math.sqrt(B_20**2 + 13.24)) / 0.01324
        
        # Polígono para rellenar el Cono de Silencio
        x_cone_vals = np.linspace(0.0, x_int, 50)
        pts_cone = [(0.0, 0.0)]
        # Borde superior: curva de FL 500 de x_int a 0
        for x in reversed(x_cone_vals):
            pts_cone.append((x, 500.0 - 0.00662 * (x**2)))
        pts_cone.append((0.0, 0.0))
        
        from matplotlib.patches import Polygon
        poly_cone = Polygon(pts_cone, closed=True, facecolor='#2B2D35', edgecolor='#A0A5B5', linewidth=0.8, alpha=0.5, hatch='\\\\', label='Cono de Silencio')
        ax2.add_patch(poly_cone)
        ax2.text(15, 260, "Cono de\nSilencio\n(>20°)", color='#A0A5B5', fontsize=8, ha='center', va='center', fontweight='bold')
        
        # 1. Dibujar línea de eje Y vertical y ticks de FL
        # El eje Y representa el rango 0, de y = 0 a y = 500 FL
        ax2.plot([0, 0], [0, 500], color='#A0A5B5', alpha=0.6, linewidth=1.2)
        fl_levels = [0, 50, 100, 150, 200, 250, 300, 350, 400, 450, 500]
        for fl in fl_levels:
            ax2.plot([-4, 0], [fl, fl], color='#A0A5B5', alpha=0.6, linewidth=1.0)
            ax2.text(-7, fl, f"{fl}", color='#A0A5B5', fontsize=8.5, ha='right', va='center')
        ax2.text(-28, 250, "Nivel de Vuelo (FL)", color='#A0A5B5', fontsize=9.5, rotation=90, va='center', ha='center')
        
        # 2. Dibujar línea de eje X horizontal y ticks de rango
        # El eje X horizontal representa la línea tangente al radar a elevación 0° (y = 0)
        ax2.plot([0, 240], [0, 0], color='#A0A5B5', alpha=0.6, linewidth=1.2)
        for r in [0, 60, 120, 180, 240]:
            # Dibujar ticks en el eje X
            ax2.plot([r, r], [-6, 0], color='#A0A5B5', alpha=0.6, linewidth=1.0)
            ax2.text(r, -15, f"{r:.1f}", color='#A0A5B5', fontsize=8.5, ha='center')
        ax2.text(120, -32, "Distancia al Radar (NM)", color='#A0A5B5', fontsize=9.5, ha='center')
        
        # 3. Superponer líneas de elevación constantes (Rectas que irradian desde el origen)
        elevations = [-0.5, -0.3, 0.0, 0.3, 0.5, 0.8, 1.0, 1.3, 1.5, 1.8, 2.0, 2.5, 3.0, 4.0, 5.0, 7.5, 20.0]
        for el in elevations:
            if el == 0.0:
                continue # Ya dibujado como el eje X
                
            sin_el = math.sin(math.radians(el))
            B_el = 60.76115 * sin_el
            
            if el > 0.0:
                # Intersección con el límite superior (FL 500)
                x_end = (-B_el + math.sqrt(B_el**2 + 13.24)) / 0.01324
                if x_end > 240.0:
                    x_end = 240.0
                    y_end = 240.0 * B_el
                else:
                    y_end = 500.0 - 0.00662 * (x_end**2)
            else:
                # Intersección con la superficie de la Tierra (H = 0 => y = -0.00662 * x^2)
                # x * B_el = -0.00662 * x^2 => x = -B_el / 0.00662
                x_end = -B_el / 0.00662
                if x_end > 240.0:
                    x_end = 240.0
                    y_end = 240.0 * B_el
                else:
                    y_end = -0.00662 * (x_end**2)
                    
            linestyle = '-' if el <= 0.0 else '--'
            linewidth = 0.8
            ax2.plot([0, x_end], [0, y_end], color='#ffffff', alpha=0.35, linestyle=linestyle, linewidth=linewidth)
            
            # Etiqueta al final de la línea recta de elevación
            if el > 0.0:
                if x_end < 240.0:
                    # En la curva superior FL 500
                    ax2.text(x_end, y_end + 6, f"{el}°", color='#A0A5B5', fontsize=8, ha='center', va='bottom')
                else:
                    # En el límite derecho de 240 NM
                    ax2.text(x_end + 3, y_end, f"{el}°", color='#A0A5B5', fontsize=8, ha='left', va='center')
            else:
                if x_end < 240.0:
                    # En la superficie de la Tierra
                    ax2.text(x_end + 2, y_end - 6, f"{el}°", color='#A0A5B5', fontsize=8, ha='left', va='top')
                else:
                    # En el límite derecho
                    ax2.text(x_end + 3, y_end, f"{el}°", color='#A0A5B5', fontsize=8, ha='left', va='center')
                    
        # 4. Dibujar líneas verticales de rango (NM) desde la superficie de la Tierra hasta la curva de FL 500
        for r in [40, 80, 120, 160, 200, 240]:
            y_start = -0.00662 * (r**2)
            y_end = 500.0 - 0.00662 * (r**2)
            ax2.plot([r, r], [y_start, y_end], color='#ffffff', alpha=0.25, linestyle=':')
            # Etiqueta de rango en la curva de la Tierra
            ax2.text(r, y_start - 12, f"{r}", color='#A0A5B5', fontsize=8, ha='center', va='top')
            
        # 5. Superponer curvas de Flight Levels (Curvas de altitud constante según 4/3 del radio terrestre)
        # y = fl - 0.00662 * x^2
        x_c = np.linspace(0.0, 240.0, 100)
        fl_levels = [50, 100, 150, 200, 250, 300, 350, 400, 450, 500]
        for fl in fl_levels:
            y_c = fl - 0.00662 * (x_c**2)
            ax2.plot(x_c, y_c, color='#ffffff', alpha=0.22, linestyle='-', linewidth=0.8)
                
        # Agregar leyenda de colores SASS-C
        from matplotlib.patches import Patch
        legend_elements = [
            Patch(facecolor='#2C5A59', label='[100%] Excelente'),
            Patch(facecolor='#02C39A', label='[97 - 100%) Cumple'),
            Patch(facecolor='#FFD700', label='[95 - 97%) Tolerancia'),
            Patch(facecolor='#FF5A5F', label='[0 - 95%) Degradado')
        ]
        ax2.legend(handles=legend_elements, facecolor='#0E131F', labelcolor='#FFFFFF', loc='upper right', fontsize=8)
        
        fig.tight_layout()
        self.canvas_sass_c.draw()

    # ============================================================
    # RENDERIZADO DE GRÁFICOS MATPLOTLIB
    # ============================================================

    def _plot_dynamic_coverage(self):
        """Dibuja el gráfico de cobertura dinámico basado en las selecciones de Eje X y Eje Y."""
        self.canvas_pd.figure.clear()
        fig = self.canvas_pd.figure
        ax = fig.add_subplot(111)
        
        ax.set_facecolor('#0E131F')
        ax.tick_params(colors='#A0A5B5', labelsize=10)
        ax.xaxis.label.set_color('#A0A5B5')
        ax.yaxis.label.set_color('#A0A5B5')
        ax.title.set_color(COLOR_ACCENT_CYAN)
        ax.grid(True, color='#ffffff', alpha=0.1, linestyle='--')
        
        selected_keys = self.combo_sensor_charts.get_checked_data()
        items_to_plot = [(key, self.results[key]) for key in selected_keys if key in self.results]
        
        axis_x_text = self.combo_axis_x.currentText()
        axis_y_text = self.combo_axis_y.currentText()
        
        has_data = False
        
        # Formateador de tiempo HH:MM:SS
        import matplotlib.ticker as ticker
        def format_tod(x, pos):
            total_seconds = int(max(0, x))
            hours = (total_seconds // 3600) % 24
            minutes = (total_seconds // 60) % 60
            seconds = total_seconds % 60
            return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
            
        if axis_x_text == "Tiempo (HH:MM:SS)":
            ax.xaxis.set_major_formatter(ticker.FuncFormatter(format_tod))
            
        if axis_y_text == "Probabilidad de Detección (Pd %)":
            # Gráficos de curvas de probabilidad (Línea)
            for sac_sic, data in items_to_plot:
                curve = []
                if axis_x_text == "Rango (NM)":
                    curve = data.get('pd_vs_range', [])
                elif axis_x_text == "Acimut (°)":
                    curve = data.get('pd_vs_azimuth', [])
                elif axis_x_text == "Altitud (Miles de Pies)":
                    curve = data.get('pd_vs_fl', [])
                elif axis_x_text == "Tiempo (HH:MM:SS)":
                    curve = data.get('pd_vs_time', [])
                    
                if curve:
                    has_data = True
                    xs = [pt[0] for pt in curve]
                    ys = [pt[1] for pt in curve]
                    ax.plot(xs, ys, marker='o', linewidth=2, label=f"{data['name']}")
                    
            if has_data:
                ax.axhline(95.0, color=COLOR_NEON_GREEN, linestyle='--', alpha=0.8, linewidth=1.5, label="Meta SASS-C Pd Gen (≥95%)")
                ax.axhline(98.0, color=COLOR_ACCENT_CYAN, linestyle=':', alpha=0.8, linewidth=1.5, label="Meta SASS-C Modo A (≥98%)")

            ax.set_ylim(0, 105)
            ax.set_ylabel("Probabilidad de Detección (Pd %)")
            ax.set_xlabel(axis_x_text)
            ax.set_title(f"Probabilidad de Detección vs {axis_x_text}")
        else:
            # Gráficos de dispersión de ploteos (Scatter)
            # Mapeo de campos
            field_map = {
                "Rango (NM)": "range_nm",
                "Acimut (°)": "azimuth",
                "Altitud (Miles de Pies)": "flight_level",
                "Tiempo (HH:MM:SS)": "time",
                "Modo A (Squawk)": "mode3a"
            }
            
            x_field = field_map.get(axis_x_text)
            y_field = field_map.get(axis_y_text)
            
            for sac_sic, data in items_to_plot:
                plots_list = data.get('plots_data', [])
                if plots_list:
                    # Extraer coordenadas válidas
                    xs = []
                    ys = []
                    for pt in plots_list:
                        vx = pt.get(x_field)
                        vy = pt.get(y_field)
                        if vx is not None and vy is not None:
                            # Prevenir valores negativos para Rango y Altitud
                            if x_field in ['range_nm', 'flight_level']:
                                    vx = max(0.0, vx)
                            if y_field in ['range_nm', 'flight_level']:
                                    vy = max(0.0, vy)
                            xs.append(vx)
                            ys.append(vy)
                            
                    if xs:
                        has_data = True
                        # Reducir número de puntos para evitar colgar la UI si hay demasiados
                        max_pts = 3000 if len(selected_keys) == 1 else 1000
                        if len(xs) > max_pts:
                            indices = np.random.choice(len(xs), max_pts, replace=False)
                            xs_plot = [xs[i] for i in indices]
                            ys_plot = [ys[i] for i in indices]
                        else:
                            xs_plot = xs
                            ys_plot = ys
                            
                        ax.scatter(xs_plot, ys_plot, s=15, alpha=0.6, label=f"{data['name']}")
                        
            ax.set_ylabel(axis_y_text)
            ax.set_xlabel(axis_x_text)
            ax.set_title(f"Dispersión: {axis_y_text} vs {axis_x_text}")
            
        if has_data:
            ax.legend(facecolor='#0E131F', labelcolor='#FFFFFF', loc='upper right')
            
        fig.tight_layout()
        self.canvas_pd.draw()

    def _plot_polar_residuals(self):
        """Dibuja los residuos de distancia y acimut en representación Polar."""
        self.canvas_res.figure.clear()
        fig = self.canvas_res.figure
        
        # Representación de Dispersión de Errores
        ax = fig.add_subplot(111, projection='polar')
        ax.set_facecolor('#0E131F')
        ax.tick_params(colors='#A0A5B5')
        ax.grid(True, color='#ffffff', alpha=0.1, linestyle='--')
        ax.set_theta_zero_location('N')
        ax.set_theta_direction(-1)
        
        selected_keys = self.combo_sensor_charts.get_checked_data()
        items_to_plot = [(key, self.results[key]) for key in selected_keys if key in self.results]
        
        has_data = False
        sc = None
        for sac_sic, data in items_to_plot:
            res_list = data['spatial_residuals']
            if res_list:
                has_data = True
                # Reducir el límite de puntos en vista múltiple para evitar bloquear la interfaz
                max_pts = 6000 if len(selected_keys) == 1 else 1200
                if len(res_list) > max_pts:
                    indices = np.random.choice(len(res_list), max_pts, replace=False)
                    sample = [res_list[i] for i in indices]
                else:
                    sample = res_list
                    
                theta = [np.radians(pt['azimuth']) for pt in sample]
                r = [pt['range_nm'] for pt in sample]
                errors_m = [pt['dr_m'] for pt in sample]
                
                sc = ax.scatter(theta, r, c=errors_m, cmap='coolwarm', s=12, alpha=0.7, label=data['name'])
                
        if has_data and sc is not None:
            cbar = fig.colorbar(sc, ax=ax, orientation='vertical', pad=0.1)
            cbar.set_label("Residuo de Distancia ΔR (m)", color='#A0A5B5')
            cbar.ax.yaxis.set_tick_params(color='#A0A5B5', labelcolor='#A0A5B5')
            
        ax.set_title("Distribución Espacial de Blanco y Error ΔR (m)", color=COLOR_ACCENT_CYAN, pad=20)
        
        # --- ZOOM INTERACTIVO POR RUEDA DEL RATÓN ---
        if hasattr(self, '_scroll_cid_res') and self._scroll_cid_res is not None:
            try:
                self.canvas_res.mpl_disconnect(self._scroll_cid_res)
            except Exception:
                pass
                
        def on_scroll(event):
            if event.inaxes != ax:
                return
            base_scale = 1.15
            if event.button == 'up':
                scale_factor = 1.0 / base_scale
            elif event.button == 'down':
                scale_factor = base_scale
            else:
                scale_factor = 1.0
            current_rmax = ax.get_rmax()
            ax.set_rmax(current_rmax * scale_factor)
            ax.figure.canvas.draw_idle()
            
        self._scroll_cid_res = self.canvas_res.mpl_connect('scroll_event', on_scroll)
        
        # --- DESPLAZAMIENTO INTERACTIVO (PAN) CON CLICK IZQUIERDO ---
        if hasattr(self, '_pan_press_cid') and self._pan_press_cid is not None:
            try:
                self.canvas_res.mpl_disconnect(self._pan_press_cid)
            except Exception:
                pass
        if hasattr(self, '_pan_release_cid') and self._pan_release_cid is not None:
            try:
                self.canvas_res.mpl_disconnect(self._pan_release_cid)
            except Exception:
                pass
        if hasattr(self, '_pan_motion_cid') and self._pan_motion_cid is not None:
            try:
                self.canvas_res.mpl_disconnect(self._pan_motion_cid)
            except Exception:
                pass

        self._pan_active = False
        self._pan_start_x = 0
        self._pan_start_y = 0
        self._pan_start_rmin = 0.0
        self._pan_start_rmax = 240.0
        self._pan_start_theta_offset = 0.0

        def on_press(event):
            if event.button != 1 or event.inaxes != ax:
                return
            self._pan_active = True
            self._pan_start_x = event.x
            self._pan_start_y = event.y
            self._pan_start_rmin = ax.get_rmin()
            self._pan_start_rmax = ax.get_rmax()
            self._pan_start_theta_offset = ax.get_theta_offset()

        def on_release(event):
            self._pan_active = False

        def on_motion(event):
            if not getattr(self, '_pan_active', False) or event.inaxes != ax:
                return
            dx = event.x - self._pan_start_x
            dy = event.y - self._pan_start_y
            
            # Mapear arrastre vertical (dy) al desplazamiento radial (alcance)
            r_range = self._pan_start_rmax - self._pan_start_rmin
            h = ax.bbox.height if ax.bbox.height > 0 else 100.0
            delta_r = (dy / h) * r_range
            
            new_rmin = self._pan_start_rmin + delta_r
            new_rmax = self._pan_start_rmax + delta_r
            
            # Impedir valores negativos de radio mínimo para mantener coherencia polar
            if new_rmin < 0.0:
                new_rmax = new_rmax - new_rmin
                new_rmin = 0.0
                
            # Mapear arrastre horizontal (dx) a la rotación angular (acimut)
            w = ax.bbox.width if ax.bbox.width > 0 else 100.0
            delta_theta = (dx / w) * np.pi
            new_offset = self._pan_start_theta_offset + delta_theta
            
            ax.set_rmin(new_rmin)
            ax.set_rmax(new_rmax)
            ax.set_theta_offset(new_offset)
            ax.figure.canvas.draw_idle()

        self._pan_press_cid = self.canvas_res.mpl_connect('button_press_event', on_press)
        self._pan_release_cid = self.canvas_res.mpl_connect('button_release_event', on_release)
        self._pan_motion_cid = self.canvas_res.mpl_connect('motion_notify_event', on_motion)
        
        fig.tight_layout()
        self.canvas_res.draw()

    def _plot_histograms(self):
        """Dibuja el histograma de errores con curvas de distribución Gaussiana ajustadas."""
        self.canvas_hist.figure.clear()
        fig = self.canvas_hist.figure
        
        ax1 = fig.add_subplot(121)
        ax2 = fig.add_subplot(122)
        
        for ax in [ax1, ax2]:
            ax.set_facecolor('#0E131F')
            ax.tick_params(colors='#A0A5B5')
            ax.xaxis.label.set_color('#A0A5B5')
            ax.yaxis.label.set_color('#A0A5B5')
            ax.title.set_color(COLOR_ACCENT_CYAN)
            ax.grid(True, color='#ffffff', alpha=0.1, linestyle='--')
            
        selected_keys = self.combo_sensor_charts.get_checked_data()
        items_to_plot = [(key, self.results[key]) for key in selected_keys if key in self.results]
        
        has_data = False
        for sac_sic, data in items_to_plot:
            res_list = data['spatial_residuals']
            if not res_list:
                continue
                
            has_data = True
            dr_list = [pt['dr_m'] for pt in res_list]
            daz_list = [pt['daz_deg'] for pt in res_list]
            
            # Histograma del error en distancia
            ax1.hist(dr_list, bins=30, density=True, alpha=0.4, label=data['name'])
            
            # Curva Gaussiana manual
            mean_r = data['range_bias_m']
            std_r = data['range_jitter_m']
            if std_r > 0.0:
                x_fit = np.linspace(min(dr_list), max(dr_list), 100)
                y_fit = (1.0 / (std_r * np.sqrt(2 * np.pi))) * np.exp(-0.5 * ((x_fit - mean_r) / std_r) ** 2)
                ax1.plot(x_fit, y_fit, linewidth=2, linestyle='-')
                
            # Histograma del error en acimut
            ax2.hist(daz_list, bins=30, density=True, alpha=0.4, label=data['name'])
            
            mean_az = data['azimuth_bias_deg']
            std_az = data['azimuth_jitter_deg']
            if std_az > 0.0:
                x_fit_az = np.linspace(min(daz_list), max(daz_list), 100)
                y_fit_az = (1.0 / (std_az * np.sqrt(2 * np.pi))) * np.exp(-0.5 * ((x_fit_az - mean_az) / std_az) ** 2)
                ax2.plot(x_fit_az, y_fit_az, linewidth=2, linestyle='-')

        if has_data:
            # Draw Eurocontrol SASS-C Range Bias Limit [-100m, 100m]
            ax1.axvline(-100, color=COLOR_NEON_RED, linestyle='--', alpha=0.7, label="Límite Sesgo (±100m)")
            ax1.axvline(100, color=COLOR_NEON_RED, linestyle='--', alpha=0.7)
            
            # Draw Eurocontrol SASS-C Azimuth Bias Limit [-0.15°, 0.15°]
            ax2.axvline(-0.15, color=COLOR_NEON_RED, linestyle='--', alpha=0.7, label="Límite Sesgo (±0.15°)")
            ax2.axvline(0.15, color=COLOR_NEON_RED, linestyle='--', alpha=0.7)

        ax1.set_xlabel("Error de Distancia ΔR (m)")
        ax1.set_ylabel("Frecuencia Densidad")
        ax1.set_title("Frecuencia Histograma - Jitter Distancia")
        
        ax2.set_xlabel("Error de Acimut Δθ (°)")
        ax2.set_ylabel("Frecuencia Densidad")
        ax2.set_title("Frecuencia Histograma - Jitter Acimut")
        
        if has_data:
            ax1.legend(facecolor='#0E131F', labelcolor='#FFFFFF')
            ax2.legend(facecolor='#0E131F', labelcolor='#FFFFFF')
        fig.tight_layout()
        self.canvas_hist.draw()

    def _plot_advanced_parameters(self):
        """Dibuja los gráficos de Parámetros Avanzados: Range Gain, Delays, Reflexiones."""
        self.canvas_adv.figure.clear()
        fig = self.canvas_adv.figure
        
        ax1 = fig.add_subplot(131)
        ax2 = fig.add_subplot(132)
        ax3 = fig.add_subplot(133)
        
        for ax in [ax1, ax2, ax3]:
            ax.set_facecolor('#0E131F')
            ax.tick_params(colors='#A0A5B5', labelsize=8)
            ax.xaxis.label.set_color('#A0A5B5')
            ax.yaxis.label.set_color('#A0A5B5')
            ax.title.set_color(COLOR_ACCENT_CYAN)
            ax.grid(True, color='#ffffff', alpha=0.1, linestyle='--')
        
        selected_keys = self.combo_sensor_charts.get_checked_data()
        items_to_plot = [(key, self.results[key]) for key in selected_keys if key in self.results]
        
        # ========= SUBPLOT 1: Range Gain =========
        has_rg = False
        for sac_sic, data in items_to_plot:
            res_list = data.get('spatial_residuals', [])
            if len(res_list) < 10:
                continue
            has_rg = True
            
            R_true = [sr['range_nm'] for sr in res_list]
            deltas = [sr['dr_m'] for sr in res_list]
            
            # Subsample si hay demasiados puntos
            max_pts = 2000
            if len(R_true) > max_pts:
                indices = np.random.choice(len(R_true), max_pts, replace=False)
                R_plot = [R_true[i] for i in indices]
                d_plot = [deltas[i] for i in indices]
            else:
                R_plot = R_true
                d_plot = deltas
            
            ax1.scatter(R_plot, d_plot, s=8, alpha=0.4, label=data['name'])
            
            # Línea de regresión
            slope = data.get('range_gain_slope', 0.0)
            intercept = data.get('range_gain_intercept', 0.0)
            r2 = data.get('range_gain_r2', 0.0)
            
            if abs(slope) > 1e-12 or abs(intercept) > 1e-12:
                x_line = np.array([min(R_true), max(R_true)])
                y_line = slope * x_line + intercept
                color_line = COLOR_NEON_RED if abs(slope) > 0.001 else COLOR_NEON_GREEN
                ax1.plot(x_line, y_line, color=color_line, linewidth=2.5, linestyle='-',
                         label=f"ΔR = {slope:+.4f}·R {intercept:+.1f}m  (R²={r2:.3f})")
        
        if has_rg:
            # Dibujar zona de tolerancia Eurocontrol SASS-C de Range Gain [y = ±0.001 * R]
            xlims = ax1.get_xlim()
            x_vals = np.linspace(max(0.0, xlims[0]), xlims[1], 100)
            ax1.fill_between(x_vals, -0.001 * x_vals, 0.001 * x_vals, color='#02C39A', alpha=0.1, label="Límite SASS-C (±0.001)")
            ax1.plot(x_vals, 0.001 * x_vals, color='#02C39A', linestyle=':', alpha=0.5, linewidth=1.0)
            ax1.plot(x_vals, -0.001 * x_vals, color='#02C39A', linestyle=':', alpha=0.5, linewidth=1.0)

        ax1.set_xlabel("Rango Verdadero (NM)")
        ax1.set_ylabel("Residuo ΔR (m)")
        ax1.set_title("Range Gain — Regresión Lineal")
        if has_rg:
            ax1.legend(facecolor='#0E131F', labelcolor='#FFFFFF', fontsize=7, loc='best')
        
        # ========= SUBPLOT 2: Transmission Delays =========
        has_delay = False
        for sac_sic, data in items_to_plot:
            delays_arr = data.get('delays_data', [])
            if not delays_arr:
                continue
            has_delay = True
            
            ax2.hist(delays_arr, bins=40, density=True, alpha=0.5, label=data['name'])
            
            mean_d = data.get('delay_mean', 0.0)
            std_d = data.get('delay_std', 0.0)
            p95_d = data.get('delay_p95', 0.0)
            
            # Línea vertical en la media
            color_mean = COLOR_NEON_RED if abs(mean_d) > 2.0 else COLOR_NEON_GREEN
            ax2.axvline(mean_d, color=color_mean, linewidth=2.0, linestyle='-',
                       label=f"μ={mean_d:.3f}s σ={std_d:.3f}s")
            ax2.axvline(p95_d, color=COLOR_NEON_ORANGE, linewidth=1.5, linestyle='--',
                       label=f"P95={p95_d:.3f}s")
        
        if has_delay:
            # Dibujar línea límite de retardo de Eurocontrol (2.0s)
            ax2.axvline(2.0, color=COLOR_NEON_RED, linestyle='--', linewidth=1.5, alpha=0.8, label="Límite SASS-C (2.0s)")

        ax2.set_xlabel("Demora de Transmisión (s)")
        ax2.set_ylabel("Frecuencia Densidad")
        ax2.set_title("Demoras de Transmisión (PCAP - TOD)")
        if has_delay:
            ax2.legend(facecolor='#0E131F', labelcolor='#FFFFFF', fontsize=7, loc='best')
        
        # ========= SUBPLOT 3: Reflection Rate Summary =========
        sensor_names = []
        refl_rates = []
        refl_counts = []
        bar_colors = []
        
        for sac_sic, data in items_to_plot:
            rate = data.get('reflection_rate', 0.0)
            count = data.get('reflection_count', 0)
            sensor_names.append(data['name'][:18])
            refl_rates.append(rate)
            refl_counts.append(count)
            if rate <= 1.0:
                bar_colors.append(COLOR_NEON_GREEN)
            elif rate <= 2.0:
                bar_colors.append(COLOR_NEON_ORANGE)
            else:
                bar_colors.append(COLOR_NEON_RED)
        
        if sensor_names:
            y_pos = np.arange(len(sensor_names))
            ax3.barh(y_pos, refl_rates, color=bar_colors, alpha=0.85, height=0.6)
            ax3.set_yticks(y_pos)
            ax3.set_yticklabels(sensor_names, fontsize=7, color='#FFFFFF')
            
            # Anotar conteo absoluto
            for i, (rate, count) in enumerate(zip(refl_rates, refl_counts)):
                ax3.text(rate + 0.05, i, f"{rate:.2f}% ({count})", va='center',
                         color='#FFFFFF', fontsize=7)
            
            # Línea umbral 1%
            ax3.axvline(1.0, color=COLOR_NEON_ORANGE, linewidth=1.5, linestyle='--', alpha=0.8, label="Meta SASS-C (1%)")
            ax3.axvline(2.0, color=COLOR_NEON_RED, linewidth=1.5, linestyle='--', alpha=0.8, label="Límite SASS-C (2%)")
        
        ax3.set_xlabel("Tasa de Reflexión (%)")
        ax3.set_title("Reflexiones Detectadas")
        if sensor_names:
            ax3.legend(facecolor='#0E131F', labelcolor='#FFFFFF', fontsize=7, loc='best')
        
        fig.tight_layout()
        self.canvas_adv.draw()

    # ============================================================
    # EXPORTADORES DE REPORTES
    # ============================================================

    def _export_csv(self):
        """Exporta las estadísticas de la tabla de desempeño a un archivo CSV."""
        filepath, _ = QFileDialog.getSaveFileName(
            self, "Guardar Estadísticas PASS", "", "Archivos CSV (*.csv)"
        )
        if not filepath:
            return
            
        try:
            with open(filepath, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                # Escribir cabecera
                writer.writerow([
                    "Sensor", "Centro_Control_ACC", "SAC_SIC", "Categoria", "Muestras", "RPM",
                    "Pd_Global_Pct", "Pd_Modo_A_Pct", "Pd_Modo_C_Pct", "Sesgo_R_m", "Sesgo_Az_deg", "Jitter_R_m", "Jitter_Az_deg", "Split_Plots_Pct",
                    "Range_Gain_Slope", "Range_Gain_Intercept", "Range_Gain_R2",
                    "Delay_Mean_s", "Delay_Std_s", "Delay_P95_s",
                    "Reflection_Count", "Reflection_Rate_Pct"
                ])
                
                for sac_sic, data in sorted(self.results.items()):
                    accs = obtener_centros_control(data['name'], sac_sic[0], sac_sic[1])
                    writer.writerow([
                        data['name'],
                        ", ".join(accs),
                        f"{sac_sic[0]}_{sac_sic[1]}",
                        data['category'],
                        data['total_plots'],
                        f"{data['rpm']:.1f}",
                        f"{data['pd_global']:.2f}",
                        f"{data.get('pd_mode_a', 0.0):.2f}",
                        f"{data.get('pd_mode_c', 0.0):.2f}",
                        f"{data['range_bias_m']:.2f}",
                        f"{data['azimuth_bias_deg']:.4f}",
                        f"{data['range_jitter_m']:.2f}",
                        f"{data['azimuth_jitter_deg']:.4f}",
                        f"{data['split_plots_pct']:.2f}",
                        f"{data.get('range_gain_slope', 0.0):.6f}",
                        f"{data.get('range_gain_intercept', 0.0):.2f}",
                        f"{data.get('range_gain_r2', 0.0):.4f}",
                        f"{data.get('delay_mean', 0.0):.4f}",
                        f"{data.get('delay_std', 0.0):.4f}",
                        f"{data.get('delay_p95', 0.0):.4f}",
                        f"{data.get('reflection_count', 0)}",
                        f"{data.get('reflection_rate', 0.0):.3f}"
                    ])
            QMessageBox.information(self, "Exportación Exitosa", f"Estadísticas exportadas a: {filepath}")
        except Exception as e:
            QMessageBox.critical(self, "Error de Exportación", f"Error al guardar CSV: {e}")

    def _export_pdf(self):
        """Genera un reporte PDF formal del análisis usando fpdf2."""
        if not HAS_FPDF:
            QMessageBox.warning(
                self, "Librería Inexistente",
                "La librería 'fpdf2' no se encuentra instalada en el entorno.\n"
                "Para exportar reportes en PDF, instálela ejecutando:\n'pip install fpdf2'"
            )
            return

        filepath, _ = QFileDialog.getSaveFileName(
            self, "Guardar Reporte PASS PDF", "", "Documentos PDF (*.pdf)"
        )
        if not filepath:
            return

        try:
            pdf = FPDF()
            pdf.add_page()
            
            # --- TÍTULO Y CABECERA ---
            pdf.set_fill_color(11, 14, 20)
            pdf.rect(0, 0, 210, 40, 'F')
            
            pdf.set_text_color(0, 229, 255)
            pdf.set_font("Helvetica", 'B', 20)
            pdf.set_y(10)
            pdf.cell(0, 10, "INFORME DE PRESTACIONES DE VIGILANCIA", 0, 1, 'C')
            pdf.set_font("Helvetica", 'I', 11)
            pdf.cell(0, 8, "Evaluacion de Calidad y Sesgos de Radar (Estandard Eurocontrol SASS-C / PASS)", 0, 1, 'C')
            
            pdf.set_text_color(0, 0, 0)
            pdf.ln(15)
            
            # --- RESUMEN GENERAL ---
            pdf.set_font("Helvetica", 'B', 14)
            pdf.cell(0, 10, "1. Resumen Ejecutivo del Conjunto de Datos", 0, 1)
            pdf.set_font("Helvetica", '', 10)
            
            total_plots = sum(r['total_plots'] for r in self.results.values())
            pdf.multi_cell(0, 6, 
                f"El presente reporte contiene la evaluacion sistematica de calidad y alineamiento de la red "
                f"de sensores de vigilancia a partir de los datos ASTERIX capturados.\n\n"
                f"  - Total de Estaciones Analizadas: {len(self.results)}\n"
                f"  - Numero de Muestras / Ploteos Totales: {total_plots}\n"
                f"  - Fecha de Analisis: {np.datetime64('now')}\n"
            )
            pdf.ln(5)
            
            # --- TABLA DE SENSORES AGRUPADOS POR ACC ---
            pdf.set_font("Helvetica", 'B', 14)
            pdf.cell(0, 10, "2. Cuadro de Medición de Sesgos y Calidad por ACC", 0, 1)
            pdf.ln(2)
            
            col_widths = [35, 16, 10, 12, 18, 16, 16, 18, 18, 18, 13]
            headers = ["Estacion", "SAC/SIC", "Cat", "RPM", "Pd Glob", "Pd A", "Pd C", "Sesgo R", "Sesgo Az", "Jitter R", "Split"]
            
            accs_to_render = ["Comodoro", "Córdoba", "Ezeiza", "Mendoza", "Resistencia", "Otros"]
            for acc in accs_to_render:
                acc_sensors = []
                for sac_sic, data in sorted(self.results.items()):
                    sensor_accs = obtener_centros_control(data['name'], sac_sic[0], sac_sic[1])
                    if acc == "Otros" and not any(a in accs_to_render[:-1] for a in sensor_accs):
                        acc_sensors.append((sac_sic, data))
                    elif acc in sensor_accs:
                        acc_sensors.append((sac_sic, data))
                        
                if not acc_sensors:
                    continue
                    
                # Dibujar Cabecera del ACC
                pdf.set_font("Helvetica", 'B', 11)
                pdf.set_text_color(0, 120, 200) # Azul ACC
                pdf.cell(0, 8, f"Centro de Control (ACC) {acc}", 0, 1)
                pdf.set_text_color(0, 0, 0)
                
                # Encabezados de tabla
                pdf.set_font("Helvetica", 'B', 7.5)
                pdf.set_fill_color(22, 29, 43)
                pdf.set_text_color(255, 255, 255)
                for i, h in enumerate(headers):
                    pdf.cell(col_widths[i], 7, h, 1, 0, 'C', True)
                pdf.ln()
                
                pdf.set_font("Helvetica", '', 7.0)
                pdf.set_text_color(0, 0, 0)
                for sac_sic, data in acc_sensors:
                    pdf.cell(col_widths[0], 7, data['name'], 1, 0, 'L')
                    pdf.cell(col_widths[1], 7, f"{sac_sic[0]}/{sac_sic[1]}", 1, 0, 'C')
                    pdf.cell(col_widths[2], 7, data['category'], 1, 0, 'C')
                    pdf.cell(col_widths[3], 7, f"{data['rpm']:.1f}", 1, 0, 'C')
                    pdf.cell(col_widths[4], 7, f"{data['pd_global']:.1f}%", 1, 0, 'C')
                    pdf.cell(col_widths[5], 7, f"{data.get('pd_mode_a', 0.0):.1f}%", 1, 0, 'C')
                    pdf.cell(col_widths[6], 7, f"{data.get('pd_mode_c', 0.0):.1f}%", 1, 0, 'C')
                    pdf.cell(col_widths[7], 7, f"{data['range_bias_m']:+.1f} m", 1, 0, 'C')
                    pdf.cell(col_widths[8], 7, f"{data['azimuth_bias_deg']:+.3f}°", 1, 0, 'C')
                    pdf.cell(col_widths[9], 7, f"{data['range_jitter_m']:.1f} m", 1, 0, 'C')
                    pdf.cell(col_widths[10], 7, f"{data['split_plots_pct']:.1f}%", 1, 0, 'C')
                    pdf.ln()
                pdf.ln(5)
                
            pdf.ln(5)
            
            # --- EVALUACIÓN DE LIMITES ---
            pdf.set_font("Helvetica", 'B', 14)
            pdf.cell(0, 10, "3. Analisis de Desviacion e Incumplimiento por Region", 0, 1)
            pdf.set_font("Helvetica", '', 9.5)
            
            pdf.multi_cell(0, 6,
                "De acuerdo a los limites estandar definidos por Eurocontrol:\n"
                "  - Probabilidad de Deteccion (Pd Global) debe ser mayor o igual a 95.0%.\n"
                "  - Probabilidad de Deteccion de Squawk (Pd Modo A) debe ser mayor o igual a 98.0%.\n"
                "  - Probabilidad de Deteccion de Altitud (Pd Modo C) debe ser mayor o igual a 95.0%.\n"
                "  - El error sistematico en distancia (Sesgo R) debe ser menor o igual a +/- 100 metros.\n"
                "  - El error de alineacion azimutal (Sesgo Az) debe ser menor o igual a +/- 0.150 grados.\n"
                "  - El ruido instrumental (Jitter Distancia) debe mantenerse por debajo de los 150 metros.\n"
            )
            pdf.ln(5)
            
            # Revisión de inconformidades agrupada por ACC
            has_violations_any = False
            for acc in accs_to_render:
                acc_sensors = []
                for sac_sic, data in sorted(self.results.items()):
                    sensor_accs = obtener_centros_control(data['name'], sac_sic[0], sac_sic[1])
                    if acc == "Otros" and not any(a in accs_to_render[:-1] for a in sensor_accs):
                        acc_sensors.append((sac_sic, data))
                    elif acc in sensor_accs:
                        acc_sensors.append((sac_sic, data))
                        
                if not acc_sensors:
                    continue
                    
                violations = []
                for sac_sic, data in acc_sensors:
                    s_viol = []
                    if data['pd_global'] < 95.0:
                        s_viol.append(f"Pd Insuficiente ({data['pd_global']:.2f}%)")
                    pda_val = data.get('pd_mode_a', 0.0)
                    if pda_val < 98.0:
                        s_viol.append(f"Pd Modo A Insuficiente ({pda_val:.2f}%)")
                    pdc_val = data.get('pd_mode_c', 0.0)
                    if pdc_val < 95.0:
                        s_viol.append(f"Pd Modo C Insuficiente ({pdc_val:.2f}%)")
                    if abs(data['range_bias_m']) > 100.0:
                        s_viol.append(f"Sesgo Distancia Excedido ({data['range_bias_m']:+.1f} m)")
                    if abs(data['azimuth_bias_deg']) > 0.15:
                        s_viol.append(f"Desalineacion Azimutal Excedida ({data['azimuth_bias_deg']:+.3f} deg)")
                    if data['range_jitter_m'] > 150.0:
                        s_viol.append(f"Jitter Distancia Elevado ({data['range_jitter_m']:.1f} m)")
                    # Alertas de parámetros avanzados
                    rg_slope = data.get('range_gain_slope', 0.0)
                    if abs(rg_slope) > 0.001:
                        s_viol.append(f"Range Gain Anomalo (slope={rg_slope:+.4f} m/NM)")
                    delay_m = data.get('delay_mean', 0.0)
                    if abs(delay_m) > 2.0:
                        s_viol.append(f"Demora Transmision Excesiva (media={delay_m:.3f}s)")
                    refl_rate = data.get('reflection_rate', 0.0)
                    if refl_rate > 1.0:
                        s_viol.append(f"Reflexiones Elevadas ({refl_rate:.2f}%)")
                        
                    if s_viol:
                        violations.append(f"  * Sensor {data['name']} [{sac_sic[0]}/{sac_sic[1]}]: " + ", ".join(s_viol))
                        
                if violations:
                    has_violations_any = True
                    pdf.set_font("Helvetica", 'B', 10)
                    pdf.set_text_color(220, 50, 50)
                    pdf.cell(0, 8, f"ACC {acc} - ALERTAS DETECTADAS:", 0, 1)
                    pdf.set_font("Helvetica", '', 9)
                    pdf.set_text_color(0, 0, 0)
                    pdf.multi_cell(0, 5, "\n".join(violations))
                    pdf.ln(3)
                else:
                    pdf.set_font("Helvetica", 'B', 10)
                    pdf.set_text_color(30, 150, 30)
                    pdf.cell(0, 8, f"ACC {acc} - CUMPLIMIENTO EXITOSO (100% Ok)", 0, 1)
                    pdf.set_text_color(0, 0, 0)
                    pdf.ln(3)
            
            # --- SECCIÓN 4: PARÁMETROS AVANZADOS ---
            pdf.add_page()
            pdf.set_font("Helvetica", 'B', 14)
            pdf.cell(0, 10, "4. Parametros Avanzados de Evaluacion", 0, 1)
            pdf.set_font("Helvetica", '', 9.5)
            pdf.multi_cell(0, 6,
                "Esta seccion presenta los parametros avanzados de evaluacion de desempeno:\n"
                "  - Range Gain: Pendiente de regresion lineal de residuos de distancia vs rango verdadero.\n"
                "    Un |slope| > 0.001 indica error sistematico de reloj maestro.\n"
                "  - Demora de Transmision: Diferencia entre timestamp PCAP y Time of Day ASTERIX.\n"
                "    Una media > 2.0s indica retrasos excesivos en la cadena de transmision.\n"
                "  - Tasa de Reflexion: Porcentaje de ploteos reflejados detectados por correlacion\n"
                "    de squawks identicos en distintos acimuts. Una tasa > 1.0% indica problemas.\n"
            )
            pdf.ln(5)
            
            # Tabla de parámetros avanzados
            adv_col_widths = [40, 22, 22, 14, 22, 18, 18, 18, 16]
            adv_headers = ["Estacion", "SAC/SIC", "RG Slope", "RG R2", "Delay Med", "Delay Std", "Delay P95", "Reflex %", "Reflex N"]
            
            pdf.set_font("Helvetica", 'B', 7.5)
            pdf.set_fill_color(22, 29, 43)
            pdf.set_text_color(255, 255, 255)
            for i, h in enumerate(adv_headers):
                pdf.cell(adv_col_widths[i], 7, h, 1, 0, 'C', True)
            pdf.ln()
            
            pdf.set_font("Helvetica", '', 7.0)
            pdf.set_text_color(0, 0, 0)
            for sac_sic, data in sorted(self.results.items()):
                pdf.cell(adv_col_widths[0], 7, data['name'][:22], 1, 0, 'L')
                pdf.cell(adv_col_widths[1], 7, f"{sac_sic[0]}/{sac_sic[1]}", 1, 0, 'C')
                pdf.cell(adv_col_widths[2], 7, f"{data.get('range_gain_slope', 0.0):+.5f}", 1, 0, 'C')
                pdf.cell(adv_col_widths[3], 7, f"{data.get('range_gain_r2', 0.0):.3f}", 1, 0, 'C')
                pdf.cell(adv_col_widths[4], 7, f"{data.get('delay_mean', 0.0):.3f}s", 1, 0, 'C')
                pdf.cell(adv_col_widths[5], 7, f"{data.get('delay_std', 0.0):.3f}s", 1, 0, 'C')
                pdf.cell(adv_col_widths[6], 7, f"{data.get('delay_p95', 0.0):.3f}s", 1, 0, 'C')
                pdf.cell(adv_col_widths[7], 7, f"{data.get('reflection_rate', 0.0):.2f}%", 1, 0, 'C')
                pdf.cell(adv_col_widths[8], 7, f"{data.get('reflection_count', 0)}", 1, 0, 'C')
                pdf.ln()
                
            pdf.output(filepath)
            QMessageBox.information(self, "Reporte Exportado", f"Informe de Calidad PASS PDF generado con éxito en:\n{filepath}")
        except Exception as e:
            QMessageBox.critical(self, "Error al generar PDF", f"Error al escribir reporte PDF: {e}")

    def _plot_overlap_comparison(self):
        """Renderiza la comparación de solapamiento según la opción seleccionada (Matriz de calor, curvas de Rango o FL)."""
        self.canvas_ov.figure.clear()
        fig = self.canvas_ov.figure
        ax = fig.add_subplot(111)
        
        ax.set_facecolor('#0B0E14')
        ax.tick_params(colors='#A0A5B5', labelsize=9)
        ax.xaxis.label.set_color('#A0A5B5')
        ax.yaxis.label.set_color('#A0A5B5')
        ax.title.set_color(COLOR_ACCENT_CYAN)
        ax.grid(True, color='#ffffff', alpha=0.1, linestyle='--')
        
        # Obtener los datos de pares de solapamiento
        pairwise = getattr(self, 'overlap_pairwise', {})
        
        if not pairwise:
            ax.set_facecolor('#0B0E14')
            ax.text(0.5, 0.5, "No se detectaron áreas de solapamiento operativo\ncon datos suficientes entre los radares cargados.",
                    color='#A0A5B5', fontsize=11, ha='center', va='center', transform=ax.transAxes)
            ax.set_title("Comparación de Solapamiento (Overlap Pd)")
            fig.tight_layout()
            self.canvas_ov.draw()
            return
            
        sensor_names = {}
        # Obtener los radares seleccionados por el usuario en el combo box superior
        selected_keys = self.combo_sensor_charts.get_checked_data()
        
        # Recolectar nombres de sensores radar puros seleccionados (excluyendo ADS-B)
        active_sensors = []
        for sac_sic in selected_keys:
            if isinstance(sac_sic, tuple) and sac_sic in self.results:
                data = self.results[sac_sic]
                if data.get('category') != 'CAT021':
                    sensor_names[sac_sic] = data.get('name', f"Radar {sac_sic[0]}/{sac_sic[1]}")
                    active_sensors.append(sac_sic)
                
        active_sensors.sort()
        n = len(active_sensors)
        
        if n < 2:
            ax.set_facecolor('#0B0E14')
            ax.text(0.5, 0.5, "Por favor, selecciona al menos 2 radares en el combo box superior\npara poder generar el análisis de solapamiento cruzado (Overlap Pd).",
                    color='#A0A5B5', fontsize=10.5, ha='center', va='center', transform=ax.transAxes)
            ax.set_title("Comparación de Solapamiento (Overlap Pd)")
            fig.tight_layout()
            self.canvas_ov.draw()
            return
            
        ov_graph_type = self.combo_ov_type.currentText()
        
        # ============================================================
        # MODO 1: MATRIZ DE CALOR (HEATMAP 2D)
        # ============================================================
        if ov_graph_type == "Matriz de Calor (Heatmap 2D)":
            # Construir matriz de correlación N x N
            matrix = np.zeros((n, n))
            matrix[:] = np.nan  # Llenar con NaN por defecto (ausencia de solapamiento operativo)
            
            # Llenar la diagonal con 100% (autodetectabilidad trivial)
            for i in range(n):
                matrix[i, i] = 100.0
                
            # Rellenar con los datos calculados de pares de solapamiento
            for i, s_tgt in enumerate(active_sensors):
                for j, s_ref in enumerate(active_sensors):
                    if i == j:
                        continue
                    # pd_val = Pd del target s_tgt validado por la referencia s_ref
                    pd_val = pairwise.get((s_tgt, s_ref), {}).get('pd')
                    if pd_val is not None:
                        matrix[i, j] = pd_val
                        
            # Crear colormap cyberpunk personalizado: de Rojo oscuro (#2E181D) a Verde neón (#00E676)
            import matplotlib.colors
            cmap = matplotlib.colors.LinearSegmentedColormap.from_list(
                "cyber_heatmap", ['#2E181D', '#FF3D00', '#FFEA00', '#00E676']
            )
            # Las celdas sin solapamiento (NaN) se pintan del color negro del fondo de pantalla (#0B0E14)
            cmap.set_bad(color='#0B0E14')
            
            # Dibujar matriz de calor
            im = ax.imshow(matrix, cmap=cmap, vmin=0, vmax=100, aspect='equal', origin='upper')
            
            # Configurar ticks y etiquetas compactas tipo [SAC/SIC] Nombre_Corto
            labels = [f"[{s[0]}/{s[1]}] {sensor_names[s].split(' ')[0]}" for s in active_sensors]
            ax.set_xticks(range(n))
            ax.set_yticks(range(n))
            ax.set_xticklabels(labels, rotation=35, ha='right', fontsize=7.5)
            ax.set_yticklabels(labels, fontsize=7.5)
            
            ax.set_xlabel("Radar de Referencia (Validador)", fontsize=9, fontweight='bold', labelpad=8)
            ax.set_ylabel("Radar Evaluado (Target)", fontsize=9, fontweight='bold', labelpad=8)
            ax.set_title("Matriz de Co-detección Cruzada SSR en Áreas Solapadas (Overlap Pd %)", 
                         color=COLOR_ACCENT_CYAN, pad=15, fontsize=10, fontweight='bold')
            
            # Agregar barra de colores (colorbar) con estilo cyberpunk
            cbar = fig.colorbar(im, ax=ax, shrink=0.75, pad=0.03)
            cbar.ax.tick_params(colors='#A0A5B5', labelsize=8)
            cbar.set_label("Probabilidad de Solapamiento (%)", color='#A0A5B5', fontsize=8.5, labelpad=8)
            cbar.outline.set_edgecolor('#A0A5B5')
            cbar.outline.set_linewidth(0.8)
            
            # Si la matriz es pequeña (<= 12 sensores), inyectar los valores numéricos de porcentaje en las celdas
            if n <= 12:
                for i in range(n):
                    for j in range(n):
                        val = matrix[i, j]
                        if not np.isnan(val):
                            # Mostrar el valor redondeado
                            ax.text(j, i, f"{val:.0f}%", ha='center', va='center', 
                                     color='#FFFFFF', fontsize=7.5, fontweight='bold')
                                     
        # ============================================================
        # MODO 2: CURVAS DE PD VS. RANGO (TRANSICIÓN)
        # ============================================================
        elif ov_graph_type == "Curvas de Pd vs. Rango (Transición)":
            x_vals = [10, 30, 50, 70, 90, 110, 130, 150, 170, 190]  # Centros de los bins de 20 NM
            
            legend_added = False
            for s_tgt in active_sensors:
                for s_ref in active_sensors:
                    if s_tgt == s_ref:
                        continue
                    
                    pair_data = pairwise.get((s_tgt, s_ref))
                    if not pair_data:
                        continue
                        
                    r_exp = pair_data.get('range_expected', [])
                    r_act = pair_data.get('range_actual', [])
                    
                    if not r_exp or not r_act:
                        continue
                        
                    # Calcular Pd por bin de rango
                    y_vals = []
                    for i in range(10):
                        exp = r_exp[i]
                        act = r_act[i]
                        if exp >= 2:  # Requerir al menos 2 puntos esperados en el bin
                            y_vals.append((act / exp) * 100.0)
                        else:
                            y_vals.append(np.nan)
                            
                    # Dibujar si hay al menos un bin con datos válidos
                    if not np.all(np.isnan(y_vals)):
                        legend_added = True
                        label = f"[{s_tgt[0]}/{s_tgt[1]}] {sensor_names[s_tgt].split(' ')[0]} (tgt) vs [{s_ref[0]}/{s_ref[1]}] {sensor_names[s_ref].split(' ')[0]} (ref)"
                        ax.plot(x_vals, y_vals, 'o-', linewidth=1.5, markersize=5, label=label)
            
            ax.set_xlim(0, 200)
            ax.set_ylim(0, 105)
            ax.set_xlabel("Distancia al Radar Evaluado (NM)", fontsize=9.5, fontweight='bold', labelpad=8)
            ax.set_ylabel("Probabilidad de Solapamiento (%)", fontsize=9.5, fontweight='bold', labelpad=8)
            ax.set_title("Transición de Probabilidad de Solapamiento (Overlap Pd %) vs. Distancia", 
                         color=COLOR_ACCENT_CYAN, pad=15, fontsize=10, fontweight='bold')
            
            if legend_added:
                ax.legend(facecolor='#0E131F', labelcolor='#FFFFFF', fontsize=7.5, loc='lower left', ncol=min(2, n))
            else:
                ax.text(0.5, 0.5, "Datos insuficientes bindeados por rango\npara los radares seleccionados.",
                        color='#A0A5B5', fontsize=11, ha='center', va='center', transform=ax.transAxes)
                        
        # ============================================================
        # MODO 3: PD VS. NIVEL DE VUELO (FL)
        # ============================================================
        elif ov_graph_type == "Pd vs. Nivel de Vuelo (FL)":
            x_vals = [25, 75, 125, 175, 225, 275, 325, 375, 425, 475]  # Centros de los bins de 50 FL
            
            legend_added = False
            for s_tgt in active_sensors:
                for s_ref in active_sensors:
                    if s_tgt == s_ref:
                        continue
                    
                    pair_data = pairwise.get((s_tgt, s_ref))
                    if not pair_data:
                        continue
                        
                    a_exp = pair_data.get('alt_expected', [])
                    a_act = pair_data.get('alt_actual', [])
                    
                    if not a_exp or not a_act:
                        continue
                        
                    # Calcular Pd por bin de altitud
                    y_vals = []
                    for j in range(10):
                        exp = a_exp[j]
                        act = a_act[j]
                        if exp >= 2:  # Requerir al menos 2 puntos esperados en el bin
                            y_vals.append((act / exp) * 100.0)
                        else:
                            y_vals.append(np.nan)
                            
                    # Dibujar si hay al menos un bin con datos válidos
                    if not np.all(np.isnan(y_vals)):
                        legend_added = True
                        label = f"[{s_tgt[0]}/{s_tgt[1]}] {sensor_names[s_tgt].split(' ')[0]} (tgt) vs [{s_ref[0]}/{s_ref[1]}] {sensor_names[s_ref].split(' ')[0]} (ref)"
                        ax.plot(x_vals, y_vals, 's-', linewidth=1.5, markersize=5, label=label)
            
            ax.set_xlim(0, 500)
            ax.set_ylim(0, 105)
            ax.set_xlabel("Nivel de Vuelo de las Aeronaves (FL)", fontsize=9.5, fontweight='bold', labelpad=8)
            ax.set_ylabel("Probabilidad de Solapamiento (%)", fontsize=9.5, fontweight='bold', labelpad=8)
            ax.set_title("Probabilidad de Solapamiento (Overlap Pd %) vs. Altitud de Vuelo (FL)", 
                         color=COLOR_ACCENT_CYAN, pad=15, fontsize=10, fontweight='bold')
            
            if legend_added:
                ax.legend(facecolor='#0E131F', labelcolor='#FFFFFF', fontsize=7.5, loc='lower right', ncol=min(2, n))
            else:
                ax.text(0.5, 0.5, "Datos insuficientes bindeados por nivel de vuelo (FL)\npara los radares seleccionados.",
                        color='#A0A5B5', fontsize=11, ha='center', va='center', transform=ax.transAxes)
                                 
        fig.tight_layout()
        self.canvas_ov.draw()
