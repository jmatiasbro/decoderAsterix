"""Wrapper embebible del Analizador de Paquetes ASTERIX."""
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel


class InspectorWidget(QWidget):
    def __init__(self, repo_db=None, worker=None, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        if repo_db is None:
            lay.addWidget(QLabel("Cargá una grabación para inspeccionar paquetes."))
            self._dialog = None
            return
        from player.packet_analyzer import AsterixAnalyzerWindow
        self._dialog = AsterixAnalyzerWindow(repo_db, worker, self)
        inner = self._dialog.layout()
        if inner is not None:
            host = QWidget()
            host.setLayout(inner)
            lay.addWidget(host)
        else:
            lay.addWidget(self._dialog)
