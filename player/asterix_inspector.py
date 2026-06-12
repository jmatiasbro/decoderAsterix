"""
asterix_inspector.py — Inspector de bajo nivel de un registro ASTERIX.

Muestra el volcado hexadecimal/ASCII de los bytes crudos del bloque (persistidos
en DuckDB como `raw_bytes`) y un árbol con los campos ya decodificados del registro.

Paso 1: hex dump + árbol con los campos disponibles. El desglose Item-por-Item con
offsets y resaltado de bytes (deep-decode según EUROCONTROL) llega en el Paso 3.
"""
from typing import Optional

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QStandardItemModel, QStandardItem
from PyQt6.QtWidgets import (
    QDialog, QHBoxLayout, QVBoxLayout, QSplitter, QTreeView, QTextEdit,
    QLabel, QWidget,
)


def generar_hex_dump(data: bytes) -> str:
    """Volcado clásico: Dirección | Bytes Hex | Representación ASCII."""
    if not data:
        return "(sin bytes crudos para este registro)"
    lines = []
    for i in range(0, len(data), 16):
        chunk = data[i:i + 16]
        hex_vals = " ".join(f"{b:02X}" for b in chunk).ljust(47)
        ascii_vals = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
        lines.append(f"{i:04X}  {hex_vals}  |{ascii_vals}|")
    return "\n".join(lines)


# (etiqueta visible, clave en el dict de info)
_CAMPOS = [
    ("SAC/SIC", "sac_sic"),
    ("Track #", "track_number"),
    ("Mode-S (ICAO)", "mode_s"),
    ("Callsign", "callsign"),
    ("SSR (Mode 3/A)", "mode3a"),
    ("Nivel de vuelo", "flight_level"),
    ("Altitud (ft)", "altitude_ft"),
    ("Vel. tierra (kt)", "ground_speed"),
    ("Rumbo (°)", "track_angle"),
    ("Régimen vert. (ft/min)", "vertical_rate"),
    ("Azimut (°)", "raw_azimuth"),
    ("Rango (NM)", "raw_range"),
    ("Latitud", "lat"),
    ("Longitud", "lon"),
    ("ToD (s)", "timestamp"),
]


class AsterixInspectorDialog(QDialog):
    """Diálogo no-modal de inspección de un registro ASTERIX."""

    def __init__(self, raw_bytes: bytes = b"", info: Optional[dict] = None, parent=None):
        super().__init__(parent)
        self.raw_bytes = raw_bytes or b""
        self.info = info or {}
        self.setWindowTitle("Inspector de Paquete ASTERIX — Bajo Nivel")
        self.resize(960, 600)
        self.setModal(False)
        self._init_ui()
        self._cargar()

    def _init_ui(self):
        layout = QHBoxLayout(self)
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # --- Panel izquierdo: árbol de estructura ---
        izq = QWidget()
        vizq = QVBoxLayout(izq)
        vizq.setContentsMargins(0, 0, 0, 0)
        vizq.addWidget(QLabel("Estructura del registro:"))
        self.tree = QTreeView()
        self.tree_model = QStandardItemModel()
        self.tree_model.setHorizontalHeaderLabels(["Campo", "Valor (hex)", "Interpretación"])
        self.tree.setModel(self.tree_model)
        vizq.addWidget(self.tree)
        splitter.addWidget(izq)

        # --- Panel derecho: hex dump + datos de ingeniería ---
        der = QSplitter(Qt.Orientation.Vertical)

        cont_hex = QWidget()
        vhex = QVBoxLayout(cont_hex)
        vhex.setContentsMargins(0, 0, 0, 0)
        vhex.addWidget(QLabel("Volcado hexadecimal / ASCII:"))
        self.hex_viewer = QTextEdit()
        self.hex_viewer.setReadOnly(True)
        self.hex_viewer.setFont(QFont("Consolas", 10))
        self.hex_viewer.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        vhex.addWidget(self.hex_viewer)
        der.addWidget(cont_hex)

        cont_asc = QWidget()
        vasc = QVBoxLayout(cont_asc)
        vasc.setContentsMargins(0, 0, 0, 0)
        vasc.addWidget(QLabel("Datos de ingeniería decodificados:"))
        self.ascii_viewer = QTextEdit()
        self.ascii_viewer.setReadOnly(True)
        self.ascii_viewer.setFont(QFont("Consolas", 10))
        vasc.addWidget(self.ascii_viewer)
        der.addWidget(cont_asc)

        splitter.addWidget(der)
        splitter.setSizes([380, 580])
        layout.addWidget(splitter)

    def _cargar(self):
        self.hex_viewer.setText(generar_hex_dump(self.raw_bytes))

        self.tree_model.removeRows(0, self.tree_model.rowCount())
        root = self.tree_model.invisibleRootItem()
        cat = self.info.get("category")
        nodo_cat = QStandardItem(f"ASTERIX Categoría {cat}" if cat is not None else "ASTERIX")
        nodo_len = QStandardItem(f"{len(self.raw_bytes)} bytes")
        root.appendRow([nodo_cat, nodo_len, QStandardItem("")])

        filas_txt = []
        for etiqueta, clave in _CAMPOS:
            val = self.info.get(clave)
            if val is None or val == "" or val == "---" or val == "----":
                continue
            nodo_cat.appendRow([
                QStandardItem(etiqueta),
                QStandardItem(self._hex_de(clave, val)),
                QStandardItem(str(val)),
            ])
            filas_txt.append(f"{etiqueta:<24}: {val}")

        self.tree.expandAll()
        self.tree.resizeColumnToContents(0)
        self.tree.resizeColumnToContents(1)
        self.ascii_viewer.setText(
            "\n".join(filas_txt) if filas_txt else "(sin campos decodificados)")

    @staticmethod
    def _hex_de(clave: str, val) -> str:
        """Representación hex auxiliar para campos donde aporta (callsign ASCII)."""
        if clave == "callsign" and isinstance(val, str) and val.strip():
            try:
                return "0x" + val.strip().encode("ascii", "ignore").hex().upper()
            except Exception:
                return ""
        return ""
