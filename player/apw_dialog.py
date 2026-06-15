from PyQt6.QtWidgets import QDialog, QVBoxLayout, QListWidget, QLabel, QListWidgetItem
from PyQt6.QtCore import Qt, QPoint
from PyQt6.QtGui import QColor, QBrush

class APWDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("⚠️ APW")
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        
        self.setFixedSize(280, 110)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(3)
        
        self.lbl_titulo = QLabel("⚠️ Area Proximity Warning (APW)")
        self.lbl_titulo.setStyleSheet("""
            color: #FFFFFF;
            background-color: rgba(255, 128, 0, 200);
            font-weight: bold;
            padding: 4px;
            font-size: 9px;
            border-top-left-radius: 4px;
            border-top-right-radius: 4px;
            font-family: 'Segoe UI', Arial, sans-serif;
            letter-spacing: 0.5px;
        """)
        self.lbl_titulo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.lbl_titulo)

        self._drag_pos = None
        self._user_moved = False
        self._radar_ref = None

        self.lista_alertas = QListWidget()
        self.lista_alertas.itemClicked.connect(self._on_item_clicked)
        self.lista_alertas.setStyleSheet("""
            QListWidget {
                background-color: rgba(11, 14, 20, 230);
                border: 1px solid rgba(255, 128, 0, 180);
                border-bottom-left-radius: 4px;
                border-bottom-right-radius: 4px;
                font-weight: bold;
                font-size: 11px;
                color: #FFFFFF;
            }
            QListWidget::item {
                padding: 3px;
                border-bottom: 1px solid rgba(255, 255, 255, 15);
            }
        """)
        layout.addWidget(self.lista_alertas)

    def actualizar_alertas(self, alertas, radar_ref=None):
        """
        Actualiza el listado interactivo de alertas.
        alertas: lista de objetos AlertaAPW
        """
        self._radar_ref = radar_ref
        self.lista_alertas.clear()
        if not alertas:
            if self.isVisible():
                self.hide()
            return

        for a in alertas:
            # Encontrar Call Sign si está disponible en la referencia de pista
            lbl = a.track_id
            fl_str = "UNK"
            if radar_ref:
                t = radar_ref.tracks.get(a.track_id) or radar_ref.pending_tracks.get(a.track_id)
                if t:
                    if t.callsign:
                        lbl = t.callsign
                    if t.flight_level is not None:
                        fl_str = f"FL{int(t.flight_level)}"

            if a.tipo == 'VIOLATION':
                # VIOLATION rojo
                item_text = f"🚨 {a.area_name}: {lbl} ({fl_str}) VIOLACIÓN"
                color = QColor("#FF3333")  # Rojo
            else:
                # PREDICTED ámbar
                item_text = f"⚠️ {a.area_name}: {lbl} ({fl_str}) T-{int(a.eta_s)}s"
                color = QColor("#FFB040")  # Ámbar/Naranja

            item = QListWidgetItem(item_text)
            item.setForeground(QBrush(color))
            item.setData(Qt.ItemDataRole.UserRole, a.track_id)
            self.lista_alertas.addItem(item)

        if not self.isVisible():
            if self.parent() and not self._user_moved:
                parent = self.parent()
                # Posicionar en la esquina superior izquierda del widget del radar, justo abajo del STCA dialog
                pos = parent.mapToGlobal(parent.rect().topLeft())
                self.move(pos.x() + 15, pos.y() + 130)
            self.show()

    def _on_item_clicked(self, item):
        tid = item.data(Qt.ItemDataRole.UserRole)
        if tid and self._radar_ref is not None:
            self._radar_ref.resaltar_tracks_alerta([tid])

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = e.globalPosition().toPoint() - self.frameGeometry().topLeft()
            e.accept()

    def mouseMoveEvent(self, e):
        if self._drag_pos is not None and (e.buttons() & Qt.MouseButton.LeftButton):
            self.move(e.globalPosition().toPoint() - self._drag_pos)
            self._user_moved = True
            e.accept()

    def mouseReleaseEvent(self, e):
        self._drag_pos = None

    def limpiar(self):
        self.lista_alertas.clear()
        if self.isVisible():
            self.hide()
