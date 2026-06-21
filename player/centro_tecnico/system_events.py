"""Lista de Mensajes de Sistema (eventos ATSEP) con ACK + log persistente.

Separa la *cola visible efímera* (se limpia con ACK) de la *auditoría
permanente* en disco. El bus es thread-safe: los productores (cadena de
safety-nets, desconexión de sensores) corren en otros hilos y publican vía
señal con conexión en cola; el render y el log ocurren en el hilo GUI.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path

from PyQt6.QtCore import Qt, QObject, pyqtSignal
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem,
    QPushButton, QLabel,
)

NIVELES = ("CRITICAL", "WARNING", "INFO")
_COLORES = {"CRITICAL": "#ff3333", "WARNING": "#ffcc00", "INFO": "#00d9ff"}

_LOG_DIR = Path(__file__).resolve().parents[2] / "logs"


def _build_logger() -> logging.Logger:
    log = logging.getLogger("SystemATM_Logger")
    if log.handlers:                       # evita duplicar handlers en reimport
        return log
    log.setLevel(logging.INFO)
    log.propagate = False
    _LOG_DIR.mkdir(exist_ok=True)
    fmt = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s",
                            datefmt="%Y-%m-%d %H:%M:%S")
    fh = RotatingFileHandler(_LOG_DIR / "system_events.log",
                             maxBytes=2_000_000, backupCount=5, encoding="utf-8")
    fh.setFormatter(fmt)
    log.addHandler(fh)
    return log


_logger = _build_logger()


@dataclass
class SystemEvent:
    nivel: str
    origen: str
    desc: str
    ts: datetime = field(default_factory=datetime.now)

    @property
    def texto(self) -> str:
        return f"[{self.ts:%H:%M:%S}] - {self.origen.upper()} -> {self.desc}"


class SystemEventBus(QObject):
    """Modelo de eventos + auditoría. Vive en el hilo GUI; thread-safe en publish."""

    evento_agregado = pyqtSignal(object)      # SystemEvent
    cola_cambiada = pyqtSignal()              # alta/baja: refrescar badges
    _publicar = pyqtSignal(str, str, str)     # marshalling worker -> GUI

    def __init__(self, parent=None):
        super().__init__(parent)
        self.activos: list[SystemEvent] = []
        # QueuedConnection: el slot corre siempre en el hilo del bus (GUI).
        self._publicar.connect(self._procesar, Qt.ConnectionType.QueuedConnection)

    def inyectar(self, nivel: str, origen: str, desc: str):
        """Punto de entrada para los productores (cualquier hilo)."""
        self._publicar.emit(nivel if nivel in NIVELES else "INFO", origen, desc)

    def _procesar(self, nivel: str, origen: str, desc: str):
        ev = SystemEvent(nivel, origen, desc)
        self.activos.append(ev)
        getattr(_logger, nivel.lower())(f"Inyección - Origen: {origen} | {desc}")
        self.evento_agregado.emit(ev)
        self.cola_cambiada.emit()

    @property
    def pendientes(self) -> int:
        return len(self.activos)

    @property
    def hay_criticos(self) -> bool:
        return any(e.nivel == "CRITICAL" for e in self.activos)

    def ack(self, ev: SystemEvent):
        if ev in self.activos:
            self.activos.remove(ev)
        _logger.info(f"ACK OPERADOR - Removido -> Origen: {ev.origen} | {ev.desc}")
        self.cola_cambiada.emit()

    def ack_all(self):
        n = len(self.activos)
        if n:
            _logger.warning(f"ACK GENERAL - Limpieza masiva: {n} eventos removidos.")
        self.activos.clear()
        self.cola_cambiada.emit()


class SystemMessagesDialog(QDialog):
    """Visor de la cola activa. Sólo renderiza: el estado vive en el bus."""

    def __init__(self, bus: SystemEventBus, parent=None):
        super().__init__(parent)
        self.bus = bus
        self.setWindowTitle("System Messages List - Lista Activa de Eventos")
        self.resize(750, 400)
        self._init_ui()
        self._recargar()
        self.bus.evento_agregado.connect(self._on_evento)

    def _init_ui(self):
        self.setStyleSheet("background-color:#06090e; color:#fff; font-family:'Consolas';")
        layout = QVBoxLayout(self)

        titulo = QLabel("VENTANA DE MENSAJES DE SISTEMA ACTIVO")
        titulo.setStyleSheet("color:#ff9900; font-weight:bold; font-size:11px; padding:4px;")
        layout.addWidget(titulo)

        self.lista = QListWidget()
        self.lista.setStyleSheet(
            "QListWidget{background:#0b1017;border:1px solid #1a2332;border-radius:4px;padding:5px;}"
            "QListWidget::item{border-bottom:1px solid #141b26;padding:6px;}"
            "QListWidget::item:selected{background:#1a2a40;color:#00ff66;}")
        layout.addWidget(self.lista)

        botones = QHBoxLayout()
        self.btn_ack = QPushButton("✔️ Dar Conocimiento (Ack)")
        self.btn_ack.setStyleSheet(
            "QPushButton{background:#162233;border:1px solid #283e5c;padding:10px;font-weight:bold;}"
            "QPushButton:hover{background:#1e3047;border-color:#00ff66;}")
        self.btn_ack.clicked.connect(self._ack)

        self.btn_ack_all = QPushButton("📋 Conocimiento General (Ack All)")
        self.btn_ack_all.setStyleSheet(
            "QPushButton{background:#1c1d24;border:1px solid #31333d;padding:10px;}"
            "QPushButton:hover{background:#262933;border-color:#ff9900;}")
        self.btn_ack_all.clicked.connect(self._ack_all)

        botones.addWidget(self.btn_ack)
        botones.addWidget(self.btn_ack_all)
        layout.addLayout(botones)

    def _add_item(self, ev: SystemEvent):
        item = QListWidgetItem(ev.texto)
        item.setData(Qt.ItemDataRole.UserRole, ev)
        item.setForeground(QColor(_COLORES.get(ev.nivel, _COLORES["INFO"])))
        self.lista.addItem(item)

    def _recargar(self):
        self.lista.clear()
        for ev in self.bus.activos:
            self._add_item(ev)

    def _on_evento(self, ev: SystemEvent):
        self._add_item(ev)

    def _ack(self):
        item = self.lista.currentItem()
        if not item:
            return
        self.bus.ack(item.data(Qt.ItemDataRole.UserRole))
        self.lista.takeItem(self.lista.row(item))

    def _ack_all(self):
        self.bus.ack_all()
        self.lista.clear()
