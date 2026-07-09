"""Diálogo de plan de vuelo FDP para un track del PPI.

Se abre desde el menú contextual (click derecho) de un track. Muestra los
datos del plan de vuelo correlacionado por callsign == ARCID. Replica el
look & feel del visor de System Messages (fondo oscuro, fuente Consolas,
título naranja). Independiente del diálogo de detalle radar.
"""
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QListWidget,
    QListWidgetItem, QPushButton,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor


# (etiqueta, clave en el dict del plan)
_CAMPOS = [
    ("ADEP (origen)",  "adep"),
    ("ADES (destino)", "ades"),
    ("Tipo aeronave",  "aircraft_type"),
    ("Estela (WTC)",   "wtc"),
    ("RFL solicitado", "requested_fl"),
    ("EOBT",           "eobt"),
    ("COP",            "cop"),
    ("Ruta",           "route"),
    ("Estado",         "status"),
]


class FlightPlanDialog(QDialog):
    """Visor del plan de vuelo FDP asociado a un track (estilo System Messages)."""

    def __init__(self, arcid: str, plan: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"FDP List - Plan de Vuelo {arcid}")
        self.resize(560, 420)
        self.setStyleSheet("background-color:#06090e; color:#fff; font-family:'Consolas';")

        layout = QVBoxLayout(self)

        titulo = QLabel("FDP LIST")
        titulo.setStyleSheet("color:#ff9900; font-weight:bold; font-size:11px; padding:4px;")
        layout.addWidget(titulo)

        ruta = f"{plan.get('adep') or '?'} -> {plan.get('ades') or '?'}"
        cancelado = (plan.get("status") == "CANCELLED")
        sub = QLabel(f"✈  {arcid}    {ruta}")
        sub.setStyleSheet(
            ("color:#888888;" if cancelado else "color:#b0c8e0;")
            + "font-weight:bold; font-size:12px; padding:2px 4px;")
        layout.addWidget(sub)

        if cancelado:
            aviso = QLabel("PLAN CANCELADO")
            aviso.setStyleSheet("color:#ff4444; font-weight:bold; padding:2px 4px;")
            layout.addWidget(aviso)

        self.lista = QListWidget()
        self.lista.setStyleSheet(
            "QListWidget{background:#0b1017;border:1px solid #1a2332;border-radius:4px;padding:5px;}"
            "QListWidget::item{border-bottom:1px solid #141b26;padding:6px;}"
            "QListWidget::item:selected{background:#1a2a40;color:#00ff66;}")
        self._poblar(plan)
        layout.addWidget(self.lista)

        botones = QHBoxLayout()
        botones.addStretch()
        self.btn_cerrar = QPushButton("Cerrar")
        self.btn_cerrar.setStyleSheet(
            "QPushButton{background:#162233;border:1px solid #283e5c;padding:8px 18px;font-weight:bold;}"
            "QPushButton:hover{background:#1e3047;border-color:#00ff66;}")
        self.btn_cerrar.clicked.connect(self.reject)
        botones.addWidget(self.btn_cerrar)
        layout.addLayout(botones)

    def _poblar(self, plan: dict):
        for etiqueta, clave in _CAMPOS:
            val = plan.get(clave)
            if val is None or val == "":
                continue
            item = QListWidgetItem(f"{etiqueta:<16}: {val}")
            item.setForeground(QColor("#b0c8e0"))
            self.lista.addItem(item)
