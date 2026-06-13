import os
import json
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QLineEdit,
    QComboBox, QSpinBox, QPushButton, QLabel, QCheckBox, QListWidget,
    QAbstractItemView, QListWidgetItem, QMessageBox
)
from PyQt6.QtCore import Qt, pyqtSignal, QThread
from PyQt6.QtGui import QRegularExpressionValidator
from PyQt6.QtCore import QRegularExpression

class AirportLoaderThread(QThread):
    """Hilo de fondo para leer los listados de aeropuertos (GeoJSON) sin congelar la GUI.

    Acepta varias rutas y combina los resultados. Soporta dos formatos:
      - nombres.json: properties.name = ICAO (sin frecuencias).
      - ar_apt.geojson: properties.icaoCode = ICAO (+ frecuencias).
    Las frecuencias prevalecen de la fuente que las provea.
    """
    airports_loaded = pyqtSignal(dict)

    def __init__(self, file_paths):
        super().__init__()
        # Acepta una ruta única (str) o una lista de rutas
        if isinstance(file_paths, str):
            file_paths = [file_paths]
        self.file_paths = file_paths

    def run(self):
        airports = {}
        for path in self.file_paths:
            try:
                if not os.path.exists(path):
                    continue
                with open(path, "r", encoding="utf-8", errors="ignore") as f:
                    data = json.load(f)
                for feature in data.get("features", []):
                    props = feature.get("properties", {})
                    # ICAO puede venir como icaoCode (ar_apt) o name (nombres.json)
                    icao = props.get("icaoCode") or props.get("name")
                    if not (icao and isinstance(icao, str) and icao.strip()):
                        continue
                    icao = icao.strip().upper()

                    geom = feature.get("geometry", {})
                    coords = geom.get("coordinates", []) if geom.get("type") == "Point" else []
                    lat = coords[1] if len(coords) >= 2 else None
                    lon = coords[0] if len(coords) >= 2 else None
                    freqs = props.get("frequencies", [])
                    nombre = props.get("name", "") if props.get("icaoCode") else ""

                    existente = airports.get(icao)
                    if existente is None:
                        airports[icao] = {
                            "lat": lat, "lon": lon,
                            "name": nombre, "frequencies": freqs,
                        }
                    else:
                        # Completar campos faltantes sin pisar datos válidos
                        if existente.get("lat") is None and lat is not None:
                            existente["lat"] = lat
                            existente["lon"] = lon
                        if not existente.get("frequencies") and freqs:
                            existente["frequencies"] = freqs
                        if not existente.get("name") and nombre:
                            existente["name"] = nombre
            except Exception as e:
                print(f"[AirportLoaderThread] Error leyendo {path}: {e}")
        # Descartar entradas sin coordenadas (no utilizables para centrar)
        airports = {k: v for k, v in airports.items() if v.get("lat") is not None and v.get("lon") is not None}
        self.airports_loaded.emit(airports)


class ProfileAdminDialog(QDialog):
    """
    Diálogo de Configuración del Perfil Operativo y Nivel de Incumbencia.
    Permite el CRUD completo de perfiles y la carga dinámica en caliente.
    Estética neón cian/verde acorde a la HMI del radar.
    """
    profile_saved = pyqtSignal(dict)
    hot_load_triggered = pyqtSignal(str)

    def __init__(self, profile_manager, parent=None):
        super().__init__(parent)
        self.profile_manager = profile_manager
        self.base_dir = self.profile_manager.base_dir
        self.aeropuertos_data = {}
        
        self.setWindowTitle("Administrador de Perfiles Operativos")
        from player.ui_scaling import escalar_ventana
        escalar_ventana(self, 500, 550, centrar=False)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        
        self._setup_style()
        self._setup_ui()
        
        # Iniciar lectura en segundo plano
        # Fuente principal de ICAO: files/nombres.json; frecuencias desde ar_apt.geojson
        nombres_path = os.path.join(self.base_dir, "files", "nombres.json")
        ar_apt_path = os.path.join(self.base_dir, "cartografia_base", "ar_apt.geojson")
        self.loader_thread = AirportLoaderThread([nombres_path, ar_apt_path])
        self.loader_thread.airports_loaded.connect(self._on_airports_loaded)
        self.loader_thread.start()
        
        # Rellenar lista de perfiles y seleccionar el activo
        self._refresh_profiles_list()
        
        # Seleccionar por defecto el perfil activo actual en el combo si existe
        active_name = self.profile_manager.profile.get("nombre_usuario") or self.profile_manager.profile.get("name")
        if active_name:
            idx = self.cmb_lista_perfiles.findText(active_name)
            if idx >= 0:
                self.cmb_lista_perfiles.setCurrentIndex(idx)
            else:
                self._on_profile_selected("[Nuevo Perfil]")
        else:
            self._on_profile_selected("[Nuevo Perfil]")

    def _setup_style(self):
        self.setStyleSheet("""
            QDialog {
                background-color: #0E131F;
                border: 2px solid #00E5FF;
                border-radius: 8px;
            }
            QLabel {
                color: #00E5FF;
                font-family: 'Segoe UI', sans-serif;
                font-size: 9pt;
                font-weight: bold;
            }
            QLineEdit, QComboBox, QSpinBox, QListWidget {
                background-color: #1A2130;
                border: 1px solid #4B5263;
                border-radius: 4px;
                color: #FFFFFF;
                font-family: 'Segoe UI', sans-serif;
                font-size: 9pt;
                padding: 4px;
            }
            QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QListWidget:focus {
                border: 1px solid #39FF14;
            }
            QLineEdit:disabled {
                background-color: #121824;
                color: #888888;
                border: 1px solid #2B3243;
            }
            QPushButton {
                background-color: #121824;
                border: 1px solid #00E5FF;
                border-radius: 4px;
                color: #00E5FF;
                font-family: 'Segoe UI', sans-serif;
                font-size: 9pt;
                font-weight: bold;
                padding: 6px 14px;
            }
            QPushButton:hover {
                border: 1px solid #39FF14;
                color: #39FF14;
                background-color: rgba(57, 255, 20, 20);
            }
            QCheckBox {
                color: #00E5FF;
                font-family: 'Segoe UI', sans-serif;
                font-size: 9pt;
                font-weight: bold;
            }
            QCheckBox::indicator {
                border: 1px solid #4B5263;
                background-color: #1A2130;
                width: 14px;
                height: 14px;
                border-radius: 2px;
            }
            QCheckBox::indicator:checked {
                border: 1px solid #39FF14;
                background-color: #39FF14;
            }
            QListWidget::item:selected {
                background-color: #00E5FF;
                color: #000000;
            }
        """)

    def _setup_ui(self):
        layout_main = QVBoxLayout(self)
        layout_main.setContentsMargins(20, 20, 20, 20)
        layout_main.setSpacing(12)
        
        # 0. Selector Maestro de Perfiles
        layout_selector = QHBoxLayout()
        lbl_selector = QLabel("Perfil Seleccionado:")
        self.cmb_lista_perfiles = QComboBox()
        self.cmb_lista_perfiles.currentTextChanged.connect(self._on_profile_selected)
        layout_selector.addWidget(lbl_selector)
        layout_selector.addWidget(self.cmb_lista_perfiles, 1)
        layout_main.addLayout(layout_selector)
        
        # Formulario
        form = QFormLayout()
        form.setSpacing(10)
        
        # 1. Identificador
        self.txt_nombre = QLineEdit()
        self.txt_nombre.setPlaceholderText("Ej. Matias_TWR")
        form.addRow("Identificador / Usuario:", self.txt_nombre)

        # 1.b Rol operativo (define la vista y permisos)
        self.cmb_rol = QComboBox()
        self.cmb_rol.addItem("Técnico", "tecnico")
        self.cmb_rol.addItem("Controlador", "controlador")
        form.addRow("Rol Operativo:", self.cmb_rol)
        
        # 2. Aeropuerto ICAO (entrada manual con sugerencias de los disponibles)
        self.cmb_aeropuerto = QComboBox()
        self.cmb_aeropuerto.setEditable(True)
        self.cmb_aeropuerto.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.cmb_aeropuerto.lineEdit().setPlaceholderText("Ej. SACO (escriba para buscar)")
        completer = self.cmb_aeropuerto.completer()
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        completer.setFilterMode(Qt.MatchFlag.MatchContains)
        self.cmb_aeropuerto.currentTextChanged.connect(self._on_airport_changed)
        form.addRow("Aeropuerto Trabajo (ICAO):", self.cmb_aeropuerto)
        
        # 3. Coordenadas de Centro (Deshabilitadas)
        self.txt_lat = QLineEdit()
        self.txt_lat.setEnabled(False)
        self.txt_lon = QLineEdit()
        self.txt_lon.setEnabled(False)
        layout_coords = QHBoxLayout()
        layout_coords.addWidget(self.txt_lat)
        layout_coords.addWidget(self.txt_lon)
        form.addRow("Coordenadas Centro [Lat, Lon]:", layout_coords)
        
        # 4. Nivel de Incumbencia Operativo (SpinBox 0-450 FL)
        self.sb_fl_incumbencia = QSpinBox()
        self.sb_fl_incumbencia.setRange(0, 450)
        self.sb_fl_incumbencia.setValue(95)
        self.sb_fl_incumbencia.setSuffix(" FL")
        form.addRow("Techo Nivel Incumbencia:", self.sb_fl_incumbencia)

        # 4.a Radio del área de incumbencia (NM) — junto al techo define el volumen de trabajo
        self.sb_radio_incumbencia = QSpinBox()
        self.sb_radio_incumbencia.setRange(1, 500)
        self.sb_radio_incumbencia.setValue(50)
        self.sb_radio_incumbencia.setSuffix(" NM")
        form.addRow("Radio de Incumbencia:", self.sb_radio_incumbencia)

        # 4.b Altitud de Transición (TA) — base de cálculo ENR 1.7
        self.sb_transition_altitude = QSpinBox()
        self.sb_transition_altitude.setRange(0, 20000)
        self.sb_transition_altitude.setSingleStep(500)
        self.sb_transition_altitude.setValue(10000)
        self.sb_transition_altitude.setSuffix(" ft")
        form.addRow("Altitud de Transición (TA):", self.sb_transition_altitude)
        
        # 5. Frecuencias del Sector
        rx = QRegularExpression(r"^1[1-3][0-9]\.[0-9]{2,3}$")
        self.validator_radio = QRegularExpressionValidator(rx, self)
        
        self.txt_frec_twr = QLineEdit()
        self.txt_frec_twr.setValidator(self.validator_radio)
        self.txt_frec_twr.setPlaceholderText("Ej. 118.30")
        form.addRow("Frecuencia TWR:", self.txt_frec_twr)
        
        self.txt_frec_gnd = QLineEdit()
        self.txt_frec_gnd.setValidator(self.validator_radio)
        self.txt_frec_gnd.setPlaceholderText("Ej. 121.75")
        form.addRow("Frecuencia GND:", self.txt_frec_gnd)
        
        self.txt_frec_app = QLineEdit()
        self.txt_frec_app.setValidator(self.validator_radio)
        self.txt_frec_app.setPlaceholderText("Ej. 119.85")
        form.addRow("Frecuencia APP:", self.txt_frec_app)
        
        # 6. Habilitador STCA
        self.chk_stca = QCheckBox("Habilitar Alertas STCA (Inhibir en TWR)")
        self.chk_stca.setChecked(False)
        form.addRow("Seguridad Operativa:", self.chk_stca)
        
        # 7. Mapas Visibles (checkbox por item = visible ON/OFF; selección = objetivo a eliminar)
        self.lst_mapas = QListWidget()
        self.lst_mapas.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.lst_mapas.setMaximumHeight(100)
        self._populate_available_maps()

        self.btn_importar_mapa = QPushButton("📥 Importar Mapa (.geojson)...")
        self.btn_importar_mapa.clicked.connect(self._on_import_map)

        self.btn_eliminar_mapa = QPushButton("🗑 Eliminar Mapa de la lista")
        self.btn_eliminar_mapa.clicked.connect(self._on_delete_map)

        layout_mapas = QVBoxLayout()
        layout_mapas.addWidget(self.lst_mapas)
        layout_botones_mapa = QHBoxLayout()
        layout_botones_mapa.addWidget(self.btn_importar_mapa)
        layout_botones_mapa.addWidget(self.btn_eliminar_mapa)
        layout_mapas.addLayout(layout_botones_mapa)

        form.addRow("Capas de Mapas Visibles:", layout_mapas)
        
        layout_main.addLayout(form)
        
        # Panel de Botones CRUD + Carga
        layout_btns = QVBoxLayout()
        
        layout_crud_btns = QHBoxLayout()
        self.btn_eliminar = QPushButton("❌ Eliminar Perfil")
        self.btn_eliminar.clicked.connect(self._on_delete)
        self.btn_guardar = QPushButton("💾 Guardar Perfil")
        self.btn_guardar.clicked.connect(self._on_save)
        layout_crud_btns.addWidget(self.btn_eliminar)
        layout_crud_btns.addWidget(self.btn_guardar)
        
        layout_action_btns = QHBoxLayout()
        self.btn_cancelar = QPushButton("Cancelar")
        self.btn_cancelar.clicked.connect(self.reject)
        self.btn_cargar_caliente = QPushButton("🚀 Cargar en Pantalla")
        self.btn_cargar_caliente.clicked.connect(self._on_hot_load)
        # Resaltar botón de carga en caliente con borde verde
        self.btn_cargar_caliente.setStyleSheet("""
            QPushButton {
                background-color: #12241A;
                border: 1px solid #39FF14;
                color: #39FF14;
            }
            QPushButton:hover {
                background-color: rgba(57, 255, 20, 40);
            }
        """)
        layout_action_btns.addWidget(self.btn_cancelar)
        layout_action_btns.addWidget(self.btn_cargar_caliente)
        
        layout_btns.addLayout(layout_crud_btns)
        layout_btns.addLayout(layout_action_btns)
        layout_main.addLayout(layout_btns)

    def _populate_available_maps(self, username=None):
        """Busca mapas GeoJSON en las carpetas y los lista."""
        self.lst_mapas.clear()
        carto_dir = os.path.join(self.base_dir, "cartografia_base")
        mapas_gen_dir = os.path.join(self.base_dir, "mapas_generales")
        
        map_files = []
        if os.path.exists(carto_dir):
            for f in os.listdir(carto_dir):
                if f.lower().endswith(".geojson"):
                    rel = f"cartografia_base/{f}"
                    map_files.append(rel)
        if os.path.exists(mapas_gen_dir):
            for f in os.listdir(mapas_gen_dir):
                if f.lower().endswith(".geojson"):
                    rel = f"mapas_generales/{f}"
                    if rel not in map_files:
                        map_files.append(rel)
                        
        if username:
            user_map_dir = os.path.join(self.base_dir, "profiles", f"mapas_{username}")
            if os.path.exists(user_map_dir):
                for f in os.listdir(user_map_dir):
                    if f.lower().endswith(".geojson"):
                        rel = f"profiles/mapas_{username}/{f}"
                        if rel not in map_files:
                            map_files.append(rel)
                            
        for m in sorted(map_files):
            item = QListWidgetItem(m)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Unchecked)
            self.lst_mapas.addItem(item)

    def _refresh_profiles_list(self, select_name=None):
        self.cmb_lista_perfiles.blockSignals(True)
        self.cmb_lista_perfiles.clear()
        self.cmb_lista_perfiles.addItem("[Nuevo Perfil]")
        
        perfiles = self.profile_manager.listar_perfiles()
        for p in perfiles:
            self.cmb_lista_perfiles.addItem(p)
            
        if select_name:
            idx = self.cmb_lista_perfiles.findText(select_name)
            if idx >= 0:
                self.cmb_lista_perfiles.setCurrentIndex(idx)
        self.cmb_lista_perfiles.blockSignals(False)

    def _on_airports_loaded(self, airports):
        self.aeropuertos_data = airports
        self.cmb_aeropuerto.blockSignals(True)
        self.cmb_aeropuerto.clear()
        
        # Poblar combo con códigos ICAO sorted
        icaos = sorted(list(airports.keys()))
        self.cmb_aeropuerto.addItems(icaos)
        
        # Restablecer aeropuerto seleccionado en el perfil cargado si existe
        active_apt = self.profile_manager.profile.get("aeropuerto_trabajo") or self.profile_manager.profile.get("aeropuerto", "")
        if active_apt:
            idx = self.cmb_aeropuerto.findText(active_apt)
            if idx >= 0:
                self.cmb_aeropuerto.setCurrentIndex(idx)
            else:
                self.cmb_aeropuerto.setCurrentText(active_apt)
        else:
            self.cmb_aeropuerto.setCurrentIndex(-1)

        self.cmb_aeropuerto.blockSignals(False)
        
        # Gatillar actualización manual si hay selección activa
        if self.cmb_aeropuerto.currentIndex() >= 0:
            self._on_airport_changed(self.cmb_aeropuerto.currentText())

    def _on_airport_changed(self, icao):
        icao = (icao or "").strip().upper()
        if icao in self.aeropuertos_data:
            info = self.aeropuertos_data[icao]
            self.txt_lat.setText(f"{info['lat']:.5f}")
            self.txt_lon.setText(f"{info['lon']:.5f}")
            
            # Autocompletado inteligente de frecuencias del aeropuerto
            freqs = info.get("frequencies", [])
            
            twr_freqs = []
            gnd_freqs = []
            app_freqs = []
            for freq in freqs:
                val = freq.get("value")
                if not val:
                    continue
                name = str(freq.get("name", "")).upper()
                ftype = freq.get("type")
                is_primary = freq.get("primary", False)
                
                if ftype == 14 or "TWR" in name or "TOW" in name or "TORRE" in name:
                    twr_freqs.append((is_primary, val))
                if ftype == 9 or "GND" in name or "GROUND" in name or "TAXI" in name or "RODAJE" in name:
                    gnd_freqs.append((is_primary, val))
                if ftype == 0 or "APP" in name or "APPROACH" in name or "CONTROL" in name or "TMA" in name:
                    app_freqs.append((is_primary, val))
            
            twr_freqs.sort(key=lambda x: x[0], reverse=True)
            gnd_freqs.sort(key=lambda x: x[0], reverse=True)
            app_freqs.sort(key=lambda x: x[0], reverse=True)
            
            if twr_freqs: self.txt_frec_twr.setText(twr_freqs[0][1])
            else: self.txt_frec_twr.clear()
            
            if gnd_freqs: self.txt_frec_gnd.setText(gnd_freqs[0][1])
            else: self.txt_frec_gnd.clear()
            
            if app_freqs: self.txt_frec_app.setText(app_freqs[0][1])
            else: self.txt_frec_app.clear()

    def _on_profile_selected(self, name):
        if name == "[Nuevo Perfil]" or not name:
            self.txt_nombre.clear()
            self.txt_nombre.setEnabled(True)
            self.cmb_rol.setCurrentIndex(0)
            self.cmb_aeropuerto.setCurrentIndex(-1)
            self.txt_lat.clear()
            self.txt_lon.clear()
            self.sb_fl_incumbencia.setValue(95)
            self.sb_radio_incumbencia.setValue(50)
            self.sb_transition_altitude.setValue(10000)
            self.txt_frec_twr.clear()
            self.txt_frec_gnd.clear()
            self.txt_frec_app.clear()
            self._populate_available_maps()
            self.lst_mapas.clearSelection()
            self.chk_stca.setChecked(False)
            return

        try:
            profile_data = self.profile_manager.leer_perfil(name)
            self.txt_nombre.setText(profile_data.get("nombre_usuario", ""))
            self.txt_nombre.setEnabled(True)

            rol_idx = self.cmb_rol.findData(str(profile_data.get("rol", "tecnico")).strip().lower())
            self.cmb_rol.setCurrentIndex(rol_idx if rol_idx >= 0 else 0)
            
            apt = profile_data.get("aeropuerto_trabajo", "")
            idx = self.cmb_aeropuerto.findText(apt)
            if idx >= 0:
                self.cmb_aeropuerto.setCurrentIndex(idx)
            elif apt:
                self.cmb_aeropuerto.setCurrentText(apt)

            self.sb_fl_incumbencia.setValue(int(profile_data.get("nivel_incumbencia", 95)))
            self.sb_radio_incumbencia.setValue(int(profile_data.get("radio_incumbencia", 50)))
            self.sb_transition_altitude.setValue(int(profile_data.get("transition_altitude", 10000)))
            
            freqs = profile_data.get("frecuencias_sector", ["", "", ""])
            self.txt_frec_twr.setText(freqs[0] if len(freqs) > 0 else "")
            self.txt_frec_gnd.setText(freqs[1] if len(freqs) > 1 else "")
            self.txt_frec_app.setText(freqs[2] if len(freqs) > 2 else "")
            
            self.chk_stca.setChecked(bool(profile_data.get("stca_habilitado", False)))
            
            # Marcar mapas visibles (checkbox)
            self._populate_available_maps(name)
            self.lst_mapas.clearSelection()
            mapas_visibles = profile_data.get("mapas_visibles", [])
            for i in range(self.lst_mapas.count()):
                item = self.lst_mapas.item(i)
                item.setCheckState(
                    Qt.CheckState.Checked if item.text() in mapas_visibles else Qt.CheckState.Unchecked
                )
                    
            coords = profile_data.get("coordenadas_centro", {})
            self.txt_lat.setText(f"{coords.get('lat', 0.0):.5f}" if "lat" in coords else "")
            self.txt_lon.setText(f"{coords.get('lon', 0.0):.5f}" if "lon" in coords else "")
            
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Error cargando el perfil: {e}")

    def _on_save(self):
        nombre = self.txt_nombre.text().strip()
        if not nombre:
            QMessageBox.warning(self, "Validación", "El identificador/nombre del perfil es obligatorio.")
            return
            
        if nombre == "[Nuevo Perfil]":
            QMessageBox.warning(self, "Validación", "El nombre del perfil no puede ser '[Nuevo Perfil]'.")
            return
            
        selected_maps = []
        for i in range(self.lst_mapas.count()):
            item = self.lst_mapas.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                selected_maps.append(item.text())
            
        try:
            lat = float(self.txt_lat.text()) if self.txt_lat.text() else -31.31
            lon = float(self.txt_lon.text()) if self.txt_lon.text() else -64.21
        except ValueError:
            lat, lon = -31.31, -64.21
            
        datos = {
            "nombre_usuario": nombre,
            "rol": self.cmb_rol.currentData(),
            "aeropuerto_trabajo": self.cmb_aeropuerto.currentText().strip().upper(),
            "coordenadas_centro": {"lat": lat, "lon": lon},
            "nivel_incumbencia": self.sb_fl_incumbencia.value(),
            "radio_incumbencia": self.sb_radio_incumbencia.value(),
            "transition_altitude": self.sb_transition_altitude.value(),
            "frecuencias_sector": [
                self.txt_frec_twr.text().strip(),
                self.txt_frec_gnd.text().strip(),
                self.txt_frec_app.text().strip()
            ],
            "mapas_visibles": selected_maps,
            "stca_habilitado": self.chk_stca.isChecked()
        }
        
        try:
            self.profile_manager.guardar_perfil(nombre, datos)
            QMessageBox.information(self, "Éxito", f"Perfil '{nombre}' guardado exitosamente.")
            self._refresh_profiles_list(nombre)
            
            # Actualizar combo box al nuevo perfil guardado
            idx = self.cmb_lista_perfiles.findText(nombre)
            if idx >= 0:
                self.cmb_lista_perfiles.setCurrentIndex(idx)
                
            # Emitir para compatibilidad
            compat_datos = self.profile_manager.to_compat_dict(self.profile_manager.to_strict_schema(datos))
            self.profile_saved.emit(compat_datos)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"No se pudo guardar el perfil: {e}")

    def _on_delete(self):
        nombre = self.cmb_lista_perfiles.currentText()
        if nombre == "[Nuevo Perfil]" or not nombre:
            QMessageBox.warning(self, "Eliminar Perfil", "Seleccione un perfil guardado de la lista para eliminar.")
            return
            
        reply = QMessageBox.question(
            self, "Confirmar eliminación",
            f"¿Está seguro de que desea eliminar permanentemente el perfil '{nombre}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            try:
                self.profile_manager.eliminar_perfil(nombre)
                QMessageBox.information(self, "Eliminado", f"Perfil '{nombre}' eliminado.")
                self._refresh_profiles_list()
                self._on_profile_selected("[Nuevo Perfil]")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"No se pudo eliminar el perfil: {e}")

    def _on_hot_load(self):
        nombre = self.txt_nombre.text().strip()
        if not nombre:
            # Intentar tomar de la selección del combo
            nombre = self.cmb_lista_perfiles.currentText()
            if nombre == "[Nuevo Perfil]" or not nombre:
                QMessageBox.warning(self, "Cargar en Pantalla", "Seleccione o guarde un perfil antes de cargarlo.")
                return
                
        # Emitir señal de carga en caliente
        self.hot_load_triggered.emit(nombre)
        self.accept()

    def _on_import_map(self):
        nombre = self.txt_nombre.text().strip()
        if not nombre or nombre == "[Nuevo Perfil]":
            QMessageBox.warning(self, "Importar Mapa", "Por favor, ingrese o seleccione un nombre de perfil antes de importar un mapa.")
            return
            
        from PyQt6.QtWidgets import QFileDialog
        import shutil
        
        filepath, _ = QFileDialog.getOpenFileName(
            self, "Seleccionar Mapa GeoJSON", "", "GeoJSON Files (*.geojson)"
        )
        if filepath:
            try:
                user_map_dir = os.path.join(self.base_dir, "profiles", f"mapas_{nombre}")
                os.makedirs(user_map_dir, exist_ok=True)
                
                filename = os.path.basename(filepath)
                dest_path = os.path.join(user_map_dir, filename)
                
                shutil.copy(filepath, dest_path)
                
                # Refrescar y seleccionar
                self._populate_available_maps(nombre)
                
                rel_path = f"profiles/mapas_{nombre}/{filename}"
                for i in range(self.lst_mapas.count()):
                    item = self.lst_mapas.item(i)
                    if item.text() == rel_path:
                        item.setCheckState(Qt.CheckState.Checked)
                        
                QMessageBox.information(
                    self, "Éxito",
                    f"El mapa '{filename}' fue copiado e importado al perfil '{nombre}' de forma exitosa."
                )
            except Exception as e:
                QMessageBox.critical(self, "Error", f"No se pudo copiar el archivo de mapa: {e}")

    def _on_delete_map(self):
        """Elimina físicamente del disco el mapa resaltado y refresca la lista."""
        item = self.lst_mapas.currentItem()
        if item is None:
            QMessageBox.warning(self, "Eliminar Mapa", "Seleccione (resalte) un mapa de la lista para eliminarlo.")
            return

        rel_path = item.text()
        abs_path = os.path.join(self.base_dir, rel_path)

        reply = QMessageBox.question(
            self, "Confirmar eliminación de mapa",
            f"¿Eliminar permanentemente el archivo de mapa?\n\n{rel_path}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        try:
            if os.path.exists(abs_path):
                os.remove(abs_path)
            nombre = self.txt_nombre.text().strip()
            self._populate_available_maps(nombre if nombre and nombre != "[Nuevo Perfil]" else None)
            QMessageBox.information(self, "Eliminado", f"Mapa '{rel_path}' eliminado.")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"No se pudo eliminar el archivo de mapa: {e}")
