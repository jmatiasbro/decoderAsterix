import os
from typing import Dict, Any, List, Set
from PyQt6.QtWidgets import (
    QDialog, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QGroupBox, QCheckBox, QRadioButton, QLineEdit, QSpinBox,
    QDoubleSpinBox, QPushButton, QLabel, QButtonGroup,
    QScrollArea, QListWidget, QListWidgetItem, QSizePolicy
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont, QColor

class LabelFilterDialog(QDialog):
    """
    Diálogo de Filtro de Etiquetas táctico con estética neón cian/verde.
    Permite seleccionar qué campos se imprimen en el Data Block de los plots,
    así como elegir su orientación espacial (NO, NE, SO, SE) y forma de selección.
    """
    config_changed = pyqtSignal(dict)

    def __init__(self, current_config: dict, available_fields: set = None, parent=None):
        super().__init__(parent)
        self.config = current_config.copy()
        self.available_fields = available_fields
        
        self.setWindowTitle("Filtro de Etiquetas")
        self.resize(460, 320)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        
        self._setup_style()
        self._setup_ui()
        self._load_config()

    def _setup_style(self):
        self.setStyleSheet("""
            QDialog {
                background-color: #0E131F;
                border: 2px solid #00E5FF;
                border-radius: 8px;
            }
            QGroupBox {
                border: 1px solid #4B5263;
                border-radius: 6px;
                margin-top: 15px;
                padding-top: 10px;
                color: #00E5FF;
                font-family: 'Segoe UI', sans-serif;
                font-size: 9pt;
                font-weight: bold;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 3px 0 3px;
            }
            QLabel {
                color: #FFFFFF;
                font-family: 'Segoe UI', sans-serif;
                font-size: 9pt;
            }
            QCheckBox, QRadioButton {
                color: #E0E6ED;
                font-family: 'Segoe UI', sans-serif;
                font-size: 9pt;
            }
            QCheckBox::indicator, QRadioButton::indicator {
                width: 14px;
                height: 14px;
                border: 1px solid #00E5FF;
                background-color: #1A2130;
                border-radius: 3px;
            }
            QCheckBox::indicator:checked, QRadioButton::indicator:checked {
                background-color: #00E5FF;
                border: 1px solid #00E5FF;
            }
            QPushButton {
                background-color: #121824;
                border: 1px solid #00E5FF;
                border-radius: 4px;
                color: #00E5FF;
                font-family: 'Segoe UI', sans-serif;
                font-size: 9pt;
                font-weight: bold;
                padding: 5px 12px;
            }
            QPushButton:hover {
                border: 1px solid #39FF14;
                color: #39FF14;
                background-color: rgba(57, 255, 20, 20);
            }
            QPushButton:pressed {
                background-color: rgba(57, 255, 20, 50);
            }
        """)

    def _setup_ui(self):
        layout_main = QVBoxLayout(self)
        layout_main.setContentsMargins(15, 10, 15, 15)
        
        # Grid superior para Campos y la derecha
        layout_h = QHBoxLayout()
        
        # 1. Campos
        group_campos = QGroupBox("Campos")
        grid_campos = QGridLayout(group_campos)
        grid_campos.setContentsMargins(10, 15, 10, 10)
        
        self.chks = {}
        fields = [
            ("codigo_a", "Código A"),
            ("numero_mensaje", "Número Mensaje"),
            ("codigo_c", "Código C"),
            ("direccion_aeronave", "Dirección Aeronave"),
            ("numero_respuestas", "Número Respuestas"),
            ("velocidad", "Velocidad"),
            ("hora_utc", "Hora UTC"),
            ("numero_pista", "Número de Pista"),
            ("identific_aeronave", "Identific. Aeronave"),
            ("altitud_adsb", "Altitud ADSB"),
            ("cat_emisor_adsb", "Cat. Emisor ADS-B"),
            ("veloc_vertic_adsb", "Veloc. Vertic. ADS-B"),
            ("rho_theta", "RHO / THETA")
        ]
        
        for i, (key, label) in enumerate(fields):
            chk = QCheckBox(label)
            self.chks[key] = chk
            
            # Deshabilitar control si no hay telemetría de este tipo en la captura activa
            if self.available_fields is not None and key not in self.available_fields:
                chk.setEnabled(False)
                chk.setChecked(False)
                chk.setToolTip("No hay información disponible para este campo en la captura actual.")
                
            row = i // 2
            col = i % 2
            grid_campos.addWidget(chk, row, col)
            chk.stateChanged.connect(self._on_change)
            
        layout_h.addWidget(group_campos, stretch=3)
        
        # Lado derecho: Orientación y Selección Ratón
        layout_derecha = QVBoxLayout()
        
        # 2. Orientación
        group_orientacion = QGroupBox("Orientación")
        grid_or = QGridLayout(group_orientacion)
        grid_or.setContentsMargins(10, 15, 10, 10)
        
        self.btn_group_or = QButtonGroup(self)
        self.rb_no = QRadioButton("NO")
        self.rb_ne = QRadioButton("NE")
        self.rb_so = QRadioButton("SO")
        self.rb_se = QRadioButton("SE")
        
        self.btn_group_or.addButton(self.rb_no, 0)
        self.btn_group_or.addButton(self.rb_ne, 1)
        self.btn_group_or.addButton(self.rb_so, 2)
        self.btn_group_or.addButton(self.rb_se, 3)
        
        grid_or.addWidget(self.rb_no, 0, 0)
        grid_or.addWidget(self.rb_ne, 0, 1)
        grid_or.addWidget(self.rb_so, 1, 0)
        grid_or.addWidget(self.rb_se, 1, 1)
        
        self.rb_no.toggled.connect(self._on_change)
        self.rb_ne.toggled.connect(self._on_change)
        self.rb_so.toggled.connect(self._on_change)
        self.rb_se.toggled.connect(self._on_change)
        
        layout_derecha.addWidget(group_orientacion)
        
        # 3. Selección Ratón
        group_seleccion = QGroupBox("Seleccion Raton")
        v_sel = QVBoxLayout(group_seleccion)
        v_sel.setContentsMargins(10, 15, 10, 10)
        
        self.chk_sel_codigo = QCheckBox("por Código A")
        self.chk_sel_posicion = QCheckBox("por Posición")
        v_sel.addWidget(self.chk_sel_codigo)
        v_sel.addWidget(self.chk_sel_posicion)
        
        self.chk_sel_codigo.stateChanged.connect(self._on_change)
        self.chk_sel_posicion.stateChanged.connect(self._on_change)
        
        layout_derecha.addWidget(group_seleccion)
        layout_h.addLayout(layout_derecha, stretch=2)
        
        layout_main.addLayout(layout_h)
        
        # Botón Cerrar
        layout_btn = QHBoxLayout()
        layout_btn.addStretch()
        self.btn_cerrar = QPushButton("Cerrar")
        self.btn_cerrar.clicked.connect(self.accept)
        layout_btn.addWidget(self.btn_cerrar)
        layout_main.addLayout(layout_btn)

    def _load_config(self):
        # Campos
        for key, chk in self.chks.items():
            val = self.config.get(key, True)
            chk.setChecked(val)
            
        # Orientación
        orient = self.config.get("orientacion", "NE")
        if orient == "NO": self.rb_no.setChecked(True)
        elif orient == "SO": self.rb_so.setChecked(True)
        elif orient == "SE": self.rb_se.setChecked(True)
        else: self.rb_ne.setChecked(True)
        
        # Selección Ratón
        self.chk_sel_codigo.setChecked(self.config.get("sel_por_codigo_a", True))
        self.chk_sel_posicion.setChecked(self.config.get("sel_por_posicion", False))

    def _on_change(self):
        # Actualizar config
        for key, chk in self.chks.items():
            self.config[key] = chk.isChecked()
            
        if self.rb_no.isChecked(): self.config["orientacion"] = "NO"
        elif self.rb_so.isChecked(): self.config["orientacion"] = "SO"
        elif self.rb_se.isChecked(): self.config["orientacion"] = "SE"
        else: self.config["orientacion"] = "NE"
        
        self.config["sel_por_codigo_a"] = self.chk_sel_codigo.isChecked()
        self.config["sel_por_posicion"] = self.chk_sel_posicion.isChecked()
        
        self.config_changed.emit(self.config)


class RadarDataFilterDialog(QDialog):
    """
    Diálogo de Filtro de Datos Radar con estética neón cian/verde.
    Permite filtrar los plots en base a Squawk, tipos de códigos,
    rangos geográficos (Distancia, Acimut, Altura), SAC/SIC, y categorías de informes.
    """
    filter_applied = pyqtSignal(dict)

    def __init__(self, current_config: dict, total_messages: int, selected_messages: int,
                 sensors_list: list = None, parent=None):
        """sensors_list: lista de tuplas (sac, sic, name) de los sensores disponibles en la captura."""
        super().__init__(parent)
        self.config = current_config.copy()
        self.total_messages = total_messages
        self.selected_messages = selected_messages
        self.sensors_list = sensors_list or []  # [(sac, sic, name), ...]
        
        self.setWindowTitle("Filtro de Datos Radar")
        self.resize(560, 560)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        
        self._setup_style()
        self._setup_ui()
        self._load_config()
        self.actualizar_contador(selected_messages, total_messages)

    def _setup_style(self):
        self.setStyleSheet("""
            QDialog {
                background-color: #0E131F;
                border: 2px solid #00E5FF;
                border-radius: 8px;
            }
            QGroupBox {
                border: 1px solid #4B5263;
                border-radius: 6px;
                margin-top: 12px;
                padding-top: 10px;
                color: #00E5FF;
                font-family: 'Segoe UI', sans-serif;
                font-size: 8.5pt;
                font-weight: bold;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 3px 0 3px;
            }
            QLabel {
                color: #FFFFFF;
                font-family: 'Segoe UI', sans-serif;
                font-size: 8.5pt;
            }
            QCheckBox {
                color: #E0E6ED;
                font-family: 'Segoe UI', sans-serif;
                font-size: 8.5pt;
            }
            QCheckBox::indicator {
                width: 13px;
                height: 13px;
                border: 1px solid #00E5FF;
                background-color: #1A2130;
                border-radius: 3px;
            }
            QCheckBox::indicator:checked {
                background-color: #00E5FF;
                border: 1px solid #00E5FF;
            }
            QLineEdit, QSpinBox, QDoubleSpinBox {
                background-color: #1A2130;
                border: 1px solid #4B5263;
                border-radius: 4px;
                color: #FFFFFF;
                font-family: 'Monospace', sans-serif;
                font-size: 9pt;
                padding: 2px;
            }
            QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus {
                border: 1px solid #39FF14;
            }
            QPushButton {
                background-color: #121824;
                border: 1px solid #00E5FF;
                border-radius: 4px;
                color: #00E5FF;
                font-family: 'Segoe UI', sans-serif;
                font-size: 9pt;
                font-weight: bold;
                padding: 6px 16px;
            }
            QPushButton:hover {
                border: 1px solid #39FF14;
                color: #39FF14;
                background-color: rgba(57, 255, 20, 20);
            }
            QPushButton:pressed {
                background-color: rgba(57, 255, 20, 50);
            }
        """)

    def _setup_ui(self):
        layout_main = QVBoxLayout(self)
        layout_main.setContentsMargins(15, 10, 15, 15)
        
        # Grid superior principal
        layout_grid = QGridLayout()
        
        # 1. Códigos Seleccionados (Arriba Izquierda)
        group_cods = QGroupBox("Códigos Seleccionados")
        l_cods = QVBoxLayout(group_cods)
        l_cods.setContentsMargins(10, 15, 10, 10)
        
        l_inputs = QHBoxLayout()
        self.txt_codes = []
        for _ in range(4):
            txt = QLineEdit()
            txt.setMaxLength(4)
            txt.setFixedWidth(50)
            txt.setAlignment(Qt.AlignmentFlag.AlignCenter)
            l_inputs.addWidget(txt)
            self.txt_codes.append(txt)
            
        self.chk_filtro_codes = QCheckBox("Habilitar Filtro Códigos")
        l_cods.addLayout(l_inputs)
        l_cods.addWidget(self.chk_filtro_codes)
        layout_grid.addWidget(group_cods, 0, 0)
        
        # 2. Tipo de Códigos (Arriba Derecha)
        group_tipo_cods = QGroupBox("Tipo de Códigos")
        grid_tipo_cods = QGridLayout(group_tipo_cods)
        grid_tipo_cods.setContentsMargins(10, 15, 10, 10)
        
        grid_tipo_cods.addWidget(QLabel(""), 0, 0)
        grid_tipo_cods.addWidget(QLabel("A"), 0, 1, Qt.AlignmentFlag.AlignCenter)
        grid_tipo_cods.addWidget(QLabel("C"), 0, 2, Qt.AlignmentFlag.AlignCenter)
        
        self.chks_codes = {}
        rows = [
            ("todos", "Todos"),
            ("validos", "Validos"),
            ("invalidos", "Invalidos"),
            ("ausentes", "Ausentes")
        ]
        for i, (key, label) in enumerate(rows):
            grid_tipo_cods.addWidget(QLabel(label), i + 1, 0)
            chk_a = QCheckBox()
            chk_c = QCheckBox()
            self.chks_codes[f"a_{key}"] = chk_a
            self.chks_codes[f"c_{key}"] = chk_c
            grid_tipo_cods.addWidget(chk_a, i + 1, 1, Qt.AlignmentFlag.AlignCenter)
            grid_tipo_cods.addWidget(chk_c, i + 1, 2, Qt.AlignmentFlag.AlignCenter)
            
        # Checkboxes extra de tipo de códigos
        v_extra = QVBoxLayout()
        v_extra.setSpacing(2)
        self.chks_extra_cods = {}
        extra_keys = [
            ("todos_extra", "Todos"),
            ("spi", "SPI"),
            ("emx", "EMx"),
            ("cal", "CAL"),
            ("nocal", "NoCAL"),
            ("cmb", "CMB"),
            ("nocmb", "NoCMB")
        ]
        for key, label in extra_keys:
            chk = QCheckBox(label)
            self.chks_extra_cods[key] = chk
            v_extra.addWidget(chk)
            
        grid_tipo_cods.addLayout(v_extra, 0, 3, 5, 1)
        layout_grid.addWidget(group_tipo_cods, 0, 1)
        
        # 3. Rangos (Centro Izquierda)
        group_rangos = QGroupBox("Rangos")
        grid_rangos = QGridLayout(group_rangos)
        grid_rangos.setContentsMargins(10, 15, 10, 10)
        
        grid_rangos.addWidget(QLabel("Inferior"), 0, 1, Qt.AlignmentFlag.AlignCenter)
        grid_rangos.addWidget(QLabel("Superior"), 0, 2, Qt.AlignmentFlag.AlignCenter)
        
        # Distancia
        grid_rangos.addWidget(QLabel("Distancia"), 1, 0)
        self.sp_dist_inf = QDoubleSpinBox()
        self.sp_dist_inf.setRange(0, 500)
        self.sp_dist_sup = QDoubleSpinBox()
        self.sp_dist_sup.setRange(0, 500)
        grid_rangos.addWidget(self.sp_dist_inf, 1, 1)
        grid_rangos.addWidget(self.sp_dist_sup, 1, 2)
        
        # Acimut
        grid_rangos.addWidget(QLabel("Acimut"), 2, 0)
        self.sp_az_inf = QSpinBox()
        self.sp_az_inf.setRange(0, 360)
        self.sp_az_sup = QSpinBox()
        self.sp_az_sup.setRange(0, 360)
        grid_rangos.addWidget(self.sp_az_inf, 2, 1)
        grid_rangos.addWidget(self.sp_az_sup, 2, 2)
        
        # Altura
        grid_rangos.addWidget(QLabel("Altura"), 3, 0)
        self.sp_alt_inf = QSpinBox()
        self.sp_alt_inf.setRange(-9999, 99999)
        self.sp_alt_sup = QSpinBox()
        self.sp_alt_sup.setRange(-9999, 99999)
        grid_rangos.addWidget(self.sp_alt_inf, 3, 1)
        grid_rangos.addWidget(self.sp_alt_sup, 3, 2)
        
        # Mensajes
        grid_rangos.addWidget(QLabel("Mensajes"), 4, 0)
        self.sp_msg_inf = QSpinBox()
        self.sp_msg_inf.setRange(1, 9999999)
        self.sp_msg_sup = QSpinBox()
        self.sp_msg_sup.setRange(1, 9999999)
        grid_rangos.addWidget(self.sp_msg_inf, 4, 1)
        grid_rangos.addWidget(self.sp_msg_sup, 4, 2)
        
        # ID Cat 21
        grid_rangos.addWidget(QLabel("ID Cat 21"), 5, 0)
        self.txt_id21_inf = QLineEdit()
        self.txt_id21_inf.setMaxLength(6)
        self.txt_id21_sup = QLineEdit()
        self.txt_id21_sup.setMaxLength(6)
        grid_rangos.addWidget(self.txt_id21_inf, 5, 1)
        grid_rangos.addWidget(self.txt_id21_sup, 5, 2)
        
        layout_grid.addWidget(group_rangos, 1, 0)
        
        # 4. Tipo de Informes (Centro Derecha)
        group_informes = QGroupBox("Tipo de Informes")
        grid_inf = QGridLayout(group_informes)
        grid_inf.setContentsMargins(10, 15, 10, 10)
        
        self.chks_inf = {
            "plots_secun": QCheckBox("Plots Secun."),
            "plots_prim": QCheckBox("Plots Prim."),
            "pistas_secun": QCheckBox("Pistas Secun."),
            "pistas_prim": QCheckBox("Pistas Prim."),
            "servicio": QCheckBox("Servicio"),
            "meteos": QCheckBox("Meteos"),
            "ads_b": QCheckBox("ADS-B")
        }
        
        grid_inf.addWidget(self.chks_inf["plots_secun"], 0, 0)
        grid_inf.addWidget(self.chks_inf["plots_prim"], 0, 1)
        grid_inf.addWidget(self.chks_inf["pistas_secun"], 1, 0)
        grid_inf.addWidget(self.chks_inf["pistas_prim"], 1, 1)
        grid_inf.addWidget(self.chks_inf["servicio"], 2, 0)
        grid_inf.addWidget(self.chks_inf["meteos"], 2, 1)
        grid_inf.addWidget(self.chks_inf["ads_b"], 3, 0)
        
        layout_grid.addWidget(group_informes, 1, 1)
        
        # 5. SENSORES (SAC/SIC) — lista de checkboxes dinámicos
        group_sacsic = QGroupBox("Sensores (SAC/SIC)")
        v_sacsic = QVBoxLayout(group_sacsic)
        v_sacsic.setContentsMargins(8, 14, 8, 8)
        v_sacsic.setSpacing(4)

        # Botones Todos / Ninguno
        h_btns_s = QHBoxLayout()
        self.btn_sens_todos = QPushButton("Todos")
        self.btn_sens_ninguno = QPushButton("Ninguno")
        self.btn_sens_todos.setFixedHeight(22)
        self.btn_sens_ninguno.setFixedHeight(22)
        self.btn_sens_todos.clicked.connect(self._sensores_todos)
        self.btn_sens_ninguno.clicked.connect(self._sensores_ninguno)
        h_btns_s.addWidget(self.btn_sens_todos)
        h_btns_s.addWidget(self.btn_sens_ninguno)
        h_btns_s.addStretch()
        v_sacsic.addLayout(h_btns_s)

        # Área de scroll con checkboxes
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFixedHeight(90)
        scroll.setStyleSheet("QScrollArea { border: 1px solid #4B5263; background-color: #0E131F; }")

        container = QWidget()
        container.setStyleSheet("background-color: #0E131F;")
        grid_sens = QGridLayout(container)
        grid_sens.setContentsMargins(4, 4, 4, 4)
        grid_sens.setSpacing(3)

        self.sensor_checkboxes: Dict[str, QCheckBox] = {}  # {"226/108": QCheckBox}

        if self.sensors_list:
            for idx, (sac, sic, name) in enumerate(self.sensors_list):
                sid = f"{sac}/{sic}"
                label = f"[{sac}/{sic}] {name}"
                chk = QCheckBox(label)
                chk.setChecked(True)   # por defecto todos seleccionados
                chk.setStyleSheet("color: #E0E6ED; font-size: 8pt;")
                chk.setToolTip(f"SAC: {sac}  SIC: {sic}\n{name}")
                self.sensor_checkboxes[sid] = chk
                row, col = divmod(idx, 2)
                grid_sens.addWidget(chk, row, col)
        else:
            grid_sens.addWidget(QLabel("(Sin sensores cargados)"), 0, 0)

        scroll.setWidget(container)
        v_sacsic.addWidget(scroll)
        layout_grid.addWidget(group_sacsic, 2, 0, 1, 2)
        
        layout_main.addLayout(layout_grid)
        
        # Barra de estado de Mensajes ASTERIX
        self.lbl_contador = QLabel("Seleccionados: 0 de 0 Mensajes ASTERIX")
        self.lbl_contador.setFont(QFont("Monospace", 9, QFont.Weight.Bold))
        self.lbl_contador.setStyleSheet("color: #39FF14; background-color: rgba(20, 24, 33, 140); padding: 6px; border: 1px solid #4B5263; border-radius: 4px; margin-top: 5px;")
        self.lbl_contador.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout_main.addWidget(self.lbl_contador)
        
        # Botones de Acción (OK, Aplicar, Cerrar)
        layout_btns = QHBoxLayout()
        layout_btns.setContentsMargins(0, 10, 0, 0)
        
        self.btn_ok = QPushButton("OK")
        self.btn_aplicar = QPushButton("Aplicar")
        self.btn_cerrar = QPushButton("Cerrar")
        
        layout_btns.addStretch()
        layout_btns.addWidget(self.btn_ok)
        layout_btns.addWidget(self.btn_aplicar)
        layout_btns.addWidget(self.btn_cerrar)
        layout_main.addLayout(layout_btns)
        
        # Conexiones
        self.btn_ok.clicked.connect(self._on_ok)
        self.btn_aplicar.clicked.connect(self._on_aplicar)
        self.btn_cerrar.clicked.connect(self.reject)

    def _load_config(self):
        # Códigos Seleccionados
        codes = self.config.get("codes", ["", "", "", ""])
        for i, code in enumerate(codes):
            if i < len(self.txt_codes):
                self.txt_codes[i].setText(str(code))
        self.chk_filtro_codes.setChecked(self.config.get("habilitar_filtro_codigos", False))
        
        # Tipo de Códigos A/C
        for key, chk in self.chks_codes.items():
            chk.setChecked(self.config.get(key, True if "todos" in key else False))
            
        # Checkboxes extra de tipo de códigos
        for key, chk in self.chks_extra_cods.items():
            chk.setChecked(self.config.get(key, True if "todos" in key else False))
            
        # Rangos
        self.sp_dist_inf.setValue(self.config.get("dist_inf", 0.0))
        self.sp_dist_sup.setValue(self.config.get("dist_sup", 500.0))
        
        self.sp_az_inf.setValue(self.config.get("az_inf", 0))
        self.sp_az_sup.setValue(self.config.get("az_sup", 360))
        
        self.sp_alt_inf.setValue(self.config.get("alt_inf", -9999))
        self.sp_alt_sup.setValue(self.config.get("alt_sup", 99999))
        
        self.sp_msg_inf.setValue(self.config.get("msg_inf", 1))
        self.sp_msg_sup.setValue(self.config.get("msg_sup", 302761))
        
        self.txt_id21_inf.setText(self.config.get("id21_inf", "000000"))
        self.txt_id21_sup.setText(self.config.get("id21_sup", "FFFFFF"))
        
        # SAC/SIC — sensores seleccionados
        # Por defecto: todos seleccionados (conjunto de todos los sensor_ids del sensors_list)
        saved = self.config.get("sensores_seleccionados", None)
        for sid, chk in self.sensor_checkboxes.items():
            if saved is None:
                chk.setChecked(True)   # primera apertura: todos
            else:
                chk.setChecked(sid in saved)
        
        # Tipo de Informes
        for key, chk in self.chks_inf.items():
            chk.setChecked(self.config.get(key, True))

    def _save_to_config(self):
        # Guardar Códigos Seleccionados
        self.config["codes"] = [txt.text().strip() for txt in self.txt_codes]
        self.config["habilitar_filtro_codigos"] = self.chk_filtro_codes.isChecked()
        
        # Tipo de Códigos A/C
        for key, chk in self.chks_codes.items():
            self.config[key] = chk.isChecked()
            
        # Checkboxes extra de tipo de códigos
        for key, chk in self.chks_extra_cods.items():
            self.config[key] = chk.isChecked()
            
        # Rangos
        self.config["dist_inf"] = self.sp_dist_inf.value()
        self.config["dist_sup"] = self.sp_dist_sup.value()
        
        self.config["az_inf"] = self.sp_az_inf.value()
        self.config["az_sup"] = self.sp_az_sup.value()
        
        self.config["alt_inf"] = self.sp_alt_inf.value()
        self.config["alt_sup"] = self.sp_alt_sup.value()
        
        self.config["msg_inf"] = self.sp_msg_inf.value()
        self.config["msg_sup"] = self.sp_msg_sup.value()
        
        self.config["id21_inf"] = self.txt_id21_inf.text().strip().upper()
        self.config["id21_sup"] = self.txt_id21_sup.text().strip().upper()
        
        # SAC/SIC — guardar conjunto de sensor_ids seleccionados
        self.config["sensores_seleccionados"] = {
            sid for sid, chk in self.sensor_checkboxes.items() if chk.isChecked()
        }
        
        # Tipo de Informes
        for key, chk in self.chks_inf.items():
            self.config[key] = chk.isChecked()

    def actualizar_contador(self, selected: int, total: int):
        self.selected_messages = selected
        self.total_messages = total
        self.lbl_contador.setText(f"Seleccionados: {selected} de {total} Mensajes ASTERIX")

    def _sensores_todos(self):
        for chk in self.sensor_checkboxes.values():
            chk.setChecked(True)

    def _sensores_ninguno(self):
        for chk in self.sensor_checkboxes.values():
            chk.setChecked(False)

    def _on_aplicar(self):
        self._save_to_config()
        self.filter_applied.emit(self.config)

    def _on_ok(self):
        self._save_to_config()
        self.filter_applied.emit(self.config)
        self.accept()
