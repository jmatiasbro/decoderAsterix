"""Controlador de reproducción flotante (vista delgada sobre PlaybackWorker).

No mantiene estado propio del simulador: emite señales que MainWindow conecta
a sus handlers existentes (_cargar_pcap / _toggle_play / _stop / velocidad /
seek) y expone setters para que MainWindow refleje el estado real del worker.
"""

from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QPushButton, QComboBox, QSlider
)
from PyQt6.QtCore import Qt, pyqtSignal


VELOCIDADES = ["1x", "2x", "5x", "10x", "30x"]


class PlaybackPlayerWidget(QWidget):
    """Reproductor flotante compacto estilo centro de control."""

    open_requested = pyqtSignal()
    playpause_requested = pyqtSignal()
    stop_requested = pyqtSignal()
    speed_changed = pyqtSignal(str)
    seek_requested = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent, Qt.WindowType.Tool)
        self.setWindowTitle("Reproductor")
        self.setMinimumWidth(360)
        self._build_ui()
        self._aplicar_estilo()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)

        # Fila 1: archivo
        fila_archivo = QHBoxLayout()
        self.btn_abrir = QPushButton("📂  Abrir archivo…")
        self.btn_abrir.clicked.connect(self.open_requested)
        fila_archivo.addWidget(self.btn_abrir)
        root.addLayout(fila_archivo)

        self.lbl_archivo = QLabel("— sin archivo —")
        self.lbl_archivo.setObjectName("lblArchivo")
        root.addWidget(self.lbl_archivo)

        # Fila 2: transporte
        fila_transporte = QHBoxLayout()
        self.btn_play = QPushButton("▶")
        self.btn_play.setToolTip("Reproducir / Pausa")
        self.btn_play.clicked.connect(self.playpause_requested)
        self.btn_stop = QPushButton("⬛")
        self.btn_stop.setToolTip("Detener")
        self.btn_stop.clicked.connect(self.stop_requested)
        for b in (self.btn_play, self.btn_stop):
            b.setFixedSize(44, 32)
            fila_transporte.addWidget(b)

        fila_transporte.addStretch(1)
        fila_transporte.addWidget(QLabel("Velocidad:"))
        self.combo_vel = QComboBox()
        self.combo_vel.addItems(VELOCIDADES)
        self.combo_vel.currentTextChanged.connect(self.speed_changed)
        fila_transporte.addWidget(self.combo_vel)
        root.addLayout(fila_transporte)

        # Fila 3: posición
        fila_pos = QHBoxLayout()
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(0, 100)
        self.slider.sliderReleased.connect(
            lambda: self.seek_requested.emit(self.slider.value()))
        fila_pos.addWidget(self.slider, 1)
        self.lbl_tiempo = QLabel("00:00:00")
        self.lbl_tiempo.setObjectName("lblTiempo")
        fila_pos.addWidget(self.lbl_tiempo)
        root.addLayout(fila_pos)

        self.set_enabled_transport(False)

    def _aplicar_estilo(self):
        self.setStyleSheet("""
            QWidget { background-color: #1B1E26; color: #E6E6E6; }
            QPushButton {
                background-color: #2D313C; border: 1px solid #3A3F4B;
                border-radius: 4px; padding: 4px 8px; font-size: 14px;
            }
            QPushButton:hover:enabled { background-color: #3A3F4B; }
            QPushButton:disabled { color: #666; }
            QComboBox { background-color: #2D313C; border: 1px solid #3A3F4B;
                        border-radius: 4px; padding: 2px 6px; }
            QLabel#lblArchivo { color: #9AA0AC; font-style: italic; }
            QLabel#lblTiempo { font-family: monospace; color: #5DD6A0; }
        """)

    # --- Setters dirigidos por MainWindow (única fuente de verdad = worker) ---
    def set_playing(self, playing: bool):
        self.btn_play.setText("❚❚" if playing else "▶")

    def set_progress(self, pct: int):
        self.slider.blockSignals(True)
        self.slider.setValue(int(pct))
        self.slider.blockSignals(False)

    def set_time_label(self, texto: str):
        self.lbl_tiempo.setText(texto)

    def set_filename(self, nombre: str):
        self.lbl_archivo.setText(nombre or "— sin archivo —")

    def set_speed_text(self, texto: str):
        i = self.combo_vel.findText(texto)
        if i >= 0:
            self.combo_vel.blockSignals(True)
            self.combo_vel.setCurrentIndex(i)
            self.combo_vel.blockSignals(False)

    def set_enabled_transport(self, on: bool):
        self.btn_play.setEnabled(on)
        self.btn_stop.setEnabled(on)
        self.slider.setEnabled(on)
