from PyQt6.QtWidgets import QVBoxLayout, QListWidget, QLabel, QListWidgetItem
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QBrush

from player.alert_panel import AlertOverlayPanel


class STCADialog(AlertOverlayPanel):
    DEFAULT_POS = (15, 15)

    def __init__(self, parent=None):
        super().__init__(parent)
        # Tamaño fijo mucho más fino y compacto para el panel táctico
        self.setFixedSize(280, 110)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(3)

        self.lbl_titulo = QLabel("⚠️ Short-Term Conflict Alert (STCA)")
        self.lbl_titulo.setStyleSheet("""
            color: #FFFFFF;
            background-color: rgba(255, 51, 51, 200);
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

        self.lista_alertas = QListWidget()
        self.lista_alertas.itemClicked.connect(self._on_item_clicked)
        self.lista_alertas.setStyleSheet("""
            QListWidget {
                background-color: rgba(11, 14, 20, 230);
                border: 1px solid rgba(255, 51, 51, 180);
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

    def actualizar_alertas(self, conflictos, radar_ref=None):
        """
        Actualiza el listado interactivo de alertas.
        conflictos: lista de tuplas (t1, t2, estado, tiempo)
        """
        self._radar_ref = radar_ref
        self.lista_alertas.clear()
        if not conflictos:
            if self.isVisible(): 
                self.hide()
            return

        for t1, t2, estado, tiempo, dist_h, dist_v in conflictos:
            if estado == 'VIOLATION':
                item_text = f"🚨 {t1} ↔ {t2} VIOLACIÓN ({dist_h:.1f}NM, {int(dist_v)}ft)"
                color = QColor("#FF3333")  # Rojo brillante
            else:
                item_text = f"⚠️ {t1} ↔ {t2} T-{tiempo}s ({dist_h:.1f}NM, {int(dist_v)}ft)"
                color = QColor("#FFFF00")  # Amarillo neón

            item = QListWidgetItem(item_text)
            item.setForeground(QBrush(color))
            item.setData(Qt.ItemDataRole.UserRole, (t1, t2))
            self.lista_alertas.addItem(item)

        if not self.isVisible():
            self._mostrar_overlay()

    def _on_item_clicked(self, item):
        par = item.data(Qt.ItemDataRole.UserRole)
        if par and self._radar_ref is not None:
            self._radar_ref.resaltar_tracks_alerta(list(par))

    def limpiar(self):
        self.lista_alertas.clear()
        if self.isVisible():
            self.hide()
