"""Controlador de reproducción flotante (vista delgada sobre PlaybackWorker).

No mantiene estado propio del simulador: emite señales que MainWindow conecta
a sus handlers existentes (_cargar_pcap / _toggle_play / _stop / velocidad /
seek) y expone setters para que MainWindow refleje el estado real del worker.
"""

from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QPushButton, QComboBox, QSlider,
    QTimeEdit, QFrame, QProgressBar
)
from PyQt6.QtCore import Qt, pyqtSignal, QTime


VELOCIDADES = ["1x", "2x", "5x", "10x", "30x"]


class PlaybackPlayerWidget(QWidget):
    """Reproductor flotante compacto estilo centro de control."""

    open_requested = pyqtSignal()
    playpause_requested = pyqtSignal()
    stop_requested = pyqtSignal()
    speed_changed = pyqtSignal(str)
    seek_requested = pyqtSignal(int)
    range_changed = pyqtSignal(int, int)   # (t0, t1) en segundos de ToD; -1 = sin límite

    def __init__(self, parent=None):
        # Ventana flotante con botón de minimizar (Qt.Tool no minimiza a la barra
        # de tareas en Windows; usamos Window con los hints explícitos).
        super().__init__(
            parent,
            Qt.WindowType.Window
            | Qt.WindowType.WindowTitleHint
            | Qt.WindowType.WindowSystemMenuHint
            | Qt.WindowType.WindowMinimizeButtonHint
            | Qt.WindowType.WindowCloseButtonHint
        )
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

        # Barra de progreso de carga/decodificación (oculta salvo durante el scan)
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setFormat("Cargando… %p%")
        self.progress.setVisible(False)
        root.addWidget(self.progress)

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

        # Separador
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color: #3A3F4B;")
        root.addWidget(sep)

        # Fila 4: tramo horario (recorte de reproducción)
        fila_tramo = QHBoxLayout()
        fila_tramo.addWidget(QLabel("Tramo:"))
        fila_tramo.addWidget(QLabel("Desde"))
        self.time_desde = QTimeEdit()
        self.time_desde.setDisplayFormat("HH:mm:ss")
        fila_tramo.addWidget(self.time_desde)
        fila_tramo.addWidget(QLabel("Hasta"))
        self.time_hasta = QTimeEdit()
        self.time_hasta.setDisplayFormat("HH:mm:ss")
        fila_tramo.addWidget(self.time_hasta)
        self.btn_aplicar_tramo = QPushButton("Aplicar")
        self.btn_aplicar_tramo.clicked.connect(self._emit_range)
        fila_tramo.addWidget(self.btn_aplicar_tramo)
        self.btn_limpiar_tramo = QPushButton("Todo")
        self.btn_limpiar_tramo.setToolTip("Reproducir el archivo completo (sin recorte)")
        self.btn_limpiar_tramo.clicked.connect(self._clear_range)
        fila_tramo.addWidget(self.btn_limpiar_tramo)
        root.addLayout(fila_tramo)

        self.set_enabled_transport(False)

    @staticmethod
    def _qtime_a_seg(t: QTime) -> int:
        return t.hour() * 3600 + t.minute() * 60 + t.second()

    def _emit_range(self):
        t0 = self._qtime_a_seg(self.time_desde.time())
        t1 = self._qtime_a_seg(self.time_hasta.time())
        self.range_changed.emit(t0, t1)

    def _clear_range(self):
        self.range_changed.emit(-1, -1)

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

    def set_loading_progress(self, pct: int):
        """Muestra el avance de carga/decodificación; se oculta al llegar a 100%."""
        pct = int(pct)
        self.progress.setVisible(0 <= pct < 100)
        self.progress.setValue(pct)

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
        for w in (self.time_desde, self.time_hasta,
                  self.btn_aplicar_tramo, self.btn_limpiar_tramo):
            w.setEnabled(on)

    def set_time_bounds(self, min_seg: int, max_seg: int):
        """Fija el rango disponible (seg de ToD) y precarga Desde/Hasta al total."""
        tmin = QTime(0, 0, 0).addSecs(int(min_seg) % 86400)
        tmax = QTime(0, 0, 0).addSecs(int(max_seg) % 86400)
        for ed in (self.time_desde, self.time_hasta):
            ed.blockSignals(True)
            ed.setMinimumTime(tmin)
            ed.setMaximumTime(tmax)
            ed.blockSignals(False)
        self.time_desde.setTime(tmin)
        self.time_hasta.setTime(tmax)
