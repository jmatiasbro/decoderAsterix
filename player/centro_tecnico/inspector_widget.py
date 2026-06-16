"""Wrapper embebible del Analizador de Paquetes ASTERIX."""
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel


class InspectorWidget(QWidget):
    def __init__(self, repo_db=None, worker=None, parent=None):
        super().__init__(parent)
        self._worker = worker
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self._dialog = None
        self.refresh(repo_db)

    def refresh(self, repo_db):
        # Limpiar layout anterior si existía algún widget
        layout = self.layout()
        if layout:
            while layout.count():
                item = layout.takeAt(0)
                widget = item.widget()
                if widget is not None:
                    widget.deleteLater()

        if repo_db is None:
            lbl = QLabel("Cargá una grabación para inspeccionar paquetes.")
            self.layout().addWidget(lbl)
            self._dialog = None
            return

        from player.packet_analyzer import AsterixAnalyzerWindow
        self._dialog = AsterixAnalyzerWindow(repo_db, self._worker, self)
        inner = self._dialog.layout()
        if inner is not None:
            host = QWidget()
            host.setLayout(inner)
            self.layout().addWidget(host)
        else:
            self.layout().addWidget(self._dialog)
