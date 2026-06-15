import sys
import os
import re
import time
import shutil
import tempfile
from typing import Dict, Tuple, List, Optional, Set, Any

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout,
    QHBoxLayout, QGridLayout, QFileDialog, QGroupBox, QSizePolicy,
    QListWidget, QListWidgetItem, QPushButton, QLabel, QSlider, QComboBox,
    QSpinBox, QCheckBox, QLineEdit, QMessageBox, QProgressDialog,
    QMenuBar, QToolBar, QDockWidget, QScrollArea, QMenu,
    QDialog, QDialogButtonBox, QFormLayout
)
from PyQt6.QtCore import Qt, QTimer, QPropertyAnimation, QRect, QThread, pyqtSignal, QEvent
from PyQt6.QtGui import QFont, QColor, QPainterPath, QPixmap, QIcon, QBrush, QPainter, QPen

import qtawesome as qta

from utils.geo import cargar_sensores
from player.playback_worker import PlaybackWorker
from player.radar_widget import RadarWidget
from player.profile_manager import ProfileManager
from analysis.exporters import PassExporter
from analysis.stca_analyzer import STCA_Engine
from player.stca_dialog import STCADialog
from player.filter_dialog import QualityFilterDialog

import math

# Color de acento para iconos vectoriales (QtAwesome), alineado al tema radar
ICON_COLOR = "#00E5FF"

def _icon(name: str, color: str = ICON_COLOR):
    return qta.icon(name, color=color)

def parse_coordinate(coord_str: str) -> Optional[Tuple[float, float]]:
    match = re.match(r'^(\d{2})(\d{2})(\d{2}(?:\.\d+)?)([NS])(\d{3})(\d{2})(\d{2}(?:\.\d+)?)([EW])$', coord_str.strip())
    if not match:
        return None
    
    lat_deg, lat_min, lat_sec, lat_hem, lon_deg, lon_min, lon_sec, lon_hem = match.groups()
    
    lat = float(lat_deg) + float(lat_min) / 60.0 + float(lat_sec) / 3600.0
    if lat_hem == 'S':
        lat = -lat
        
    lon = float(lon_deg) + float(lon_min) / 60.0 + float(lon_sec) / 3600.0
    if lon_hem == 'W':
        lon = -lon
        
    return lat, lon

class DxfLoaderThread(QThread):
    """Carga mapas GeoJSON (.geojson/.json) en hilo separado. Emite segmentos serializables."""
    dxf_data = pyqtSignal(object, float, float, float, float)
    dxf_error = pyqtSignal(str)

    def __init__(self, filepath: str):
        super().__init__()
        self.filepath = filepath

    def run(self):
        # Intentar ruta directa o relativa al directorio raíz del proyecto
        path = self.filepath
        if not os.path.exists(path):
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            path = os.path.join(base_dir, self.filepath)
        
        if not os.path.exists(path):
            self.dxf_error.emit(f"Archivo de mapa no encontrado: {self.filepath}")
            return

        if path.lower().endswith('.geojson') or path.lower().endswith('.json'):
            try:
                import json
                with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                    data = json.load(f)
                
                segments = []
                min_x = min_y = float('inf')
                max_x = max_y = float('-inf')
                
                def update_ext(x, y):
                    nonlocal min_x, max_x, min_y, max_y
                    min_x = min(min_x, x)
                    max_x = max(max_x, x)
                    min_y = min(min_y, y)
                    max_y = max(max_y, y)
                    
                features = data.get("features", [])
                for feat in features:
                    geom = feat.get("geometry", {})
                    props = feat.get("properties", {})
                    gtype = geom.get("type")
                    layer = props.get("layer", "LINEAS_DE_MAPA")
                    name = props.get("name", "")
                    
                    if gtype == "LineString":
                        coords = geom.get("coordinates", [])
                        if coords:
                            # GeoJSON coords are [lon, lat]
                            lon0, lat0 = coords[0]
                            segments.append(('M', layer, lat0, lon0))
                            update_ext(lat0, lon0)
                            for lon, lat in coords[1:]:
                                segments.append(('L', layer, lat, lon))
                                update_ext(lat, lon)
                                
                    elif gtype == "Point":
                        coords = geom.get("coordinates", [])
                        if len(coords) >= 2:
                            lon, lat = coords[0], coords[1]
                            ptype = props.get("type", "text")
                            if ptype == "symbol":
                                segments.append(('S', "SIMBOLOS_WAYPOINTS", lat, lon, name))
                            else:
                                segments.append(('T', "NOMBRES_WAYPOINTS", lat, lon, name))
                            update_ext(lat, lon)
                            
                if min_x == float('inf'):
                    self.dxf_error.emit("Sin entidades válidas en el archivo GeoJSON")
                    return
                self.dxf_data.emit(segments, min_x, min_y, max_x, max_y)
            except Exception as e:
                self.dxf_error.emit(f"Error cargando GeoJSON: {e}")
            return
        self.dxf_error.emit(f"Formato no soportado (solo .geojson/.json): {self.filepath}")

class PASSAnalysisWorker(QThread):
    """Worker QThread para ejecutar el análisis PASS en segundo plano."""
    finished = pyqtSignal(dict)
    error = pyqtSignal(str)
    progress = pyqtSignal(str)

    def __init__(self, engine, plots, sensor_rpms):
        super().__init__()
        self.engine = engine
        self.plots = plots
        self.sensor_rpms = sensor_rpms

    def run(self):
        try:
            self.progress.emit("Preparando datos de ploteos...")
            plots_data = [p.to_dict() for p in self.plots]
            
            self.progress.emit("Ejecutando cálculos PASS (SASS-C)...")
            resultados = self.engine.analyze_data(plots_data, self.sensor_rpms)
            
            self.finished.emit(resultados)
        except Exception as e:
            self.error.emit(str(e))

class HoverTopPanel(QWidget):
    """Panel superior con auto-hide (Glassmorphism / Overlay)."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(135)
        
        # Efecto visual glassmorphism
        self.setStyleSheet("""
            QWidget {
                background-color: rgba(26, 28, 35, 230);
                border-bottom: 1px solid rgba(97, 175, 239, 100);
            }
            QGroupBox {
                background-color: transparent;
                border: 1px solid rgba(58, 63, 76, 180);
                border-radius: 6px;
                margin-top: 18px;
                color: #E0E6ED;
                font-weight: bold;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                padding: 0 8px;
                color: #61AFEF;
                background-color: rgba(26, 28, 35, 255);
                border-radius: 4px;
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
                border: 1px solid #61AFEF;
                color: #61AFEF;
            }
            QPushButton:disabled {
                background-color: rgba(45, 49, 60, 100);
                color: gray;
            }
            QListWidget {
                background-color: rgba(26, 28, 35, 180);
                border: 1px solid #3A3F4C;
                border-radius: 4px;
                color: #E0E6ED;
            }
            QListWidget::item:selected {
                background-color: #3E4451;
                color: #61AFEF;
            }
        """)


class RelojFlotanteUTC(QWidget):
    """Reloj flotante de hora UTC real (hora local + offset), arrastrable.

    - Se superpone al PPI; el controlador lo arrastra a donde le quede cómodo.
    - Toggle de visibilidad desde el menú Ver.
    - UTC = hora local del sistema + UTC_OFFSET_H (Argentina UTC-3 → +3).
    """
    UTC_OFFSET_H = 3

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setCursor(Qt.CursorShape.SizeAllCursor)
        self.setStyleSheet("""
            QWidget { background-color: rgba(11, 14, 20, 200); border: 1px solid rgba(0, 229, 255, 90); border-radius: 6px; }
            QLabel { border: none; background: transparent; }
        """)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 4, 10, 4)
        lay.setSpacing(0)
        self.lbl_hora = QLabel("--:--:--")
        self.lbl_hora.setFont(QFont("Monospace", 18, QFont.Weight.Bold))
        self.lbl_hora.setStyleSheet("color: #39FF14;")
        self.lbl_hora.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sub = QLabel("UTC")
        sub.setFont(QFont("Monospace", 7, QFont.Weight.Bold))
        sub.setStyleSheet("color: #6B7A8D;")
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self.lbl_hora)
        lay.addWidget(sub)

        self._drag_offset = None

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._refrescar)
        self._timer.start(1000)
        self._refrescar()
        self.adjustSize()

    def _refrescar(self):
        import datetime
        utc = datetime.datetime.now() + datetime.timedelta(hours=self.UTC_OFFSET_H)
        self.lbl_hora.setText(utc.strftime("%H:%M:%S"))

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_offset = event.position().toPoint()

    def mouseMoveEvent(self, event):
        if self._drag_offset is not None:
            nueva = self.mapToParent(event.position().toPoint() - self._drag_offset)
            if self.parent() is not None:
                r = self.parent().rect()
                x = max(0, min(nueva.x(), r.width() - self.width()))
                y = max(0, min(nueva.y(), r.height() - self.height()))
                nueva.setX(x)
                nueva.setY(y)
            self.move(nueva)

    def mouseReleaseEvent(self, event):
        self._drag_offset = None


class RadarSensorItemWidget(QWidget):
    toggled = pyqtSignal(str, bool)
    colorClicked = pyqtSignal(str)

    def __init__(self, color: QColor, text: str, checked: bool = True, parent=None):
        super().__init__(parent)
        self.setFixedHeight(24)
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 0, 6, 0)
        layout.setSpacing(8)
        layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        self.checkbox = QCheckBox()
        self.checkbox.setChecked(checked)
        self.checkbox.setStyleSheet("""
            QCheckBox {
                spacing: 0px;
                padding: 0px;
            }
            QCheckBox::indicator {
                width: 12px;
                height: 12px;
                border: 1px solid #00F5FF;
                background-color: #2D313C;
                border-radius: 2px;
            }
            QCheckBox::indicator:checked {
                background-color: #00F5FF;
            }
        """)
        layout.addWidget(self.checkbox)

        # Círculo de color premium (clickeable para cambiar el color del sensor)
        self.color_badge = QLabel()
        self.color_badge.setFixedSize(14, 14)
        self.color_badge.setCursor(Qt.CursorShape.PointingHandCursor)
        self.color_badge.setToolTip("Clic para cambiar el color del sensor")
        self.color_badge.mousePressEvent = self._on_badge_click
        self._render_badge(color)
        layout.addWidget(self.color_badge)

        self.label = QLabel(text)
        self.label.setStyleSheet("color: #E0E6ED; font-size: 8pt; font-weight: bold;")
        layout.addWidget(self.label)
        layout.addStretch()

        self.text_label = text
        self.checkbox.toggled.connect(self._on_toggled)

    def _render_badge(self, color: QColor):
        pixmap = QPixmap(14, 14)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(QBrush(color))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(0, 0, 14, 14, 3, 3)
        painter.end()
        self.color_badge.setPixmap(pixmap)

    def set_color(self, color: QColor):
        self._render_badge(color)

    def _on_badge_click(self, event):
        self.colorClicked.emit(self.text_label)

    def _on_toggled(self, checked: bool):
        self.toggled.emit(self.text_label, checked)


class PanelSensoresFlotante(QWidget):
    """Panel flotante 'Sensores' arrastrable sobre el PPI.

    Grilla horizontal de radares. Cada celda tiene dos controles independientes:
      - CHECKBOX de color (cuadro): activa/desactiva el HISTÓRICO (estela) de ese
        radar. Clic izquierdo alterna; clic derecho elige el color.
      - Botón ON/OFF: prende/apaga la PRESENTACIÓN del radar (símbolos/plots).
    Emite señales que el MainWindow conecta a sus handlers.
    """
    presentacionToggled = pyqtSignal(str, bool)   # botón ON/OFF (símbolos)
    historicoToggled = pyqtSignal(str, bool)       # checkbox color (estela)
    colorClicked = pyqtSignal(str)
    cerrado = pyqtSignal()                         # botón ✕ de cierre

    N_COLS = 2          # columnas de la grilla
    CELL_W = 162        # ancho de cada celda (checkbox + nombre + ON/OFF)
    ROW_H = 22
    ROW_SPACING = 4
    HEADER_H = 28       # título + botones Todos/Ninguno

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("panelSensores")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet("""
            QWidget#panelSensores { background-color: rgba(11, 14, 20, 230);
                border: 1px solid rgba(0, 229, 255, 110); border-radius: 6px; }
            QLabel { background: transparent; border: none; }
        """)
        self._rows: Dict[str, dict] = {}
        self._drag_offset = None

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 6, 8, 8)
        root.setSpacing(6)

        # Barra de título (zona de arrastre)
        header = QHBoxLayout()
        titulo = QLabel("Sensores")
        titulo.setStyleSheet("color:#00E5FF; font-weight:bold; font-size:9pt;")
        header.addWidget(titulo)
        header.addStretch()
        btn_todos = QPushButton("Todos")
        btn_ninguno = QPushButton("Ninguno")
        for b in (btn_todos, btn_ninguno):
            b.setFixedHeight(18)
            b.setStyleSheet("font-size:7pt; padding:1px 6px;")
        btn_todos.clicked.connect(lambda: self._set_all(True))
        btn_ninguno.clicked.connect(lambda: self._set_all(False))
        header.addWidget(btn_todos)
        header.addWidget(btn_ninguno)
        btn_cerrar = QPushButton("✕")
        btn_cerrar.setFixedSize(18, 18)
        btn_cerrar.setToolTip("Cerrar panel")
        btn_cerrar.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_cerrar.setStyleSheet(
            "QPushButton { font-size:8pt; padding:0; color:#E0E6ED; border:none; }"
            "QPushButton:hover { color:#FF5555; }")
        btn_cerrar.clicked.connect(self.cerrado.emit)
        header.addWidget(btn_cerrar)
        root.addLayout(header)

        self._grid = QGridLayout()
        self._grid.setHorizontalSpacing(10)
        self._grid.setVerticalSpacing(self.ROW_SPACING)
        self._grid.setContentsMargins(0, 0, 0, 0)
        root.addLayout(self._grid)

        self.lbl_vacio = QLabel("— sin sensores —")
        self.lbl_vacio.setStyleSheet("color:#6B7A8D; font-size:8pt;")
        self._grid.addWidget(self.lbl_vacio, 0, 0)
        self._refrescar_tamano()

    def agregar_sensor(self, text_label: str, color: QColor,
                       presentacion: bool = True, historico: bool = True):
        if text_label in self._rows:
            return
        self.lbl_vacio.setVisible(False)

        cell = QWidget()
        cell.setFixedHeight(self.ROW_H)
        cell.setFixedWidth(self.CELL_W)
        h = QHBoxLayout(cell)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(6)

        swatch = QLabel()
        swatch.setFixedSize(16, 16)
        swatch.setCursor(Qt.CursorShape.PointingHandCursor)
        swatch.setToolTip("Histórico/estela — Izq: activar/desactivar · Der: color")
        swatch.mousePressEvent = lambda e, t=text_label: self._on_swatch_click(e, t)
        h.addWidget(swatch)

        lbl = QLabel(self._short_name(text_label))
        lbl.setStyleSheet("color:#E0E6ED; font-size:8pt; font-weight:bold;")
        h.addWidget(lbl)
        h.addStretch()

        btn = QPushButton("ON" if presentacion else "OFF")
        btn.setFixedSize(52, 22)
        btn.setToolTip("Presentación del radar (símbolos/plots)")
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.clicked.connect(lambda _=False, t=text_label: self._on_btn_click(t))
        h.addWidget(btn)

        idx = len(self._rows)
        self._grid.addWidget(cell, idx // self.N_COLS, idx % self.N_COLS)
        self._rows[text_label] = {"cell": cell, "swatch": swatch, "label": lbl,
                                  "btn": btn, "color": QColor(color),
                                  "historico": historico, "presentacion": presentacion}
        self._render_swatch(swatch, color, historico)
        self._style_btn(btn, presentacion)
        self._refrescar_tamano()

    def _refrescar_tamano(self):
        """Fija el tamaño del panel manualmente. Con el panel ya visible, el
        sizeHint del layout anidado no propaga, así que adjustSize() colapsaría
        las celdas. Calculamos ancho/alto nosotros según la grilla."""
        n = len(self._rows)
        ncols = min(self.N_COLS, n) if n else 1
        nrows = (n + self.N_COLS - 1) // self.N_COLS if n else 0
        ancho = 16 + ncols * self.CELL_W + (ncols - 1) * 10
        if n == 0:
            alto = self.HEADER_H + 26
        else:
            alto = self.HEADER_H + nrows * self.ROW_H + (nrows - 1) * self.ROW_SPACING + 14
        self.setFixedWidth(max(ancho, 230))
        self.setFixedHeight(alto)
        lay = self.layout()
        if lay is not None:
            lay.invalidate()
            lay.activate()

    def actualizar_color(self, text_label: str, color: QColor):
        r = self._rows.get(text_label)
        if r:
            r["color"] = QColor(color)
            self._render_swatch(r["swatch"], color, r["historico"])

    def set_presentacion(self, text_label: str, activo: bool):
        r = self._rows.get(text_label)
        if r:
            r["presentacion"] = activo
            r["btn"].setText("ON" if activo else "OFF")
            self._style_btn(r["btn"], activo)

    def set_historico(self, text_label: str, activo: bool):
        r = self._rows.get(text_label)
        if r:
            r["historico"] = activo
            self._render_swatch(r["swatch"], r["color"], activo)

    def limpiar(self):
        for r in self._rows.values():
            r["cell"].setParent(None)
            r["cell"].deleteLater()
        self._rows.clear()
        self.lbl_vacio.setVisible(True)
        self._refrescar_tamano()

    def _on_swatch_click(self, event, text: str):
        if event.button() == Qt.MouseButton.LeftButton:
            r = self._rows.get(text)
            if r:
                nuevo = not r["historico"]
                r["historico"] = nuevo
                self._render_swatch(r["swatch"], r["color"], nuevo)
                self.historicoToggled.emit(text, nuevo)
        elif event.button() == Qt.MouseButton.RightButton:
            self.colorClicked.emit(text)

    def _on_btn_click(self, text: str):
        r = self._rows.get(text)
        if r:
            nuevo = not r["presentacion"]
            r["presentacion"] = nuevo
            r["btn"].setText("ON" if nuevo else "OFF")
            self._style_btn(r["btn"], nuevo)
            self.presentacionToggled.emit(text, nuevo)

    def _set_all(self, activo: bool):
        for text, r in self._rows.items():
            if r["presentacion"] != activo:
                r["presentacion"] = activo
                r["btn"].setText("ON" if activo else "OFF")
                self._style_btn(r["btn"], activo)
                self.presentacionToggled.emit(text, activo)

    def _style_btn(self, btn: QPushButton, on: bool):
        if on:
            btn.setStyleSheet("QPushButton{background:#1f7a1f; border:1px solid #39FF14;"
                              "color:#CFFFCF; font-weight:bold; font-size:8pt; border-radius:3px;}")
        else:
            btn.setStyleSheet("QPushButton{background:#5a1c1c; border:1px solid #FF4040;"
                              "color:#FFD0D0; font-weight:bold; font-size:8pt; border-radius:3px;}")

    def _render_swatch(self, lbl: QLabel, color: QColor, activo: bool = True):
        pm = QPixmap(16, 16)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if activo:
            # Cuadro relleno con el color de la estela (histórico activo)
            p.setBrush(QBrush(color))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawRoundedRect(0, 0, 15, 15, 3, 3)
        else:
            # Histórico desactivado: solo contorno gris
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(QColor("#5A6472"), 1.5))
            p.drawRoundedRect(1, 1, 13, 13, 3, 3)
        p.end()
        lbl.setPixmap(pm)

    @staticmethod
    def _short_name(text_label: str) -> str:
        m = re.match(r'^\[\d+/\d+\]\s*(.+)$', text_label)
        return (m.group(1) if m else text_label).strip()[:11]

    # --- arrastre (las áreas vacías mueven el panel; los cuadros consumen su clic) ---
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_offset = event.position().toPoint()

    def mouseMoveEvent(self, event):
        if self._drag_offset is not None:
            nueva = self.mapToParent(event.position().toPoint() - self._drag_offset)
            if self.parent() is not None:
                r = self.parent().rect()
                nueva.setX(max(0, min(nueva.x(), r.width() - self.width())))
                nueva.setY(max(0, min(nueva.y(), r.height() - self.height())))
            self.move(nueva)

    def mouseReleaseEvent(self, event):
        self._drag_offset = None


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("ASTERIX Radar Decoder - Reproductor Multi-Sensor")
        from player.ui_scaling import escalar_ventana
        escalar_ventana(self, 1280, 800)
        
        # Estilo Global Premium: Cyber Radar Theme
        self.setStyleSheet("""
            /* Fondo principal y texto general */
            QMainWindow, QWidget {
                background-color: #0B0E14;
                color: #E0E6ED;
                font-family: 'Segoe UI', Arial, sans-serif;
                font-size: 10pt;
            }

            /* Estilo para los paneles de agrupación */
            QGroupBox {
                background-color: rgba(20, 24, 33, 140);
                border: 1px solid rgba(0, 229, 255, 60);
                border-radius: 6px;
                margin-top: 18px;
                font-weight: bold;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                padding: 0 8px;
                color: #00E5FF; /* Cyan Técnico */
                background-color: #0B0E14;
                border-radius: 4px;
            }

            /* Botones con efectos visuales premium y glow en hover */
            QPushButton {
                background-color: rgba(45, 52, 71, 180);
                border: 1px solid rgba(0, 229, 255, 80);
                border-radius: 4px;
                padding: 6px 12px;
                color: #FFFFFF;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: rgba(0, 229, 255, 30);
                border: 1px solid #39FF14; /* Borde neón verde en hover */
                color: #39FF14;
            }
            QPushButton:pressed {
                background-color: #39FF14;
                color: #0B0E14;
            }
            QPushButton:disabled {
                background-color: rgba(45, 52, 71, 80);
                border: 1px solid rgba(255, 255, 255, 20);
                color: gray;
            }

            /* Listas de Selección (Sensores) */
            QListWidget {
                background-color: rgba(14, 18, 27, 220);
                border: 1px solid rgba(0, 229, 255, 80);
                border-radius: 4px;
                padding: 4px;
                color: #E0E6ED;
            }
            QListWidget::item {
                padding: 6px;
                border-bottom: 1px solid rgba(255, 255, 255, 10);
            }
            QListWidget::item:hover {
                background-color: rgba(0, 229, 255, 20);
            }
            QListWidget::item:selected {
                background-color: rgba(0, 229, 255, 40);
                color: #00E5FF;
                border-left: 3px solid #00E5FF;
            }


            /* Controles numéricos y desplegables (SpinBoxes / ComboBoxes) */
            QComboBox {
                background-color: #1A2130;
                border: 1px solid rgba(0, 229, 255, 80);
                border-radius: 4px;
                padding: 3px 5px;
                color: white;
            }
            QComboBox::drop-down {
                subcontrol-origin: padding;
                subcontrol-position: top right;
                width: 20px;
                border-left: 1px solid rgba(0, 229, 255, 80);
            }
            QComboBox QAbstractItemView {
                background-color: #0B0E14;
                color: #E0E6ED;
                border: 1px solid #00E5FF;
                selection-background-color: rgba(0, 229, 255, 40);
                selection-color: #00E5FF;
            }

            QSpinBox {
                background-color: #1A2130;
                color: white;
                border: 1px solid rgba(0, 229, 255, 80);
                border-radius: 4px;
                padding: 3px 5px;
            }

            /* Timeline Slider premium estilo ATC */
            QSlider::groove:horizontal {
                border: 1px solid rgba(255, 255, 255, 20);
                height: 6px;
                background: #0E131F;
                border-radius: 3px;
            }
            QSlider::sub-page:horizontal {
                background: #00E5FF; /* Relleno cyan */
                border-radius: 3px;
            }
            QSlider::handle:horizontal {
                background: #00E5FF;
                border: 1px solid #39FF14;
                width: 14px;
                height: 14px;
                margin-top: -4px;
                margin-bottom: -4px;
                border-radius: 7px;
            }
            QSlider::handle:horizontal:hover {
                background: #39FF14;
                border: 1px solid #FFFFFF;
            }

            /* Scrollbars futuristas estilizados */
            QScrollBar:vertical {
                border: none;
                background: #0B0E14;
                width: 8px;
            }
            QScrollBar::handle:vertical {
                background: rgba(0, 229, 255, 80);
                min-height: 20px;
                border-radius: 4px;
            }
            QScrollBar::handle:vertical:hover {
                background: #39FF14;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
        """)
        
        # Estado — Resolve default-site-params directory robustly
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        site_params_dir = os.path.join(base_dir, "default-site-params")
        self.sensores = cargar_sensores(site_params_dir)
        self.sensores_conocidos: Set[str] = set()
        self.sensores_activos: Set[str] = set()      # presentación (símbolos/plots)
        self.estelas_activas: Set[str] = set()       # histórico/estela por radar
        self.autocentered_on_first_sensor = False
        self._sensor_rpms: Dict[Tuple[int, int], float] = {}
        self._sensor_categories: Dict[Tuple[int, int], Set[int]] = {}
        
        # Filtros Avanzados y Contadores de Mensajes ASTERIX (Fase 9)
        self.total_messages_received = 0
        self.selected_messages_received = 0
        self.data_filter_dialog = None
        
        self.label_filter_config = {
            "codigo_a": True, "numero_mensaje": False, "codigo_c": True,
            "direccion_aeronave": True, "numero_respuestas": False, "velocidad": True,
            "hora_utc": False, "numero_pista": True, "identific_aeronave": True,
            "altitud_adsb": True, "cat_emisor_adsb": False, "veloc_vertic_adsb": False,
            "rho_theta": False, "rumbo_verdadero": False, "rumbo_magnetico": False,
            "orientacion": "NE", "sel_por_codigo_a": True, "sel_por_posicion": False
        }
        
        self.data_filter_config = {
            "codes": ["", "", "", ""], "habilitar_filtro_codigos": False,
            "a_todos": True, "a_validos": False, "a_invalidos": False, "a_ausentes": False,
            "c_todos": True, "c_validos": False, "c_invalidos": False, "c_ausentes": False,
            "todos_extra": True, "spi": False, "emx": False, "cal": False, "nocal": False,
            "cmb": False, "nocmb": False, "dist_inf": 0.0, "dist_sup": 500.0,
            "az_inf": 0, "az_sup": 360, "alt_inf": -9999, "alt_sup": 99999,
            "msg_inf": 1, "msg_sup": 302761, "id21_inf": "000000", "id21_sup": "FFFFFF",
            "sac_filtro": "", "sic_filtro": "",
            "plots_secun": True, "plots_prim": True, "pistas_secun": True, "pistas_prim": True,
            "servicio": True, "meteos": True, "ads_b": True
        }
        
        self.worker: Optional[PlaybackWorker] = None
        self.profile_manager = ProfileManager()
        self.techo_incumbencia = self.profile_manager.get_nivel_incumbencia()
        self.cache_dir = tempfile.mkdtemp(prefix="asterix_cache_")
        
        self.exporter = PassExporter()
        
        # Mapas interactivos con checkboxes (seleccionar/deseleccionar)
        self._loaded_custom_maps = {}
        self._active_map_paths = set()
        self.map_actions = {}
        self.user_areas = []

        # Fusión/Sensores STCA se maneja ahora de forma autocontenida en RadarWidget
        self._setup_ui()

        self.playing = False
        self.total_frames = 0
        self.duration = 0.0
        self.pcap_path = ""
        # Centro/zoom previos a una reproducción filtrada (para restaurar al detener)
        self._centro_pre_filtrado = None
        self.udp_active = False
        self._playback_player = None

        # Aplicar el perfil guardado en disco
        self._aplicar_perfil(self.profile_manager.profile)

        # Cargar cartografía base + mapas generales + mapas del perfil al arrancar
        if hasattr(self.radar, 'map_manager') and hasattr(self.radar.map_manager, 'load_profile_maps'):
            self.radar.map_manager.load_profile_maps(self.profile_manager.profile, self.profile_manager)
            self.radar.map_manager.reproject_all(self.radar.proy)
            self.radar.update()

    def _setup_ui(self):
        # 1. Widget Central (El Mapa de Radar)
        self.radar = RadarWidget(
            sensores=self.sensores,
            declinacion_magnetica=self.profile_manager.get_declinacion_magnetica()
        )
        self.radar.plot_filter_fn = self._plot_passes_filters
        self.radar.sensores_visibles = self.sensores_activos.copy()
        self.radar.setStyleSheet("background-color: #0B0E14;")
        # Inyectar perfil activo al gestor de altimetría (TA + estación)
        self.radar.altimetry.apply_profile(self.profile_manager.profile)
        # Pre-poblar RPMs conocidos desde default-site-params (antes de que lleguen mensajes CAT34)
        for (sac, sic), info in self.sensores.items():
            rpm = info.get('rpm')
            if rpm is not None and rpm > 0:
                self.radar.sensor_rpms[(sac, sic)] = rpm
                self._sensor_rpms[(sac, sic)] = rpm
        self.setCentralWidget(self.radar)

        # 2. Panel Lateral Acoplable (QDockWidget)
        self._setup_dock_widget()
        self._setup_technical_monitor_dock()

        # 3. Barra de Menú (QMenuBar)
        self._setup_menu_bar()

        # 4. Barra de Herramientas (QToolBar)
        self._setup_tool_bar()

        # 5. Barra HUD operativa (siempre visible, también para controlador)
        self._setup_hud_bar()

        # 6. Reloj flotante UTC (arrastrable, visible en ambos roles)
        self.reloj_utc = RelojFlotanteUTC(self.radar)
        self._reposicionar_reloj()
        self.reloj_utc.show()
        self.reloj_utc.raise_()

        # 6b. Panel flotante 'Sensores' (arrastrable, ON/OFF + color de estela)
        self.panel_sensores = PanelSensoresFlotante(self.radar)
        self.panel_sensores.presentacionToggled.connect(self._on_custom_sensor_toggled)
        self.panel_sensores.historicoToggled.connect(self._on_historico_toggled)
        self.panel_sensores.colorClicked.connect(self._on_sensor_color_clicked)
        self.panel_sensores.cerrado.connect(self._cerrar_panel_sensores)
        self.panel_sensores.move(20, 20)
        self.panel_sensores.show()
        self.panel_sensores.raise_()
        # Reubicar el reloj cuando cambia el ancho del radar (ej. al ensanchar el
        # dock lateral, que no dispara el resizeEvent de la ventana).
        self.radar.installEventFilter(self)

    def _setup_menu_bar(self):
        menu_bar = self.menuBar()
        menu_bar.setStyleSheet("""
            QMenuBar {
                background-color: #121824;
                color: #E0E6ED;
                border-bottom: 1px solid rgba(0, 229, 255, 50);
            }
            QMenuBar::item {
                background-color: transparent;
                padding: 5px 10px;
            }
            QMenuBar::item:selected {
                background-color: rgba(0, 229, 255, 30);
                color: #39FF14;
            }
            QMenu {
                background-color: #0E131F;
                color: #E0E6ED;
                border: 1px solid #00E5FF;
            }
            QMenu::item {
                padding: 6px 20px;
            }
            QMenu::item:selected {
                background-color: rgba(0, 229, 255, 30);
                color: #39FF14;
            }
        """)

        # Menú Archivo
        menu_archivo = menu_bar.addMenu("Archivo")
        self.act_ver_logs = menu_archivo.addAction("Ver Log de Alertas STCA...", self._abrir_log_stca)
        self.act_ver_logs_calidad = menu_archivo.addAction("Log de Eventos", self._abrir_log_calidad)
        menu_archivo.addSeparator()
        self.act_salir = menu_archivo.addAction("Salir", self.close)

        # Menú Exportar
        menu_exportar = menu_bar.addMenu("Exportar")
        self.act_exp_kmz = menu_exportar.addAction("Trayectorias a Google Earth (KMZ)", self.exportar_kmz)
        self.act_exp_playback = menu_exportar.addAction("Reproducción de Vuelo Animado a Google Earth (KMZ)...", self.exportar_playback_kmz)
        self.act_exp_cobertura = menu_exportar.addAction("Mapa de Cobertura Real a Google Earth (KMZ)...", self.exportar_cobertura_kmz)
        self.act_exp_csv = menu_exportar.addAction("Heatmap a QGIS (CSV)", self.exportar_csv)
        self.act_exp_parquet = menu_exportar.addAction("Datos a Power BI (Parquet)", self.exportar_parquet)
        self.act_exp_kmz.setEnabled(False)
        self.act_exp_playback.setEnabled(False)
        self.act_exp_cobertura.setEnabled(False)
        self.act_exp_csv.setEnabled(False)
        self.act_exp_parquet.setEnabled(False)

        # Menú Ver
        menu_ver = menu_bar.addMenu("Ver")
        self.act_toggle_dock = self.dock_lateral.toggleViewAction()
        self.act_toggle_dock.setText("Panel Lateral de Controles")
        menu_ver.addAction(self.act_toggle_dock)
        
        self.act_toggle_tech_dock = self.dock_technical.toggleViewAction()
        self.act_toggle_tech_dock.setText("Diagnóstico Técnico ATSEP")
        menu_ver.addAction(self.act_toggle_tech_dock)
        
        self.act_toggle_reloj = menu_ver.addAction("Reloj UTC Flotante")
        self.act_toggle_reloj.setCheckable(True)
        self.act_toggle_reloj.setChecked(True)
        self.act_toggle_reloj.toggled.connect(self._toggle_reloj_utc)
        self.act_toggle_panel_sensores = menu_ver.addAction("Panel Sensores Flotante")
        self.act_toggle_panel_sensores.setCheckable(True)
        self.act_toggle_panel_sensores.setChecked(True)
        self.act_toggle_panel_sensores.toggled.connect(
            lambda v: self.panel_sensores.setVisible(v) or (self.panel_sensores.raise_() if v else None))
        menu_ver.addSeparator()
        self.act_analizador_paquetes = menu_ver.addAction("Analizador de Paquetes…", self._abrir_analizador_paquetes)
        menu_ver.addSeparator()
        self.act_toggle_incumbencia = menu_ver.addAction("Vista de Incumbencia (Jurisdicción)")
        self.act_toggle_incumbencia.setCheckable(True)
        self.act_toggle_incumbencia.setChecked(False)
        self.act_toggle_incumbencia.toggled.connect(self._toggle_incumbencia)

        menu_ver.addSeparator()
        self.act_stca_habilitado = menu_ver.addAction("Habilitar STCA")
        self.act_stca_habilitado.setCheckable(True)
        self.act_stca_habilitado.setChecked(self.radar.stca_habilitado if hasattr(self, 'radar') and self.radar else True)
        self.act_stca_habilitado.toggled.connect(self._toggle_stca_habilitado)

        self.act_apw_habilitado = menu_ver.addAction("Habilitar APW")
        self.act_apw_habilitado.setCheckable(True)
        self.act_apw_habilitado.setChecked(self.radar.apw_habilitado if hasattr(self, 'radar') and self.radar else True)
        self.act_apw_habilitado.toggled.connect(self._toggle_apw_habilitado)

        self.act_msaw_habilitado = menu_ver.addAction("Habilitar MSAW")
        self.act_msaw_habilitado.setCheckable(True)
        self.act_msaw_habilitado.setChecked(self.radar.msaw_habilitado if hasattr(self, 'radar') and self.radar else True)
        self.act_msaw_habilitado.toggled.connect(self._toggle_msaw_habilitado)

        # Submenú: horizonte del vector velocidad (1/2/3 min)
        menu_vector = menu_ver.addMenu("Vector Velocidad")
        from PyQt6.QtGui import QActionGroup
        self._grupo_vector_min = QActionGroup(self)
        self._grupo_vector_min.setExclusive(True)
        actual_min = getattr(self.radar, 'vector_tiempo_minutos', 2)
        for minutos in (1, 2, 3):
            act = menu_vector.addAction(f"{minutos} minuto{'s' if minutos > 1 else ''}")
            act.setCheckable(True)
            act.setChecked(minutos == actual_min)
            act.triggered.connect(lambda _checked, m=minutos: self._set_vector_minutos(m))
            self._grupo_vector_min.addAction(act)

        # Menú Configuración
        menu_config = menu_bar.addMenu("Configuración")
        menu_config.addAction(_icon("fa5s.cog"), "Perfil Operativo / Jurisdicción...", self._abrir_perfil_admin)
        # Submenú dinámico para cambiar de perfil activo en caliente
        self.menu_perfiles = menu_config.addMenu("Cambiar Perfil")
        self.menu_perfiles.aboutToShow.connect(self._rebuild_profiles_menu)
        # Submenú para cambiar el rol operativo rápido (controlador ↔ técnico)
        self.menu_rol = menu_config.addMenu("Rol Operativo")
        self.menu_rol.aboutToShow.connect(self._rebuild_rol_menu)
        # Calibración de registración: SOLO rol técnico (se habilita según rol)
        menu_config.addSeparator()
        self.act_calibracion = menu_config.addAction(
            "Análisis y Calibración (Técnico)…", self._abrir_calibracion)
        self.act_calibracion.setEnabled(self.profile_manager.get_rol() == "tecnico")

        # Menú Mapas — capas generadas dinámicamente desde la base ATM (atm.duckdb)
        from player import atm_db, atm_maps
        self.menu_mapas = menu_bar.addMenu("Mapas")
        self.atm_map_actions = {}

        if atm_db.available():
            sub_aero = self.menu_mapas.addMenu("Aerovías")
            for label, cat in [("Superiores", "SUP"), ("Inferiores", "INF"), ("RNAV", "RNAV")]:
                self._add_atm_action(sub_aero, f"AERO_{cat}", label,
                                     (lambda c=cat: atm_maps.airway_segments(c)))

            sub_proc = self.menu_mapas.addMenu("Procedimientos por Aeropuerto")
            for icao in atm_db.airports_with_procedures():
                sub_ap = sub_proc.addMenu(icao)
                for kind in ("SID", "STAR", "IAP"):
                    self._add_atm_action(sub_ap, f"{icao}_{kind}", kind,
                                         (lambda i=icao, k=kind: atm_maps.procedure_segments(i, k)))

            sub_fix = self.menu_mapas.addMenu("Puntos y Fixes (Waypoints)")
            for label, kinds in [("VOR", ["VO"]), ("NDB", ["ND"]), ("DME", ["DM"]),
                                 ("Ruta (ROU)", ["RO"]), ("Terminal (APP)", ["AP"])]:
                self._add_atm_action(sub_fix, f"FIX_{label}", label,
                                     (lambda k=kinds: atm_maps.fix_segments(k)))
        else:
            act_na = self.menu_mapas.addAction("Base ATM no encontrada (data/atm/atm.duckdb)")
            act_na.setEnabled(False)

        self.menu_mapas.addSeparator()
        self.menu_mapas.addAction("Cargar Mapa Personalizado (.geojson)...", self._cargar_mapa_personalizado)

        # Menú Áreas — restringidas / prohibidas / peligrosas (desde atm.duckdb)
        self.menu_areas = menu_bar.addMenu("Áreas")
        self.area_submenus = {}
        self.individual_area_actions = {}
        self._rebuild_areas_menu()

        # Menú Modo (Playback / Consola)
        menu_modo = menu_bar.addMenu("Modo")
        # El controlador trabaja online: no puede activar playback (se gatea en _aplicar_rol).
        self.act_modo_playback = menu_modo.addAction(
            _icon("fa5s.play-circle"), "Modo Playback", self._abrir_modo_playback)
        menu_modo.addAction(_icon("fa5s.network-wired"), "Modo Consola", self._abrir_modo_consola)
        menu_modo.addSeparator()
        # --- Vista EUROCONTROL ODS (controlador) ---
        self.act_ods = menu_modo.addAction(_icon("fa5s.satellite-dish"), "Vista ODS (controlador)")
        self.act_ods.setCheckable(True)
        self.act_ods.setChecked(bool(getattr(getattr(self, 'radar', None), 'ods_enabled', True)))
        self.act_ods.toggled.connect(self._toggle_ods)
        menu_modo.addAction(_icon("fa5s.sliders-h"), "Intensidad Visual…", self._abrir_ods_intensidad)
        menu_modo.addSeparator()
        self.act_fir = menu_modo.addAction(_icon("fa5s.globe-americas"), "Vista FIR (satélite)")
        self.act_fir.setCheckable(True)
        self.act_fir.toggled.connect(self._toggle_vista_fir)

    def _toggle_vista_fir(self, on: bool):
        """Vista FIR satelital EMBEBIDA: cubre el PPI (hija del radar). Off -> oculta."""
        import os
        from player.firmap.firmap_view import FirMapView
        if on:
            if getattr(self, '_fir_view', None) is None:
                path = "data/firmap/argentina.mbtiles"
                if not os.path.exists(path):
                    alt = "data/firmap/_test_lowzoom.mbtiles"
                    path = alt if os.path.exists(alt) else None
                v = FirMapView(path, parent=self.radar)  # embebida sobre el PPI
                lat = getattr(self.radar, 'aeropuerto_lat', None)
                lon = getattr(self.radar, 'aeropuerto_lon', None)
                if lat is not None and lon is not None:
                    v.set_center(lon, lat)
                    v.set_home(lon, lat)
                # Arrancar al mayor zoom disponible que no supere ~nivel TMA.
                v.set_zoom(min(v.max_zoom, 8))
                v.track_selected.connect(self._fir_select_track)
                self._fir_view = v
                self._fir_timer = QTimer(self)
                self._fir_timer.timeout.connect(self._refresh_fir)
            self._fir_view.setGeometry(self.radar.rect())
            self._fir_view.show()
            self._fir_view.raise_()
            self._fir_view.setFocus()
            self._fir_timer.start(300)  # ~3 Hz
            self._refresh_fir()          # primer frame inmediato
        else:
            if getattr(self, '_fir_timer', None) is not None:
                self._fir_timer.stop()
            if getattr(self, '_fir_view', None) is not None:
                self._fir_view.hide()

    def _cerrar_panel_sensores(self):
        self.panel_sensores.hide()
        if hasattr(self, 'act_toggle_panel_sensores'):
            self.act_toggle_panel_sensores.setChecked(False)

    def _refresh_fir(self):
        from player.firmap.feed import build_tracks, build_maps
        if getattr(self, '_fir_view', None) is not None:
            from player.ods import palette as _pal
            intens = getattr(self.radar, 'ods_layer_intensity', _pal.LAYER_DEFAULT)
            self._fir_view.set_map_intensity(intens.get('map', _pal.LAYER_DEFAULT['map']))
            self._fir_view.set_maps(build_maps(self.radar))
            self._fir_view.set_tracks(build_tracks(self.radar))

    def _fir_select_track(self, track_id):
        """Click en un avión de la vista FIR -> selecciona el track en el PPI."""
        if hasattr(self.radar, 'focused_target_id'):
            self.radar.focused_target_id = track_id
            self.radar.update()

    def _toggle_ods(self, on: bool):
        if hasattr(self.radar, 'ods_enabled'):
            self.radar.ods_enabled = bool(on)
            self.radar.update()

    def _abrir_ods_intensidad(self):
        """Diálogo con sliders de intensidad por capa ODS (0–100%)."""
        from PyQt6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QSlider
        from PyQt6.QtCore import Qt
        from player.ui_scaling import escalar_ventana
        dlg = QDialog(self)
        dlg.setWindowTitle("Intensidad Visual")
        v = QVBoxLayout(dlg)
        capas = [("map", "Mapa"), ("labels", "Etiquetas"),
                 ("history", "Historial"), ("compass", "Rosa de rumbos"),
                 ("tools", "Herramientas (RBL)")]
        intens = getattr(self.radar, 'ods_layer_intensity', {})
        for key, lbl in capas:
            row = QHBoxLayout()
            etq = QLabel(lbl)
            etq.setMinimumWidth(110)
            row.addWidget(etq)
            s = QSlider(Qt.Orientation.Horizontal)
            s.setRange(0, 100)
            s.setValue(int(intens.get(key, 0.5) * 100))
            s.valueChanged.connect(
                lambda val, k=key: self.radar.set_ods_layer_intensity(k, val / 100.0))
            row.addWidget(s)
            v.addLayout(row)
        escalar_ventana(dlg, 380, 240, centrar=False)
        dlg.show()

    def _abrir_modo_playback(self):
        """Abre el reproductor flotante y permite elegir el archivo a reproducir."""
        # El controlador trabaja online: el playback está vedado.
        if self.profile_manager.get_rol() == "controlador":
            QMessageBox.information(self, "Modo Playback",
                                    "El rol Controlador trabaja en vivo (UDP). "
                                    "El modo Playback es exclusivo del rol Técnico.")
            return
        from player.playback_player_widget import PlaybackPlayerWidget
        if getattr(self, '_playback_player', None) is None:
            w = PlaybackPlayerWidget(self)
            w.open_requested.connect(self._cargar_pcap)
            w.playpause_requested.connect(self._toggle_play)
            w.stop_requested.connect(self._stop)
            w.speed_changed.connect(self._modo_playback_velocidad)
            w.seek_requested.connect(self._modo_playback_seek)
            w.range_changed.connect(self._modo_playback_rango)
            self._playback_player = w
        self._playback_player.set_enabled_transport(self.worker is not None and self.worker.scanned)
        self._playback_player.show()
        self._playback_player.raise_()
        self._playback_player.activateWindow()

    def _modo_playback_velocidad(self, texto: str):
        i = self.combo_vel.findText(texto)
        if i >= 0:
            self.combo_vel.setCurrentIndex(i)  # dispara _cambiar_velocidad

    def _modo_playback_seek(self, pct: int):
        self.slider_tiempo.setValue(int(pct))
        self._seek()

    def _modo_playback_rango(self, t0: int, t1: int):
        """Aplica el tramo horario al worker. -1 = sin límite en ese extremo."""
        if self.worker is None:
            return
        a = None if t0 < 0 else float(t0)
        b = None if t1 < 0 else float(t1)
        self.worker.set_time_range(a, b)

    def _abrir_modo_consola(self):
        """Abre el diálogo para conectar por IP y puerto (entrada UDP en vivo)."""
        if self.udp_active:
            QMessageBox.information(self, "Modo Consola",
                                    "Ya hay una conexión UDP activa.")
            return
        datos = self._dialogo_conexion_udp(
            ip=self.txt_udp_ip.text().strip(),
            puerto=self.txt_udp_port.text().strip())
        if not datos:
            return
        _nombre, ip, puerto = datos
        if not ip or not puerto:
            return
        self.txt_udp_ip.setText(ip)
        self.txt_udp_port.setText(puerto)
        self._toggle_udp()

    def _setup_tool_bar(self):
        self.toolbar = QToolBar("Controles de Reproducción")
        self.toolbar.setMovable(False)
        self.toolbar.setStyleSheet("""
            QToolBar {
                background-color: #121824;
                border-bottom: 1px solid rgba(0, 229, 255, 40);
                padding: 6px;
                spacing: 12px;
            }
            QLabel {
                color: #00E5FF;
                font-weight: bold;
            }
        """)
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, self.toolbar)

        # Botón Play / Pause
        self.btn_play = QPushButton(" Reproducir")
        self.btn_play.setIcon(_icon("fa5s.play"))
        self.btn_play.setEnabled(False)
        self.btn_play.clicked.connect(self._toggle_play)
        self.toolbar.addWidget(self.btn_play)

        # Botón Stop
        self.btn_stop = QPushButton(" Stop")
        self.btn_stop.setIcon(_icon("fa5s.stop"))
        self.btn_stop.setEnabled(False)
        self.btn_stop.clicked.connect(self._stop)
        self.toolbar.addWidget(self.btn_stop)

        self.toolbar.addSeparator()

        # Label de Hora Actual (TDD)
        lbl_tdd_title = QLabel("Hora UTC: ")
        self.toolbar.addWidget(lbl_tdd_title)

        self.lbl_tiempo = QLabel("00:00:00")
        self.lbl_tiempo.setFont(QFont("Monospace", 12, QFont.Weight.Bold))
        self.lbl_tiempo.setStyleSheet("color: #39FF14; background-color: #0B0E14; padding: 2px 6px; border: 1px solid #4B5263; border-radius: 4px;")
        self.toolbar.addWidget(self.lbl_tiempo)

        self.toolbar.addSeparator()

        # Slider de Línea de Tiempo
        lbl_slider_title = QLabel("Timeline: ")
        self.toolbar.addWidget(lbl_slider_title)

        self.slider_tiempo = QSlider(Qt.Orientation.Horizontal)
        self.slider_tiempo.setEnabled(False)
        self.slider_tiempo.setMinimum(0)
        self.slider_tiempo.setMaximum(100)
        self.slider_tiempo.setMinimumWidth(250)
        self.slider_tiempo.sliderReleased.connect(self._seek)
        self.toolbar.addWidget(self.slider_tiempo)

        self.toolbar.addSeparator()

        # Selector de Velocidad
        lbl_vel_title = QLabel("Velocidad: ")
        self.toolbar.addWidget(lbl_vel_title)

        self.combo_vel = QComboBox()
        self.combo_vel.addItems(["1x", "2x", "4x", "5x", "10x", "50x"])
        self.combo_vel.currentIndexChanged.connect(self._cambiar_velocidad)
        self.combo_vel.setStyleSheet("background-color: #2D313C; color: white;")
        self.toolbar.addWidget(self.combo_vel)

        # Controles de reproducción ocultos hasta que se cargue un archivo (Modo Playback)
        self._playback_disponible = False
        self.toolbar.setVisible(False)

    def _setup_hud_bar(self):
        """Barra HUD operativa siempre visible (incluido rol controlador).
        Muestra: usuario/rol, aeropuerto, frecuencias de sector, QNH, TA y hora UTC.
        """
        self.hud_bar = QToolBar("HUD Operativo")
        self.hud_bar.setMovable(False)
        self.hud_bar.setStyleSheet("""
            QToolBar {
                background-color: #0E1420;
                border-bottom: 1px solid rgba(0, 229, 255, 60);
                padding: 4px;
                spacing: 10px;
            }
        """)
        # Nueva fila propia, encima de la toolbar de playback
        self.addToolBarBreak(Qt.ToolBarArea.TopToolBarArea)
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, self.hud_bar)

        def _campo(titulo: str, valor: str, color_valor: str = "#39FF14"):
            cont = QWidget()
            lay = QHBoxLayout(cont)
            lay.setContentsMargins(6, 0, 6, 0)
            lay.setSpacing(4)
            t = QLabel(titulo)
            t.setStyleSheet("color: #6B7A8D; font-size: 8pt; font-weight: bold;")
            v = QLabel(valor)
            v.setFont(QFont("Monospace", 9, QFont.Weight.Bold))
            v.setStyleSheet(f"color: {color_valor};")
            lay.addWidget(t)
            lay.addWidget(v)
            return cont, v

        cont_user, self.lbl_hud_user = _campo("OP", "—", "#00E5FF")
        self.hud_bar.addWidget(cont_user)
        self.hud_bar.addSeparator()
        cont_apt, self.lbl_hud_apt = _campo("APT", "—", "#00E5FF")
        self.hud_bar.addWidget(cont_apt)
        self.hud_bar.addSeparator()
        cont_freq, self.lbl_hud_freqs = _campo("TWR/GND/APP", "—", "#FFD700")
        self.hud_bar.addWidget(cont_freq)
        self.hud_bar.addSeparator()
        cont_qnh, self.lbl_hud_qnh = _campo("QNH", "1013 hPa")
        self.hud_bar.addWidget(cont_qnh)
        self.hud_bar.addSeparator()
        cont_ta, self.lbl_hud_ta = _campo("TA", "—")
        self.hud_bar.addWidget(cont_ta)

        # Espaciador para empujar la hora UTC a la derecha
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.hud_bar.addWidget(spacer)
        cont_utc, self.lbl_hud_utc = _campo("UTC", "00:00:00", "#39FF14")
        self.hud_bar.addWidget(cont_utc)

        self._actualizar_hud(self.profile_manager.profile)

    def _actualizar_hud(self, perfil_data: dict):
        """Refresca los campos del HUD desde el perfil operativo."""
        if not hasattr(self, 'hud_bar'):
            return
        nombre = perfil_data.get("nombre_usuario", "—")
        rol = str(perfil_data.get("rol", "tecnico")).strip().upper()
        apt = perfil_data.get("aeropuerto_trabajo") or perfil_data.get("aeropuerto") or "—"
        freqs = perfil_data.get("frecuencias_sector", ["", "", ""])
        freqs = [str(f).strip() if str(f).strip() else "---" for f in (list(freqs) + ["", "", ""])[:3]]
        ta = perfil_data.get("transition_altitude", 10000)

        self.lbl_hud_user.setText(f"{nombre} ({rol})")
        self.lbl_hud_apt.setText(str(apt))
        self.lbl_hud_freqs.setText(" / ".join(freqs))
        self.lbl_hud_ta.setText(f"{int(ta)} ft")

    def _make_toggle_button(self, text: str, accent: str = "#00E5FF", checked: bool = False) -> QPushButton:
        """Botón checkable estilo toggle para la consola (reemplazo de QCheckBox)."""
        btn = QPushButton(text)
        btn.setCheckable(True)
        btn.setChecked(checked)
        btn.setFixedHeight(24)
        btn.setStyleSheet(f"""
            QPushButton {{
                background-color: #121824;
                border: 1px solid {accent};
                border-radius: 4px;
                color: {accent};
                font-size: 8pt;
                font-weight: bold;
                padding: 4px 8px;
                text-align: left;
            }}
            QPushButton:hover {{
                background-color: rgba(255, 255, 255, 12);
            }}
            QPushButton:checked {{
                background-color: {accent};
                color: #0B0E14;
            }}
            QPushButton:disabled {{
                border: 1px solid rgba(255, 255, 255, 30);
                color: gray;
                background-color: rgba(45, 52, 71, 80);
            }}
        """)
        return btn

    def _setup_dock_widget(self):
        self.dock_lateral = QDockWidget("Controles y Filtros", self)
        self.dock_lateral.setAllowedAreas(Qt.DockWidgetArea.LeftDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea)
        
        # Scroll area dentro del dock para evitar clipping
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea { border: none; background-color: #0B0E14; }")
        
        container = QWidget()
        container.setStyleSheet("background-color: #0B0E14;")
        v_layout = QVBoxLayout(container)
        v_layout.setContentsMargins(6, 6, 6, 6)
        v_layout.setSpacing(10)

        # A. Grupo Cargar PCAP (Acceso Rápido)
        grupo_rep = QGroupBox("Carga Rápida")
        l_rep = QVBoxLayout()
        l_rep.setSpacing(6)
        self.btn_cargar = QPushButton(" Modo Playback")
        self.btn_cargar.setIcon(_icon("fa5s.folder-open"))
        self.btn_centrar = QPushButton(" Centrar Mapa")
        self.btn_centrar.setIcon(_icon("fa5s.crosshairs"))
        self.btn_centrar.setToolTip("Recentrar la vista en el sensor activo")
        self.btn_cargar.clicked.connect(self._cargar_pcap)
        self.btn_centrar.clicked.connect(self._centrar_mapa)
        l_rep.addWidget(self.btn_cargar)
        l_rep.addWidget(self.btn_centrar)
        grupo_rep.setLayout(l_rep)
        v_layout.addWidget(grupo_rep)

        # Grupo Proyección (debajo de Centrar Mapa)
        self.grupo_proy = QGroupBox("Proyección")
        l_sensor = QVBoxLayout()
        l_sensor.setContentsMargins(6, 12, 6, 6)
        l_sensor.setSpacing(4)
        self.combo_sensor = QComboBox()
        self.combo_sensor.addItem("Autocentrado")
        self.combo_sensor.setToolTip("Seleccionar sensor para centrar y proyectar la vista")
        self.combo_sensor.currentIndexChanged.connect(self._on_sensor_combo_changed)
        self.combo_sensor.setStyleSheet("background-color: #2D313C; color: white;")
        l_sensor.addWidget(self.combo_sensor)
        self.grupo_proy.setLayout(l_sensor)
        v_layout.addWidget(self.grupo_proy)

        # B. Grupo Radares Activos (SAC/SIC)
        grupo_sacsic = QGroupBox("Radares Activos (SAC/SIC)")
        v_s = QVBoxLayout(grupo_sacsic)
        v_s.setContentsMargins(6, 12, 6, 6)
        v_s.setSpacing(4)

        # Botones Todos / Ninguno
        h_btns_s = QHBoxLayout()
        self.btn_sens_todos = QPushButton("Todos")
        self.btn_sens_ninguno = QPushButton("Ninguno")
        self.btn_sens_todos.setFixedHeight(20)
        self.btn_sens_ninguno.setFixedHeight(20)
        self.btn_sens_todos.setStyleSheet("font-size: 8pt; padding: 2px;")
        self.btn_sens_ninguno.setStyleSheet("font-size: 8pt; padding: 2px;")
        self.btn_sens_todos.clicked.connect(self._sensores_todos)
        self.btn_sens_ninguno.clicked.connect(self._sensores_ninguno)
        h_btns_s.addWidget(self.btn_sens_todos)
        h_btns_s.addWidget(self.btn_sens_ninguno)
        v_s.addLayout(h_btns_s)

        # Lista interactiva
        self.list_sensores = QListWidget()
        self.list_sensores.setFixedHeight(120)
        self.list_sensores.itemChanged.connect(self._on_sensor_check_changed)
        v_s.addWidget(self.list_sensores)
        # El control de radares activos ahora vive en el panel flotante 'Sensores'
        # (menú Ver). Mantenemos este grupo oculto como respaldo de estado/sync
        # interno (list_sensores lo usan el registro de sensores y _sync_panel_sensores).
        grupo_sacsic.setParent(container)
        grupo_sacsic.setVisible(False)

        # C. Grupo Entrada UDP en Vivo
        grupo_udp = QGroupBox("Entrada UDP en Vivo")
        l_udp = QVBoxLayout()
        l_udp.setContentsMargins(6, 12, 6, 6)
        l_udp.setSpacing(4)

        # Fila de presets guardados (radar -> ip/puerto)
        l_udp_preset = QHBoxLayout()
        self.combo_udp_preset = QComboBox()
        self.combo_udp_preset.setFixedHeight(22)
        self.combo_udp_preset.setStyleSheet("background-color: #2D313C; color: white; border: 1px solid #4B5263; border-radius: 4px; padding: 1px;")
        self.combo_udp_preset.currentIndexChanged.connect(self._on_udp_preset_selected)
        self.btn_guardar_udp = QPushButton()
        self.btn_guardar_udp.setIcon(_icon("fa5s.save"))
        self.btn_guardar_udp.setToolTip("Guardar IP y puerto actuales como un radar")
        self.btn_guardar_udp.setFixedSize(28, 22)
        self.btn_guardar_udp.clicked.connect(self._guardar_udp_preset)
        self.btn_eliminar_udp = QPushButton()
        self.btn_eliminar_udp.setIcon(_icon("fa5s.trash-alt", "#F44336"))
        self.btn_eliminar_udp.setToolTip("Eliminar la conexión seleccionada")
        self.btn_eliminar_udp.setFixedSize(28, 22)
        self.btn_eliminar_udp.clicked.connect(self._eliminar_udp_preset)
        l_udp_preset.addWidget(self.combo_udp_preset, stretch=1)
        l_udp_preset.addWidget(self.btn_guardar_udp)
        l_udp_preset.addWidget(self.btn_eliminar_udp)

        l_udp_inputs = QHBoxLayout()
        self.txt_udp_ip = QLineEdit("127.0.0.1")
        self.txt_udp_ip.setPlaceholderText("IP")
        self.txt_udp_ip.setFixedHeight(22)
        self.txt_udp_ip.setStyleSheet("background-color: #2D313C; color: white; border: 1px solid #4B5263; border-radius: 4px; padding: 2px;")
        
        self.txt_udp_port = QLineEdit("20000")
        self.txt_udp_port.setPlaceholderText("Puerto(s): 6610,6611,6612")
        self.txt_udp_port.setToolTip("Uno o varios puertos separados por coma para escuchar en simultáneo")
        self.txt_udp_port.setFixedHeight(22)
        self.txt_udp_port.setStyleSheet("background-color: #2D313C; color: white; border: 1px solid #4B5263; border-radius: 4px; padding: 2px;")
        
        l_udp_inputs.addWidget(self.txt_udp_ip, stretch=3)
        l_udp_inputs.addWidget(self.txt_udp_port, stretch=2)

        self.chk_grabar_pcap = self._make_toggle_button("Grabar Captura", "#00E5FF")

        self.btn_conectar_udp = QPushButton(" Conectar UDP")
        self.btn_conectar_udp.setIcon(_icon("fa5s.plug"))
        self.btn_conectar_udp.setFixedHeight(26)
        self.btn_conectar_udp.clicked.connect(self._toggle_udp)
        self.btn_conectar_udp.setStyleSheet("""
            QPushButton {
                background-color: #0E2A30;
                border: 1px solid #00E5FF;
                border-radius: 4px;
                color: #00E5FF;
                font-size: 8pt;
                font-weight: bold;
                padding: 4px;
            }
            QPushButton:hover {
                border: 1px solid #39FF14;
                color: #39FF14;
                background-color: #14323A;
            }
        """)

        l_udp.addLayout(l_udp_preset)
        l_udp.addLayout(l_udp_inputs)
        l_udp.addWidget(self.chk_grabar_pcap)
        l_udp.addWidget(self.btn_conectar_udp)
        grupo_udp.setLayout(l_udp)
        v_layout.addWidget(grupo_udp)
        self._refrescar_combo_udp_presets()

        # D. Grupo Historial / Estela
        grupo_hist = QGroupBox("Historial / Estela")
        l_hist = QVBoxLayout()
        l_hist.setContentsMargins(6, 12, 6, 6)
        l_hist.setSpacing(4)

        # Checkbox para mostrar/ocultar historial
        self.chk_show_history = self._make_toggle_button("Mostrar Estela", "#00F5FF", checked=True)
        self.chk_show_history.toggled.connect(self._on_show_history_toggled)

        # Fila 1: Modo de visualización
        l_modo = QHBoxLayout()
        lbl_modo = QLabel("Modo:")
        lbl_modo.setStyleSheet("color: #E0E6ED; font-size: 8pt;")
        self.combo_mode = QComboBox()
        self.combo_mode.addItems(["Tracking", "Historic"])
        self.combo_mode.setCurrentText("Tracking")
        self.combo_mode.setFixedHeight(22)
        self.combo_mode.setStyleSheet("background-color: #2D313C; color: white; border: 1px solid #4B5263; border-radius: 4px;")
        self.combo_mode.currentTextChanged.connect(self._on_mode_changed)
        l_modo.addWidget(lbl_modo)
        l_modo.addWidget(self.combo_mode)

        l_cant = QHBoxLayout()
        lbl_cant = QLabel("Puntos:")
        lbl_cant.setStyleSheet("color: #E0E6ED; font-size: 8pt;")
        self.spin_hist = QSpinBox()
        self.spin_hist.setRange(0, 500)
        self.spin_hist.setValue(500)
        self.spin_hist.setFixedHeight(22)
        self.spin_hist.setStyleSheet("background-color: #2D313C; color: white; border: 1px solid #4B5263; border-radius: 4px;")
        self.spin_hist.valueChanged.connect(self._on_history_limit_changed)
        l_cant.addWidget(lbl_cant)
        l_cant.addWidget(self.spin_hist)

        self.btn_clear_hist = QPushButton(" Limpiar")
        self.btn_clear_hist.setIcon(_icon("fa5s.trash-alt", "#F44336"))
        self.btn_clear_hist.setFixedHeight(22)
        self.btn_clear_hist.clicked.connect(self._clear_history)
        self.btn_clear_hist.setStyleSheet("""
            QPushButton {
                background-color: #2A1416;
                border: 1px solid #F44336;
                border-radius: 4px;
                color: #FF6B6B;
                font-size: 8pt;
                font-weight: bold;
                padding: 4px;
            }
            QPushButton:hover {
                background-color: #F44336;
                color: #FFFFFF;
            }
        """)

        self.chk_sweep = self._make_toggle_button("Barrido Radar", "#00E5FF")
        self.chk_sweep.toggled.connect(self._update_sweep_state)

        self.chk_silence_cone = self._make_toggle_button("Cono de Silencio", "#FF3366")
        self.chk_silence_cone.toggled.connect(self._on_silence_cone_toggled)

        self.chk_modo_integrado = self._make_toggle_button("Modo Integrado (MRT)", "#00E5FF", checked=True)
        self.chk_modo_integrado.toggled.connect(self._on_modo_integrado_toggled)

        self.chk_show_mtr = self._make_toggle_button("Obstáculos MTR", "#FF3366", checked=True)
        self.chk_show_mtr.toggled.connect(self._on_show_mtr_toggled)

        self.chk_modo_crudo = self._make_toggle_button("Ver Plots Crudos (Sin Filtros)", "#FFD700")
        self.chk_modo_crudo.toggled.connect(self._on_modo_crudo_toggled)

        self.chk_ocultar_parrot = self._make_toggle_button("Ocultar Parrot (Sqwk 0000)", "#FFA500")

        # Control QNH manual (hPa) — recalcula TL y etiquetas A/F en caliente
        l_qnh = QHBoxLayout()
        lbl_qnh = QLabel("QNH:")
        lbl_qnh.setStyleSheet("color: #E0E6ED; font-size: 8pt;")
        self.sb_qnh = QSpinBox()
        self.sb_qnh.setRange(940, 1050)
        self.sb_qnh.setValue(1013)
        self.sb_qnh.setSuffix(" hPa")
        self.sb_qnh.setFixedHeight(22)
        self.sb_qnh.setStyleSheet("background-color: #2D313C; color: white; border: 1px solid #4B5263; border-radius: 4px;")
        self.sb_qnh.valueChanged.connect(self._on_qnh_changed)
        l_qnh.addWidget(lbl_qnh)
        l_qnh.addWidget(self.sb_qnh)

        l_hist.addWidget(self.chk_show_history)
        l_hist.addLayout(l_qnh)
        l_hist.addLayout(l_modo)
        l_hist.addLayout(l_cant)
        l_hist.addWidget(self.btn_clear_hist)
        # Grilla 2 columnas × 3 filas con los 6 toggles tácticos (más grandes)
        grid_toggles = QGridLayout()
        grid_toggles.setHorizontalSpacing(6)
        grid_toggles.setVerticalSpacing(6)
        _toggles_grid = [
            self.chk_sweep, self.chk_silence_cone,
            self.chk_modo_integrado, self.chk_modo_crudo,
            self.chk_show_mtr, self.chk_ocultar_parrot,
        ]
        for i, btn in enumerate(_toggles_grid):
            btn.setFixedHeight(44)  # reemplaza el fijo de 24 de _make_toggle_button
            btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            grid_toggles.addWidget(btn, i // 2, i % 2)
        grid_toggles.setColumnStretch(0, 1)
        grid_toggles.setColumnStretch(1, 1)
        l_hist.addLayout(grid_toggles)
        grupo_hist.setLayout(l_hist)
        v_layout.addWidget(grupo_hist)

        # F. Grupo Filtros Tácticos
        grupo_filtros = QGroupBox("Filtros Avanzados")
        l_filtros = QVBoxLayout()
        l_filtros.setContentsMargins(6, 12, 6, 6)
        l_filtros.setSpacing(4)
        self.btn_filtro_datos = QPushButton(" Filtro Datos")
        self.btn_filtro_datos.setIcon(_icon("fa5s.filter"))
        self.btn_filtro_etiquetas = QPushButton(" Filtro Etiquetas")
        self.btn_filtro_etiquetas.setIcon(_icon("fa5s.tags"))
        self.btn_filtro_datos.clicked.connect(self._abrir_filtro_datos)
        self.btn_filtro_etiquetas.clicked.connect(self._abrir_filtro_etiquetas)
        self.btn_filtro_datos.setStyleSheet("""
            QPushButton {
                background-color: #121824;
                border: 1px solid #00E5FF;
                border-radius: 4px;
                color: #00E5FF;
                font-weight: bold;
                padding: 4px;
            }
            QPushButton:hover {
                border: 1px solid #39FF14;
                color: #39FF14;
                background-color: rgba(57, 255, 20, 15);
            }
        """)
        self.btn_filtro_etiquetas.setStyleSheet(self.btn_filtro_datos.styleSheet())
        self.btn_dqf = QPushButton(" Filtros Calidad (DQF)")
        self.btn_dqf.setIcon(_icon("fa5s.sliders-h"))
        self.btn_dqf.clicked.connect(self._abrir_filtro_calidad)
        self.btn_dqf.setStyleSheet(self.btn_filtro_datos.styleSheet())
        
        l_filtros.addWidget(self.btn_filtro_datos)
        l_filtros.addWidget(self.btn_filtro_etiquetas)
        l_filtros.addWidget(self.btn_dqf)
        grupo_filtros.setLayout(l_filtros)
        v_layout.addWidget(grupo_filtros)

        # F2. Cartografía: acceso directo a la herramienta de dibujo
        grupo_carto = QGroupBox("Cartografía")
        l_carto = QVBoxLayout()
        l_carto.setContentsMargins(6, 12, 6, 6)
        l_carto.setSpacing(4)
        self.btn_dibujo = QPushButton(" Herramienta de Dibujo")
        self.btn_dibujo.setIcon(_icon("fa5s.pencil-alt"))
        self.btn_dibujo.setToolTip("Abre el gestor de capas / herramienta de dibujo de cartografía")
        self.btn_dibujo.clicked.connect(self._abrir_map_editor)
        self.btn_dibujo.setStyleSheet(self.btn_filtro_datos.styleSheet())
        l_carto.addWidget(self.btn_dibujo)
        grupo_carto.setLayout(l_carto)
        v_layout.addWidget(grupo_carto)

        # G. Botón Análisis PASS (Acceso Directo Lateral)
        grupo_analisis = QGroupBox("Análisis PASS")
        l_analisis = QVBoxLayout()
        l_analisis.setContentsMargins(6, 12, 6, 6)
        self.btn_pass = QPushButton(" Análisis PASS")
        self.btn_pass.setIcon(_icon("fa5s.chart-bar"))
        self.btn_pass.setEnabled(False)
        self.btn_pass.clicked.connect(self._abrir_analisis_pass)
        self.btn_pass.setStyleSheet("""
            QPushButton {
                background-color: rgba(0, 229, 255, 15);
                border: 1px solid #00E5FF;
                border-radius: 4px;
                color: #00E5FF;
                font-weight: bold;
                padding: 6px;
            }
            QPushButton:hover {
                border: 1px solid #39FF14;
                color: #39FF14;
                background-color: rgba(57, 255, 20, 15);
            }
            QPushButton:disabled {
                background-color: rgba(45, 52, 71, 80);
                border: 1px solid rgba(255, 255, 255, 20);
                color: gray;
            }
        """)
        l_analisis.addWidget(self.btn_pass)
        grupo_analisis.setLayout(l_analisis)
        v_layout.addWidget(grupo_analisis)

        scroll.setWidget(container)
        self.dock_lateral.setWidget(scroll)
        self.dock_lateral.setMinimumWidth(260)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.dock_lateral)
        # Garantizar que el panel sea visible y acoplado al arrancar
        self.dock_lateral.setFloating(False)
        self.dock_lateral.setVisible(True)
        self.dock_lateral.raise_()

    def _setup_technical_monitor_dock(self):
        from player.technical_monitor import TechnicalMonitorWidget
        self.dock_technical = QDockWidget("Diagnóstico Técnico ATSEP (CAT 034 / 023)", self)
        self.tech_monitor = TechnicalMonitorWidget(self)
        self.dock_technical.setWidget(self.tech_monitor)
        self.dock_technical.setAllowedAreas(Qt.DockWidgetArea.BottomDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea | Qt.DockWidgetArea.LeftDockWidgetArea)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self.dock_technical)
        self.dock_technical.setFloating(False)
        self.dock_technical.setVisible(False)  # oculto por defecto; se abre desde Ver → Diagnóstico ATSEP

    def _on_custom_sensor_toggled(self, text: str, checked: bool):
        """Maneja la selección individual de un sensor desde su checkbox personalizado."""
        match = re.match(r'^\[(\d+)/(\d+)\]', text)
        if match:
            sac, sic = map(int, match.groups())
            sensor_id = f"{sac}/{sic}"
            if checked:
                self.sensores_activos.add(sensor_id)
            else:
                self.sensores_activos.discard(sensor_id)
            
            # Sincronizar con el filtro de datos
            self.data_filter_config["sensores_seleccionados"] = self.sensores_activos.copy()
            
            # Forzar actualización del radar
            self.radar.sensores_visibles = self.sensores_activos.copy()
            self.radar.update()

            # Mantener sincronizados lista lateral y panel flotante
            if hasattr(self, 'panel_sensores'):
                self.panel_sensores.set_presentacion(text, checked)
            for i in range(self.list_sensores.count()):
                w = self.list_sensores.itemWidget(self.list_sensores.item(i))
                if w and getattr(w, 'text_label', None) == text and w.checkbox.isChecked() != checked:
                    w.checkbox.blockSignals(True)
                    w.checkbox.setChecked(checked)
                    w.checkbox.blockSignals(False)
                    break

    def _on_historico_toggled(self, text: str, checked: bool):
        """Activa/desactiva el histórico (estela) de un radar puntual.
        Independiente de la presentación (ON/OFF)."""
        match = re.match(r'^\[(\d+)/(\d+)\]', text)
        if not match:
            return
        sac, sic = map(int, match.groups())
        sensor_id = f"{sac}/{sic}"
        if not hasattr(self, 'estelas_activas'):
            self.estelas_activas = set(self.sensores_conocidos)
        if checked:
            self.estelas_activas.add(sensor_id)
        else:
            self.estelas_activas.discard(sensor_id)
        self.radar.estelas_visibles = self.estelas_activas.copy()
        self.radar.update()

    def _on_sensor_color_clicked(self, text: str):
        """Abre un selector de color para cambiar el color de un sensor en vivo."""
        from PyQt6.QtWidgets import QColorDialog
        match = re.match(r'^\[(\d+)/(\d+)\]', text)
        if not match:
            return
        sac, sic = map(int, match.groups())
        actual = self.radar._get_sensor_color(sac, sic)
        nuevo = QColorDialog.getColor(actual, self, "Color del sensor")
        if not nuevo.isValid():
            return
        self.radar.set_sensor_color(sac, sic, nuevo)
        # Reflejar el cambio en el badge de la lista
        for i in range(self.list_sensores.count()):
            widget = self.list_sensores.itemWidget(self.list_sensores.item(i))
            if widget and getattr(widget, 'text_label', None) == text:
                widget.set_color(nuevo)
                break
        # Reflejar el cambio en el panel flotante
        if hasattr(self, 'panel_sensores'):
            self.panel_sensores.actualizar_color(text, nuevo)

    def _on_sensor_check_changed(self, item):
        pass

    def _sensores_todos(self):
        self.list_sensores.blockSignals(True)
        for i in range(self.list_sensores.count()):
            item = self.list_sensores.item(i)
            widget = self.list_sensores.itemWidget(item)
            if widget:
                widget.checkbox.blockSignals(True)
                widget.checkbox.setChecked(True)
                widget.checkbox.blockSignals(False)
            text = item.data(Qt.ItemDataRole.UserRole) or item.text() or ""
            match = re.match(r'^\[(\d+)/(\d+)\]', text)
            if match:
                sac, sic = map(int, match.groups())
                self.sensores_activos.add(f"{sac}/{sic}")
        self.list_sensores.blockSignals(False)
        self.data_filter_config["sensores_seleccionados"] = self.sensores_activos.copy()
        self.radar.sensores_visibles = self.sensores_activos.copy()
        self.radar.update()

    def _sensores_ninguno(self):
        self.list_sensores.blockSignals(True)
        for i in range(self.list_sensores.count()):
            item = self.list_sensores.item(i)
            widget = self.list_sensores.itemWidget(item)
            if widget:
                widget.checkbox.blockSignals(True)
                widget.checkbox.setChecked(False)
                widget.checkbox.blockSignals(False)
            text = item.data(Qt.ItemDataRole.UserRole) or item.text() or ""
            match = re.match(r'^\[(\d+)/(\d+)\]', text)
            if match:
                sac, sic = map(int, match.groups())
                self.sensores_activos.discard(f"{sac}/{sic}")
        self.list_sensores.blockSignals(False)
        self.data_filter_config["sensores_seleccionados"] = self.sensores_activos.copy()
        self.radar.sensores_visibles = self.sensores_activos.copy()
        self.radar.update()

    def _on_history_limit_changed(self, val: int):
        self.radar.history_limit = val
        self.radar.update()

    def _on_mode_changed(self, mode: str):
        """Cambia entre modo Tracking (trayectoria) y Historic (puntos)."""
        self.radar.history_mode = mode
        self.radar.update()

    def _on_show_history_toggled(self, checked: bool):
        """Muestra u oculta la estela histórica del radar."""
        if hasattr(self, 'radar') and self.radar is not None:
            self.radar.set_history_visible(checked)

    def _ajustar_alto_lista_sensores(self):
        """Ajusta el alto de la lista de radares a su contenido (hasta 16 filas) para que
        no se corte el último radar; el scroll del dock absorbe el resto."""
        n = self.list_sensores.count()
        if n == 0:
            self.list_sensores.setFixedHeight(40)
            return
        row_h = self.list_sensores.sizeHintForRow(0)
        if row_h <= 0:
            row_h = 24
        frame = 2 * self.list_sensores.frameWidth() + 4
        visibles = min(n, 16)
        self.list_sensores.setFixedHeight(row_h * visibles + frame)

    def _on_show_mtr_toggled(self, checked: bool):
        """Muestra u oculta los obstáculos/reflectores MTR en la pantalla del radar."""
        if hasattr(self, 'radar') and self.radar is not None:
            self.radar.mtr_visible = checked
            self.radar.update()

    def _clear_history(self):
        if hasattr(self.radar, 'history'):
            self.radar.history.clear()
        if hasattr(self.radar, 'plots_raw'):
            self.radar.plots_raw.clear()
        self.radar.update()

    def _show_panel(self):
        pass

    def _hide_panel(self):
        pass

    def _abrir_analizador_paquetes(self):
        """Abre el visor histórico de plots ASTERIX (filtros sobre DuckDB)."""
        repo_db = None
        if self.worker is not None and getattr(self.worker, 'engine', None) is not None:
            repo_db = getattr(self.worker.engine, 'repo_db', None)
        if repo_db is None:
            QMessageBox.information(
                self, "Analizador de Paquetes",
                "Cargá y escaneá un archivo (Modo Playback) antes de abrir el analizador.")
            return
        if getattr(self, '_analizador_win', None) is None:
            from player.packet_analyzer import AsterixAnalyzerWindow
            self._analizador_win = AsterixAnalyzerWindow(repo_db, self.worker, self)
            self._analizador_win.seek_solicitado.connect(self._analizador_seek)
            self._analizador_win.reproducir_filtrado.connect(self._analizador_reproducir_filtrado)
        else:
            # Reapuntar a la BD/worker vigentes y refrescar
            self._analizador_win.repo_db = repo_db
            self._analizador_win.worker = self.worker
            self._analizador_win.aplicar_filtros_base_datos(None)
        self._analizador_win.show()
        self._analizador_win.raise_()
        self._analizador_win.activateWindow()

    def _iniciar_reproduccion(self):
        """Arranca/reanuda la reproducción (lógica compartida con el botón Play)."""
        if self.worker is None or self.playing:
            return
        if not self.worker.isRunning():
            self.worker.engine.tracks.clear()
            self.worker.engine.relojes_sensores.clear()
            self.worker.engine.is_playing = True
            self._cambiar_velocidad()
            self.worker.start()
        else:
            self.worker.engine.is_playing = True
            self.worker.set_paused(False)
        self.playing = True
        if hasattr(self, 'radar') and self.radar is not None:
            self.radar.play()
        self._set_play_state(True)

    def _analizador_seek(self, t: float):
        """Doble clic en el analizador: reposicionar la consola a ese instante."""
        if self.worker is None:
            return
        self.worker.set_target_filter(None)  # quitar cualquier filtro de reproducción previo
        self.worker.seek_to_time(float(t))
        self._iniciar_reproduccion()

    def _analizador_reproducir_filtrado(self, t0: float, lat_c: float, lon_c: float,
                                        radio_nm: float, targets):
        """Reproduce en la consola solo las aeronaves filtradas en el analizador.
        Encuadra la vista en la(s) aeronave(s) para que entren en el filtro de
        distancia (si no, un blanco lejano al centro actual se descarta)."""
        if self.worker is None:
            return
        if self.worker.contar_targets(targets) == 0:
            QMessageBox.warning(
                self, "Reproducir filtrado",
                "Ninguna de las filas filtradas tiene identificador de aeronave "
                "reproducible (callsign / Mode-S / track#).")
            return
        self.worker.set_target_filter(targets)
        self.worker.seek_to_time(float(t0))
        # Encuadrar la pantalla táctica en la(s) aeronave(s) filtrada(s),
        # guardando antes el centro previo para restaurarlo al detener.
        if abs(lat_c) > 0.1 and abs(lon_c) > 0.1:
            if self._centro_pre_filtrado is None:
                self._centro_pre_filtrado = (
                    self.radar.centro_lat, self.radar.centro_lon,
                    self.radar.center_key, self.radar.zoom_factor)
            self.radar.centrar_en_objetivo(lat_c, lon_c, radio_nm)
        self._iniciar_reproduccion()

    def _abrir_log_stca(self):
        import os
        log_path = "c:/documentos/decode_asterix/stca_conflicts.log"
        if os.path.exists(log_path):
            try:
                os.startfile(os.path.normpath(log_path))
            except Exception:
                import webbrowser
                webbrowser.open(log_path)
        else:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.information(
                self, "Información", 
                "El archivo de log de STCA no existe o aún no se han registrado alertas en esta sesión."
            )

    def _abrir_log_calidad(self):
        import os
        log_path = "c:/documentos/decode_asterix/quality_events.log"
        if os.path.exists(log_path):
            try:
                os.startfile(os.path.normpath(log_path))
            except Exception:
                import webbrowser
                webbrowser.open(log_path)
        else:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.information(
                self, "Información",
                "El archivo de eventos de calidad no existe o aún no se han registrado eventos (FRUIT/GARBLING/REFLEXIÓN) en esta sesión."
            )

    def _toggle_reloj_utc(self, visible: bool):
        if hasattr(self, 'reloj_utc'):
            self.reloj_utc.setVisible(visible)
            if visible:
                self.reloj_utc.raise_()

    def _reposicionar_reloj(self):
        """Ancla el reloj flotante a la esquina superior derecha, debajo de la caja de coordenadas."""
        if hasattr(self, 'reloj_utc') and hasattr(self, 'radar'):
            self.reloj_utc.adjustSize()
            x = self.radar.width() - self.reloj_utc.width() - 20
            y = 80  # justo debajo de la caja de coordenadas (y=45, alto 28)
            self.reloj_utc.move(max(0, x), y)

    def eventFilter(self, obj, event):
        from PyQt6.QtCore import QEvent
        if obj is getattr(self, 'radar', None) and event.type() == QEvent.Type.Resize:
            self._reposicionar_reloj()
            if hasattr(self, 'reloj_utc'):
                self.reloj_utc.raise_()
            fv = getattr(self, '_fir_view', None)
            if fv is not None and fv.isVisible():
                fv.setGeometry(self.radar.rect())
                fv.raise_()
        return super().eventFilter(obj, event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._reposicionar_reloj()

    def _toggle_incumbencia(self, activo: bool):
        if hasattr(self, 'radar'):
            self.radar.mostrar_incumbencia = activo
            self.radar.update()

    def _toggle_stca_habilitado(self, checked: bool):
        if hasattr(self, 'radar') and self.radar:
            self.radar.stca_habilitado = checked
            self.radar.evaluar_stca()

    def _toggle_apw_habilitado(self, checked: bool):
        if hasattr(self, 'radar') and self.radar:
            self.radar.apw_habilitado = checked
            self.radar.evaluar_stca()

    def _toggle_msaw_habilitado(self, checked: bool):
        if hasattr(self, 'radar') and self.radar:
            self.radar.msaw_habilitado = checked
            self.radar.evaluar_msaw()

    def _abrir_map_editor(self):
        # Toggle: si ya está abierto, cerrarlo desde el mismo botón
        dlg = getattr(self, 'map_editor_dialog', None)
        if dlg is not None and dlg.isVisible():
            dlg.close()
            return
        from player.map_dialog import MapEditorDialog
        dialog = MapEditorDialog(self.radar.map_manager, self)
        self.map_editor_dialog = dialog
        dialog.finished.connect(lambda _r: setattr(self, 'map_editor_dialog', None))
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()

    def _cargar_pcap(self):
        file_paths, _ = QFileDialog.getOpenFileNames(
            self, "Seleccionar Archivo(s)", ".", "Todos los Soportados (*.pcap *.pcapng *.raw *.ast *.bin *.Z);;Archivos PCAP (*.pcap *.pcapng);;Archivos Crudos (*.raw *.ast *.bin *.Z);;Todos (*)"
        )
        if not file_paths: return
        
        if len(file_paths) == 1:
            self.pcap_path = file_paths[0]
            self.setWindowTitle(f"ASTERIX Radar Decoder - {os.path.basename(file_paths[0])}")
        else:
            self.pcap_path = file_paths
            names_str = ", ".join([os.path.basename(fp) for fp in file_paths[:3]])
            if len(file_paths) > 3:
                names_str += f" (+{len(file_paths) - 3})"
            self.setWindowTitle(f"ASTERIX Radar Decoder - [Múltiples PCAP: {names_str}]")
        
        if getattr(self, '_playback_player', None) is not None:
            self._playback_player.set_filename(
                os.path.basename(file_paths[0]) if len(file_paths) == 1
                else f"{len(file_paths)} archivos")

        # Iniciar fase de decodificación/carga inmediatamente
        self.btn_play.setEnabled(False)
        self.btn_cargar.setEnabled(False)
        self.btn_cargar.setText(" Cargando... 0%")
        self.btn_stop.setEnabled(False)
        self.btn_pass.setEnabled(False)
        self.act_exp_kmz.setEnabled(False)
        self.act_exp_playback.setEnabled(False)
        self.act_exp_cobertura.setEnabled(False)
        self.act_exp_csv.setEnabled(False)
        self.act_exp_parquet.setEnabled(False)
        self.chk_modo_integrado.setEnabled(False)
        self._modo_manual = False  # permitir default automático por nº de sensores
        self._auto_modo_estado = None

        # Limpiar combo box de proyección
        self.combo_sensor.blockSignals(True)
        self.combo_sensor.clear()
        self.combo_sensor.addItem("Autocentrado")
        self.combo_sensor.blockSignals(False)

        # Limpiar lista de sensores en barra lateral
        self.list_sensores.blockSignals(True)
        self.list_sensores.clear()
        self.list_sensores.blockSignals(False)
        if hasattr(self, 'panel_sensores'):
            self.panel_sensores.limpiar()

        self.radar.limpiar_pantalla()
        self.sensores_conocidos.clear()
        self.sensores_activos.clear()
        self.estelas_activas.clear()
        self.autocentered_on_first_sensor = False
        self._sensor_categories.clear()
        self._sensor_rpms.clear()
        self.radar.sensores_visibles = self.sensores_activos.copy()
        # Limpiar la selección de sensores del config de filtro al cargar nuevo archivo
        self.data_filter_config.pop("sensores_seleccionados", None)
        self.total_messages_received = 0
        self.selected_messages_received = 0
        
        self._limpiar_worker()
        
        # Crear y arrancar el worker inmediatamente para decodificación/escaneo
        self.worker = PlaybackWorker(
            pcap_file=self.pcap_path,
            sensores=self.sensores,
            cache_dir=self.cache_dir,
            profile_config=self.profile_manager.profile
        )
        self.worker.new_plot_batch.connect(self._on_new_plot_batch)
        self.worker.progress_updated.connect(self._on_decoding_progress)
        self.worker.tod_updated.connect(self._on_tod_update)
        self.worker.scan_complete.connect(self._on_scan_complete)
        self.worker.playback_finished.connect(self._on_playback_finished)
        self.worker.sensor_detected.connect(self._on_sensor_detected)
        self.worker.rotation_speed_detected.connect(self._on_rotation_speed_detected)
        self.worker.radar_health_changed.connect(self.tech_monitor.update_sensor_status)
        
        self.worker.start()

    def _set_play_state(self, playing: bool):
        """Actualiza icono y texto del botón play/pausa según el estado."""
        if playing:
            self.btn_play.setIcon(_icon("fa5s.pause"))
            self.btn_play.setText(" Pausa")
        else:
            self.btn_play.setIcon(_icon("fa5s.play"))
            self.btn_play.setText(" Reproducir")
        if getattr(self, '_playback_player', None) is not None:
            self._playback_player.set_playing(playing)

    def _toggle_play(self):
        if self.worker is not None:
            if not self.playing:
                # Si el worker ya terminó la fase de scan, lo arrancamos para reproducción
                if not self.worker.isRunning():
                    self.worker.engine.tracks.clear()
                    self.worker.engine.relojes_sensores.clear()
                    self.worker.engine.is_playing = True
                    self._cambiar_velocidad()
                    self.worker.start() # Arrancará en _playback_loop
                    self.playing = True
                    self.radar.play()
                    self._set_play_state(True)
                else:
                    # Si ya estaba corriendo en playback_loop pero pausado, reanudar
                    self.worker.engine.is_playing = True
                    self.worker.set_paused(False)
                    self.playing = True
                    self.radar.play()
                    self._set_play_state(True)
            else:
                # Si está reproduciendo, pausar
                self.worker.engine.is_playing = False
                self.worker.set_paused(True)
                self.playing = False
                if hasattr(self, 'radar') and self.radar is not None:
                    self.radar.pause()
                self._set_play_state(False)

    def _stop(self):
        self.playing = False
        if self.worker:
            self.worker.set_paused(True)
            self.worker.set_target_filter(None)
            self.worker.seek_to_percent(0)
        # Restaurar el centro/zoom previos si veníamos de una reproducción filtrada
        if self._centro_pre_filtrado is not None:
            lat, lon, ckey, zoom = self._centro_pre_filtrado
            self._centro_pre_filtrado = None
            if lat is not None and lon is not None:
                sac, sic = ckey if isinstance(ckey, tuple) else (0, 0)
                self.radar.reset_origin_for_new_file(lat, lon, sac, sic)
                self.radar.zoom_factor = zoom
                self.radar._clamp_zoom()
        if hasattr(self, 'radar') and self.radar is not None:
            self.radar.pause()
            self.radar.reset_sweep_angle()
            
        self.btn_play.setEnabled(True)
        self._set_play_state(False)
        self.btn_stop.setEnabled(True)
        self.slider_tiempo.setValue(0)
        self.lbl_tiempo.setText("00:00:00")
        
        self.radar.sensores_visibles = self.sensores_activos
        self.radar.limpiar_pantalla()
        if self.radar is not None and hasattr(self.radar, 'stca_dialog') and self.radar.stca_dialog:
            self.radar.stca_dialog.limpiar()
        if self.radar is not None and hasattr(self.radar, 'apw_dialog') and self.radar.apw_dialog:
            self.radar.apw_dialog.limpiar()
        self._show_panel()

    def _seek(self):
        if self.worker:
            pct = self.slider_tiempo.value()
            self.worker.seek_to_percent(pct)

    def _cambiar_velocidad(self):
        vel = float(self.combo_vel.currentText().replace('x', ''))
        if self.worker:
            self.worker.set_speed(vel)
        if hasattr(self, 'radar') and self.radar is not None:
            self.radar.playback_speed = vel
            from player.radar_widget import SimulationTime
            SimulationTime.instance().set_speed(vel)

    def _limpiar_worker(self):
        if self.worker:
            self.worker.stop()
            self.worker = None

    def _sync_panel_sensores(self):
        """Reconstruye el panel flotante a partir de la lista lateral (red de seguridad
        ante cualquier desfase de orden en la detección de sensores)."""
        if not hasattr(self, 'panel_sensores'):
            return
        self.panel_sensores.limpiar()
        for i in range(self.list_sensores.count()):
            w = self.list_sensores.itemWidget(self.list_sensores.item(i))
            if not w:
                continue
            text_label = getattr(w, 'text_label', None)
            if not text_label:
                continue
            m = re.match(r'^\[(\d+)/(\d+)\]', text_label)
            if not m:
                continue
            sac, sic = map(int, m.groups())
            sensor_id = f"{sac}/{sic}"
            color = self.radar._get_sensor_color(sac, sic)
            present = sensor_id in self.sensores_activos
            histo = sensor_id in getattr(self, 'estelas_activas', self.sensores_conocidos)
            self.panel_sensores.agregar_sensor(text_label, color,
                                               presentacion=present, historico=histo)

    def _on_scan_complete(self, success: bool):
        self.btn_cargar.setEnabled(True)
        self.btn_cargar.setText(" Modo Playback")
        self._sync_panel_sensores()
        if self.worker:
            self.worker.wait() # Asegurar que el hilo de escaneo termine y se una completamente
        if success:
            # Desconectar progreso de decodificación y conectar a progreso de reproducción
            try:
                self.worker.progress_updated.disconnect(self._on_decoding_progress)
            except TypeError:
                pass
            self.worker.progress_updated.connect(self._on_progress)
            
            self.btn_play.setEnabled(True)
            self._set_play_state(False)
            self.btn_stop.setEnabled(True)
            self.btn_pass.setEnabled(True)
            self.slider_tiempo.setEnabled(True)
            self.slider_tiempo.setMaximum(100)
            if getattr(self, '_playback_player', None) is not None:
                self._playback_player.set_enabled_transport(True)
                self._playback_player.set_loading_progress(100)  # oculta la barra
                self._playback_player.set_time_bounds(
                    int(self.worker.t_min), int(self.worker.t_max))

            # El reproductor vive ahora en el widget flotante (menú Modo → Playback);
            # la barra de transporte bajo el menú queda retirada.
            self._playback_disponible = True
            self.toolbar.setVisible(False)
            
            # Asegurar que todos los sensores detectados sean visibles en el widget del radar
            self.radar.sensores_visibles = self.sensores_activos.copy()
            
            # Sincronizar el estado inicial de la simulación al primer plot cargado (evita desincronización de tiempo)
            if self.worker:
                self.worker.seek_to_percent(0)
                self._cambiar_velocidad()
            
            # Habilitar opciones de exportación y análisis en el menú principal
            self.act_exp_kmz.setEnabled(True)
            self.act_exp_playback.setEnabled(True)
            self.act_exp_cobertura.setEnabled(True)
            self.act_exp_csv.setEnabled(True)
            self.act_exp_parquet.setEnabled(True)

            # Default por nº de sensores: multisensor -> Integrado, un solo sensor -> Crudo.
            # Ambos botones quedan habilitados (modos mutuamente excluyentes).
            self.chk_modo_integrado.setEnabled(True)
            self.chk_modo_crudo.setEnabled(True)
            if not getattr(self, '_modo_manual', False):
                multis = len(self.sensores_conocidos) > 1
                self._auto_modo_estado = multis
                self._set_modo(multis)
        else:
            self.btn_play.setText("Error en PCAP")
            self._show_panel()

    def _on_sensor_detected(self, sac: int, sic: int):
        sensor_id = f"{sac}/{sic}"
        
        info = self.sensores.get((sac, sic))
        nombre = info.get('name', f"Radar {sac}/{sic}") if info else f"Radar {sac}/{sic}"
        text_label = f"[{sac}/{sic}] {nombre}"

        # 1. Asegurar registro en los sets internos
        if sensor_id not in self.sensores_conocidos:
            self.sensores_conocidos.add(sensor_id)
        if sensor_id not in self.sensores_activos:
            self.sensores_activos.add(sensor_id)
        if not hasattr(self, 'estelas_activas'):
            self.estelas_activas = set()
        self.estelas_activas.add(sensor_id)

        if hasattr(self, 'radar') and self.radar is not None:
            if hasattr(self.radar, 'sensores_visibles'):
                self.radar.sensores_visibles.add(sensor_id)
            if getattr(self.radar, 'estelas_visibles', None) is None:
                self.radar.estelas_visibles = set()
            self.radar.estelas_visibles.add(sensor_id)

        # 2. Evitar agregar duplicados al combo box
        exists_in_combo = False
        for i in range(self.combo_sensor.count()):
            if self.combo_sensor.itemData(i) == sensor_id:
                exists_in_combo = True
                break
        if not exists_in_combo:
            self.combo_sensor.blockSignals(True)
            self.combo_sensor.addItem(text_label, sensor_id)
            self.combo_sensor.blockSignals(False)

        # 3. Evitar agregar duplicados a la lista interactiva lateral
        exists_in_list = False
        for i in range(self.list_sensores.count()):
            item = self.list_sensores.item(i)
            widget = self.list_sensores.itemWidget(item)
            if widget and widget.text_label == text_label:
                exists_in_list = True
                break
            elif item:
                item_text = item.data(Qt.ItemDataRole.UserRole) or item.text()
                if item_text == text_label:
                    exists_in_list = True
                    break
        if not exists_in_list:
            self.list_sensores.blockSignals(True)
            
            # Obtener el color único asignado a este sensor
            color_sensor = self.radar._get_sensor_color(sac, sic)
            
            item = QListWidgetItem(self.list_sensores)
            item.setText("")  # Limpiar texto del item para evitar que Qt lo dibuje duplicado encima del widget
            item.setData(Qt.ItemDataRole.UserRole, text_label)  # Guardar para búsquedas/compatibilidad
            
            # Instanciar widget personalizado con color badge y checkbox
            sensor_widget = RadarSensorItemWidget(color_sensor, text_label, checked=True, parent=self)
            sensor_widget.toggled.connect(self._on_custom_sensor_toggled)
            sensor_widget.colorClicked.connect(self._on_sensor_color_clicked)
            
            item.setSizeHint(sensor_widget.sizeHint())
            self.list_sensores.addItem(item)
            self.list_sensores.setItemWidget(item, sensor_widget)

            self.list_sensores.blockSignals(False)
            self._ajustar_alto_lista_sensores()

            # Reflejar el sensor en el panel flotante 'Sensores'
            if hasattr(self, 'panel_sensores'):
                self.panel_sensores.agregar_sensor(text_label, color_sensor,
                                                   presentacion=True, historico=True)

        # 4. Autocenter en el primer sensor detectado (una única vez para evitar re-proyectar el mapa DXF constantemente)
        if not getattr(self, 'autocentered_on_first_sensor', False) and len(self.sensores_conocidos) == 1:
            if info and info.get('lat') and info.get('lon'):
                self.autocentered_on_first_sensor = True
                self.radar.reset_origin_for_new_file(
                    info['lat'], info['lon'], sac, sic, nombre
                )
                self.combo_sensor.blockSignals(True)
                self.combo_sensor.setCurrentIndex(self.combo_sensor.count() - 1)
                self.combo_sensor.blockSignals(False)
                self._update_sweep_state()
            print(f"[SENSOR] Detectado: [{sac}/{sic}] {nombre}")

        # Default dinámico en vivo (UDP): mientras el usuario no haya elegido manualmente,
        # un solo sensor -> Crudo; al aparecer el segundo -> Integrado.
        # IMPORTANTE: solo actuar cuando cambia el estado 1<->multisensor (no en cada
        # plot), porque _set_modo reconstruye pistas/estela y causaría parpadeo.
        self.chk_modo_integrado.setEnabled(True)
        self.chk_modo_crudo.setEnabled(True)
        if not getattr(self, '_modo_manual', False):
            multis = len(self.sensores_conocidos) > 1
            if multis != getattr(self, '_auto_modo_estado', None):
                self._auto_modo_estado = multis
                self._set_modo(multis)

    def _on_sensor_combo_changed(self, index):
        if index <= 0:
            # Autocentrado o ninguno
            self._update_sweep_state()
            return
            
        sensor_id = self.combo_sensor.itemData(index)
        if not sensor_id or '/' not in sensor_id:
            return
            
        try:
            sac, sic = map(int, sensor_id.split('/'))
        except ValueError:
            return
            
        info = self.sensores.get((sac, sic))
        if info and info.get('lat') and info.get('lon'):
            lat, lon = info['lat'], info['lon']
            nombre = info.get('name', f"Radar {sac}/{sic}")
            
            # Cambiar proyección y centrar
            self.radar.set_projection_center(lat, lon, (sac, sic))
            self.radar.reproject_all_coordinates()
            self.radar._active_sensor_label = f"SENSOR ACTIVO: {nombre} ({sac}/{sic})"
            
            # Sincronizar velocidad de rotación de la antena (RPM) si fue detectada
            rpm = self._sensor_rpms.get((sac, sic), 12.0)
            self.radar.set_sweep_speed(rpm)
            
            self._update_sweep_state()
            
            self.radar.recenter_to_fit_map()
            print(f"[COMBO SENSOR] Cambiado a {nombre} ({sac}/{sic}) - Lat: {lat:.5f}, Lon: {lon:.5f}")

    def _update_sweep_state(self):
        # Obtener el sensor activo actual
        center_key = getattr(self.radar, 'center_key', None)
        if not center_key:
            self.radar.set_sweep_enabled(False)
            self.radar.set_sweep_visible(False)
            return

        # Determinar si el sensor emite CAT 48 / CAT 01 o es un radar según el JSON
        info = self.sensores.get(center_key)
        
        is_radar = False
        if info:
            sensor_cat = info.get('category', '')
            sensor_type = info.get('type', '')
            is_radar = ('048' in sensor_cat) or ('001' in sensor_cat) or ('SSR' in sensor_type) or ('PSR' in sensor_type)
            
        # Si no está en default-site-params, comprobar en las categorías vistas en tiempo real
        if not is_radar and center_key in self._sensor_categories:
            cats = self._sensor_categories[center_key]
            is_radar = (48 in cats) or (1 in cats)

        # La línea de barrido solo debe activarse para radares (CAT 48 / CAT 01) y si el checkbox está marcado
        if is_radar and self.chk_sweep.isChecked():
            self.radar.set_sweep_enabled(True)
            self.radar.set_sweep_visible(True)
        else:
            self.radar.set_sweep_enabled(False)
            self.radar.set_sweep_visible(False)
        self.radar.update()

    def _on_silence_cone_toggled(self, checked: bool):
        self.radar.show_silence_cone = checked
        self.radar.update()

    def _set_modo(self, integrado: bool):
        """Modos mutuamente excluyentes: siempre exactamente uno activo.
        Integrado = fusión de identidad + filtros. Crudo = todos los plots por
        sensor, sin filtros. El suavizado se aplica en ambos."""
        if not hasattr(self, 'radar'):
            return
        self.radar.modo_integrado = integrado
        self.radar.modo_crudo = not integrado
        # Sincronizar ambos botones sin reentrar en los handlers
        self.chk_modo_integrado.blockSignals(True)
        self.chk_modo_crudo.blockSignals(True)
        self.chk_modo_integrado.setChecked(integrado)
        self.chk_modo_crudo.setChecked(not integrado)
        self.chk_modo_integrado.blockSignals(False)
        self.chk_modo_crudo.blockSignals(False)
        # Reconstruir pistas/estela al cambiar de modo (la fusión cambia)
        if hasattr(self.radar, 'tracks'):
            self.radar.tracks.clear()
        if hasattr(self.radar, 'pending_tracks'):
            self.radar.pending_tracks.clear()
        if hasattr(self.radar, 'history'):
            self.radar.history.clear()
        self.radar.update()

    def _set_vector_minutos(self, minutos: int):
        """Cambia el horizonte (min) del vector de tendencia en caliente."""
        if hasattr(self, 'radar'):
            self.radar.vector_tiempo_minutos = int(minutos)
            self.radar.update()

    def _on_modo_integrado_toggled(self, checked: bool):
        # Toggle excluyente: integrado on -> crudo off; integrado off -> crudo on
        self._modo_manual = True
        self._set_modo(checked)

    def _on_modo_crudo_toggled(self, checked: bool):
        self._modo_manual = True
        self._set_modo(not checked)

    def _plot_passes_filters(self, plot) -> bool:
        """
        Determina si un plot (diccionario, AsterixPlot o RadarPlot) pasa todos los filtros
        de datos activos configurados en self.data_filter_config.
        """
        def get_val(obj, key, default=None):
            if isinstance(obj, dict):
                return obj.get(key, default)
            return getattr(obj, key, default)

        cfg = self.data_filter_config
        cat = get_val(plot, 'category')
        is_psr = get_val(plot, 'is_psr', False)
        
        # Obtener Squawk (SSR code)
        mode3a = get_val(plot, 'mode3a') or get_val(plot, 'mode_3a')
        mode3a_str = ""
        if mode3a is not None:
            if isinstance(mode3a, int):
                mode3a_str = f"{mode3a:04o}"
            else:
                mode3a_str = str(mode3a).strip()

        # A. Filtro de Categoría / Tipo de informe
        if cat == 21 and not cfg.get("ads_b", True): return False
        elif cat == 62:
            if not (cfg.get("pistas_secun", True) or cfg.get("pistas_prim", True)): return False
        elif cat in (1, 48):
            is_track = get_val(plot, 'is_track', False)
            if mode3a_str and mode3a_str != "----" and mode3a_str != "0000" and not is_psr:
                if not (cfg.get("pistas_secun", True) or cfg.get("plots_secun", True)):
                    return False
            else:
                if is_track:
                    if is_psr:
                        if not cfg.get("pistas_prim", True): return False
                    else:
                        if not cfg.get("pistas_secun", True): return False
                else:
                    if is_psr:
                        if not cfg.get("plots_prim", True): return False
                    else:
                        if not cfg.get("plots_secun", True): return False
        elif cat in (2, 34) and not cfg.get("servicio", True): return False

        # B. Filtro de Sensores
        sensores_sel = cfg.get("sensores_seleccionados", None)
        if sensores_sel is not None:
            plot_sid = get_val(plot, 'sac_sic', '')
            if plot_sid not in sensores_sel and cat != 62:
                return False

        # C. Filtro de Códigos Mode 3/A (Squawk)
        if cfg.get("habilitar_filtro_codigos", False):
            valid_codes = [c.strip() for c in cfg.get("codes", []) if c.strip()]
            if valid_codes:
                if mode3a_str not in valid_codes:
                    return False

        # D. Filtros de Rangos Numéricos
        # - Distancia (en NM) desde el origen del radar
        px = get_val(plot, 'x')
        py = get_val(plot, 'y')
        dist_nm = 0.0
        if px is not None and py is not None:
            dist_nm = math.sqrt(px**2 + py**2) / 1852.0
        else:
            plat = get_val(plot, 'lat')
            plon = get_val(plot, 'lon')
            if plat is not None and plon is not None and self.radar.centro_lat is not None:
                try:
                    if WGS84_GEOD:
                        _, _, dist_m = WGS84_GEOD.inv(self.radar.centro_lon, self.radar.centro_lat, plon, plat)
                        dist_nm = dist_m / 1852.0
                except Exception:
                    pass
                    
        if not (cfg.get("dist_inf", 0.0) <= dist_nm <= cfg.get("dist_sup", 500.0)):
            return False

        # - Acimut (en grados)
        az_deg = 0.0
        if px is not None and py is not None:
            if not (abs(px) < 1e-6 and abs(py) < 1e-6):
                az_deg = math.degrees(math.atan2(px, py))
                if az_deg < 0: az_deg += 360.0
        else:
            plat = get_val(plot, 'lat')
            plon = get_val(plot, 'lon')
            if plat is not None and plon is not None and self.radar.centro_lat is not None:
                try:
                    az_deg = self.radar.proy.azimuth_vincenty(
                        self.radar.centro_lat, self.radar.centro_lon, plat, plon
                    )
                    if az_deg < 0: az_deg += 360.0
                except Exception:
                    pass
                    
        if not (cfg.get("az_inf", 0) <= az_deg <= cfg.get("az_sup", 360)):
            return False

        # - Altura (pies o Flight Level)
        fl = get_val(plot, 'flight_level')
        alt_ft = get_val(plot, 'altitude_ft')
        alt_val = 0.0
        if fl is not None:
            alt_val = fl * 100.0
        elif alt_ft is not None:
            alt_val = alt_ft
            
        if not (cfg.get("alt_inf", -9999) <= alt_val <= cfg.get("alt_sup", 99999)):
            return False

        # - Dirección Mode S / ICAO Hex
        mode_s = (get_val(plot, 'mode_s') or "").strip().upper()
        if mode_s:
            id_inf = cfg.get("id21_inf", "000000").strip().upper()
            id_sup = cfg.get("id21_sup", "FFFFFF").strip().upper()
            if not (id_inf <= mode_s <= id_sup):
                return False

        return True

    def _on_new_plot_batch(self, batch: List[Dict]):
        # Separar plots técnicos (CAT 23 y 34) de los plots cinemáticos de radar
        tech_plots = []
        radar_plots = []
        for p in batch:
            cat = p.get('category')
            if cat in (23, 34):
                tech_plots.append(p)
            else:
                radar_plots.append(p)

        # Procesar los plots de telemetría técnica (actualizar HMI en caliente)
        for p in tech_plots:
            plot_time = p.get('time')
            if plot_time is not None:
                from player.radar_widget import SimulationTime
                SimulationTime.instance().set_time(plot_time)
            
            sid = p.get('sac_sic')
            if sid:
                try:
                    parts = sid.split('/')
                    key = (int(parts[0]), int(parts[1]))
                    telemetria = p.get('bds_data')
                    if telemetria:
                        self.tech_monitor.update_sensor_status(key, telemetria)
                except Exception:
                    pass

        # Continuar solo si quedan plots de radar
        batch = radar_plots
        if not batch:
            return

        # Registrar las categorías vistas para cada sensor en tiempo real
        for plot in batch:
            # Sincronizar el reloj de simulación con cada plot procesado en el lote (usar TOD del mensaje ASTERIX)
            plot_time = plot.get('time')
            if plot_time is not None:
                from player.radar_widget import SimulationTime
                SimulationTime.instance().set_time(plot_time)
                
            sid = plot.get('sac_sic')
            cat = plot.get('category')
            if sid and cat:
                try:
                    parts = sid.split('/')
                    sk = (int(parts[0]), int(parts[1]))
                    if sk not in self._sensor_categories:
                        self._sensor_categories[sk] = set()
                    self._sensor_categories[sk].add(int(cat))
                except Exception:
                    pass

        # Si la proyección no se ha inicializado (ej. archivo CAT 62 sin coordenadas de radar),
        # auto-centramos la proyección en el primer plot válido del lote para habilitar el mapa y tracking.
        if not self.radar.projection_set and batch:
            for plot in batch:
                plat = plot.get('lat')
                plon = plot.get('lon')
                if plat is not None and plon is not None and abs(plat) <= 90.0 and abs(plon) <= 180.0 and abs(plat) > 1.0 and abs(plon) > 1.0:
                    sid = plot.get('sac_sic', '0/0')
                    try:
                        sac, sic = map(int, sid.split('/'))
                    except ValueError:
                        sac, sic = 0, 0
                    print(f"[AUTOCENTER FALLBACK] Inicializando proyección en primer blanco válido: Lat={plat:.5f}, Lon={plon:.5f}")
                    self.radar.reset_origin_for_new_file(
                        plat, plon, sac, sic, "System Center (CAT62)"
                    )
                    break

        # Filtrar y enviar plots al radar
        for plot in batch:
            self.total_messages_received += 1

            # 2. EVALUAR FILTROS DE DATOS (data_filter_config)
            cfg = self.data_filter_config
            
            # A. Filtro de Categoría / Tipo de informe
            cat = plot.get('category')
            is_psr = plot.get('is_psr', False)
            
            # Obtener Squawk (SSR code)
            mode3a = plot.get('mode3a') or plot.get('mode_3a')
            mode3a_str = ""
            if mode3a is not None:
                if isinstance(mode3a, int):
                    mode3a_str = f"{mode3a:04o}"
                else:
                    mode3a_str = str(mode3a).strip()
            
            # Filtro parrot: squawk 0000 = transpondedor en standby
            if mode3a_str == "0000" and getattr(self, 'chk_ocultar_parrot', None) and self.chk_ocultar_parrot.isChecked():
                continue

            # DEDUPLICACIÓN MULTI-SENSOR (prioridad: Mode-S → callsign → squawk → proximidad < 1 NM)
            mode_s_addr = (plot.get('mode_s') or "").strip().upper()
            if cat in (1, 48) and getattr(self.radar, 'modo_integrado', True):
                has_higher_priority_track = False
                if hasattr(self, 'radar') and self.radar is not None:
                    all_tracks = list(self.radar.tracks.values()) + list(self.radar.pending_tracks.values())
                    plot_cs = (plot.get('callsign') or "").strip().upper()
                    px = plot.get('x')
                    py = plot.get('y')
                    for track in all_tracks:
                        if not (track.category in (21, 62) and track.is_alive()):
                            continue
                        # 1. Aircraft address (Mode-S / ICAO)
                        if mode_s_addr:
                            t_ms = (track.mode_s or "").strip().upper()
                            if t_ms and t_ms == mode_s_addr:
                                has_higher_priority_track = True
                                break
                        # 2. Callsign
                        if plot_cs:
                            t_cs = (track.callsign or "").strip().upper()
                            if t_cs and t_cs == plot_cs:
                                has_higher_priority_track = True
                                break
                        # 3. Squawk (Mode 3/A)
                        if mode3a_str and mode3a_str not in ("----", "0000"):
                            t_sq = track.mode3a
                            if t_sq is not None:
                                t_sq_str = f"{t_sq:04o}" if isinstance(t_sq, int) else str(t_sq).strip()
                                if t_sq_str == mode3a_str:
                                    has_higher_priority_track = True
                                    break
                        # 4. Proximidad < 1 NM
                        if px is not None and py is not None:
                            dx = track.x - px
                            dy = track.y - py
                            if (dx*dx + dy*dy) < (1852.0 * 1852.0):
                                has_higher_priority_track = True
                                break
                if has_higher_priority_track:
                    continue

            if cat == 21 and not cfg.get("ads_b", True): continue
            elif cat == 62 and not (cfg.get("pistas_secun", True) or cfg.get("pistas_prim", True)): continue
            elif cat in (1, 48):
                is_track = plot.get('is_track', False)
                # Blanco Secundario con Squawk válido: pasa si se permite pista secundaria O plot secundario.
                if mode3a_str and mode3a_str != "----" and mode3a_str != "0000" and not is_psr:
                    if not (cfg.get("pistas_secun", True) or cfg.get("plots_secun", True)):
                        continue
                else:
                    if is_track:
                        if is_psr:
                            if not cfg.get("pistas_prim", True): continue
                        else:
                            if not cfg.get("pistas_secun", True): continue
                    else:
                        if is_psr:
                            if not cfg.get("plots_prim", True): continue
                        else:
                            if not cfg.get("plots_secun", True): continue
            elif cat in (2, 34) and not cfg.get("servicio", True): continue

            # B. Filtro de Sensores (desde diálogo Filtro Datos)
            sensores_sel = cfg.get("sensores_seleccionados", None)
            if sensores_sel is not None:
                # Si hay filtro activo (incluso si está vacío), el sensor del plot debe estar en el conjunto
                plot_sid = plot.get('sac_sic', '')
                if plot_sid not in sensores_sel and plot.get('category') != 62:
                    continue
                
            # C. Filtro de Códigos Mode 3/A (Squawk)
            mode3a = plot.get('mode_3a') or plot.get('mode3a')
            if cfg.get("habilitar_filtro_codigos", False):
                valid_codes = [c.strip() for c in cfg.get("codes", []) if c.strip()]
                if valid_codes:
                    mode3a_str = ""
                    if mode3a is not None:
                        if isinstance(mode3a, int):
                            mode3a_str = f"{mode3a:04o}"
                        else:
                            mode3a_str = str(mode3a).strip()
                    if mode3a_str not in valid_codes:
                        continue
                        
            # D. Filtros de Rangos Numéricos
            # - Distancia (en NM) desde el origen del radar
            px = plot.get('x')
            py = plot.get('y')
            dist_nm = 0.0
            if px is not None and py is not None:
                dist_nm = math.sqrt(px**2 + py**2) / 1852.0
            else:
                plat = plot.get('lat')
                plon = plot.get('lon')
                if plat is not None and plon is not None and self.radar.centro_lat is not None:
                    try:
                        dist_m = self.radar.proy.distancia_vincenty(
                            self.radar.centro_lat, self.radar.centro_lon, plat, plon
                        )
                        dist_nm = dist_m / 1852.0
                    except Exception:
                        pass
                    
            if not (cfg.get("dist_inf", 0.0) <= dist_nm <= cfg.get("dist_sup", 500.0)):
                continue

            # - Acimut (en grados)
            az_deg = 0.0
            if px is not None and py is not None:
                if not (abs(px) < 1e-6 and abs(py) < 1e-6):
                    az_deg = math.degrees(math.atan2(px, py))
                    if az_deg < 0: az_deg += 360.0
            else:
                plat = plot.get('lat')
                plon = plot.get('lon')
                if plat is not None and plon is not None and self.radar.centro_lat is not None:
                    try:
                        az_deg = self.radar.proy.azimuth_vincenty(
                            self.radar.centro_lat, self.radar.centro_lon, plat, plon
                        )
                        if az_deg < 0: az_deg += 360.0
                    except Exception:
                        pass
                    
            if not (cfg.get("az_inf", 0) <= az_deg <= cfg.get("az_sup", 360)):
                continue

            # - Altura (pies o Flight Level)
            fl = plot.get('flight_level')
            alt_ft = plot.get('altitude_ft')
            alt_val = 0.0
            if fl is not None:
                alt_val = fl * 100.0
            elif alt_ft is not None:
                alt_val = alt_ft
                
            if not (cfg.get("alt_inf", -9999) <= alt_val <= cfg.get("alt_sup", 99999)):
                continue

            # - Dirección Mode S / ICAO Hex
            mode_s = (plot.get('mode_s') or "").strip().upper()
            if mode_s:
                id_inf = cfg.get("id21_inf", "000000").strip().upper()
                id_sup = cfg.get("id21_sup", "FFFFFF").strip().upper()
                if not (id_inf <= mode_s <= id_sup):
                    continue

            # Si pasa todos los filtros, incrementamos contador de seleccionados y agregamos
            self.selected_messages_received += 1
            plot['lat_render'] = plot.get('lat')
            plot['lon_render'] = plot.get('lon')
            self.radar.agregar_plot_individual(plot, trigger_update=False)
            
        # Refrescar el widget de radar una única vez para todo el lote
        self.radar.update()
        
        # Evaluar conflictos STCA tras actualizar el radar
        self.evaluar_stca()

        # Si el diálogo de filtros de datos está abierto, actualizamos su contador en caliente
        if getattr(self, 'data_filter_dialog', None) is not None:
            try:
                self.data_filter_dialog.actualizar_contador(
                    self.selected_messages_received,
                    self.total_messages_received
                )
            except Exception:
                pass

    def _abrir_filtro_datos(self):
        # Toggle: si ya está abierto, cerrarlo desde el mismo botón
        dlg = getattr(self, 'data_filter_dialog', None)
        if dlg is not None and dlg.isVisible():
            dlg.close()
            return
        from player.dialogs import RadarDataFilterDialog
        # Construir lista de sensores disponibles para el diálogo
        sensors_list = []
        for sid in sorted(self.sensores_conocidos):
            if '/' not in sid:
                continue
            try:
                sac, sic = map(int, sid.split('/'))
                info = self.sensores.get((sac, sic))
                nombre = info.get('name', f"Radar {sac}/{sic}") if info else f"Radar {sac}/{sic}"
                sensors_list.append((sac, sic, nombre))
            except ValueError:
                continue
        dialog = RadarDataFilterDialog(
            self.data_filter_config,
            self.total_messages_received,
            self.selected_messages_received,
            sensors_list=sensors_list,
            parent=self
        )
        self.data_filter_dialog = dialog
        dialog.filter_applied.connect(self._aplicar_filtro_datos)
        dialog.finished.connect(lambda _r: setattr(self, 'data_filter_dialog', None))
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()

    def _aplicar_filtro_datos(self, config):
        self.data_filter_config = config
        
        # Sincronizar sensores visibles del widget de radar
        sensores_sel = config.get("sensores_seleccionados", None)
        if sensores_sel is not None:
            self.radar.sensores_visibles = sensores_sel
        else:
            self.radar.sensores_visibles = self.sensores_activos
            
        # Forzar repintado para aplicar el filtro al instante sobre los plots ya cargados en pantalla
        self.radar.update()

    def _get_available_fields(self):
        if not self.worker or not self.worker._plots:
            # Si no hay archivo cargado, habilitar todos por defecto
            return {
                "codigo_a", "numero_mensaje", "codigo_c", "direccion_aeronave",
                "numero_respuestas", "velocidad", "hora_utc", "numero_pista",
                "identific_aeronave", "altitud_adsb", "cat_emisor_adsb", "veloc_vertic_adsb",
                "rho_theta"
            }
            
        fields = set()
        plots = self.worker._plots
        
        # 1. Código A (Squawk)
        if any(p.mode3a and p.mode3a != "----" and p.mode3a != "0000" for p in plots):
            fields.add("codigo_a")
            
        # 2. Código C / Flight Level / Altitud
        if any(p.flight_level is not None or p.altitude_ft is not None for p in plots):
            fields.add("codigo_c")
            
        # 3. Identificación Aeronave (Callsign)
        if any(p.callsign and p.callsign.strip() and p.callsign != "----" for p in plots):
            fields.add("identific_aeronave")
            
        # 4. Dirección Aeronave (Mode S)
        if any(p.mode_s and p.mode_s != "----" for p in plots):
            fields.add("direccion_aeronave")
            
        # 5. Velocidad (Ground speed or track angle)
        if any(p.ground_speed is not None or p.track_angle is not None for p in plots):
            fields.add("velocidad")
            
        # 6. Hora UTC
        if any(p.time is not None for p in plots):
            fields.add("hora_utc")
            
        # 7. Número de pista (Track number)
        if any(p.track_number is not None for p in plots):
            fields.add("numero_pista")
            
        # 8. Número de Mensaje (Si hay BDS o categorías 1, 48)
        if any(p.bds_data or p.category in (1, 48) for p in plots):
            fields.add("numero_mensaje")
            
        # 9. Número Respuestas
        if any(p.category in (1, 48) for p in plots):
            fields.add("numero_respuestas")
            
        # 10. Campos exclusivos de ADS-B (CAT 21)
        if any(p.category == 21 for p in plots):
            fields.add("altitud_adsb")
            fields.add("cat_emisor_adsb")
            fields.add("veloc_vertic_adsb")
            
        # 11. RHO / THETA (Distancia/Acimut)
        if any(getattr(p, 'raw_range', None) is not None or getattr(p, 'raw_azimuth', None) is not None for p in plots):
            fields.add("rho_theta")
            
        return fields

    def _abrir_filtro_etiquetas(self):
        # Toggle: si ya está abierto, cerrarlo desde el mismo botón
        dlg = getattr(self, 'label_filter_dialog', None)
        if dlg is not None and dlg.isVisible():
            dlg.close()
            return
        from player.dialogs import LabelFilterDialog
        dialog = LabelFilterDialog(self.label_filter_config, None, self)
        self.label_filter_dialog = dialog
        dialog.config_changed.connect(self._aplicar_filtro_etiquetas)
        dialog.finished.connect(lambda _r: setattr(self, 'label_filter_dialog', None))
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()

    def _aplicar_filtro_etiquetas(self, config):
        self.label_filter_config = config
        self.radar.set_label_filter_config(config)
        self.radar.update()

    def _abrir_perfil_admin(self):
        from player.profile_dialog import ProfileAdminDialog
        dialog = ProfileAdminDialog(self.profile_manager, self)
        dialog.profile_saved.connect(self._aplicar_perfil)
        dialog.hot_load_triggered.connect(self.hot_load_profile)
        dialog.exec()

    def _rebuild_profiles_menu(self):
        """Reconstruye el submenú 'Cambiar Perfil' con los perfiles disponibles,
        marcando el activo. Se reconstruye cada vez que se abre para reflejar
        altas/bajas de perfiles."""
        from PyQt6.QtGui import QActionGroup
        self.menu_perfiles.clear()
        try:
            perfiles = self.profile_manager.listar_perfiles()
        except Exception:
            perfiles = []
        activo = str(self.profile_manager.profile.get("nombre_usuario", "")).strip()

        if not perfiles:
            accion = self.menu_perfiles.addAction("(no hay perfiles)")
            accion.setEnabled(False)
            return

        grupo = QActionGroup(self.menu_perfiles)
        grupo.setExclusive(True)
        for nombre in perfiles:
            accion = self.menu_perfiles.addAction(nombre)
            accion.setCheckable(True)
            accion.setChecked(nombre == activo)
            accion.triggered.connect(lambda _checked=False, n=nombre: self._cambiar_perfil(n))
            grupo.addAction(accion)

    def _cambiar_perfil(self, nombre: str):
        """Cambia el perfil activo en caliente desde el menú."""
        if nombre and nombre != str(self.profile_manager.profile.get("nombre_usuario", "")).strip():
            self.hot_load_profile(nombre)

    def _rebuild_rol_menu(self):
        """Reconstruye el submenú 'Rol Operativo' marcando el rol activo."""
        from PyQt6.QtGui import QActionGroup
        self.menu_rol.clear()
        activo = str(self.profile_manager.profile.get("rol", "tecnico")).strip().lower()
        grupo = QActionGroup(self.menu_rol)
        grupo.setExclusive(True)
        for clave, etiqueta in (("controlador", "Controlador"), ("tecnico", "Técnico")):
            accion = self.menu_rol.addAction(etiqueta)
            accion.setCheckable(True)
            accion.setChecked(clave == activo)
            accion.triggered.connect(lambda _checked=False, r=clave: self._cambiar_rol(r))
            grupo.addAction(accion)

    def _cambiar_rol(self, rol: str):
        """Cambia el rol operativo en caliente, lo persiste y re-aplica la vista."""
        actual = str(self.profile_manager.profile.get("rol", "tecnico")).strip().lower()
        if rol == actual:
            return
        # Persistir el nuevo rol en el perfil activo y re-aplicar
        self.profile_manager.update_profile({"rol": rol})
        self._aplicar_rol(self.profile_manager.profile)
        # La calibración de registración es exclusiva del rol técnico
        if hasattr(self, 'act_calibracion'):
            self.act_calibracion.setEnabled(rol == "tecnico")
        self.radar.update()
        print(f"[ROL] Cambiado en caliente a: {rol}")

    def _abrir_calibracion(self):
        """Abre el panel técnico de calibración de registración (solo rol técnico)."""
        if self.profile_manager.get_rol() != "tecnico":
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "Acceso restringido",
                                "La calibración de registración es exclusiva del rol técnico.")
            return
        from player.calib_dialog import CalibrationDialog
        # No-modal: se mantiene la referencia para que no lo recolecte el GC y
        # se permite seguir usando la consola mientras el calibrador está abierto.
        if getattr(self, '_calib_dialog', None) is not None:
            self._calib_dialog.raise_()
            self._calib_dialog.activateWindow()
            return
        self._calib_dialog = CalibrationDialog(
            self.sensores, pcap_path=getattr(self, 'pcap_path', ''), parent=self)
        self._calib_dialog.setModal(False)
        self._calib_dialog.accepted.connect(self._recargar_sensores_calib)
        self._calib_dialog.finished.connect(lambda _=0: setattr(self, '_calib_dialog', None))
        self._calib_dialog.show()

    def _recargar_sensores_calib(self):
        """Recarga sensores con los offsets recién guardados por el calibrador."""
        import os
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        from utils.geo import cargar_sensores
        self.sensores = cargar_sensores(os.path.join(base_dir, "default-site-params"))

    def hot_load_profile(self, profile_name: str):
        """
        Carga y aplica un perfil de trabajo en caliente sin reiniciar la aplicación.
        """
        try:
            # 1. Leer el perfil mediante el profile_manager
            perfil_data = self.profile_manager.leer_perfil(profile_name)
            
            # 2. Establecer como perfil activo y guardarlo
            self.profile_manager.update_profile(perfil_data)
            
            # 3. Ancla y Zoom Geográfico
            lat = perfil_data.get("center_lat")
            lon = perfil_data.get("center_lon")
            if lat is not None and lon is not None:
                self.radar.configurar_vista_perfil(lat, lon)
                
            # 4. Lógica de Propiedad (Jurisdicción)
            self.techo_incumbencia = perfil_data.get("nivel_incumbencia", 95)
            self.radar.techo_incumbencia = self.techo_incumbencia
            self.radar.radio_incumbencia = float(perfil_data.get("radio_incumbencia", 50))
            self.radar.aeropuerto_lat = lat
            self.radar.aeropuerto_lon = lon
            # Reconfigurar altimetría con la TA del nuevo perfil
            self.radar.altimetry.apply_profile(perfil_data)
            
            # 5. Seguridad Operativa
            self.radar.stca_habilitado = bool(perfil_data.get("stca_habilitado", True))
            self.radar.apw_habilitado = bool(perfil_data.get("apw_habilitado", True))
            if hasattr(self, 'act_stca_habilitado'):
                self.act_stca_habilitado.setChecked(self.radar.stca_habilitado)
            if hasattr(self, 'act_apw_habilitado'):
                self.act_apw_habilitado.setChecked(self.radar.apw_habilitado)
            
            # 6. Carga de Mapas Preexistentes
            if hasattr(self.radar, 'map_manager') and hasattr(self.radar.map_manager, 'load_profile_maps'):
                self.radar.map_manager.load_profile_maps(perfil_data, self.profile_manager)
                self.radar.map_manager.reproject_all(self.radar.proy)
                
            # 7. Re-dibujar los mapas y re-anclar el boundary
            self._rebuild_and_draw_maps()

            # 7.b Aplicar rol operativo (vista limpia + bloqueo playback si es controlador)
            self._aplicar_rol(perfil_data)

            # 8. Actualizar título de la ventana
            apt = perfil_data.get("aeropuerto", "")
            nombre = perfil_data.get("name", "")
            fl = perfil_data.get("nivel_incumbencia", 95)
            self.setWindowTitle(f"ASTERIX Decoder — {nombre} [{apt}] — FL{fl}")

            # Cargar áreas de usuario del store
            self._cargar_areas_usuario(nombre or "Default")

            self.radar.update()
            
            print(f"[HOT SWAP] Perfil '{profile_name}' cargado en caliente con éxito.")
            
        except Exception as e:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.critical(self, "Error de Carga", f"No se pudo cargar el perfil '{profile_name}': {e}")

    def _on_qnh_changed(self, value: int):
        """Refresca el QNH del gestor de altimetría y repinta etiquetas (TL / A-F)."""
        self.radar.altimetry.qnh_local = float(value)
        if hasattr(self, 'lbl_hud_qnh'):
            self.lbl_hud_qnh.setText(f"{value} hPa")
        self.radar.update()

    def _aplicar_rol(self, perfil_data: dict):
        """Aplica el rol operativo: vista limpia + bloqueo de playback para el controlador.

        - Controlador: trabaja online (UDP). Sin playback (PCAP), sin coberturas/símbolo/
          sweep de radar; vista centrada en el área de control. No puede configurar playback.
        - Técnico: acceso completo (configura el playback y ve la vista de diagnóstico).
        """
        rol = str(perfil_data.get("rol", "tecnico")).strip().lower()
        es_controlador = (rol == "controlador")

        # Vista del PPI (ODS: set_vista_controlador apaga el barrido en controlador)
        if hasattr(self.radar, 'set_vista_controlador'):
            self.radar.set_vista_controlador(es_controlador)
        else:
            self.radar.vista_controlador = es_controlador

        # Panel técnico ATSEP: no se abre por defecto. El controlador no puede
        # mostrarlo; el técnico lo abre manualmente desde Ver → Diagnóstico ATSEP.
        if hasattr(self, 'dock_technical') and es_controlador:
            self.dock_technical.setVisible(False)
        if hasattr(self, 'act_toggle_tech_dock'):
            self.act_toggle_tech_dock.setVisible(not es_controlador)

        # Barra de transporte retirada: el reproductor es el widget flotante (menú Modo).
        self.toolbar.setVisible(False)
        if hasattr(self, 'btn_cargar'):
            self.btn_cargar.setEnabled(not es_controlador)
            self.btn_cargar.setVisible(not es_controlador)
        # Acción de menú "Modo Playback": también vedada al controlador.
        if hasattr(self, 'act_modo_playback'):
            self.act_modo_playback.setEnabled(not es_controlador)
            self.act_modo_playback.setVisible(not es_controlador)

        # Controlador: enmarcar el área de control en el aeropuerto del perfil
        if es_controlador:
            lat = perfil_data.get("center_lat")
            lon = perfil_data.get("center_lon")
            if lat is not None and lon is not None:
                self.radar.configurar_vista_perfil(lat, lon)

        self.radar.update()
        self._actualizar_hud(perfil_data)
        print(f"[ROL] Aplicado: {rol} (vista_controlador={es_controlador})")

    def _aplicar_perfil(self, perfil_data: dict):
        """Aplica el perfil operativo guardado: actualiza jurisdicción, recentra mapa."""
        # 1. Persistir al disco
        self.profile_manager.update_profile(perfil_data)
        self._actualizar_hud(perfil_data)

        # 2. Actualizar techo de incumbencia operativa
        self.techo_incumbencia = perfil_data.get("nivel_incumbencia", 95)
        # 2.b Reconfigurar altimetría con la TA del perfil
        self.radar.altimetry.apply_profile(perfil_data)

        # 3. Exportar el techo y radio al RadarWidget (volumen de incumbencia)
        self.radar.techo_incumbencia = self.techo_incumbencia
        self.radar.radio_incumbencia = float(perfil_data.get("radio_incumbencia", 50))
        self.radar.aeropuerto_lat = perfil_data.get("center_lat", -31.31548)
        self.radar.aeropuerto_lon = perfil_data.get("center_lon", -64.21545)
        
        # 3.5. Seguridad operativa STCA y APW
        self.radar.stca_habilitado = bool(perfil_data.get("stca_habilitado", True))
        self.radar.apw_habilitado = bool(perfil_data.get("apw_habilitado", True))
        if hasattr(self, 'act_stca_habilitado'):
            self.act_stca_habilitado.setChecked(self.radar.stca_habilitado)
        if hasattr(self, 'act_apw_habilitado'):
            self.act_apw_habilitado.setChecked(self.radar.apw_habilitado)

        # 4. Recentrar el mapa en el aeropuerto seleccionado
        lat = perfil_data.get("center_lat")
        lon = perfil_data.get("center_lon")
        if lat is not None and lon is not None:
            self.radar.set_projection_center(lat, lon)
            self.radar.centrar_en_coordenadas(lat, lon)

        # 5. Actualizar título de la ventana con el aeropuerto
        apt = perfil_data.get("aeropuerto", "")
        nombre = perfil_data.get("name", "")
        fl = perfil_data.get("nivel_incumbencia", 95)
        self.setWindowTitle(f"ASTERIX Decoder — {nombre} [{apt}] — FL{fl}")

        print(f"[Perfil] Aplicado: {nombre} | Aeropuerto: {apt} | Techo: FL{fl} | "
              f"Centro: ({lat:.5f}, {lon:.5f})")
        
        # Carga en Caliente de Mapas de Perfil y Globales
        if hasattr(self.radar, 'map_manager') and hasattr(self.radar.map_manager, 'load_profile_maps'):
            self.radar.map_manager.load_profile_maps(perfil_data, self.profile_manager)
            self.radar.map_manager.reproject_all(self.radar.proy)
            
        # Re-dibujar los mapas y re-anclar el boundary
        self._rebuild_and_draw_maps()

        # Aplicar rol operativo (vista limpia + bloqueo playback si es controlador)
        self._aplicar_rol(perfil_data)

        # Cargar áreas de usuario del store
        self._cargar_areas_usuario(nombre or "Default")

        self.radar.update()

    def _abrir_filtro_calidad(self):
        # Toggle: si ya está abierto, cerrarlo desde el mismo botón
        dlg = getattr(self, 'quality_filter_dialog', None)
        if dlg is not None and dlg.isVisible():
            dlg.close()
            return
        dialog = QualityFilterDialog(self.radar.quality_manager, self)
        self.quality_filter_dialog = dialog
        dialog.accepted.connect(self._reevaluar_calidad)
        dialog.finished.connect(lambda _r: setattr(self, 'quality_filter_dialog', None))
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()

    def _reevaluar_calidad(self):
        # Forzar reevaluación al instante para todos los tracks con las nuevas reglas
        for tid, track in self.radar.tracks.items():
            from player.radar_widget import SimulationTime
            track_age = SimulationTime.time() - getattr(track, '_first_seen', SimulationTime.time())
            degradada, razon = self.radar.quality_manager.evaluar_pista(
                track.id,
                {'garbled': getattr(track, 'garbled', False), 'update_count': getattr(track, '_update_count', 1), 'age': track_age}
            )
            track.degradada = degradada
            track.dqf_razon = razon
        self.radar.evaluar_stca()
        self.radar.update()

    def _on_progress(self, current: int, total: int):
        if total > 0:
            pct = int((current / total) * 100)
            self.slider_tiempo.blockSignals(True)
            self.slider_tiempo.setValue(pct)
            self.slider_tiempo.blockSignals(False)
            if getattr(self, '_playback_player', None) is not None:
                self._playback_player.set_progress(pct)

    def _on_decoding_progress(self, current: int, total: int):
        if total > 0:
            pct = int((current / total) * 100)
            self.btn_cargar.setText(f" Cargando... {pct}%")
            if getattr(self, '_playback_player', None) is not None:
                self._playback_player.set_loading_progress(pct)

    def _on_tod_update(self, tod: float):
        from player.radar_widget import SimulationTime
        SimulationTime.instance().set_time(tod)
        hours = int(tod // 3600) % 24
        minutes = int((tod % 3600) // 60)
        seconds = int(tod % 60)
        self.lbl_tiempo.setText(f"{hours:02d}:{minutes:02d}:{seconds:02d}")
        if hasattr(self, 'lbl_hud_utc'):
            self.lbl_hud_utc.setText(f"{hours:02d}:{minutes:02d}:{seconds:02d}")
        if getattr(self, '_playback_player', None) is not None:
            self._playback_player.set_time_label(f"{hours:02d}:{minutes:02d}:{seconds:02d}")

    def evaluar_stca(self):
        """Redirige la evaluación al widget de radar central."""
        if self.radar is not None and hasattr(self.radar, 'evaluar_stca'):
            self.radar.evaluar_stca()

    def _on_playback_finished(self):
        self.playing = False
        self._set_play_state(False)
        self._show_panel()



    def _centrar_mapa(self):
        """Recentra la vista según el rol.

        - Controlador: vuelve a centrar el mapa en el área de incumbencia (aeropuerto del perfil).
        - Técnico: centra en el radar seleccionado / sensor activo.
        """
        # Vista FIR satelital activa: recentrarla (en el aeropuerto, o encuadrar tráfico).
        fv = getattr(self, '_fir_view', None)
        if fv is not None and fv.isVisible():
            lat = getattr(self.radar, 'aeropuerto_lat', None)
            lon = getattr(self.radar, 'aeropuerto_lon', None)
            if lat is not None and lon is not None:
                fv.set_center(lon, lat)
            elif fv.tracks:
                fv.fit_to_tracks()
            return

        # Controlador: re-encuadrar el área de incumbencia
        if getattr(self.radar, 'vista_controlador', False):
            lat = getattr(self.radar, 'aeropuerto_lat', None)
            lon = getattr(self.radar, 'aeropuerto_lon', None)
            if lat is not None and lon is not None:
                self.radar.configurar_vista_perfil(lat, lon)
                print(f"[CENTRAR MAPA] Controlador: recentrado en área de incumbencia ({lat:.5f}, {lon:.5f})")
                return

        # Intentar centrar en el sensor activo actual del widget
        center_key = getattr(self.radar, 'center_key', None)
        if center_key:
            sac, sic = center_key
            info = self.sensores.get((sac, sic))
            if info and info.get('lat') and info.get('lon'):
                lat, lon = info['lat'], info['lon']
                nombre = info.get('name', f"Radar {sac}/{sic}")
                self.radar.set_projection_center(lat, lon, center_key)
                self.radar.reproject_all_coordinates()
                self.radar._active_sensor_label = f"SENSOR ACTIVO: {nombre} ({sac}/{sic})"
                print(f"[CENTRAR MAPA] Recentrado en sensor activo: {nombre} ({sac}/{sic})")
                self.radar.centrar_en_coordenadas(lat, lon)
                return

        # Fallback: centrar en el primer sensor conocido con coordenadas
        for sid in self.sensores_conocidos:
            if "/" not in sid:
                continue
            try:
                sac, sic = map(int, sid.split('/'))
                info = self.sensores.get((sac, sic))
                if info and info.get('lat') and info.get('lon'):
                    lat, lon = info['lat'], info['lon']
                    nombre = info.get('name', f"Radar {sac}/{sic}")
                    self.radar.set_projection_center(lat, lon, (sac, sic))
                    self.radar.reproject_all_coordinates()
                    self.radar._active_sensor_label = f"SENSOR ACTIVO: {nombre} ({sac}/{sic})"
                    print(f"[CENTRAR MAPA] Fallback - Centrado en: {nombre} ({sac}/{sic})")
                    self.radar.centrar_en_coordenadas(lat, lon)
                    return
            except (ValueError, AttributeError):
                continue

        # Sin coordenadas disponibles, resetear el zoom
        if hasattr(self.radar, 'zoom_factor'):
            self.radar.zoom_factor = 1.0
            self.radar.update()
            print("[CENTRAR MAPA] Sin coordenadas de sensor, zoom reseteado")

    def _on_rotation_speed_detected(self, sac: int, sic: int, rpm: float):
        sensor_key = (sac, sic)
        self._sensor_rpms[sensor_key] = rpm
        if hasattr(self.radar, 'sensor_rpms'):
            self.radar.sensor_rpms[sensor_key] = rpm
        if self.radar.center_key == sensor_key:
            self.radar.set_sweep_speed(rpm)
        print(f"[REPROYECTOR] Velocidad de rotación detectada para {sac}/{sic} -> {rpm:.2f} RPM")


    def _load_custom_map(self, file_path: str):
        abs_path = os.path.abspath(file_path)
        self._load_and_register_custom_map(abs_path)

    def _load_custom_map_by_name(self, relative_path: str):
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        full_path = os.path.join(base_dir, relative_path)
        self._load_and_register_custom_map(full_path)

    def _cargar_mapa_personalizado(self):
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        initial_dir = os.path.join(base_dir, "files", "INFERIOR")
        if not os.path.exists(initial_dir):
            initial_dir = os.path.join(base_dir, "files")
        if not os.path.exists(initial_dir):
            initial_dir = "."
            
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Seleccionar Archivo de Mapa", initial_dir, "Archivos GeoJSON (*.geojson *.json);;Todos (*)"
        )
        if file_path:
            abs_path = os.path.abspath(file_path)
            self._load_and_register_custom_map(abs_path)

    def _load_and_register_custom_map(self, abs_path: str):
        abs_path = os.path.abspath(abs_path)
        if abs_path in self.map_actions:
            action = self.map_actions[abs_path]
            action.setChecked(True)
            self._on_map_action_triggered(abs_path)
            return

        if not os.path.exists(abs_path):
            print(f"[MAPA PERSONALIZADO] Error: El archivo {abs_path} no existe.")
            return

        name = os.path.basename(abs_path)
        if not hasattr(self, '_custom_maps_separator'):
            self._custom_maps_separator = self.menu_mapas.addSeparator()
            
        action = self.menu_mapas.addAction(name)
        action.setCheckable(True)
        action.setChecked(True)
        action.triggered.connect(lambda checked, p=abs_path: self._on_map_action_triggered(p))
        self.map_actions[abs_path] = action
        
        self._on_map_action_triggered(abs_path)

    def _on_map_action_triggered(self, abs_path: str):
        abs_path = os.path.abspath(abs_path)
        action = self.map_actions.get(abs_path)
        if not action:
            return
            
        is_checked = action.isChecked()
        print(f"[MAPAS] Capa de mapa gatillada: {abs_path} - Activa: {is_checked}")
        
        if is_checked:
            if abs_path in self._loaded_custom_maps:
                self._active_map_paths.add(abs_path)
                self._rebuild_and_draw_maps()
            else:
                print(f"[MAPAS] Iniciando carga asíncrona de capa: {abs_path}")
                self.radar.map_is_absolute = True
                loader = DxfLoaderThread(abs_path)
                loader.dxf_data.connect(self._on_custom_map_loaded)
                loader.dxf_error.connect(lambda msg, p=abs_path: self._on_custom_map_error(p, msg))
                loader.start()
                if not hasattr(self, '_active_loaders'):
                    self._active_loaders = []
                self._active_loaders.append(loader)
        else:
            if abs_path in self._active_map_paths:
                self._active_map_paths.remove(abs_path)
            self._rebuild_and_draw_maps()

    def _on_custom_map_loaded(self, segments, min_x, min_y, max_x, max_y):
        loader = self.sender()
        if not loader:
            return
            
        abs_path = os.path.abspath(loader.filepath)
        if hasattr(self, '_active_loaders') and loader in self._active_loaders:
            self._active_loaders.remove(loader)
            
        print(f"[MAPAS] Capa cargada con éxito: {abs_path} ({len(segments)} segmentos)")
        self._loaded_custom_maps[abs_path] = (segments, min_x, min_y, max_x, max_y)
        
        action = self.map_actions.get(abs_path)
        if action and action.isChecked():
            self._active_map_paths.add(abs_path)
            
        self._rebuild_and_draw_maps()

    def _on_custom_map_error(self, abs_path: str, msg: str):
        loader = self.sender()
        if loader and hasattr(self, '_active_loaders') and loader in self._active_loaders:
            self._active_loaders.remove(loader)
            
        print(f"[MAPAS Error] Error cargando capa {abs_path}: {msg}")
        action = self.map_actions.get(abs_path)
        if action:
            action.setChecked(False)
        if abs_path in self._active_map_paths:
            self._active_map_paths.remove(abs_path)
        self._rebuild_and_draw_maps()

    def _add_atm_action(self, menu, key, label, builder):
        act = menu.addAction(label)
        act.setCheckable(True)
        act.toggled.connect(lambda on, k=key, b=builder: self._toggle_atm_layer(k, on, b))
        self.atm_map_actions[key] = act

    def _toggle_atm_layer(self, key, on, builder):
        """Agrega/quita una capa ATM (aerovía/procedimiento/fixes) en el PPI."""
        from player import atm_maps
        mm = getattr(self.radar, 'map_manager', None)
        if mm is None:
            return
        layer_name = f"ATM::{key}"
        if on:
            try:
                segs = builder()
            except Exception as e:
                print(f"[ATM Mapas] Error generando capa {key}: {e}")
                return
            if not segs:
                print(f"[ATM Mapas] Capa {key} sin geometría")
                return
            mm.add_layer(layer_name, segs, "TACTICO")
            if key.startswith("AERO_") and layer_name in mm.layers:
                cat = key.split("_", 1)[1]
                mm.layers[layer_name].color = atm_maps.AIRWAY_COLORS.get(cat, "#00E5FF")
            if getattr(self.radar, 'proy', None) is not None:
                mm.reproject_all(self.radar.proy)
        else:
            mm.layers.pop(layer_name, None)
        self.radar.update()

    def _rebuild_areas_menu(self):
        """Reconstruye el menú 'Áreas' con los submenús Restringidas, Prohibidas y Peligrosas
        y sus respectivas áreas individuales de la base de datos dentro de listas scrollables."""
        self.menu_areas.clear()
        self.individual_area_actions = {}

        from player import atm_db
        if not atm_db.available():
            na = self.menu_areas.addAction("Base ATM no encontrada (data/atm/atm.duckdb)")
            na.setEnabled(False)
            return

        all_db_areas = atm_db.restricted_airspaces()
        areas_by_kind = {"R": [], "P": [], "D": []}
        for area in all_db_areas:
            if area.kind in areas_by_kind:
                areas_by_kind[area.kind].append(area)

        # Limpiar capas de áreas de DB que hayan sido eliminadas
        mm = getattr(self.radar, 'map_manager', None)
        if mm is not None:
            current_db_names = {a.name for a in all_db_areas}
            user_names = {a.name for a in getattr(self, 'user_areas', [])}
            for name in list(mm.layers.keys()):
                if name.startswith("AREA::"):
                    area_name = name.split("::", 1)[1]
                    if area_name not in current_db_names and area_name not in user_names:
                        mm.layers.pop(name, None)

        from PyQt6.QtWidgets import QWidgetAction, QListWidget, QListWidgetItem
        from PyQt6.QtCore import Qt

        class ScrollableAreaListMenu(QWidgetAction):
            def __init__(self, parent_menu, areas, main_window):
                super().__init__(parent_menu)
                self.main_window = main_window
                self.areas = areas
                
                self.list_widget = QListWidget()
                self.list_widget.setFixedHeight(300)
                self.list_widget.setFixedWidth(220)
                self.list_widget.setStyleSheet("""
                    QListWidget {
                        background-color: #0B0E14;
                        color: #E0E6ED;
                        border: 1px solid rgba(0, 229, 255, 40);
                        font-size: 8pt;
                    }
                    QListWidget::item {
                        padding: 4px;
                    }
                    QListWidget::item:hover {
                        background-color: rgba(0, 229, 255, 20);
                    }
                """)
                
                mm_ref = getattr(main_window.radar, 'map_manager', None)
                for area in areas:
                    item = QListWidgetItem(area.name)
                    item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                    
                    layer_name = f"AREA::{area.name}"
                    was_visible = mm_ref is not None and layer_name in mm_ref.layers
                    item.setCheckState(Qt.CheckState.Checked if was_visible else Qt.CheckState.Unchecked)
                    
                    item.setData(Qt.ItemDataRole.UserRole, area)
                    self.list_widget.addItem(item)
                    
                self.list_widget.itemChanged.connect(self.on_item_changed)
                self.setDefaultWidget(self.list_widget)
                
            def on_item_changed(self, item):
                area = item.data(Qt.ItemDataRole.UserRole)
                checked = item.checkState() == Qt.CheckState.Checked
                self.main_window._toggle_individual_db_area(area, checked)

        self.area_list_widgets = {}

        # Para cada tipo, creamos un submenú y agregamos el widget de lista scrollable
        for label, kind in [("Restringidas", "R"), ("Prohibidas", "P"),
                             ("Peligrosas", "D")]:
            submenu = self.menu_areas.addMenu(label)
            self.area_submenus[kind] = submenu
            
            sorted_areas = sorted(areas_by_kind[kind], key=lambda a: a.name)
            
            if sorted_areas:
                scroll_action = ScrollableAreaListMenu(submenu, sorted_areas, self)
                submenu.addAction(scroll_action)
                self.area_list_widgets[kind] = scroll_action
            else:
                act_empty = submenu.addAction("(vacío)")
                act_empty.setEnabled(False)

        # Capa de referencia: sectores de Altitud Mínima de Sector (MSAW)
        self.menu_areas.addSeparator()
        self.act_msa_sectores = self.menu_areas.addAction("Mostrar sectores MSA")
        self.act_msa_sectores.setCheckable(True)
        self.act_msa_sectores.setChecked(getattr(self, '_msa_sectores_on', False))
        self.act_msa_sectores.toggled.connect(self._toggle_msa_sectores)

    def _toggle_msa_sectores(self, on):
        """Muestra/oculta los sectores MSA (anillo+radiales+MSA) como referencia."""
        from player.msaw import render as _mr
        self._msa_sectores_on = on
        mm = getattr(self.radar, 'map_manager', None)
        if mm is None:
            return
        name = "MSA::SECTORS"
        if on:
            try:
                segs = _mr.msa_segments()
            except Exception as e:
                print(f"[MSA] Error generando sectores: {e}")
                return
            if not segs:
                return
            mm.add_layer(name, segs, "TACTICO")
            if name in mm.layers:
                mm.layers[name].color = _mr.MSA_COLOR
            if getattr(self.radar, 'proy', None) is not None:
                mm.reproject_all(self.radar.proy)
        else:
            mm.layers.pop(name, None)
        self.radar.update()

    def _toggle_individual_db_area(self, area, on):
        """Muestra u oculta una área de base de datos específica en el PPI/ODS."""
        from player.areas import render as _ar
        mm = getattr(self.radar, 'map_manager', None)
        if mm is None:
            return
        layer_name = f"AREA::{area.name}"
        if on:
            try:
                segs = _ar.area_segments([area])
                mm.add_layer(layer_name, segs, "TACTICO")
                if layer_name in mm.layers:
                    mm.layers[layer_name].color = _ar.AREA_COLORS.get(area.kind, "#39C5FF")
                if getattr(self.radar, 'proy', None) is not None:
                    mm.reproject_all(self.radar.proy)
            except Exception as e:
                print(f"[Áreas] Error generando capa individual {area.name}: {e}")
        else:
            mm.layers.pop(layer_name, None)
        self.radar.update()

    def _toggle_area_layer(self, kind, on):
        """Refresca las capas de áreas individuales de la base de datos de un cierto tipo."""
        if not on:
            return
        
        # Reconstruir el menú para reflejar cualquier cambio (alta, baja, modificación)
        self._rebuild_areas_menu()

        # Para todas las áreas individuales de este tipo que estén marcadas como activas (checked),
        # refrescamos su geometría en el map_manager
        mm = getattr(self.radar, 'map_manager', None)
        if mm is not None:
            from player import atm_db
            from player.areas import render as _ar
            
            db_areas = atm_db.restricted_airspaces(kinds=[kind])
            for area in db_areas:
                layer_name = f"AREA::{area.name}"
                if layer_name in mm.layers:
                    try:
                        segs = _ar.area_segments([area])
                        mm.add_layer(layer_name, segs, "TACTICO")
                        if layer_name in mm.layers:
                            mm.layers[layer_name].color = _ar.AREA_COLORS.get(kind, "#39C5FF")
                    except Exception as e:
                        print(f"[Áreas] Error refrescando capa individual {area.name}: {e}")
            
            if getattr(self.radar, 'proy', None) is not None:
                mm.reproject_all(self.radar.proy)
        self.radar.update()

    def _cargar_areas_usuario(self, profile_name: str):
        """Carga las áreas de usuario para el perfil especificado y actualiza las capas del mapa."""
        from player.areas import store as _store
        from player.areas import render as _ar

        # 1. Cargar desde store
        self.user_areas = _store.cargar_todas(profile_name)
        self.radar.user_areas = self.user_areas

        # 2. Limpiar capas de áreas de usuario previas
        mm = getattr(self.radar, 'map_manager', None)
        if mm is not None:
            user_layers = [name for name in mm.layers if name.startswith("AREA::") and name not in ("AREA::R", "AREA::P", "AREA::D")]
            for name in user_layers:
                mm.layers.pop(name, None)

            # 3. Registrar y renderizar las áreas de usuario que estén habilitadas
            for area in self.user_areas:
                if area.vigencia.habilitada:
                    layer_name = f"AREA::{area.name}"
                    segs = _ar.area_segments([area])
                    mm.add_layer(layer_name, segs, "TACTICO")
                    if layer_name in mm.layers:
                        mm.layers[layer_name].color = _ar.AREA_COLORS.get(area.kind, "#39C5FF")

            if getattr(self.radar, 'proy', None) is not None:
                mm.reproject_all(self.radar.proy)

    def get_all_areas(self):
        """Devuelve la combinación de áreas de la base de datos y de usuario."""
        from player import atm_db
        db_a = atm_db.restricted_airspaces() if atm_db.available() else []
        usr_a = getattr(self, 'user_areas', [])
        return db_a + usr_a

    def _rebuild_and_draw_maps(self):
        # 1. Limpiar SOLO las capas gestionadas por estos menús (no las del perfil/cartografía)
        nombres_gestionados = {os.path.basename(p) for p in self.map_actions}
        capas_a_borrar = [name for name in self.radar.map_manager.layers if name in nombres_gestionados]
        for nombre in capas_a_borrar:
            del self.radar.map_manager.layers[nombre]

        # 2. Agregar los mapas tácticos seleccionados
        for path in list(self._active_map_paths):
            if path in self._loaded_custom_maps:
                segs, mx, my, max_x_val, max_y_val = self._loaded_custom_maps[path]
                nombre_base = os.path.basename(path)
                self.radar.set_raw_map_segments(segs, mx, my, max_x_val, max_y_val, nombre_base)
                
        # 4. Forzar dibujado
        self.radar.update()

    # ================================================================
    # Presets UDP (radares guardados: nombre -> ip/puerto)
    # ================================================================
    def _udp_presets_path(self) -> str:
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        cfg_dir = os.path.join(base_dir, "config")
        os.makedirs(cfg_dir, exist_ok=True)
        return os.path.join(cfg_dir, "udp_presets.json")

    def _load_udp_presets(self) -> list:
        path = self._udp_presets_path()
        if not os.path.exists(path):
            return []
        try:
            import json
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return data if isinstance(data, list) else []
        except Exception as e:
            print(f"[UDP Presets] Error leyendo {path}: {e}")
            return []

    def _save_udp_presets(self, presets: list) -> None:
        try:
            import json
            with open(self._udp_presets_path(), 'w', encoding='utf-8') as f:
                json.dump(presets, f, indent=4, ensure_ascii=False)
        except Exception as e:
            print(f"[UDP Presets] Error guardando: {e}")

    def _refrescar_combo_udp_presets(self, seleccionar: str = None) -> None:
        self.combo_udp_preset.blockSignals(True)
        self.combo_udp_preset.clear()
        self.combo_udp_preset.addItem("— Radares guardados —", None)
        idx_sel = 0
        for p in self._load_udp_presets():
            etiqueta = f"{p.get('nombre', '?')}  ({p.get('ip', '')}:{p.get('puerto', '')})"
            self.combo_udp_preset.addItem(etiqueta, p)
            if seleccionar and p.get('nombre') == seleccionar:
                idx_sel = self.combo_udp_preset.count() - 1
        self.combo_udp_preset.setCurrentIndex(idx_sel)
        self.combo_udp_preset.blockSignals(False)

    @staticmethod
    def _parse_ports(texto: str) -> list:
        """Convierte 'p1,p2,...' en lista de puertos válidos (1-65535), sin duplicados."""
        puertos = []
        for tok in str(texto).replace(";", ",").split(","):
            tok = tok.strip()
            if not tok:
                continue
            try:
                v = int(tok)
            except ValueError:
                continue
            if 1 <= v <= 65535 and v not in puertos:
                puertos.append(v)
        return puertos

    def _on_udp_preset_selected(self, _index: int) -> None:
        p = self.combo_udp_preset.currentData()
        if not isinstance(p, dict):
            return
        self.txt_udp_ip.setText(str(p.get('ip', '')))
        self.txt_udp_port.setText(str(p.get('puerto', '')))

    def _upsert_udp_preset(self, nombre: str, ip: str, puerto, match_key: str = "nombre") -> None:
        """Crea o actualiza un preset. puerto puede ser '6610,6611,6612'.
        match_key: 'nombre' o 'endpoint' (ip+puerto)."""
        puerto = str(puerto)
        presets = self._load_udp_presets()
        encontrado = False
        for p in presets:
            if match_key == "endpoint":
                if p.get('ip') == ip and str(p.get('puerto', '')) == puerto:
                    # Ya existe ese endpoint: respetar su nombre, no sobrescribir
                    encontrado = True
                    break
            elif p.get('nombre') == nombre:
                p['ip'], p['puerto'] = ip, puerto
                encontrado = True
                break
        if not encontrado:
            presets.append({"nombre": nombre, "ip": ip, "puerto": puerto})
        self._save_udp_presets(presets)

    def _eliminar_udp_preset(self) -> None:
        p = self.combo_udp_preset.currentData()
        if not isinstance(p, dict):
            QMessageBox.information(self, "Eliminar conexión", "Seleccioná una conexión guardada para eliminar.")
            return
        nombre = p.get('nombre', '')
        resp = QMessageBox.question(
            self, "Eliminar conexión",
            f"¿Eliminar la conexión «{nombre}» ({p.get('ip')}:{p.get('puerto')})?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if resp != QMessageBox.StandardButton.Yes:
            return
        presets = [x for x in self._load_udp_presets()
                   if not (x.get('nombre') == nombre
                           and x.get('ip') == p.get('ip')
                           and str(x.get('puerto', '')) == str(p.get('puerto', '')))]
        self._save_udp_presets(presets)
        self._refrescar_combo_udp_presets()

    def _dialogo_conexion_udp(self, nombre: str = "", ip: str = "", puerto: str = "20000"):
        """Diálogo con nombre, IP y puerto(s). Retorna (nombre, ip, puerto) o None."""
        dlg = QDialog(self)
        dlg.setWindowTitle("Guardar conexión / radar")
        form = QFormLayout(dlg)
        in_nombre = QLineEdit(nombre)
        in_nombre.setPlaceholderText("Ej: Córdoba APP")
        in_ip = QLineEdit(ip)
        in_ip.setPlaceholderText("IP")
        in_puerto = QLineEdit(str(puerto))
        in_puerto.setPlaceholderText("Puerto(s): 6610,6611,6612")
        form.addRow("Nombre:", in_nombre)
        form.addRow("IP:", in_ip)
        form.addRow("Puerto(s):", in_puerto)
        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        form.addRow(btns)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return None
        return in_nombre.text().strip(), in_ip.text().strip(), in_puerto.text().strip()

    def _guardar_udp_preset(self) -> None:
        datos = self._dialogo_conexion_udp(
            ip=self.txt_udp_ip.text().strip(),
            puerto=self.txt_udp_port.text().strip()
        )
        if datos is None:
            return
        nombre, ip, puerto = datos
        if not nombre or not ip or not self._parse_ports(puerto):
            QMessageBox.warning(self, "Guardar conexión", "Nombre, IP y al menos un puerto válido son obligatorios.")
            return
        self._upsert_udp_preset(nombre, ip, puerto, match_key="nombre")
        # Reflejar en los campos activos y seleccionar en el combo
        self.txt_udp_ip.setText(ip)
        self.txt_udp_port.setText(puerto)
        self._refrescar_combo_udp_presets(seleccionar=nombre)

    def _toggle_udp(self):
        if not self.udp_active:
            # 1. Si se requiere grabar PCAP, preguntar ubicación de guardado
            pcap_record_file = None
            if self.chk_grabar_pcap.isChecked():
                pcap_record_file, _ = QFileDialog.getSaveFileName(
                    self, "Guardar Captura ASTERIX PCAP", ".", "Archivos PCAP (*.pcap);;Todos (*)"
                )
                if not pcap_record_file:
                    print("[UDP Live] Grabación cancelada por el usuario.")
                    return

            # 2. Inicializar limpieza de variables de telemetría y pantalla
            self.radar.limpiar_pantalla()
            self.sensores_conocidos.clear()
            self.sensores_activos.clear()
            self.estelas_activas.clear()
            self._modo_manual = False  # permitir default automático por nº de sensores
            self._auto_modo_estado = None
            self.autocentered_on_first_sensor = False
            self.data_filter_config.pop("sensores_seleccionados", None)
            self.total_messages_received = 0
            self.selected_messages_received = 0

            # Limpiar listas y combos de interfaz gráfica para evitar residuos históricos
            self.list_sensores.blockSignals(True)
            self.list_sensores.clear()
            self.list_sensores.blockSignals(False)
            if hasattr(self, 'panel_sensores'):
                self.panel_sensores.limpiar()

            self.combo_sensor.blockSignals(True)
            self.combo_sensor.clear()
            self.combo_sensor.addItem("Autocentrado")
            self.combo_sensor.blockSignals(False)

            # 3. Limpiar cualquier worker activo (si existía)
            self._limpiar_worker()

            # 4. Crear nuevo PlaybackWorker en modo UDP en vivo
            ip_escucha = self.txt_udp_ip.text().strip()
            puertos_texto = self.txt_udp_port.text().strip()
            puertos_escucha = self._parse_ports(puertos_texto)
            if not puertos_escucha:
                QMessageBox.warning(self, "Conectar UDP", "Ingresá al menos un puerto válido (ej: 6610,6611,6612).")
                return

            # Auto-guardar el endpoint como preset (si no existe uno con esa ip:puerto)
            if ip_escucha:
                self._upsert_udp_preset(f"{ip_escucha}:{puertos_texto}", ip_escucha, puertos_texto, match_key="endpoint")
                self._refrescar_combo_udp_presets()

            self.worker = PlaybackWorker(
                udp_ip=ip_escucha,
                udp_port=puertos_escucha,
                pcap_record_file=pcap_record_file,
                sensores=self.sensores,
                cache_dir=self.cache_dir,
                profile_config=self.profile_manager.profile
            )

            # Conectar señales
            self.worker.new_plot_batch.connect(self._on_new_plot_batch)
            self.worker.sensor_detected.connect(self._on_sensor_detected)
            self.worker.rotation_speed_detected.connect(self._on_rotation_speed_detected)
            self.worker.north_mark_detected.connect(self._on_north_mark_detected)
            self.worker.error_occurred.connect(self._on_udp_error)
            self.worker.playback_finished.connect(self._on_udp_finished)
            self.worker.radar_health_changed.connect(self.tech_monitor.update_sensor_status)

            # 5. Deshabilitar controles históricos conflictivos
            self.btn_cargar.setEnabled(False)
            self.btn_play.setEnabled(False)
            self.btn_stop.setEnabled(False)
            self.slider_tiempo.setEnabled(False)
            self.combo_vel.setEnabled(False)
            self.txt_udp_ip.setEnabled(False)
            self.txt_udp_port.setEnabled(False)
            self.chk_grabar_pcap.setEnabled(False)

            # 6. Cambiar apariencia del botón Conectar a Desconectar (Rojo Neón)
            self.btn_conectar_udp.setIcon(_icon("fa5s.unlink"))
            self.btn_conectar_udp.setText(" Desconectar")
            self.btn_conectar_udp.setStyleSheet("""
                QPushButton {
                    background-color: #2A1416;
                    border: 1px solid #F44336;
                    border-radius: 4px;
                    color: #FF6B6B;
                    font-family: 'Segoe UI', sans-serif;
                    font-size: 8pt;
                    font-weight: bold;
                    padding: 4px 6px;
                }
                QPushButton:hover {
                    border: 1px solid #FF5252;
                    color: #FFFFFF;
                    background-color: #F44336;
                }
                QPushButton:pressed {
                    background-color: #FF5252;
                    color: #0B0E14;
                }
            """)

            # 7. Arrancar hilo y barrido radar
            self.worker.start()
            self.playing = True
            self.udp_active = True
            self.radar.play()
            self.btn_pass.setEnabled(True)

            _puertos_str = ",".join(str(p) for p in puertos_escucha)
            print(f"[UDP Live] Conectado exitosamente. Escuchando en {ip_escucha}:{_puertos_str}")
            self.setWindowTitle(f"ASTERIX Radar Decoder - LIVE UDP ({ip_escucha}:{_puertos_str})")
        else:
            self._desconectar_udp_ui()

    def _desconectar_udp_ui(self):
        if not self.udp_active:
            return

        print("[UDP Live] Desconectando receptor UDP...")
        # 1. Detener hilo
        self._limpiar_worker()

        # 2. Detener barrido radar
        self.radar.stop_sweep()
        
        # 2b. Limpiar diálogo STCA y APW
        if self.radar is not None and hasattr(self.radar, 'stca_dialog') and self.radar.stca_dialog:
            self.radar.stca_dialog.limpiar()
        if self.radar is not None and hasattr(self.radar, 'apw_dialog') and self.radar.apw_dialog:
            self.radar.apw_dialog.limpiar()

        # 3. Habilitar controles históricos
        self.btn_cargar.setEnabled(True)
        self.txt_udp_ip.setEnabled(True)
        self.txt_udp_port.setEnabled(True)
        self.chk_grabar_pcap.setEnabled(True)

        # 4. Restaurar estilo del botón Conectar UDP
        self.btn_conectar_udp.setIcon(_icon("fa5s.plug"))
        self.btn_conectar_udp.setText(" Conectar UDP")
        self.btn_conectar_udp.setStyleSheet("""
            QPushButton {
                background-color: #0E2A30;
                border: 1px solid #00E5FF;
                border-radius: 4px;
                color: #00E5FF;
                font-family: 'Segoe UI', sans-serif;
                font-size: 8pt;
                font-weight: bold;
                padding: 4px 6px;
            }
            QPushButton:hover {
                border: 1px solid #39FF14;
                color: #39FF14;
                background-color: #14323A;
            }
            QPushButton:pressed {
                background-color: #39FF14;
                color: #0B0E14;
            }
        """)

        # 5. Reiniciar estados
        self.playing = False
        self.udp_active = False
        self.setWindowTitle("ASTERIX Radar Decoder - Reproductor Multi-Sensor")
        print("[UDP Live] Desconectado.")

    def _on_udp_error(self, message: str):
        # Desconectar ante error de red/socket
        print(f"[UDP Live Error] {message}")
        self._desconectar_udp_ui()
        from PyQt6.QtWidgets import QMessageBox
        QMessageBox.critical(self, "Error de Conexión UDP", message)

    def _on_udp_finished(self):
        # Se gatilla si el hilo finaliza por sí solo o es matado
        if self.udp_active:
            self._desconectar_udp_ui()

    def _on_north_mark_detected(self, sac: int, sic: int):
        # Sincronizar la línea de barrido con la marca de norte si el sensor de referencia la emite
        center_key = getattr(self.radar, 'center_key', None)
        if center_key == (sac, sic):
            self.radar.reset_sweep_angle()
            print(f"[NORTH DETECTED] Barrido sincronizado con marca de norte de {sac}/{sic}")

    def _abrir_analisis_pass(self):
        if not self.worker or not self.worker._plots:
            QMessageBox.warning(self, "Sin datos", "No hay datos cargados para analizar.")
            return
            
        self.btn_pass.setEnabled(False)
        self.btn_pass.setText("Procesando...")
        
        # Copiar ploteos de forma segura (thread-safe)
        self.worker._mutex.lock()
        plots_copy = list(self.worker._plots)
        self.worker._mutex.unlock()
        
        try:
            from analysis.pass_analyzer import PASSAnalyticsEngine
            
            # Instanciar el motor de análisis
            engine = PASSAnalyticsEngine(sensores=self.sensores)
            sensor_rpms = getattr(self, '_sensor_rpms', {})
            
            # Crear y mostrar el diálogo de progreso con estilo cyber
            self._pass_progress = QProgressDialog("Inicializando análisis...", "Cancelar", 0, 0, self)
            self._pass_progress.setWindowTitle("Procesando Análisis PASS (SASS-C)")
            self._pass_progress.setWindowModality(Qt.WindowModality.WindowModal)
            self._pass_progress.setMinimumDuration(0) # Mostrar inmediatamente
            self._pass_progress.setStyleSheet("""
                QProgressDialog {
                    background-color: #0E131F;
                    color: #FFFFFF;
                    border: 2px solid #00E5FF;
                    border-radius: 8px;
                }
                QLabel {
                    color: #00E5FF;
                    font-family: 'Segoe UI', sans-serif;
                    font-weight: bold;
                    font-size: 11pt;
                }
                QPushButton {
                    background-color: #121824;
                    border: 1px solid #FF3366;
                    border-radius: 4px;
                    color: #FF3366;
                    padding: 5px 15px;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background-color: rgba(255, 51, 102, 20);
                }
                QProgressBar {
                    border: 1px solid #00E5FF;
                    border-radius: 4px;
                    text-align: center;
                    background-color: #121824;
                    color: #FFFFFF;
                }
                QProgressBar::chunk {
                    background-color: #00E5FF;
                }
            """)
            
            # Crear worker
            self._pass_worker = PASSAnalysisWorker(engine, plots_copy, sensor_rpms)
            
            # Conectar señales
            self._pass_worker.progress.connect(self._on_pass_analysis_progress)
            self._pass_worker.finished.connect(self._on_pass_analysis_finished)
            self._pass_worker.error.connect(self._on_pass_analysis_error)
            
            # Cancelar
            self._pass_progress.canceled.connect(self._cancelar_analisis_pass)
            
            # Iniciar el hilo
            self._pass_worker.start()
            self._pass_progress.exec()
            
        except Exception as e:
            QMessageBox.critical(self, "Error en Análisis", f"Error iniciando análisis PASS:\n{str(e)}")
            self.btn_pass.setEnabled(True)
            self.btn_pass.setText(" Análisis PASS")

    def _cancelar_analisis_pass(self):
        if hasattr(self, '_pass_worker') and self._pass_worker.isRunning():
            self._pass_worker.terminate()
            self._pass_worker.wait()
        self.btn_pass.setEnabled(True)
        self.btn_pass.setText(" Análisis PASS")
        print("[PASS Analysis] Análisis cancelado por el usuario.")

    def _on_pass_analysis_progress(self, msg: str):
        if hasattr(self, '_pass_progress') and self._pass_progress.isVisible():
            self._pass_progress.setLabelText(msg)

    def _on_pass_analysis_finished(self, resultados: dict):
        if hasattr(self, '_pass_progress'):
            self._pass_progress.close()
            
        self.btn_pass.setEnabled(True)
        self.btn_pass.setText(" Análisis PASS")
        
        try:
            from player.pass_dashboard import PassDashboardDialog
            dialog = PassDashboardDialog(resultados, self)
            dialog.exec()
        except Exception as e:
            QMessageBox.critical(self, "Error en Dashboard", f"Error abriendo el dashboard de resultados:\n{str(e)}")

    def _on_pass_analysis_error(self, err_msg: str):
        if hasattr(self, '_pass_progress'):
            self._pass_progress.close()
            
        self.btn_pass.setEnabled(True)
        self.btn_pass.setText(" Análisis PASS")
        QMessageBox.critical(self, "Error en Análisis", f"Error ejecutando análisis PASS:\n{err_msg}")

    def exportar_kmz(self):
        output_file, _ = QFileDialog.getSaveFileName(
            self, "Exportar Trayectorias a Google Earth (KMZ)", "trajectories.kmz", "Archivos KMZ (*.kmz)"
        )
        if output_file:
            repo_db = None
            if self.worker and hasattr(self.worker, 'engine') and hasattr(self.worker.engine, 'repo_db'):
                repo_db = self.worker.engine.repo_db
            exporter = PassExporter(repo_db=repo_db)
            success = exporter.export_trajectories_kmz(output_file)
            if success:
                QMessageBox.information(self, "Exportación Completada", f"Trayectorias exportadas exitosamente a:\n{output_file}")
            else:
                QMessageBox.critical(self, "Error de Exportación", "Hubo un error al generar el archivo KMZ.")

    def exportar_csv(self):
        output_file, _ = QFileDialog.getSaveFileName(
            self, "Exportar Heatmap a QGIS (CSV)", "export_qgis_heatmap.csv", "Archivos CSV (*.csv)"
        )
        if output_file:
            repo_db = None
            if self.worker and hasattr(self.worker, 'engine') and hasattr(self.worker.engine, 'repo_db'):
                repo_db = self.worker.engine.repo_db
            exporter = PassExporter(repo_db=repo_db)
            success = exporter.export_heatmap_qgis(output_file)
            if success:
                QMessageBox.information(self, "Exportación Completada", f"Datos espaciales exportados exitosamente a:\n{output_file}")
            else:
                QMessageBox.critical(self, "Error de Exportación", "Hubo un error al generar el archivo CSV.")

    def exportar_parquet(self):
        output_file, _ = QFileDialog.getSaveFileName(
            self, "Exportar Datos a Power BI (Parquet)", "export_powerbi.parquet", "Archivos Parquet (*.parquet)"
        )
        if output_file:
            repo_db = None
            if self.worker and hasattr(self.worker, 'engine') and hasattr(self.worker.engine, 'repo_db'):
                repo_db = self.worker.engine.repo_db
            exporter = PassExporter(repo_db=repo_db)
            success = exporter.export_to_powerbi(output_file)
            if success:
                QMessageBox.information(self, "Exportación Completada", f"Datos Parquet exportados exitosamente a:\n{output_file}")
            else:
                QMessageBox.critical(self, "Error de Exportación", "Hubo un error al generar el archivo Parquet.")

    def exportar_playback_kmz(self):
        """Permite seleccionar de forma interactiva un vuelo y exportar su reproducción animada KMZ."""
        from PyQt6.QtWidgets import QInputDialog
        
        # Obtener la conexión a la base de datos para recuperar los track_id válidos
        repo_db = None
        if self.worker and hasattr(self.worker, 'engine') and hasattr(self.worker.engine, 'repo_db'):
            repo_db = self.worker.engine.repo_db
            
        tracks = []
        if repo_db:
            try:
                res = repo_db.query("SELECT DISTINCT track_id FROM asterix_plots WHERE track_id != '' AND lat != 0.0 AND lon != 0.0 ORDER BY track_id")
                tracks = [r[0] for r in res if r[0]]
            except Exception as e:
                print(f"[GUI] Error al consultar tracks: {e}")
                
        if not tracks:
            QMessageBox.warning(self, "Sin datos de trayectoria", "No se encontraron trayectorias de vuelos válidas (con coordenadas proyectadas) en la base de datos actual.")
            return

        track_id, ok = QInputDialog.getItem(
            self, "Reproducción de Vuelo KML", 
            "Selecciona el Vuelo (Track ID) para exportar su reproducción animada en Google Earth:",
            tracks, 0, False
        )
        
        if ok and track_id:
            output_file, _ = QFileDialog.getSaveFileName(
                self, f"Exportar Animación Vuelo {track_id} (KMZ)", f"playback_track_{track_id}.kmz", "Archivos KMZ (*.kmz)"
            )
            if output_file:
                exporter = PassExporter(repo_db=repo_db)
                success = exporter.export_flight_playback_kmz(track_id, output_file)
                if success:
                    QMessageBox.information(self, "Exportación Completada", f"La reproducción animada del Vuelo {track_id} se ha generado exitosamente en:\n{output_file}")
                else:
                    QMessageBox.critical(self, "Error de Exportación", f"Hubo un error al generar el archivo KMZ de reproducción para el Vuelo {track_id}.")

    def exportar_cobertura_kmz(self):
        """Permite seleccionar de forma interactiva un sensor de radar y exportar su mapa de cobertura real KMZ."""
        from PyQt6.QtWidgets import QInputDialog
        
        repo_db = None
        if self.worker and hasattr(self.worker, 'engine') and hasattr(self.worker.engine, 'repo_db'):
            repo_db = self.worker.engine.repo_db
            
        sensors = []
        if repo_db:
            try:
                res = repo_db.query("SELECT DISTINCT sac_sic FROM asterix_plots WHERE sac_sic != '' AND lat != 0.0 AND lon != 0.0 ORDER BY sac_sic")
                sensors = [r[0] for r in res if r[0]]
            except Exception as e:
                print(f"[GUI] Error al consultar sensores para cobertura: {e}")
                
        if not sensors:
            QMessageBox.warning(self, "Sin datos de sensores", "No se encontraron sensores con datos de ploteos válidos (coordenadas proyectadas) en la base de datos actual.")
            return

        sensor_id, ok = QInputDialog.getItem(
            self, "Mapa de Cobertura Radar KML", 
            "Selecciona el Sensor (SAC/SIC) para exportar su Mapa de Cobertura Real (polígono):",
            sensors, 0, False
        )
        
        if ok and sensor_id:
            output_file, _ = QFileDialog.getSaveFileName(
                self, f"Exportar Cobertura Radar {sensor_id} (KMZ)", f"cobertura_radar_{sensor_id.replace('/', '_')}.kmz", "Archivos KMZ (*.kmz)"
            )
            if output_file:
                exporter = PassExporter(repo_db=repo_db)
                success = exporter.export_coverage_map_kmz(sensor_id, output_file)
                if success:
                    QMessageBox.information(self, "Exportación Completada", f"El mapa de cobertura para el radar {sensor_id} se ha generado exitosamente en:\n{output_file}")
                else:
                    QMessageBox.critical(self, "Error de Exportación", f"Hubo un error al generar el archivo KMZ de cobertura para el radar {sensor_id}.")

    def closeEvent(self, event):
        self._limpiar_worker()
        shutil.rmtree(self.cache_dir, ignore_errors=True)
        event.accept()

if __name__ == '__main__':
    app = QApplication(sys.argv)
    w = MainWindow()
    w.show()
    sys.exit(app.exec())
