from PyQt6.QtWidgets import (QFrame, QLabel, QVBoxLayout, QWidget, QGridLayout, QScrollArea,
                             QHBoxLayout, QDockWidget, QDialog, QTextBrowser, QPushButton)
from PyQt6.QtCore import Qt, pyqtSignal, pyqtSlot, QTimer, QSize
from PyQt6.QtGui import QColor, QFont

COLOR_BG_GLASS       = QColor(20, 24, 32, 220)   # #141820 con alpha
COLOR_BORDER         = QColor(42, 58, 74, 180)   # #2A3A4A
COLOR_TEXT_PRIMARY   = QColor("#FFFFFF")
COLOR_TEXT_SECONDARY = QColor("#AAAAAA")
COLOR_ACCENT_CYAN    = QColor("#00FFFF")

# Descripción operativa de cada alarma: (severidad, origen ASTERIX, explicación).
ALARM_INFO = {
    "NOGO":            ("CRÍTICA",  "CAT 034 I034/050 (COM/NOGO)", "El sistema reporta operación inhibida: los datos NO deben usarse operacionalmente."),
    "OVL RDP":         ("DEGRADADA","CAT 034 I034/050 (COM/OVLRDP)", "Sobrecarga del procesador de datos radar (RDP)."),
    "OVL XMT":         ("DEGRADADA","CAT 034 I034/050 (COM/OVLXMT)", "Sobrecarga del subsistema de transmisión."),
    "MONITOR DISC":    ("AVISO",    "CAT 034 I034/050 (COM/MSC)", "Sistema de monitoreo desconectado del sensor."),
    "TIME INVALID":    ("DEGRADADA","CAT 034 I034/050 (COM/TSV)", "Fuente de tiempo inválida: el sellado temporal puede no ser confiable."),
    "PSR OVL":         ("DEGRADADA","CAT 034 I034/050 (PSR)", "Sobrecarga del canal primario (PSR)."),
    "SSR OVL":         ("DEGRADADA","CAT 034 I034/050 (SSR)", "Sobrecarga del canal secundario (SSR)."),
    "MDS OVL":         ("DEGRADADA","CAT 034 I034/050 (MDS)", "Sobrecarga del canal Mode S."),
    "SYSTEM CRITICAL": ("CRÍTICA",  "CAT 023 (system_state=3)", "Falla crítica de la estación: el sistema reporta estado no operativo."),
    "OVERLOAD":        ("DEGRADADA","CAT 023 (system_state=2)", "Sobrecarga del sistema: capacidad de procesamiento excedida."),
    "DEGRADED":        ("DEGRADADA","CAT 023 (system_state=1)", "Servicio degradado: el sistema opera con prestaciones reducidas."),
    "UPS ACTIVE":      ("AVISO",    "CAT 023", "Alimentación por UPS activa: corte de la red eléctrica primaria."),
}

class RadarStatusCard(QFrame):
    """Tarjeta visual que representa un sensor físico en la red ATSEP en PyQt6."""
    def __init__(self, key, name="Sensor", parent=None):
        super().__init__(parent)
        self.key = key  # (sac, sic)
        self.name = name
        self.channel_ab = "UNKNOWN"
        self.antenna_azimuth = None
        # Estado COM de I034/050 (CAT 034)
        self.sys_nogo = False
        self.ovl_rdp = False
        self.ovl_xmt = False
        self.monitor_disc = False
        self.time_invalid = False
        self.psr_ovl = False
        self.ssr_ovl = False
        self.mds_ovl = False
        # Estado de estación (CAT 023)
        self.system_state = None
        self.ups_active = None
        self.last_update_time = 0.0  # tiempo real
        self.is_offline = True
        self.fruit_events = []  # Lista de eventos {"ssr": ssr, "timestamp": timestamp}
        self.state = "OFFLINE"
        self.active_alarms = []  # Lista de códigos de alarma activos (claves de ALARM_INFO)

        self.setMinimumWidth(220)
        self.setMaximumWidth(280)
        self.setFixedHeight(110)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._set_style("OFFLINE")
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(6)

        self.lbl_name = QLabel(f"{self.name} ({self.key[0]}/{self.key[1]})")
        self.lbl_name.setStyleSheet("color: white; font-weight: bold; font-size: 12px; border: none; background-color: transparent;")
        
        self.lbl_status = QLabel("STATUS: OFFLINE")
        self.lbl_status.setStyleSheet("color: #888; border: none; background-color: transparent; font-weight: bold;")
        
        self.lbl_details = QLabel("Antenna: --° | Chan: --")
        self.lbl_details.setStyleSheet("color: #aaa; font-size: 10px; border: none; background-color: transparent;")

        self.lbl_alarms = QLabel("Alarms: None")
        self.lbl_alarms.setStyleSheet("color: #888; font-size: 10px; border: none; background-color: transparent;")
        
        self.lbl_fruits = QLabel("FRUIT Count: 0")
        self.lbl_fruits.setStyleSheet("color: #FFA500; font-size: 10px; border: none; background-color: transparent; font-weight: bold;")

        layout.addWidget(self.lbl_name)
        layout.addWidget(self.lbl_status)
        layout.addWidget(self.lbl_details)
        layout.addWidget(self.lbl_alarms)
        layout.addWidget(self.lbl_fruits)

    def _set_style(self, state):
        bg_color = "rgba(30, 34, 42, 200)"
        border_col = "rgba(80, 80, 80, 180)"
        if state == "OK":
            bg_color = "rgba(0, 43, 0, 200)"
            border_col = "green"
        elif state == "DEGRADED":
            bg_color = "rgba(74, 74, 0, 200)"
            border_col = "yellow"
        elif state == "FAULT":
            bg_color = "rgba(74, 0, 0, 200)"
            border_col = "red"

        self.setStyleSheet(f"""
            RadarStatusCard {{
                background-color: {bg_color};
                border: 2px solid {border_col};
                border-radius: 8px;
            }}
        """)

    def actualizar_tarjeta(self, data, current_time: float):
        """Actualiza el estado y los campos de telemetría de la tarjeta."""
        self.last_update_time = current_time
        self.is_offline = False

        if "channel_ab" in data:
            self.channel_ab = data["channel_ab"]
        if "antenna_azimuth" in data:
            self.antenna_azimuth = data["antenna_azimuth"]
        for campo in ("sys_nogo", "ovl_rdp", "ovl_xmt", "monitor_disc", "time_invalid",
                      "psr_ovl", "ssr_ovl", "mds_ovl"):
            if campo in data:
                setattr(self, campo, data[campo])
        if "system_state" in data:
            self.system_state = data["system_state"]
        if "ups_active" in data:
            self.ups_active = data["ups_active"]

        # Determinar alarmas y estado
        alarmas = []
        is_fault = False
        is_degraded = False

        # Alarmas de CAT 034 (I034/050)
        if self.sys_nogo:
            alarmas.append("NOGO")
            is_fault = True
        if self.ovl_rdp:
            alarmas.append("OVL RDP")
            is_degraded = True
        if self.ovl_xmt:
            alarmas.append("OVL XMT")
            is_degraded = True
        if self.time_invalid:
            alarmas.append("TIME INVALID")
            is_degraded = True
        if self.psr_ovl:
            alarmas.append("PSR OVL")
            is_degraded = True
        if self.ssr_ovl:
            alarmas.append("SSR OVL")
            is_degraded = True
        if self.mds_ovl:
            alarmas.append("MDS OVL")
            is_degraded = True
        if self.monitor_disc:
            alarmas.append("MONITOR DISC")

        # Alarmas de CAT 023
        if self.system_state == 3: # Falla Crítica
            alarmas.append("SYSTEM CRITICAL")
            is_fault = True
        elif self.system_state == 2: # Sobrecarga
            alarmas.append("OVERLOAD")
            is_degraded = True
        elif self.system_state == 1: # Degradado
            alarmas.append("DEGRADED")
            is_degraded = True

        if self.ups_active:
            alarmas.append("UPS ACTIVE")

        # Texto de estado
        if is_fault:
            state = "FAULT"
            self.lbl_status.setText("STATUS: FAULT / ALARM")
            self.lbl_status.setStyleSheet("color: #FF3333; font-weight: bold; border: none; background-color: transparent;")
        elif is_degraded:
            state = "DEGRADED"
            self.lbl_status.setText("STATUS: DEGRADED")
            self.lbl_status.setStyleSheet("color: #FFFF33; font-weight: bold; border: none; background-color: transparent;")
        else:
            state = "OK"
            self.lbl_status.setText(f"STATUS: OPERATIONAL")
            self.lbl_status.setStyleSheet("color: #33FF33; font-weight: bold; border: none; background-color: transparent;")

        self.state = state
        self.active_alarms = list(alarmas)
        self._set_style(state)

        # Detalles
        az_str = f"{self.antenna_azimuth:.1f}°" if self.antenna_azimuth is not None else "--°"
        self.lbl_details.setText(f"Antenna: {az_str} | Chan: {self.channel_ab}")
        
        # Alarmas
        if alarmas:
            self.lbl_alarms.setText(f"Alarms: {', '.join(alarmas)}")
            self.lbl_alarms.setStyleSheet("color: #FF7777; font-size: 10px; border: none; background-color: transparent;")
        else:
            self.lbl_alarms.setText("Alarms: None")
            self.lbl_alarms.setStyleSheet("color: #888; font-size: 10px; border: none; background-color: transparent;")

    def marcar_offline(self):
        self.is_offline = True
        self.state = "OFFLINE"
        self.active_alarms = []
        self.lbl_status.setText("STATUS: TIMEOUT / OFFLINE")
        self.lbl_status.setStyleSheet("color: #888; font-weight: bold; border: none; background-color: transparent;")
        self._set_style("OFFLINE")

    def mousePressEvent(self, event):
        """Al hacer click, si el sensor está alarmado abre la ventana de evento."""
        if event.button() == Qt.MouseButton.LeftButton and self.active_alarms:
            self._mostrar_evento()
        super().mousePressEvent(event)

    def _mostrar_evento(self):
        """Ventana con la descripción detallada del/los evento(s) que alarmaron al sensor."""
        sev_color = "#FF3333" if self.state == "FAULT" else "#FFCC33"
        filas = []
        for cod in self.active_alarms:
            sev, origen, desc = ALARM_INFO.get(cod, ("AVISO", "—", "Evento sin descripción."))
            filas.append(
                f"<tr>"
                f"<td style='color:{sev_color}; font-weight:bold; padding:4px 10px 4px 0;'>{cod}</td>"
                f"<td style='color:#AAAAAA; padding:4px 10px 4px 0;'>{sev}</td>"
                f"<td style='color:#7FB0FF; padding:4px 10px 4px 0;'>{origen}</td>"
                f"<td style='color:#E0E0E0; padding:4px 0;'>{desc}</td>"
                f"</tr>"
            )
        az_str = f"{self.antenna_azimuth:.1f}°" if self.antenna_azimuth is not None else "--°"
        html = (
            f"<h3 style='color:{sev_color}; margin:0 0 8px 0;'>{self.name} ({self.key[0]}/{self.key[1]}) — {self.state}</h3>"
            f"<p style='color:#AAAAAA; margin:0 0 10px 0;'>Canal: {self.channel_ab} &nbsp;|&nbsp; Antena: {az_str}</p>"
            f"<table style='border-collapse:collapse;'>"
            f"<tr style='color:#00FFFF;'><th align='left' style='padding:0 10px 6px 0;'>Alarma</th>"
            f"<th align='left' style='padding:0 10px 6px 0;'>Severidad</th>"
            f"<th align='left' style='padding:0 10px 6px 0;'>Origen</th>"
            f"<th align='left' style='padding:0 0 6px 0;'>Descripción</th></tr>"
            f"{''.join(filas)}"
            f"</table>"
        )

        dlg = QDialog(self)
        dlg.setWindowTitle(f"Evento — {self.name} ({self.key[0]}/{self.key[1]})")
        dlg.setMinimumWidth(560)
        dlg.setStyleSheet("QDialog { background-color: #141820; }")
        lay = QVBoxLayout(dlg)
        browser = QTextBrowser()
        browser.setStyleSheet("background-color: #1A1F2A; border: 1px solid #2A3A4A; color: #E0E0E0;")
        browser.setHtml(html)
        lay.addWidget(browser)
        btn = QPushButton("Cerrar")
        btn.clicked.connect(dlg.accept)
        lay.addWidget(btn, alignment=Qt.AlignmentFlag.AlignRight)
        dlg.exec()

    def registrar_fruit_evento(self, ssr_code, timestamp):
        """Registra un evento FRUIT y actualiza la UI y el tooltip."""
        self.fruit_events.append({"ssr": ssr_code, "timestamp": timestamp})
        count = len(self.fruit_events)
        self.lbl_fruits.setText(f"FRUIT Count: {count}")
        
        # Tooltip con los últimos 15 eventos con timestamp y código SSR
        ultimos_eventos = self.fruit_events[-15:]
        tooltip_txt = "Last 15 FRUIT Events:\n" + "\n".join(
            f"[{e['timestamp']}] SSR: {e['ssr'] if e['ssr'] else 'UNKNOWN'}" for e in ultimos_eventos
        )
        self.setToolTip(tooltip_txt)


class TechnicalMonitorWidget(QWidget):
    """Panel visual que presenta el estado de salud de todos los sensores en la red."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.cards = {}
        self.last_needed_height = 150
        
        # Setup UI
        self.init_ui()

        # Timer de verificación de timeouts (cada 2 segundos)
        self.timeout_timer = QTimer(self)
        self.timeout_timer.timeout.connect(self._check_timeouts)
        self.timeout_timer.start(2000)

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)

        header = QLabel("ANALISTA CAT 34/23 — Estado de sensores (CAT 034 / 023)")
        header.setStyleSheet("color: #00FFFF; font-family: 'Consolas', 'Monospace'; font-size: 14px; font-weight: bold; padding: 4px;")
        main_layout.addWidget(header)

        # Scroll Area para las tarjetas
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("background-color: transparent; border: none;")
        
        container = QWidget()
        container.setStyleSheet("background-color: transparent;")
        self.grid = QGridLayout(container)
        self.grid.setSpacing(10)
        self.grid.setContentsMargins(5, 5, 5, 5)

        scroll.setWidget(container)
        main_layout.addWidget(scroll)

    @pyqtSlot(tuple, dict)
    def update_sensor_status(self, key, data):
        """Callback invocado cuando llega telemetría para un SAC/SIC."""
        sac, sic = key
        current_time = data.get("local_time", 0.0)
        if current_time == 0.0:
            from player.radar_widget import SimulationTime
            current_time = SimulationTime.instance().now()

        if key not in self.cards:
            # Crear nueva tarjeta
            # Buscar si el sensor tiene un nombre en el registro global
            sensor_name = f"RADAR {sac}/{sic}"
            card = RadarStatusCard(key, sensor_name, self)
            self.cards[key] = card
            self.reorganizar_grid()

        self.cards[key].actualizar_tarjeta(data, current_time)

    def registrar_fruit(self, key, ssr_code, timestamp):
        """Registra un evento FRUIT para un sensor específico."""
        sac, sic = key
        if key not in self.cards:
            sensor_name = f"RADAR {sac}/{sic}"
            card = RadarStatusCard(key, sensor_name, self)
            self.cards[key] = card
            self.reorganizar_grid()
            
        self.cards[key].registrar_fruit_evento(ssr_code, timestamp)

    def reorganizar_grid(self):
        """Reorganiza la cuadrícula de tarjetas dinámicamente según el ancho disponible."""
        if not self.cards:
            return
        
        # Calcular columnas basadas en el ancho del panel (restando margen para el scroll)
        width = self.width()
        available_width = max(200, width - 30)
        card_min_width = 240
        
        max_cols = max(1, available_width // card_min_width)
        cols = min(max_cols, len(self.cards))

        # Quitar todas las tarjetas del layout
        for card in self.cards.values():
            self.grid.removeWidget(card)

        # Re-añadir en las nuevas posiciones
        row = 0
        col = 0
        for idx, card in enumerate(self.cards.values()):
            row = idx // cols
            col = idx % cols
            self.grid.addWidget(card, row, col)

        # Resetear stretches en todas las posibles filas/columnas de la grilla
        for c in range(self.grid.columnCount() + 2):
            self.grid.setColumnStretch(c, 0)
        for r in range(self.grid.rowCount() + 2):
            self.grid.setRowStretch(r, 0)

        # Establecer stretch en la columna posterior al final y en la fila posterior al final
        # para que todas las tarjetas se agrupen compactamente en la esquina superior izquierda
        self.grid.setColumnStretch(cols, 1)
        self.grid.setRowStretch(row + 1, 1)

        # Notificar cambio de geometría
        self.updateGeometry()

        # Calcular la altura necesaria basándose en las filas y dimensiones
        nrows = row + 1 if self.cards else 0
        card_height = 110
        spacing = 10
        margins_and_header = 20 + 30 + 10  # main_layout margins + header label + grid margins
        needed_height = margins_and_header + nrows * card_height + max(0, nrows - 1) * spacing + 15
        needed_height = max(150, min(needed_height, 450))

        # Adaptar el tamaño del QDockWidget (cuadro de diagnóstico) a la cantidad de sensores
        # Solo redimensionamos si la altura necesaria ha cambiado significativamente
        if needed_height != self.last_needed_height:
            self.last_needed_height = needed_height
            dock = self.parentWidget()
            if isinstance(dock, QDockWidget):
                if dock.isFloating():
                    dock.adjustSize()
                else:
                    main_win = dock.parentWidget()
                    if main_win and hasattr(main_win, "resizeDocks"):
                        main_win.resizeDocks([dock], [needed_height], Qt.Orientation.Vertical)

    def sizeHint(self):
        if not self.cards:
            return QSize(800, 150)
        
        width = self.width()
        available_width = max(200, width - 30)
        card_min_width = 240
        
        max_cols = max(1, available_width // card_min_width)
        cols = min(max_cols, len(self.cards))
        nrows = (len(self.cards) + cols - 1) // cols if cols else 0
        
        card_height = 110
        spacing = 10
        margins_and_header = 20 + 30 + 10
        
        needed_height = margins_and_header + nrows * card_height + max(0, nrows - 1) * spacing + 15
        needed_height = max(150, min(needed_height, 450))
        
        return QSize(width, needed_height)

    def minimumSizeHint(self):
        return QSize(200, 120)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.reorganizar_grid()

    def _check_timeouts(self):
        """Verifica timeouts de comunicación (15 segundos de inactividad)."""
        from player.radar_widget import SimulationTime
        now = SimulationTime.instance().now()
        for key, card in self.cards.items():
            delta = now - card.last_update_time
            # Manejar el rollover de medianoche (86400 segundos) en el tiempo de simulación
            if delta < -43200:
                delta += 86400
            elif delta > 43200:
                delta -= 86400

            if not card.is_offline and (delta > 15.0):
                card.marcar_offline()
