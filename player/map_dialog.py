import os
import re
import math
from datetime import time
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QWidget, QGroupBox,
    QPushButton, QLabel, QComboBox, QListWidget,
    QListWidgetItem, QMessageBox, QButtonGroup, QCheckBox, QFormLayout,
    QTextEdit, QLineEdit, QRadioButton, QTimeEdit, QTabWidget, QDoubleSpinBox, QSpinBox
)
from PyQt6.QtCore import Qt, QEvent, QPointF
from PyQt6.QtGui import QPainter, QPen, QColor, QPolygonF, QBrush
from geo_tools import GeoTools

class FLSpinBox(QSpinBox):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setRange(0, 999)
        self.setValue(0)

    def textFromValue(self, value):
        if value == 999:
            return "UNL"
        return f"{value:03d}"

    def valueFromText(self, text):
        if text.strip().upper() == "UNL":
            return 999
        try:
            return int(text)
        except ValueError:
            return 0

# Color mapping for presentation and drawing
COLOR_MAP = {
    "Cian (#00E5FF)": QColor("#00E5FF"),
    "Rojo (#FF0000)": QColor("#FF0000"),
    "Amarillo (#FFFF00)": QColor("#FFFF00"),
    "Blanco (#FFFFFF)": QColor("#FFFFFF"),
    "Naranja (#FFA500)": QColor("#FFA500")
}

STYLE_MAP = {
    "Solid Line": Qt.PenStyle.SolidLine,
    "Dash Line": Qt.PenStyle.DashLine,
    "Dot Line": Qt.PenStyle.DotLine
}

WIDTH_MAP = {
    "1px": 1,
    "2px": 2,
    "3px": 3
}

def is_valid_coord(x, y):
    try:
        return x is not None and y is not None and not math.isnan(x) and not math.isnan(y) and not math.isinf(x) and not math.isinf(y)
    except Exception:
        return False

def decimal_to_dms(lat, lon):
    def lat_to_dms(val):
        ns = 'N' if val >= 0 else 'S'
        val = abs(val)
        deg = int(val)
        min_val = int((val - deg) * 60)
        sec_val = round(((val - deg) * 60 - min_val) * 60, 1)
        if sec_val >= 60.0:
            sec_val = 0.0
            min_val += 1
        if min_val >= 60:
            min_val = 0
            deg += 1
        return f"{deg:02d}{min_val:02d}{sec_val:04.1f}{ns}"

    def lon_to_dms(val):
        ew = 'E' if val >= 0 else 'W'
        val = abs(val)
        deg = int(val)
        min_val = int((val - deg) * 60)
        sec_val = round(((val - deg) * 60 - min_val) * 60, 1)
        if sec_val >= 60.0:
            sec_val = 0.0
            min_val += 1
        if min_val >= 60:
            min_val = 0
            deg += 1
        return f"{deg:03d}{min_val:02d}{sec_val:04.1f}{ew}"

    return f"{lat_to_dms(lat)} {lon_to_dms(lon)}"

class LMG_Dialog(QDialog):
    """
    Local Maps Generation Tool (LMG_Dialog)
    An advanced editor dialog that integrates with the main radar widget
    to generate, edit, and persist tactical maps.
    """
    def __init__(self, map_manager, parent=None):
        super().__init__(parent)
        self.map_manager = map_manager
        self.parent_window = parent
        self.radar = parent.radar if parent and hasattr(parent, 'radar') else None
        
        self.setWindowTitle("Herramienta de Dibujo")
        self.setWindowFlags(Qt.WindowType.Tool | Qt.WindowType.WindowStaysOnTopHint)
        self.setMinimumSize(380, 700)
        from player.ui_scaling import escalar_ventana
        escalar_ventana(self, 400, 750, centrar=False)
        
        # State variables
        self.completed_shapes = []
        self.drawn_points = []
        self.shape_closed = False
        self.dragging = False
        self.circle_center = None
        self.circle_radius_nm = 0.0
        self.loaded_control_areas = []
        
        # Arc State Machine
        self.arc_step = 0
        self.arc_center = None
        self.arc_start_point = None
        
        # Regex coordinates validation
        self.regex_latlon = re.compile(
            r"^([0-8]\d|90)([0-5]\d)([0-5]\d\.\d)([NSns])\s*(0\d{2}|1[0-7]\d|180)([0-5]\d)([0-5]\d\.\d)([EWeWw])$"
        )
        
        self.setStyleSheet("""
            QDialog {
                background-color: #0B0E14;
                color: #E0E6ED;
                font-family: 'Segoe UI', 'Consolas', sans-serif;
            }
            QGroupBox {
                border: 1px solid rgba(0, 229, 255, 60);
                border-radius: 6px;
                margin-top: 10px;
                padding-top: 15px;
                color: #00E5FF;
                font-weight: bold;
                font-size: 9pt;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                padding: 0 5px;
                background-color: #0B0E14;
            }
            QLabel {
                color: #E0E6ED;
                font-size: 8pt;
            }
            QPushButton {
                background-color: rgba(0, 229, 255, 10);
                border: 1px solid rgba(0, 229, 255, 80);
                border-radius: 4px;
                color: #00E5FF;
                font-weight: bold;
                padding: 5px 10px;
                font-size: 8pt;
            }
            QPushButton:hover {
                border: 1px solid #39FF14;
                color: #39FF14;
                background-color: rgba(57, 255, 20, 15);
            }
            QPushButton:checked {
                background-color: rgba(57, 255, 20, 25);
                border: 1px solid #39FF14;
                color: #39FF14;
                background-color: rgba(57, 255, 20, 15);
            }
            QPushButton:disabled {
                background-color: rgba(255, 255, 255, 5);
                border: 1px solid rgba(255, 255, 255, 10);
                color: #555555;
            }
            QComboBox {
                background-color: #1A2130;
                color: #E0E6ED;
                border: 1px solid rgba(0, 229, 255, 60);
                border-radius: 4px;
                padding: 4px;
                font-size: 8pt;
                min-height: 20px;
            }
            QTextEdit {
                background-color: #1A2130;
                color: #E0E6ED;
                border: 1px solid rgba(0, 229, 255, 60);
                border-radius: 4px;
                padding: 4px;
                font-size: 8pt;
            }
            QLineEdit, QSpinBox, QDoubleSpinBox, QTimeEdit {
                background-color: #1A2130;
                color: #E0E6ED;
                border: 1px solid rgba(0, 229, 255, 60);
                border-radius: 4px;
                padding: 4px;
                font-size: 8pt;
                min-height: 20px;
            }
            QListWidget {
                background-color: #101520;
                border: 1px solid rgba(0, 229, 255, 40);
                border-radius: 4px;
                color: #E0E6ED;
            }
            QTabWidget::pane {
                border: 1px solid rgba(0, 229, 255, 40);
                background: #0B0E14;
                border-radius: 4px;
            }
            QTabBar::tab {
                background: #101520;
                border: 1px solid rgba(0, 229, 255, 40);
                padding: 6px 12px;
                margin-right: 2px;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
                color: #E0E6ED;
                font-size: 8pt;
                font-weight: bold;
            }
            QTabBar::tab:selected {
                background: #0B0E14;
                border-bottom-color: #0B0E14;
                color: #00E5FF;
            }
        """)
        
        # Setup main layouts
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(8)
        
        self.tabs = QTabWidget()
        self.tabs.currentChanged.connect(self.on_tab_changed)
        main_layout.addWidget(self.tabs)
        
        # --- TAB 1: DIBUJO DE CAPAS ---
        tab_draw = QWidget()
        tab_draw_layout = QVBoxLayout(tab_draw)
        tab_draw_layout.setContentsMargins(5, 5, 5, 5)
        tab_draw_layout.setSpacing(8)
        
        # 1. Primitive Graphic Type Area
        primitive_group = QGroupBox("Tipo de Gráfico Primitivo")
        primitive_layout = QHBoxLayout(primitive_group)
        
        self.btn_vector = QPushButton("Vector")
        self.btn_vector.setCheckable(True)
        self.btn_vector.setChecked(True)
        self.btn_vector.clicked.connect(self.on_mode_changed)
        
        self.btn_circle = QPushButton("Circle")
        self.btn_circle.setCheckable(True)
        self.btn_circle.clicked.connect(self.on_mode_changed)
        
        self.btn_arc = QPushButton("Arc")
        self.btn_arc.setCheckable(True)
        self.btn_arc.clicked.connect(self.on_mode_changed)
        
        self.mode_group = QButtonGroup(self)
        self.mode_group.addButton(self.btn_vector)
        self.mode_group.addButton(self.btn_circle)
        self.mode_group.addButton(self.btn_arc)
        self.mode_group.setExclusive(True)
        
        primitive_layout.addWidget(self.btn_vector)
        primitive_layout.addWidget(self.btn_circle)
        primitive_layout.addWidget(self.btn_arc)
        tab_draw_layout.addWidget(primitive_group)
        
        # 2. Edition Area (Central QGroupBox)
        edition_group = QGroupBox("Área de Edición")
        edition_layout = QVBoxLayout(edition_group)
        
        edition_layout.addWidget(QLabel("Nombre de Capa:"))
        self.combo_capas = QComboBox()
        self.combo_capas.setEditable(True)
        self.combo_capas.addItems(["MI_AREA_TACTICA", "NOTAM_ZONA", "ZONA_EXCLUSION", "CIRCULO_RANA"])
        edition_layout.addWidget(self.combo_capas)
        
        edition_layout.addWidget(QLabel("Ingreso de Coordenadas Lat/Long (DMS):"))
        self.txt_coordenadas = QTextEdit()
        self.txt_coordenadas.setPlaceholderText("Ej: 341215.3N 0582645.2W\nIngrese un punto por línea.")
        self.txt_coordenadas.setMinimumHeight(80)
        self.txt_coordenadas.textChanged.connect(self.reset_coordinate_style)
        edition_layout.addWidget(self.txt_coordenadas)
        
        btn_shape_layout = QHBoxLayout()
        self.btn_generate_shape = QPushButton("Generar Figura")
        self.btn_generate_shape.clicked.connect(self.generate_shape_clicked)
        self.btn_finish_shape = QPushButton("✔ Finalizar Figura")
        self.btn_finish_shape.clicked.connect(self.finish_current_shape)
        self.btn_new_shape = QPushButton("➕ Nueva Figura")
        self.btn_new_shape.setToolTip("Finaliza la figura actual y comienza a dibujar una nueva (sin borrar las anteriores)")
        self.btn_new_shape.clicked.connect(self.new_shape_clicked)
        btn_shape_layout.addWidget(self.btn_generate_shape)
        btn_shape_layout.addWidget(self.btn_finish_shape)
        btn_shape_layout.addWidget(self.btn_new_shape)
        edition_layout.addLayout(btn_shape_layout)
        
        # Dropdowns for Style Configuration
        form_layout = QFormLayout()
        form_layout.setSpacing(6)
        
        self.combo_color = QComboBox()
        self.combo_color.addItems(["Cian (#00E5FF)", "Rojo (#FF0000)", "Amarillo (#FFFF00)", "Blanco (#FFFFFF)", "Naranja (#FFA500)"])
        self.combo_color.currentIndexChanged.connect(self.refresh_radar)
        
        self.combo_style = QComboBox()
        self.combo_style.addItems(["Solid Line", "Dash Line", "Dot Line"])
        self.combo_style.currentIndexChanged.connect(self.refresh_radar)
        
        self.combo_width = QComboBox()
        self.combo_width.addItems(["2px", "1px", "3px"])
        self.combo_width.currentIndexChanged.connect(self.refresh_radar)
        
        form_layout.addRow(QLabel("Color:"), self.combo_color)
        form_layout.addRow(QLabel("Contorno:"), self.combo_style)
        form_layout.addRow(QLabel("Grosor:"), self.combo_width)
        edition_layout.addLayout(form_layout)
        
        tab_draw_layout.addWidget(edition_group)
        
        # 3. Command Area (Lower QGroupBox)
        command_group = QGroupBox("Comandos")
        command_layout = QVBoxLayout(command_group)
        
        btn_layout = QHBoxLayout()
        self.btn_load = QPushButton("Cargar Capas")
        self.btn_load.clicked.connect(self.load_profile_layers)
        
        self.btn_save = QPushButton("Guardar Capa")
        self.btn_save.clicked.connect(self.save_current_layer)
        
        self.btn_clear = QPushButton("Limpiar Dibujo")
        self.btn_clear.clicked.connect(self.clear_drawing)
        
        btn_layout.addWidget(self.btn_load)
        btn_layout.addWidget(self.btn_save)
        btn_layout.addWidget(self.btn_clear)
        command_layout.addLayout(btn_layout)
        
        command_layout.addWidget(QLabel("Capas del Perfil:"))
        self.list_capas = QListWidget()
        self.list_capas.setMinimumHeight(80)
        command_layout.addWidget(self.list_capas)
        
        tab_draw_layout.addWidget(command_group)
        self.tabs.addTab(tab_draw, "Dibujo de Capas")

        # --- TAB 2: ÁREAS OPERATIVAS (CRUD) ---
        tab_areas = QWidget()
        tab_areas_layout = QVBoxLayout(tab_areas)
        tab_areas_layout.setContentsMargins(5, 5, 5, 5)
        tab_areas_layout.setSpacing(8)

        # Form group box
        area_form_group = QGroupBox("Nueva / Editar Área")
        area_form_layout = QFormLayout(area_form_group)
        area_form_layout.setSpacing(6)

        self.txt_area_name = QLineEdit()
        self.txt_area_name.setPlaceholderText("Ej: SAP116, ZONA_X")
        self.txt_area_name.setStyleSheet("QLineEdit { background-color: #1A2130; color: #E0E6ED; border: 1px solid rgba(0, 229, 255, 60); border-radius: 4px; padding: 4px; }")
        
        self.combo_area_tipo = QComboBox()
        self.combo_area_tipo.addItems(["Restringida (R)", "Prohibida (P)", "Peligrosa (D)"])
        
        self.spin_area_lower = FLSpinBox()
        self.spin_area_lower.setStyleSheet("QSpinBox { background-color: #1A2130; color: #E0E6ED; border: 1px solid rgba(0, 229, 255, 60); border-radius: 4px; padding: 4px; }")
        
        self.spin_area_upper = FLSpinBox()
        self.spin_area_upper.setValue(999) # Default to unlimited
        self.spin_area_upper.setStyleSheet("QSpinBox { background-color: #1A2130; color: #E0E6ED; border: 1px solid rgba(0, 229, 255, 60); border-radius: 4px; padding: 4px; }")

        self.combo_area_shape = QComboBox()
        self.combo_area_shape.addItems(["Polígono", "Círculo"])
        self.combo_area_shape.currentIndexChanged.connect(self.on_area_shape_changed)

        self.spin_area_radius = QDoubleSpinBox()
        self.spin_area_radius.setRange(0.1, 999.0)
        self.spin_area_radius.setValue(5.0)
        self.spin_area_radius.setSuffix(" NM")
        self.spin_area_radius.setStyleSheet("QDoubleSpinBox { background-color: #1A2130; color: #E0E6ED; border: 1px solid rgba(0, 229, 255, 60); border-radius: 4px; padding: 4px; }")
        self.spin_area_radius.setEnabled(False) # Only enabled for Circle

        self.txt_area_coords = QTextEdit()
        self.txt_area_coords.setPlaceholderText("Ej para Polígono:\n341215.3N 0582645.2W\n341230.5N 0582615.1W\n\nEj para Círculo (Centro):\n341215.3N 0582645.2W")
        self.txt_area_coords.setMinimumHeight(60)
        self.txt_area_coords.setStyleSheet("background-color: #1A2130; color: #E0E6ED; border: 1px solid rgba(0, 229, 255, 60); border-radius: 4px; padding: 4px;")

        area_form_layout.addRow(QLabel("Nombre:"), self.txt_area_name)
        area_form_layout.addRow(QLabel("Tipo:"), self.combo_area_tipo)
        area_form_layout.addRow(QLabel("Límite Inferior (FL):"), self.spin_area_lower)
        area_form_layout.addRow(QLabel("Límite Superior (FL):"), self.spin_area_upper)
        area_form_layout.addRow(QLabel("Geometría:"), self.combo_area_shape)
        area_form_layout.addRow(QLabel("Radio Círculo:"), self.spin_area_radius)
        area_form_layout.addRow(QLabel("Coordenadas (DMS):"), self.txt_area_coords)

        # Vigencia Group Box inside Form
        self.rad_area_perm = QRadioButton("Permanente")
        self.rad_area_perm.setChecked(True)
        self.rad_area_temp = QRadioButton("Temporal")
        
        self.vigencia_group = QButtonGroup(self)
        self.vigencia_group.addButton(self.rad_area_perm)
        self.vigencia_group.addButton(self.rad_area_temp)
        
        vig_radio_layout = QHBoxLayout()
        vig_radio_layout.addWidget(self.rad_area_perm)
        vig_radio_layout.addWidget(self.rad_area_temp)
        area_form_layout.addRow(QLabel("Vigencia:"), vig_radio_layout)

        # Temporal Options Widget (indented/grouped)
        self.widget_temporal_options = QWidget()
        temp_opts_layout = QVBoxLayout(self.widget_temporal_options)
        temp_opts_layout.setContentsMargins(15, 0, 0, 0)
        temp_opts_layout.setSpacing(6)

        self.chk_area_enabled = QCheckBox("Activar área (Habilitada)")
        self.chk_area_enabled.setChecked(True)
        self.chk_area_enabled.setStyleSheet("QCheckBox { color: #E0E6ED; font-size: 8pt; }")
        temp_opts_layout.addWidget(self.chk_area_enabled)

        # Franja Desde-Hasta
        time_layout = QHBoxLayout()
        self.time_area_desde = QTimeEdit()
        self.time_area_desde.setDisplayFormat("HH:mm")
        self.time_area_desde.setTime(time(0, 0))
        self.time_area_desde.setStyleSheet("QTimeEdit { background-color: #1A2130; color: #E0E6ED; border: 1px solid rgba(0, 229, 255, 60); border-radius: 4px; padding: 2px; }")
        
        self.time_area_hasta = QTimeEdit()
        self.time_area_hasta.setDisplayFormat("HH:mm")
        self.time_area_hasta.setTime(time(23, 59))
        self.time_area_hasta.setStyleSheet("QTimeEdit { background-color: #1A2130; color: #E0E6ED; border: 1px solid rgba(0, 229, 255, 60); border-radius: 4px; padding: 2px; }")
        
        time_layout.addWidget(QLabel("Desde:"))
        time_layout.addWidget(self.time_area_desde)
        time_layout.addWidget(QLabel("Hasta:"))
        time_layout.addWidget(self.time_area_hasta)
        temp_opts_layout.addLayout(time_layout)

        # Days of week checkboxes
        days_layout = QHBoxLayout()
        days_names = ["Lun", "Mar", "Mie", "Jue", "Vie", "Sab", "Dom"]
        self.chk_days = []
        for d_name in days_names:
            chk = QCheckBox(d_name)
            chk.setStyleSheet("QCheckBox { color: #E0E6ED; font-size: 7.5pt; }")
            days_layout.addWidget(chk)
            self.chk_days.append(chk)
        temp_opts_layout.addLayout(days_layout)

        self.widget_temporal_options.setEnabled(False) # disabled by default
        self.rad_area_temp.toggled.connect(self.widget_temporal_options.setEnabled)
        
        area_form_layout.addRow(self.widget_temporal_options)

        # Save/Clear Form buttons
        form_btn_layout = QHBoxLayout()
        self.btn_save_area = QPushButton("Guardar Área")
        self.btn_save_area.clicked.connect(self.save_area)
        self.btn_clear_area_form = QPushButton("Limpiar Formulario")
        self.btn_clear_area_form.clicked.connect(self.clear_area_form)
        form_btn_layout.addWidget(self.btn_save_area)
        form_btn_layout.addWidget(self.btn_clear_area_form)
        area_form_layout.addRow(form_btn_layout)

        tab_areas_layout.addWidget(area_form_group)

        # Combined List Group (Non-invasive Dropdown selection)
        areas_list_group = QGroupBox("Áreas de Control (DB + Usuario)")
        areas_list_layout = QHBoxLayout(areas_list_group)
        areas_list_layout.setSpacing(6)
        areas_list_layout.setContentsMargins(5, 5, 5, 5)

        self.combo_sel_area = QComboBox()
        self.combo_sel_area.setStyleSheet("QComboBox { background-color: #1A2130; color: #E0E6ED; border: 1px solid rgba(0, 229, 255, 60); border-radius: 4px; padding: 4px; }")
        self.combo_sel_area.currentIndexChanged.connect(self.on_selected_area_changed)

        self.chk_sel_area_visible = QCheckBox("Vis")
        self.chk_sel_area_visible.setToolTip("Visibilidad del área (solo para áreas de usuario)")
        self.chk_sel_area_visible.setStyleSheet("QCheckBox { color: #00E5FF; font-size: 8pt; font-weight: bold; }")
        self.chk_sel_area_visible.toggled.connect(self.toggle_selected_user_area_visibility)

        self.btn_edit_sel_area = QPushButton("Edit")
        self.btn_edit_sel_area.setFixedSize(40, 22)
        self.btn_edit_sel_area.setStyleSheet("QPushButton { padding: 2px; font-size: 8pt; }")
        self.btn_edit_sel_area.clicked.connect(self.edit_selected_area)

        self.btn_del_sel_area = QPushButton("X")
        self.btn_del_sel_area.setFixedSize(22, 22)
        self.btn_del_sel_area.setToolTip("Eliminar área seleccionada")
        self.btn_del_sel_area.setStyleSheet("""
            QPushButton {
                background-color: rgba(255, 51, 102, 30);
                border: 1px solid #ff3366;
                color: #ff3366;
                border-radius: 4px;
                font-weight: bold;
                padding: 0px;
                font-size: 8pt;
            }
            QPushButton:hover {
                background-color: #ff3366;
                color: white;
            }
        """)
        self.btn_del_sel_area.clicked.connect(self.delete_selected_area)

        areas_list_layout.addWidget(self.combo_sel_area, 1)
        areas_list_layout.addWidget(self.chk_sel_area_visible)
        areas_list_layout.addWidget(self.btn_edit_sel_area)
        areas_list_layout.addWidget(self.btn_del_sel_area)
        tab_areas_layout.addWidget(areas_list_group)

        self.tabs.addTab(tab_areas, "Áreas")
        
        # Hook Radar Widget event filter and renderer
        if self.radar:
            self.radar.installEventFilter(self)
            self.original_paint_event = self.radar.paintEvent
            self.radar.paintEvent = self.custom_radar_paint_event
            self.radar.update()
            
        self.load_profile_layers()
        self.load_areas_list()
        
    def refresh_radar(self):
        if self.radar:
            self.radar.update()
            
    def on_mode_changed(self):
        # Solo limpia la figura en progreso, NO las figuras completadas
        self.drawn_points = []
        self.shape_closed = False
        self.circle_center = None
        self.dragging = False
        self.arc_step = 0
        self.arc_center = None
        self.arc_start_point = None
        self.refresh_radar()
        
    def get_profile_maps_dir(self):
        username = "Default"
        if self.parent_window and hasattr(self.parent_window, 'profile_manager'):
            username = self.parent_window.profile_manager.profile.get("name", "Default")
        target_dir = os.path.join(self.map_manager.profiles_dir, f"mapas_{username}")
        return target_dir
        
    def reset_coordinate_style(self):
        self.txt_coordenadas.setStyleSheet("background-color: #1A2130; color: #E0E6ED; border: 1px solid rgba(0, 229, 255, 60);")
        if hasattr(self, 'txt_area_coords') and self.txt_area_coords:
            self.txt_area_coords.setStyleSheet("background-color: #1A2130; color: #E0E6ED; border: 1px solid rgba(0, 229, 255, 60);")
            
    def parse_coordinate_string(self, text: str):
        text = text.strip()
        match = self.regex_latlon.match(text)
        if not match:
            return None
            
        lat_deg = float(match.group(1))
        lat_min = float(match.group(2))
        lat_sec = float(match.group(3))
        lat_dir = match.group(4).upper()
        
        lon_deg = float(match.group(5))
        lon_min = float(match.group(6))
        lon_sec = float(match.group(7))
        lon_dir = match.group(8).upper()
        
        # decimal = degrees + minutes/60 + seconds/3600
        lat_dec = lat_deg + lat_min / 60.0 + lat_sec / 3600.0
        if lat_dir == 'S':
            lat_dec = -lat_dec
            
        lon_dec = lon_deg + lon_min / 60.0 + lon_sec / 3600.0
        if lon_dir == 'W':
            lon_dec = -lon_dec
            
        return lat_dec, lon_dec
        
    def update_coordinates_text(self):
        dms_lines = []
        for shape in self.completed_shapes:
            shape_dms = []
            for lat, lon in shape["points"]:
                shape_dms.append(decimal_to_dms(lat, lon))
            dms_lines.append("\n".join(shape_dms))
        self.txt_coordenadas.setPlainText("\n\n".join(dms_lines))

    def finish_current_shape(self):
        """Finaliza la figura en progreso y la agrega a completed_shapes."""
        if self.drawn_points:
            self.completed_shapes.append({
                "points": list(self.drawn_points),
                "closed": self.shape_closed
            })
            self.drawn_points = []
            self.shape_closed = False
            self.update_coordinates_text()
            self.refresh_radar()

    def new_shape_clicked(self):
        """Finaliza la figura en progreso (si existe) y prepara el estado para dibujar una nueva,
        sin borrar las figuras ya completadas."""
        # Guardar figura en curso si tiene puntos
        if self.drawn_points:
            self.completed_shapes.append({
                "points": list(self.drawn_points),
                "closed": self.shape_closed
            })
            self.update_coordinates_text()
        # Resetear solo el estado de dibujo actual
        self.drawn_points = []
        self.shape_closed = False
        self.circle_center = None
        self.dragging = False
        self.arc_step = 0
        self.arc_center = None
        self.arc_start_point = None
        self.refresh_radar()

    def generate_shape_clicked(self):
        text = self.txt_coordenadas.toPlainText()
        lines = text.split('\n')
        
        shapes_to_add = []
        current_shape_points = []
        all_valid = True
        
        for line in lines:
            line_stripped = line.strip()
            if not line_stripped:
                if current_shape_points:
                    shapes_to_add.append(current_shape_points)
                    current_shape_points = []
                continue
                
            match = self.regex_latlon.match(line_stripped)
            if not match:
                all_valid = False
                break
            coords = self.parse_coordinate_string(line_stripped)
            if coords:
                current_shape_points.append(coords)
            else:
                all_valid = False
                break
                
        if current_shape_points:
            shapes_to_add.append(current_shape_points)
            
        if not all_valid or not shapes_to_add:
            self.txt_coordenadas.setStyleSheet("background-color: #FFCCCC; color: #000000;")
        else:
            self.reset_coordinate_style()
            self.completed_shapes = []
            for pts in shapes_to_add:
                closed = False
                if len(pts) > 2:
                    p0 = pts[0]
                    pN = pts[-1]
                    if abs(p0[0] - pN[0]) < 1e-7 and abs(p0[1] - pN[1]) < 1e-7:
                        closed = True
                
                self.completed_shapes.append({
                    "points": pts,
                    "closed": closed
                })
            self.drawn_points = []
            self.shape_closed = False
            self.refresh_radar()
            
    def load_profile_layers(self):
        target_dir = self.get_profile_maps_dir()
        if not os.path.exists(target_dir):
            os.makedirs(target_dir, exist_ok=True)
            
        files = [f for f in os.listdir(target_dir) if f.lower().endswith('.geojson')]
        self.list_capas.clear()
        
        for f in files:
            layer_name = f
            filepath = os.path.join(target_dir, f)
            
            if layer_name not in self.map_manager.layers:
                try:
                    self.map_manager.load_geojson(filepath, name=layer_name, tipo="TACTICO")
                    if layer_name in self.map_manager.layers:
                        self.map_manager.layers[layer_name].filepath = filepath
                except Exception as e:
                    print(f"Error loading layer {f}: {e}")
                    
            visible = True
            if layer_name in self.map_manager.layers:
                visible = self.map_manager.layers[layer_name].visible
                
            item = QListWidgetItem(self.list_capas)
            row_widget = QWidget()
            row_layout = QHBoxLayout(row_widget)
            row_layout.setContentsMargins(5, 2, 5, 2)
            
            cb = QCheckBox(layer_name)
            cb.setChecked(visible)
            cb.setStyleSheet("QCheckBox { color: #E0E6ED; font-size: 8pt; }")
            cb.toggled.connect(lambda checked, ln=layer_name: self._toggle_layer(ln, checked))
            row_layout.addWidget(cb)
            
            btn_edit = QPushButton("Edit")
            btn_edit.setFixedSize(40, 18)
            btn_edit.setStyleSheet("QPushButton { padding: 0px; font-size: 7.5pt; }")
            btn_edit.clicked.connect(lambda _, ln=layer_name: self.edit_layer_coordinates(ln))
            row_layout.addWidget(btn_edit)
            
            btn_del = QPushButton("X")
            btn_del.setFixedSize(18, 18)
            btn_del.setStyleSheet("""
                QPushButton {
                    background-color: rgba(255, 51, 102, 30);
                    border: 1px solid #ff3366;
                    color: #ff3366;
                    border-radius: 9px;
                    font-weight: bold;
                    padding: 0px;
                    font-size: 7pt;
                }
                QPushButton:hover {
                    background-color: #ff3366;
                    color: white;
                }
            """)
            btn_del.clicked.connect(lambda _, ln=layer_name: self.delete_layer(ln))
            row_layout.addWidget(btn_del)
            
            row_widget.setLayout(row_layout)
            item.setSizeHint(row_widget.sizeHint())
            self.list_capas.addItem(item)
            self.list_capas.setItemWidget(item, row_widget)
            
    def _toggle_layer(self, layer_name: str, visible: bool):
        if layer_name in self.map_manager.layers:
            self.map_manager.layers[layer_name].visible = visible
            self.refresh_radar()
            
    def edit_layer_coordinates(self, layer_name):
        if layer_name not in self.map_manager.layers:
            return
        layer = self.map_manager.layers[layer_name]
        
        self.completed_shapes = []
        self.drawn_points = []
        self.shape_closed = False
        
        current_shape_points = []
        current_shape_closed = False
        
        for seg in layer.raw_segments:
            op = seg[0]
            if op == 'M':
                if current_shape_points:
                    self.completed_shapes.append({
                        "points": current_shape_points,
                        "closed": current_shape_closed
                    })
                current_shape_points = [(seg[2], seg[3])]
                current_shape_closed = False
            elif op == 'L':
                current_shape_points.append((seg[2], seg[3]))
            elif op == 'C':
                current_shape_closed = True
                
        if current_shape_points:
            self.completed_shapes.append({
                "points": current_shape_points,
                "closed": current_shape_closed
            })
            
        name_no_ext = os.path.splitext(layer_name)[0]
        self.combo_capas.setCurrentText(name_no_ext)
        
        self.update_coordinates_text()
        self.refresh_radar()
        
    def delete_layer(self, layer_name: str):
        confirm = QMessageBox.question(
            self, "Confirmar Eliminación", 
            f"¿Está seguro de que desea eliminar la capa '{layer_name}' permanentemente?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if confirm == QMessageBox.StandardButton.Yes:
            target_dir = self.get_profile_maps_dir()
            filepath = os.path.join(target_dir, layer_name)
            if os.path.exists(filepath):
                try:
                    os.remove(filepath)
                except Exception as e:
                    print(f"Error removing file {filepath}: {e}")
            if layer_name in self.map_manager.layers:
                del self.map_manager.layers[layer_name]
            self.load_profile_layers()
            self.refresh_radar()
            
    def save_current_layer(self):
        has_completed = len(self.completed_shapes) > 0
        has_drawn = len(self.drawn_points) > 0
        if not has_completed and not has_drawn:
            QMessageBox.warning(self, "Error", "No hay puntos dibujados para guardar.")
            return
            
        layer_name = self.combo_capas.currentText().strip()
        if not layer_name:
            QMessageBox.warning(self, "Error", "El nombre de la capa no puede estar vacío.")
            return
            
        layer_name = re.sub(r'[^a-zA-Z0-9__-]', '', layer_name)
        
        segments = []
        
        def add_shape_segments(points, closed):
            if not points:
                return
            lat, lon = points[0]
            segments.append(['M', layer_name, lat, lon])
            for lat, lon in points[1:]:
                segments.append(['L', layer_name, lat, lon])
            if closed:
                segments.append(['C', layer_name])
                
        for shape in self.completed_shapes:
            add_shape_segments(shape["points"], shape["closed"])
            
        if has_drawn:
            add_shape_segments(self.drawn_points, self.shape_closed)
            
        username = "Default"
        profile_manager = None
        if self.parent_window and hasattr(self.parent_window, 'profile_manager'):
            profile_manager = self.parent_window.profile_manager
            username = profile_manager.profile.get("name", "Default")
            
        try:
            # Extraer color hex del texto del combo ("Cian (#00E5FF)" → "#00E5FF")
            import re as _re
            color_text = self.combo_color.currentText()
            color_hex_match = _re.search(r'(#[0-9A-Fa-f]{6})', color_text)
            color_hex = color_hex_match.group(1) if color_hex_match else "#00E5FF"

            self.map_manager.save_map(
                name=layer_name,
                segments=segments,
                profile_name=username,
                is_general=False,
                profile_manager=profile_manager,
                color=color_hex
            )
            self.load_profile_layers()
            self.clear_drawing()
            if self.radar:
                self.map_manager.reproject_all(self.radar.proy)
                self.radar.update()
            QMessageBox.information(self, "Éxito", f"Capa '{layer_name}' guardada correctamente.")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Error al guardar la capa: {e}")
            
    def clear_drawing(self):
        self.completed_shapes = []
        self.drawn_points = []
        self.shape_closed = False
        self.circle_center = None
        self.dragging = False
        self.arc_step = 0
        self.arc_center = None
        self.arc_start_point = None
        self.txt_coordenadas.clear()
        self.refresh_radar()

    def eventFilter(self, watched, event):
        if watched == self.radar:
            is_area_tab = (self.tabs.currentIndex() == 1)
            
            if event.type() == QEvent.Type.MouseButtonPress:
                pos = event.position()
                world_coords = self.radar._screen_to_world(pos.x(), pos.y())
                if world_coords:
                    wx, wy = world_coords
                    lat, lon = self.radar.proy.xy_to_latlon(wx, wy)
                    
                    if is_area_tab:
                        is_vector = (self.combo_area_shape.currentText() == "Polígono")
                        is_circle = (self.combo_area_shape.currentText() == "Círculo")
                    else:
                        is_vector = self.btn_vector.isChecked()
                        is_circle = self.btn_circle.isChecked()
                        
                    if is_vector:
                        if event.button() == Qt.MouseButton.LeftButton:
                            self.drawn_points.append((lat, lon))
                            if is_area_tab:
                                self.update_area_coordinates_text()
                            self.refresh_radar()
                            return True
                        elif event.button() == Qt.MouseButton.RightButton:
                            if len(self.drawn_points) >= 2:
                                # Clic derecho: cierra la figura (polígono) y permite iniciar una nueva
                                self.completed_shapes.append({
                                    "points": list(self.drawn_points),
                                    "closed": len(self.drawn_points) > 2  # cerrado si >2 pts
                                })
                                self.drawn_points = []
                                self.shape_closed = False
                                if is_area_tab:
                                    self.update_area_coordinates_text()
                                else:
                                    self.update_coordinates_text()
                                self.refresh_radar()
                            return True
                            
                    elif is_circle:
                        if event.button() == Qt.MouseButton.LeftButton:
                            self.circle_center = (lat, lon)
                            self.circle_radius_nm = 0.0
                            self.dragging = True
                            self.drawn_points = []
                            self.shape_closed = False
                            self.refresh_radar()
                            return True
                            
                    elif not is_area_tab and self.btn_arc.isChecked():
                        if event.button() == Qt.MouseButton.LeftButton:
                            if self.arc_step == 0:
                                self.arc_center = (lat, lon)
                                self.arc_start_point = None
                                self.drawn_points = []
                                self.shape_closed = False
                                self.arc_step = 1
                                self.refresh_radar()
                                return True
                            elif self.arc_step == 1:
                                self.arc_start_point = (lat, lon)
                                self.arc_step = 2
                                self.refresh_radar()
                                return True
                            elif self.arc_step == 2:
                                if self.arc_center and self.arc_start_point:
                                    cx, cy = self.radar.proy.latlon_to_xy(*self.arc_center)
                                    sx, sy = self.radar.proy.latlon_to_xy(*self.arc_start_point)
                                    mx, my = self.radar.proy.latlon_to_xy(lat, lon)
                                    R = math.sqrt((sx - cx)**2 + (sy - cy)**2)
                                    start_angle = math.atan2(sy - cy, sx - cx)
                                    end_angle = math.atan2(my - cy, mx - cx)
                                    
                                    diff = (end_angle - start_angle + math.pi) % (2.0 * math.pi) - math.pi
                                    points = []
                                    for i in range(65):
                                        t = i / 64.0
                                        angle = start_angle + t * diff
                                        px = cx + R * math.cos(angle)
                                        py = cy + R * math.sin(angle)
                                        p_lat, p_lon = self.radar.proy.xy_to_latlon(px, py)
                                        points.append((p_lat, p_lon))
                                    
                                    self.completed_shapes.append({
                                        "points": points,
                                        "closed": False
                                    })
                                    self.drawn_points = []
                                    self.shape_closed = False
                                    self.update_coordinates_text()
                                    
                                self.arc_step = 0
                                self.arc_center = None
                                self.arc_start_point = None
                                self.refresh_radar()
                                return True
  
            elif event.type() == QEvent.Type.MouseMove:
                pos = event.position()
                world_coords = self.radar._screen_to_world(pos.x(), pos.y())
                if world_coords:
                    mx, my = world_coords
                    lat, lon = self.radar.proy.xy_to_latlon(mx, my)
                    
                    if is_area_tab:
                        is_circle = (self.combo_area_shape.currentText() == "Círculo")
                        is_arc = False
                    else:
                        is_circle = self.btn_circle.isChecked()
                        is_arc = self.btn_arc.isChecked()
                        
                    if is_circle and self.dragging and self.circle_center:
                        c_lat, c_lon = self.circle_center
                        cx, cy = self.radar.proy.latlon_to_xy(c_lat, c_lon)
                        
                        dx = mx - cx
                        dy = my - cy
                        R = math.sqrt(dx*dx + dy*dy)
                        
                        points = []
                        for i in range(65):
                            angle = i * 2.0 * math.pi / 64.0
                            px = cx + R * math.cos(angle)
                            py = cy + R * math.sin(angle)
                            p_lat, p_lon = self.radar.proy.xy_to_latlon(px, py)
                            points.append((p_lat, p_lon))
                            
                        self.drawn_points = points
                        self.shape_closed = True
                        
                        # Calculate radius in NM
                        from player.areas.model import haversine_nm
                        self.circle_radius_nm = haversine_nm(c_lat, c_lon, lat, lon)
                        
                        if is_area_tab:
                            self.update_area_coordinates_text()
                            self.spin_area_radius.setValue(self.circle_radius_nm)
                            
                        self.refresh_radar()
                        return True
                        
                    elif not is_area_tab and is_arc:
                        if self.arc_step == 1 and self.arc_center:
                            self.drawn_points = [self.arc_center, (lat, lon)]
                            self.shape_closed = False
                            self.refresh_radar()
                            return True
                        elif self.arc_step == 2 and self.arc_center and self.arc_start_point:
                            cx, cy = self.radar.proy.latlon_to_xy(*self.arc_center)
                            sx, sy = self.radar.proy.latlon_to_xy(*self.arc_start_point)
                            R = math.sqrt((sx - cx)**2 + (sy - cy)**2)
                            start_angle = math.atan2(sy - cy, sx - cx)
                            end_angle = math.atan2(my - cy, mx - cx)
                            
                            diff = (end_angle - start_angle + math.pi) % (2.0 * math.pi) - math.pi
                            points = []
                            for i in range(65):
                                tz = i / 64.0
                                angle = start_angle + tz * diff
                                px = cx + R * math.cos(angle)
                                py = cy + R * math.sin(angle)
                                p_lat, p_lon = self.radar.proy.xy_to_latlon(px, py)
                                points.append((p_lat, p_lon))
                                
                            self.drawn_points = points
                            self.shape_closed = False
                            self.refresh_radar()
                            return True
                             
            elif event.type() == QEvent.Type.MouseButtonRelease:
                if is_area_tab:
                    is_circle = (self.combo_area_shape.currentText() == "Círculo")
                else:
                    is_circle = self.btn_circle.isChecked()
                    
                if is_circle and self.dragging:
                    self.dragging = False
                    if self.drawn_points:
                        self.completed_shapes.append({
                            "points": list(self.drawn_points),
                            "closed": True
                        })
                        self.drawn_points = []
                        self.shape_closed = False
                        if is_area_tab:
                            self.update_area_coordinates_text()
                        else:
                            self.update_coordinates_text()
                    self.refresh_radar()
                    return True
                    
        return super().eventFilter(watched, event)

    def _draw_arc_helpers_with_painter(self, painter, inv_z):
        if self.arc_center:
            cx, cy = self.radar.proy.latlon_to_xy(*self.arc_center)
            if is_valid_coord(cx, cy):
                painter.setPen(QPen(QColor("#00E5FF"), 1.5 * inv_z, Qt.PenStyle.DashLine))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawEllipse(QPointF(cx, cy), 6.0 * inv_z, 6.0 * inv_z)
                # Draw center crosshair
                painter.drawLine(QPointF(cx - 10.0 * inv_z, cy), QPointF(cx + 10.0 * inv_z, cy))
                painter.drawLine(QPointF(cx, cy - 10.0 * inv_z), QPointF(cx, cy + 10.0 * inv_z))
                
        if self.arc_start_point:
            sx, sy = self.radar.proy.latlon_to_xy(*self.arc_start_point)
            if is_valid_coord(sx, sy):
                painter.setPen(QPen(QColor("#FFA500"), 1.5 * inv_z, Qt.PenStyle.SolidLine))
                painter.setBrush(QBrush(QColor("#FFA500")))
                painter.drawEllipse(QPointF(sx, sy), 4.0 * inv_z, 4.0 * inv_z)
        
    def custom_radar_paint_event(self, event):
        self.original_paint_event(event)
        
        has_completed = len(self.completed_shapes) > 0
        has_drawn = len(self.drawn_points) > 0
        has_arc_helpers = self.btn_arc.isChecked() and (self.arc_center or self.arc_start_point)
        
        if not (has_completed or has_drawn or has_arc_helpers):
            return
            
        painter = QPainter(self.radar)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        w, h = self.radar.width(), self.radar.height()
        z = self.radar.zoom_factor
        inv_z = 1.0 / z if z > 0 else 1.0
        
        painter.save()
        center_x = w / 2.0 + self.radar.pan_x
        center_y = h / 2.0 + self.radar.pan_y
        painter.translate(center_x, center_y)
        painter.scale(z, -z)
        
        # Color y estilos dinámicos
        is_area_tab = (self.tabs.currentIndex() == 1)
        if is_area_tab:
            from player.areas.render import AREA_COLORS
            kind_idx = self.combo_area_tipo.currentIndex()
            kind = "R" if kind_idx == 0 else "P" if kind_idx == 1 else "D"
            pen_color = QColor(AREA_COLORS.get(kind, "#39C5FF"))
            pen_style = Qt.PenStyle.SolidLine
            pen_width = 2
        else:
            color_name = self.combo_color.currentText()
            pen_color = COLOR_MAP.get(color_name, QColor("#00E5FF"))
            
            style_name = self.combo_style.currentText()
            pen_style = STYLE_MAP.get(style_name, Qt.PenStyle.SolidLine)
            
            width_name = self.combo_width.currentText()
            pen_width = WIDTH_MAP.get(width_name, 2)
        
        def draw_single_shape(points, closed):
            if not points:
                return
            poly = QPolygonF()
            for lat, lon in points:
                wx, wy = self.radar.proy.latlon_to_xy(lat, lon)
                if is_valid_coord(wx, wy):
                    poly.append(QPointF(wx, wy))
            
            if poly.isEmpty():
                return
                
            pen = QPen(pen_color, pen_width * inv_z, pen_style)
            painter.setPen(pen)
            
            if closed:
                fill_color = QColor(pen_color)
                fill_color.setAlpha(40)
                painter.setBrush(QBrush(fill_color))
                painter.drawPolygon(poly)
            else:
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawPolyline(poly)
                
            sz = 4.0 * inv_z
            # Vértices con el mismo color de línea seleccionado
            dot_fill_color = QColor(pen_color)
            dot_fill_color.setAlpha(200)
            painter.setPen(QPen(dot_fill_color, inv_z))
            painter.setBrush(QBrush(dot_fill_color))
            for pt in poly:
                painter.drawEllipse(pt, sz, sz)
                
        for shape in self.completed_shapes:
            draw_single_shape(shape["points"], shape["closed"])
            
        if has_drawn:
            draw_single_shape(self.drawn_points, self.shape_closed)
            
        if not is_area_tab and self.btn_arc.isChecked():
            self._draw_arc_helpers_with_painter(painter, inv_z)
            
        painter.restore()
        painter.end()
 
    def closeEvent(self, event):
        if self.radar:
            self.radar.removeEventFilter(self)
            if hasattr(self, 'original_paint_event'):
                self.radar.paintEvent = self.original_paint_event
            self.radar.update()
        super().closeEvent(event)

    # --- CRUD MÉTODOS DE ÁREAS (TAB 2) ---
    def on_tab_changed(self, index):
        self.clear_drawing()

    def on_area_shape_changed(self):
        shape_text = self.combo_area_shape.currentText()
        self.spin_area_radius.setEnabled(shape_text == "Círculo")
        self.completed_shapes = []
        self.drawn_points = []
        self.shape_closed = False
        self.circle_center = None
        self.circle_radius_nm = 0.0
        self.txt_area_coords.clear()
        self.refresh_radar()

    def update_area_coordinates_text(self):
        dms_lines = []
        if self.drawn_points:
            for lat, lon in self.drawn_points:
                dms_lines.append(decimal_to_dms(lat, lon))
        elif self.completed_shapes:
            for shape in self.completed_shapes:
                for lat, lon in shape["points"]:
                    dms_lines.append(decimal_to_dms(lat, lon))
        self.txt_area_coords.setPlainText("\n".join(dms_lines))

    def clear_area_form(self):
        self.txt_area_name.clear()
        self.combo_area_tipo.setCurrentIndex(0)
        self.spin_area_lower.setValue(0)
        self.spin_area_upper.setValue(999)
        self.combo_area_shape.setCurrentIndex(0)
        self.spin_area_radius.setValue(5.0)
        self.txt_area_coords.clear()
        self.rad_area_perm.setChecked(True)
        self.chk_area_enabled.setChecked(True)
        self.time_area_desde.setTime(time(0, 0))
        self.time_area_hasta.setTime(time(23, 59))
        for chk in self.chk_days:
            chk.setChecked(False)
        self.clear_drawing()

    def load_areas_list(self):
        self.combo_sel_area.blockSignals(True)
        self.combo_sel_area.clear()
        self.loaded_control_areas = []

        # Cargar áreas de la base de datos
        from player import atm_db
        db_areas = []
        if atm_db.available():
            db_areas = atm_db.restricted_airspaces()
            
        # Cargar áreas de usuario del store
        from player.areas import store as _store
        username = "Default"
        if self.parent_window and hasattr(self.parent_window, 'profile_manager'):
            username = self.parent_window.profile_manager.profile.get("name", "Default")
        user_areas = _store.cargar_todas(username)

        # Ordenar áreas
        user_areas = sorted(user_areas, key=lambda a: a.name)
        db_areas = sorted(db_areas, key=lambda a: a.name)

        from player.areas.model import KIND_LABEL

        # Agregar áreas de usuario
        for area in user_areas:
            self.loaded_control_areas.append(area)
            self.combo_sel_area.addItem(f"{area.name} ({KIND_LABEL.get(area.kind, area.kind)}/Usr)")

        # Agregar áreas de la base de datos
        for area in db_areas:
            self.loaded_control_areas.append(area)
            self.combo_sel_area.addItem(f"{area.name} ({KIND_LABEL.get(area.kind, area.kind)}/DB)")

        self.combo_sel_area.blockSignals(False)
        
        # Trigger actualizacion del estado de botones para el elemento seleccionado
        self.on_selected_area_changed(self.combo_sel_area.currentIndex())

    def on_selected_area_changed(self, index):
        if index < 0 or index >= len(self.loaded_control_areas):
            self.chk_sel_area_visible.setEnabled(False)
            self.chk_sel_area_visible.setChecked(False)
            self.btn_edit_sel_area.setEnabled(False)
            self.btn_del_sel_area.setEnabled(False)
            return

        area = self.loaded_control_areas[index]
        self.btn_edit_sel_area.setEnabled(True)
        self.btn_del_sel_area.setEnabled(True)

        if area.origen == "usuario":
            self.chk_sel_area_visible.setEnabled(True)
            self.chk_sel_area_visible.blockSignals(True)
            layer_name = f"AREA::{area.name}"
            visible = layer_name in self.map_manager.layers
            self.chk_sel_area_visible.setChecked(visible)
            self.chk_sel_area_visible.blockSignals(False)
        else:
            self.chk_sel_area_visible.setEnabled(False)
            self.chk_sel_area_visible.blockSignals(True)
            self.chk_sel_area_visible.setChecked(False)
            self.chk_sel_area_visible.blockSignals(False)

    def toggle_selected_user_area_visibility(self, checked):
        index = self.combo_sel_area.currentIndex()
        if 0 <= index < len(self.loaded_control_areas):
            area = self.loaded_control_areas[index]
            if area.origen == "usuario":
                self.toggle_user_area_visibility(area, checked)

    def edit_selected_area(self):
        index = self.combo_sel_area.currentIndex()
        if 0 <= index < len(self.loaded_control_areas):
            area = self.loaded_control_areas[index]
            self.edit_area(area)

    def delete_selected_area(self):
        index = self.combo_sel_area.currentIndex()
        if 0 <= index < len(self.loaded_control_areas):
            area = self.loaded_control_areas[index]
            self.delete_area_action(area)

    def toggle_user_area_visibility(self, area, checked):
        layer_name = f"AREA::{area.name}"
        if checked:
            from player.areas import render as _ar
            segs = _ar.area_segments([area])
            self.map_manager.add_layer(layer_name, segs, "TACTICO")
            if layer_name in self.map_manager.layers:
                self.map_manager.layers[layer_name].color = _ar.AREA_COLORS.get(area.kind, "#39C5FF")
            if getattr(self.radar, 'proy', None) is not None:
                self.map_manager.reproject_all(self.radar.proy)
        else:
            self.map_manager.layers.pop(layer_name, None)
        self.refresh_radar()

    def edit_area(self, area):
        # Resetear estado de dibujo
        self.completed_shapes = []
        self.drawn_points = []
        self.shape_closed = False
        
        # Rellenar campos del formulario
        self.txt_area_name.setText(area.name)
        
        kind_map = {"R": 0, "P": 1, "D": 2}
        self.combo_area_tipo.setCurrentIndex(kind_map.get(area.kind, 0))
        
        self.spin_area_lower.setValue(area.lower_fl)
        self.spin_area_upper.setValue(area.upper_fl)
        
        shape_text = "Círculo" if area.shape == "circle" else "Polígono"
        self.combo_area_shape.setCurrentText(shape_text)
        
        if area.shape == "circle":
            self.spin_area_radius.setValue(area.radius_nm or 5.0)
            self.circle_center = area.center
            self.circle_radius_nm = area.radius_nm
            if area.center:
                self.txt_area_coords.setPlainText(decimal_to_dms(area.center[0], area.center[1]))
        else:
            self.circle_center = None
            self.circle_radius_nm = 0.0
            dms_pts = [decimal_to_dms(lat, lon) for lat, lon in area.vertices]
            self.txt_area_coords.setPlainText("\n".join(dms_pts))
            
        # Vigencia
        v = area.vigencia
        if v.permanente:
            self.rad_area_perm.setChecked(True)
        else:
            self.rad_area_temp.setChecked(True)
            self.chk_area_enabled.setChecked(v.habilitada)
            self.time_area_desde.setTime(v.desde if v.desde else time(0, 0))
            self.time_area_hasta.setTime(v.hasta if v.hasta else time(23, 59))
            
            # Días
            for i, chk in enumerate(self.chk_days):
                chk.setChecked(i in v.dias)
                
        # Cargar geometría en completed_shapes para previsualización
        if area.shape == "circle" and area.center:
            self.completed_shapes = [{
                "points": area.polilinea(),
                "closed": True
            }]
        elif area.shape == "poly" and area.vertices:
            self.completed_shapes = [{
                "points": list(area.vertices),
                "closed": True
            }]
            
        self.refresh_radar()

    def delete_area_action(self, area):
        confirm = QMessageBox.question(
            self, "Confirmar Eliminación", 
            f"¿Está seguro de que desea eliminar el área '{area.name}' permanentemente?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if confirm == QMessageBox.StandardButton.Yes:
            if area.origen == "usuario":
                username = "Default"
                if self.parent_window and hasattr(self.parent_window, 'profile_manager'):
                    username = self.parent_window.profile_manager.profile.get("name", "Default")
                from player.areas import store as _store
                _store.borrar(area.name, username)
                
                # Quitar capa de visualización
                self.map_manager.layers.pop(f"AREA::{area.name}", None)
                
                # Actualizar listas
                self.load_areas_list()
                if self.parent_window:
                    self.parent_window.user_areas = _store.cargar_todas(username)
                    self.parent_window.radar.user_areas = self.parent_window.user_areas
                self.refresh_radar()
            else:
                from player import atm_db
                atm_db.delete_area(area.name)
                
                # Actualizar lista y capas de menú de MainWindow
                self.load_areas_list()
                if self.parent_window:
                    self.parent_window._toggle_area_layer(area.kind, False)
                    self.parent_window._toggle_area_layer(area.kind, True)
                self.refresh_radar()

    def save_area(self):
        name = self.txt_area_name.text().strip()
        if not name:
            QMessageBox.warning(self, "Error", "El nombre del área no puede estar vacío.")
            return
            
        kind_idx = self.combo_area_tipo.currentIndex()
        kind = "R" if kind_idx == 0 else "P" if kind_idx == 1 else "D"
        
        lower_fl = self.spin_area_lower.value()
        upper_fl = self.spin_area_upper.value()
        shape_str = "circle" if self.combo_area_shape.currentText() == "Círculo" else "poly"
        
        coord_text = self.txt_area_coords.toPlainText().strip()
        if not coord_text:
            QMessageBox.warning(self, "Error", "Debe ingresar coordenadas lat/lon (DMS).")
            return
            
        lines = [l.strip() for l in coord_text.split("\n") if l.strip()]
        
        vertices = []
        center = None
        radius_nm = None
        
        if shape_str == "poly":
            for line in lines:
                coords = self.parse_coordinate_string(line)
                if not coords:
                    QMessageBox.warning(self, "Error", f"Coordenada inválida: '{line}'")
                    return
                vertices.append(coords)
            if len(vertices) < 3:
                QMessageBox.warning(self, "Error", "Un polígono debe tener al menos 3 vértices.")
                return
        else:
            coords = self.parse_coordinate_string(lines[0])
            if not coords:
                QMessageBox.warning(self, "Error", f"Centro de círculo inválido: '{lines[0]}'")
                return
            center = coords
            radius_nm = self.spin_area_radius.value()
            if radius_nm <= 0:
                QMessageBox.warning(self, "Error", "El radio del círculo debe ser mayor que 0.")
                return
                
        is_perm = self.rad_area_perm.isChecked()
        if is_perm:
            from player.areas.model import Vigencia as _Vigencia
            vig = _Vigencia(permanente=True)
        else:
            hab = self.chk_area_enabled.isChecked()
            qdesde = self.time_area_desde.time()
            qhasta = self.time_area_hasta.time()
            from datetime import time as dt_time
            desde = dt_time(qdesde.hour(), qdesde.minute())
            hasta = dt_time(qhasta.hour(), qhasta.minute())
            
            dias = set()
            for i, chk in enumerate(self.chk_days):
                if chk.isChecked():
                    dias.add(i)
                    
            from player.areas.model import Vigencia as _Vigencia
            vig = _Vigencia(permanente=False, habilitada=hab, dias=dias, desde=desde, hasta=hasta)
            
        from player.areas.model import Area as _Area
        area = _Area(
            name=name, kind=kind, shape=shape_str,
            lower_fl=lower_fl, upper_fl=upper_fl,
            vertices=vertices, center=center, radius_nm=radius_nm,
            vigencia=vig, origen="db" if is_perm else "usuario"
        )
        
        username = "Default"
        if self.parent_window and hasattr(self.parent_window, 'profile_manager'):
            username = self.parent_window.profile_manager.profile.get("name", "Default")
            
        try:
            if is_perm:
                from player import atm_db
                atm_db.write_area(area)
                
                # Borrar del store si existiera como temporal de usuario
                from player.areas import store as _store
                _store.borrar(name, username)
                
                # Quitar capa de usuario si estuviera activa
                self.map_manager.layers.pop(f"AREA::{name}", None)
                
                # Refrescar capas de base de datos en MainWindow
                if self.parent_window:
                    self.parent_window._toggle_area_layer(kind, False)
                    self.parent_window._toggle_area_layer(kind, True)
            else:
                from player.areas import store as _store
                _store.guardar(area, username)
                
                # Quitar de la base de datos si existiera como permanente
                from player import atm_db
                atm_db.delete_area(name)
                
                # Si está habilitada, actualizar la capa de mapa
                layer_name = f"AREA::{name}"
                if hab:
                    from player.areas import render as _ar
                    segs = _ar.area_segments([area])
                    self.map_manager.add_layer(layer_name, segs, "TACTICO")
                    if layer_name in self.map_manager.layers:
                        self.map_manager.layers[layer_name].color = _ar.AREA_COLORS.get(kind, "#39C5FF")
                    if getattr(self.radar, 'proy', None) is not None:
                        self.map_manager.reproject_all(self.radar.proy)
                else:
                    self.map_manager.layers.pop(layer_name, None)
                    
            # Actualizar MainWindow user_areas
            if self.parent_window:
                from player.areas import store as _store
                self.parent_window.user_areas = _store.cargar_todas(username)
                self.parent_window.radar.user_areas = self.parent_window.user_areas
                
            self.load_areas_list()
            self.clear_area_form()
            QMessageBox.information(self, "Éxito", f"Área '{name}' guardada correctamente.")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Error al guardar el área: {e}")

# Alias for backwards compatibility with main_window.py
MapEditorDialog = LMG_Dialog
