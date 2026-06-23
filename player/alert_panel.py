"""Base de los paneles de alerta (STCA / APW / MSAW) como overlay EMBEBIDO.

Antes eran ventanas `QDialog` (Qt.Tool, frameless). En Wayland/WSLg el gestor de
ventanas las ubicaba fuera del mapa y NO permitía a la app moverlas (move() se
ignora). Como widget HIJO del RadarWidget se dibujan dentro del mapa y el arrastre
funciona en todas las plataformas (Windows, X11, Wayland), porque no son ventanas
del sistema sino widgets internos posicionados en coordenadas del padre.

El arrastre se toma desde la barra de título (el QLabel propaga el clic al panel);
el listado de alertas conserva su click para resaltar la pista.
"""
from PyQt6.QtWidgets import QWidget
from PyQt6.QtCore import Qt, QPoint


class AlertOverlayPanel(QWidget):
    # Posición por defecto (x, y) relativa al RadarWidget; cada subclase la apila.
    DEFAULT_POS = (15, 15)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self._drag_pos = None
        self._user_moved = False
        self._radar_ref = None
        self.hide()                     # oculto hasta que haya alertas

    # ---- visibilidad / posicionamiento dentro del padre ----
    def _mostrar_overlay(self):
        """Muestra el panel como overlay; lo coloca por defecto la 1ª vez."""
        if not self._user_moved and self.parent() is not None:
            self.move(*self.DEFAULT_POS)
        self.raise_()
        self.show()

    def _clamp_to_parent(self, pos):
        p = self.parent()
        if p is None:
            return pos
        x = max(0, min(pos.x(), max(0, p.width() - self.width())))
        y = max(0, min(pos.y(), max(0, p.height() - self.height())))
        return QPoint(x, y)

    # ---- arrastre (coordenadas relativas al padre) ----
    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = e.position().toPoint()      # offset local dentro del panel
            e.accept()

    def mouseMoveEvent(self, e):
        if self._drag_pos is not None and (e.buttons() & Qt.MouseButton.LeftButton):
            nueva = self.mapToParent(e.position().toPoint()) - self._drag_pos
            self.move(self._clamp_to_parent(nueva))
            self._user_moved = True
            e.accept()

    def mouseReleaseEvent(self, e):
        self._drag_pos = None
