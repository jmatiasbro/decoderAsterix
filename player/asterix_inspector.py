"""
asterix_inspector.py — Inspector de bajo nivel de un registro ASTERIX.

Muestra el volcado hexadecimal/ASCII de los bytes crudos del bloque (persistidos
en DuckDB como `raw_bytes`) y un árbol con la estructura canónica
    Data Block → Data Record → Data Item I0XX/YYY  (+ Summary)
mapeando los campos ya decodificados a sus códigos de Item ASTERIX.

Paso 2: formato/árbol con los campos disponibles. El desglose Item-por-Item con
TODOS los subcampos, offsets y resaltado de bytes en el hex (deep-decode según
EUROCONTROL) llega en el Paso 3.
"""
from typing import Optional, List, Tuple

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QStandardItemModel, QStandardItem
from PyQt6.QtWidgets import (
    QDialog, QHBoxLayout, QVBoxLayout, QSplitter, QTreeView, QTextEdit,
    QLabel, QWidget, QHeaderView,
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


def _fmt_tod(s) -> str:
    """Segundos-del-día → HH:MM:SS.mmm (formato del visor de referencia)."""
    try:
        s = float(s) % 86400.0
        h = int(s // 3600)
        m = int((s % 3600) // 60)
        return f"{h:02d}:{m:02d}:{s % 60:06.3f}"
    except (TypeError, ValueError):
        return str(s)


def _num(v) -> str:
    try:
        f = float(v)
        return f"{f:g}"
    except (TypeError, ValueError):
        return str(v)


def _vacio(v) -> bool:
    return v is None or v in ("", "---", "----")


# Definición por categoría: (código de Item, [(etiqueta, clave_en_info), ...]).
# El Item se muestra solo si al menos uno de sus campos tiene valor; el Summary
# concatena los subcampos presentes. El orden imita el orden de FSPEC.
_SPEC = {
    1: [
        ("I001/010", [("SAC", "sac"), ("SIC", "sic")]),
        ("I001/141", [("TOD", "timestamp")]),
        ("I001/040", [("RHO", "raw_range"), ("THETA", "raw_azimuth")]),
        ("I001/070", [("MODE3A", "mode3a")]),
        ("I001/090", [("FL", "flight_level")]),
        ("I001/161", [("TRK", "track_number")]),
        ("I001/130", [("LAT", "lat"), ("LON", "lon")]),
    ],
    21: [
        ("I021/010", [("SAC", "sac"), ("SIC", "sic")]),
        ("I021/080", [("ICAO", "mode_s")]),
        ("I021/073", [("TOD", "timestamp")]),
        ("I021/130", [("LAT", "lat"), ("LON", "lon")]),
        ("I021/145", [("FL", "flight_level")]),
        ("I021/070", [("MODE3A", "mode3a")]),
        ("I021/160", [("GS", "ground_speed"), ("HDG", "track_angle")]),
        ("I021/155", [("V/R", "vertical_rate")]),
        ("I021/170", [("ID", "callsign")]),
        ("I021/161", [("TRK", "track_number")]),
    ],
    48: [
        ("I048/010", [("SAC", "sac"), ("SIC", "sic")]),
        ("I048/140", [("TOD", "timestamp")]),
        ("I048/040", [("RHO", "raw_range"), ("THETA", "raw_azimuth")]),
        ("I048/070", [("MODE3A", "mode3a")]),
        ("I048/090", [("FL", "flight_level")]),
        ("I048/220", [("ICAO", "mode_s")]),
        ("I048/240", [("ID", "callsign")]),
        ("I048/161", [("TRK", "track_number")]),
        ("I048/200", [("GS", "ground_speed"), ("HDG", "track_angle")]),
    ],
    62: [
        ("I062/010", [("SAC", "sac"), ("SIC", "sic")]),
        ("I062/040", [("TRK", "track_number")]),
        ("I062/070", [("TOD", "timestamp")]),
        ("I062/105", [("LAT", "lat"), ("LON", "lon")]),
        ("I062/136", [("FL", "flight_level")]),
        ("I062/060", [("MODE3A", "mode3a")]),
        ("I062/380", [("ICAO", "mode_s")]),
        ("I062/185", [("GS", "ground_speed"), ("HDG", "track_angle")]),
        ("I062/220", [("V/R", "vertical_rate")]),
        ("I062/245", [("ID", "callsign")]),
    ],
}


def _fmt_campo(clave: str, val) -> str:
    if clave == "timestamp":
        return _fmt_tod(val)
    if clave in ("lat", "lon"):
        return f"{_num(val)}°"
    if clave in ("raw_azimuth", "track_angle"):
        return f"{_num(val)}°"
    if clave == "raw_range":
        return f"{_num(val)} NM"
    if clave == "ground_speed":
        return f"{_num(val)} kt"
    if clave == "vertical_rate":
        return f"{_num(val)} ft/min"
    return str(val)


def _items_de_registro(info: dict) -> List[Tuple[str, str]]:
    """Lista [(código_item, summary)] del registro según su categoría."""
    cat = info.get("category")
    spec = _SPEC.get(int(cat)) if cat is not None else None
    if not spec:
        return []
    salida = []
    for code, campos in spec:
        partes = []
        for etiqueta, clave in campos:
            v = info.get(clave)
            if _vacio(v):
                continue
            partes.append(f"{etiqueta}:{_fmt_campo(clave, v)}")
        if partes:
            salida.append((code, "  ".join(partes)))
    return salida


class AsterixInspectorDialog(QDialog):
    """Diálogo no-modal de inspección de un registro ASTERIX."""

    def __init__(self, raw_bytes: bytes = b"", info: Optional[dict] = None, parent=None):
        super().__init__(parent)
        self.raw_bytes = raw_bytes or b""
        self.info = dict(info or {})
        # Derivar SAC/SIC numéricos a partir de "sac/sic"
        ss = str(self.info.get("sac_sic") or "")
        if "/" in ss:
            sac, sic = ss.split("/", 1)
            self.info.setdefault("sac", sac.strip())
            self.info.setdefault("sic", sic.strip())
        self.setWindowTitle("Inspector de Paquete ASTERIX — Bajo Nivel")
        self.resize(980, 600)
        self.setModal(False)
        self._init_ui()
        self._cargar()

    def _init_ui(self):
        layout = QHBoxLayout(self)
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # --- Panel izquierdo: árbol Data Block / Data Record / Data Item ---
        izq = QWidget()
        vizq = QVBoxLayout(izq)
        vizq.setContentsMargins(0, 0, 0, 0)
        self.tree = QTreeView()
        self.tree_model = QStandardItemModel()
        self.tree_model.setHorizontalHeaderLabels(["Dataitem", "Summary"])
        self.tree.setModel(self.tree_model)
        self.tree.setAlternatingRowColors(True)
        self.tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
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
        splitter.setSizes([460, 520])
        layout.addWidget(splitter)

    def _cargar(self):
        self.hex_viewer.setText(generar_hex_dump(self.raw_bytes))

        self.tree_model.removeRows(0, self.tree_model.rowCount())
        root = self.tree_model.invisibleRootItem()

        nodo_block = QStandardItem("Data Block 1")
        root.appendRow([nodo_block, QStandardItem("")])
        nodo_record = QStandardItem("Data Record 1")
        cat = self.info.get("category")
        nodo_record.setData(cat)
        nodo_block.appendRow([nodo_record, QStandardItem(f"CAT{cat:03d}" if cat else "")])

        items = _items_de_registro(self.info)
        filas_txt = []
        for code, summary in items:
            nodo_record.appendRow([
                QStandardItem(f"Data Item {code}"),
                QStandardItem(summary),
            ])
            filas_txt.append(f"{code:<10} {summary}")

        if not items:
            nodo_record.appendRow([
                QStandardItem("(sin desglose para esta categoría)"),
                QStandardItem(""),
            ])

        self.tree.expandAll()
        self.tree.resizeColumnToContents(0)
        self.ascii_viewer.setText(
            "\n".join(filas_txt) if filas_txt else "(sin campos decodificados)")
