from PyQt6.QtWidgets import QDialog, QVBoxLayout, QListWidget, QLabel, QListWidgetItem
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QBrush


class MSAWDialog(QDialog):
    """Panel flotante de alertas MSAW (Minimum Safe Altitude Warning)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("⚠️ MSAW")
        # Sin WindowStaysOnTopHint: el panel flota sobre la app (es Tool con
        # parent) pero NO sobre otras aplicaciones del escritorio (p. ej. el IDE).
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setFixedSize(280, 110)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(3)

        self.lbl_titulo = QLabel("⛰️ Minimum Safe Altitude Warning (MSAW)")
        self.lbl_titulo.setStyleSheet("""
            color: #FFFFFF; background-color: rgba(200, 40, 40, 210);
            font-weight: bold; padding: 4px; font-size: 9px;
            border-top-left-radius: 4px; border-top-right-radius: 4px;
            font-family: 'Segoe UI', Arial, sans-serif; letter-spacing: 0.5px;
        """)
        self.lbl_titulo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.lbl_titulo)

        self._drag_pos = None
        self._user_moved = False
        self._radar_ref = None

        self.lista_alertas = QListWidget()
        self.lista_alertas.itemClicked.connect(self._on_item_clicked)
        self.lista_alertas.setStyleSheet("""
            QListWidget { background-color: rgba(11, 14, 20, 230);
                border: 1px solid rgba(200, 40, 40, 180);
                border-bottom-left-radius: 4px; border-bottom-right-radius: 4px;
                font-weight: bold; font-size: 11px; color: #FFFFFF; }
            QListWidget::item { padding: 3px;
                border-bottom: 1px solid rgba(255, 255, 255, 15); }
        """)
        layout.addWidget(self.lista_alertas)

    def actualizar_alertas(self, alertas, radar_ref=None):
        self._radar_ref = radar_ref
        self.lista_alertas.clear()
        if not alertas:
            if self.isVisible():
                self.hide()
            return

        for a in alertas:
            lbl = a.track_id
            if radar_ref:
                t = radar_ref.tracks.get(a.track_id) or radar_ref.pending_tracks.get(a.track_id)
                if t and t.callsign:
                    lbl = t.callsign
            if a.tipo == 'VIOLATION':
                txt = f"🚨 {a.icao}: {lbl} {a.alt_ft}ft < MSA {a.msa_ft}ft"
                color = QColor("#FF3333")
            else:
                txt = f"⚠️ {a.icao}: {lbl} desc→MSA {a.msa_ft}ft T-{int(a.eta_s)}s"
                color = QColor("#FFB040")
            item = QListWidgetItem(txt)
            item.setForeground(QBrush(color))
            item.setData(Qt.ItemDataRole.UserRole, a.track_id)
            self.lista_alertas.addItem(item)

        if not self.isVisible():
            if self.parent() and not self._user_moved:
                parent = self.parent()
                pos = parent.mapToGlobal(parent.rect().topLeft())
                self.move(pos.x() + 15, pos.y() + 250)
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
