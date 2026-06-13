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
from PyQt6.QtGui import (
    QFont, QStandardItemModel, QStandardItem, QTextCursor, QColor, QTextCharFormat,
)
from PyQt6.QtWidgets import (
    QDialog, QHBoxLayout, QVBoxLayout, QSplitter, QTreeView, QTextEdit,
    QLabel, QWidget, QHeaderView, QTextBrowser,
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
    34: [
        ("I034/010", [("SAC", "sac"), ("SIC", "sic")]),
        ("I034/000", [("TYPE", "msg_type")]),
        ("I034/030", [("TOD", "timestamp")]),
        ("I034/020", [("SEC", "sector_number"), ("AZI", "azimuth")]),
        ("I034/041", [("PERIOD", "rotation_period"), ("RPM", "antenna_rpm")]),
    ],
    23: [
        ("I023/010", [("SAC", "sac"), ("SIC", "sic")]),
        ("I023/020", [("STATE", "system_state"), ("UPS", "ups_active")]),
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


# Nombres oficiales EUROCONTROL por Item (los más frecuentes; los que falten se
# muestran solo con el código). Clave: código "I0XX/YYY".
ITEM_NAMES = {
    # CAT048
    "I048/010": "Data Source Identifier", "I048/140": "Time of Day",
    "I048/020": "Target Report Descriptor",
    "I048/040": "Measured Position in Polar Co-ordinates",
    "I048/070": "Mode-3/A Code in Octal Representation",
    "I048/090": "Flight Level in Binary Representation",
    "I048/130": "Radar Plot Characteristics", "I048/220": "Aircraft Address",
    "I048/240": "Aircraft Identification", "I048/250": "Mode S MB Data",
    "I048/161": "Track Number",
    "I048/042": "Calculated Position in Cartesian Co-ordinates",
    "I048/200": "Calculated Track Velocity in Polar Co-ordinates",
    "I048/170": "Track Status", "I048/210": "Track Quality",
    "I048/030": "Warning/Error Conditions",
    "I048/080": "Mode-3/A Code Confidence Indicator",
    "I048/100": "Mode-C Code and Confidence Indicator",
    "I048/110": "Height Measured by 3D Radar",
    "I048/120": "Radial Doppler Speed",
    "I048/230": "Communications/ACAS Capability and Flight Status",
    "I048/260": "ACAS Resolution Advisory Report",
    "I048/055": "Mode-1 Code in Octal Representation",
    "I048/050": "Mode-2 Code in Octal Representation",
    "I048/065": "Mode-1 Code Confidence Indicator",
    "I048/060": "Mode-2 Code Confidence Indicator",
    # CAT021 (ADS-B)
    "I021/010": "Data Source Identification", "I021/040": "Target Report Descriptor",
    "I021/161": "Track Number", "I021/015": "Service Identification",
    "I021/071": "Time of Applicability for Position",
    "I021/130": "Position in WGS-84 Co-ordinates",
    "I021/131": "High-Resolution Position in WGS-84 Co-ordinates",
    "I021/072": "Time of Applicability for Velocity", "I021/080": "Target Address",
    "I021/073": "Time of Message Reception of Position",
    "I021/075": "Time of Message Reception of Velocity",
    "I021/140": "Geometric Height", "I021/090": "Quality Indicators",
    "I021/210": "MOPS Version", "I021/070": "Mode 3/A Code",
    "I021/145": "Flight Level", "I021/155": "Barometric Vertical Rate",
    "I021/160": "Airborne Ground Vector", "I021/165": "Track Angle Rate",
    "I021/170": "Target Identification", "I021/020": "Emitter Category",
    "I021/146": "Selected Altitude", "I021/200": "Target Status",
    # CAT062 (system track)
    "I062/010": "Data Source Identifier", "I062/015": "Service Identification",
    "I062/070": "Time of Track Information",
    "I062/105": "Calculated Position in WGS-84 Co-ordinates",
    "I062/100": "Calculated Position in Cartesian Co-ordinates",
    "I062/185": "Calculated Track Velocity in Cartesian Co-ordinates",
    "I062/210": "Calculated Acceleration (Cartesian)",
    "I062/060": "Track Mode 3/A Code", "I062/245": "Target Identification",
    "I062/380": "Aircraft Derived Data", "I062/040": "Track Number",
    "I062/080": "Track Status", "I062/290": "System Track Update Ages",
    "I062/200": "Mode of Movement", "I062/295": "Track Data Ages",
    "I062/136": "Measured Flight Level",
    "I062/130": "Calculated Track Geometric Altitude",
    "I062/135": "Calculated Track Barometric Altitude",
    "I062/220": "Calculated Rate of Climb/Descent",
    "I062/390": "Flight Plan Related Data", "I062/500": "Estimated Accuracies",
    # CAT001
    "I001/010": "Data Source Identifier", "I001/020": "Target Report Descriptor",
    "I001/040": "Measured Position in Polar Co-ordinates",
    "I001/070": "Mode-3/A Code in Octal Representation",
    "I001/090": "Mode-C Code in Binary Representation",
    "I001/130": "Radar Plot Characteristics", "I001/141": "Truncated Time of Day",
    "I001/131": "Received Power", "I001/161": "Track/Plot Number",
    "I001/170": "Track Status", "I001/120": "Measured Radial Doppler Speed",
    # CAT034
    "I034/010": "Data Source Identifier", "I034/000": "Message Type",
    "I034/030": "Time of Day", "I034/020": "Sector Number",
    "I034/041": "Antenna Rotation Speed",
    "I034/050": "System Configuration and Status",
    "I034/060": "System Processing Mode", "I034/070": "Message Count Values",
    # CAT023
    "I023/010": "Data Source Identifier", "I023/020": "System Status",
}


def _item_name(code: str) -> str:
    return ITEM_NAMES.get(code, "")


def _plot_a_info(p: dict) -> dict:
    """Normaliza un plot crudo del decoder al formato que usa _items_de_registro."""
    info = dict(p)
    sac, sic = p.get("sac"), p.get("sic")
    if sac is not None:
        info["sac"] = str(sac)
        info["sac_sic"] = f"{sac}/{sic}"
    if sic is not None:
        info["sic"] = str(sic)
    m3a = p.get("mode_3a")
    if isinstance(m3a, int):
        info["mode3a"] = f"{m3a:04o}"
    if p.get("latitude") is not None:
        info["lat"] = p["latitude"]
    if p.get("longitude") is not None:
        info["lon"] = p["longitude"]
    ed = p.get("extra_data", {}) or {}
    if ed.get("ground_speed_nms") is not None:
        info["ground_speed"] = ed["ground_speed_nms"] * 3600.0
    if ed.get("track_angle") is not None:
        info["track_angle"] = ed["track_angle"]
    # Copiar llaves de extra_data directamente al info
    for k, v in ed.items():
        info.setdefault(k, v)
    return info


def deep_records(category, raw_bytes):
    """Re-decodifica el bloque y devuelve una lista de Data Records; cada uno es
    (info_normalizada, [(código_item, byte_ini, byte_fin), ...]). Lista vacía si la
    categoría aún no tiene deep-decode. Usa el decoder real (camino normal intacto)."""
    if not raw_bytes or len(raw_bytes) < 4:
        return []
    try:
        cat = int(category)
        decoder = None
        if cat == 48:
            from decoder.decoders import cat048 as decoder
        elif cat == 21:
            from decoder.decoders import cat021 as decoder
        elif cat == 1:
            from decoder.decoders import cat001 as decoder
        elif cat == 34:
            from decoder.decoders import cat034 as decoder
        elif cat == 23:
            from decoder.decoders import cat023 as decoder
        if decoder is None:
            return []
        acc: list = []
        plots = decoder.decode(bytes(raw_bytes), 3, len(raw_bytes), cat, record_offsets=acc)
        por_rec: dict = {}
        for ridx, code, s, e in acc:
            por_rec.setdefault(ridx, []).append((code, s, e))
        salida = []
        for ridx in sorted(por_rec):
            plot = plots[ridx] if ridx < len(plots) else {}
            info = _plot_a_info(plot)
            info["category"] = cat
            salida.append((info, por_rec[ridx]))
        return salida
    except Exception:
        return []


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


def _u(data: bytes, a: int, b: int) -> int:
    return int.from_bytes(data[a:b], "big")


def _sf_sacsic(d):
    return [("SAC (System Area Code)", d[0]), ("SIC (System Id Code)", d[1])]


def _sf_048_140(d):
    tod = _u(d, 0, 3) / 128.0
    return [("Time of Day (s) LSB=1/128", f"{tod:.3f}"), ("ToD HH:MM:SS.mmm", _fmt_tod(tod))]


def _sf_048_040(d):
    rho = _u(d, 0, 2) / 256.0
    theta = _u(d, 2, 4) * 360.0 / 65536.0
    return [("RHO (NM) LSB=1/256", f"{rho:.4f}"),
            ("THETA (deg) LSB=360/2^16", f"{theta:.4f}")]


def _sf_048_070(d):
    raw = _u(d, 0, 2)
    return [("V (1=Validated)", 0 if raw & 0x8000 else 1),
            ("G (1=Garbled)", 1 if raw & 0x4000 else 0),
            ("L (1=Smoothed)", 1 if raw & 0x2000 else 0),
            ("Mode-3/A code (octal)", f"{raw & 0x0FFF:04o}")]


def _sf_048_090(d):
    raw = _u(d, 0, 2)
    fl = raw & 0x3FFF
    if fl & 0x2000:
        fl -= 0x4000
    return [("V (1=Validated)", 0 if raw & 0x8000 else 1),
            ("G (1=Garbled)", 1 if raw & 0x4000 else 0),
            ("Flight Level LSB=1/4", f"{fl * 0.25:.2f}")]


def _sf_048_220(d):
    return [("Aircraft Address (ICAO 24-bit)", d[:3].hex().upper())]


def _sf_048_240(d):
    from decoder.asterix_utils import _decode_callsign
    return [("Aircraft Identification", _decode_callsign(d[:6]))]


def _sf_048_161(d):
    return [("Track Number", _u(d, 0, 2))]


def _sf_034_020(d):
    raw = d[0]
    return [("Sector Number (raw)", raw),
            ("Antenna Azimuth (deg) LSB=360/256", f"{raw * 360.0 / 256.0:.4f}")]


def _sf_023_020(d):
    """I023/020 System Status (1 byte): estado del sistema + bits de servicio."""
    b = d[0]
    estados = {0: "Running", 1: "Failed", 2: "Degraded", 3: "Undefined"}
    st = (b >> 6) & 0x03
    return [("System State (bits 8-7)", f"{st} ({estados.get(st, '?')})"),
            ("UPS active (bit 3)", 1 if b & 0x04 else 0),
            ("Byte (hex)", f"{b:02X}")]


# Decodificadores de subcampos por Item (Detailed Description). Se amplían de a poco.
SUBFIELD_DECODERS = {
    "I048/010": _sf_sacsic, "I021/010": _sf_sacsic, "I062/010": _sf_sacsic,
    "I001/010": _sf_sacsic, "I034/010": _sf_sacsic, "I023/010": _sf_sacsic,
    "I048/140": _sf_048_140, "I048/040": _sf_048_040, "I048/070": _sf_048_070,
    "I048/090": _sf_048_090, "I048/220": _sf_048_220, "I048/240": _sf_048_240,
    "I048/161": _sf_048_161, "I034/020": _sf_034_020, "I023/020": _sf_023_020,
}


def _subfields(code: str, data: bytes):
    fn = SUBFIELD_DECODERS.get(code)
    if not fn:
        return []
    try:
        return [(n, str(v)) for n, v in fn(data)]
    except Exception:
        return []


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
        self.tree.selectionModel().currentChanged.connect(self._on_sel)
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

        cont_det = QWidget()
        vdet = QVBoxLayout(cont_det)
        vdet.setContentsMargins(0, 0, 0, 0)
        vdet.addWidget(QLabel("Detalle del campo seleccionado:"))
        self.detail = QTextBrowser()
        self.detail.setOpenExternalLinks(True)
        vdet.addWidget(self.detail)
        der.addWidget(cont_det)

        splitter.addWidget(der)
        splitter.setSizes([460, 520])
        der.setSizes([200, 400])
        layout.addWidget(splitter)

    def _etiqueta_item(self, code: str) -> str:
        nombre = _item_name(code)
        return f"Data Item {code} — {nombre}" if nombre else f"Data Item {code}"

    def _cargar(self):
        self.hex_viewer.setText(generar_hex_dump(self.raw_bytes))

        self.tree_model.removeRows(0, self.tree_model.rowCount())
        root = self.tree_model.invisibleRootItem()
        cat = self.info.get("category")

        nodo_block = QStandardItem("Data Block 1")
        root.appendRow([nodo_block, QStandardItem(f"CAT{cat:03d}" if cat else "")])

        filas_txt = []
        records = deep_records(cat, self.raw_bytes)

        if records:
            # Deep-decode: todos los Data Records del bloque, con offsets y nombres.
            for ridx, (info, items) in enumerate(records):
                nodo_rec = QStandardItem(f"Data Record {ridx + 1}")
                nodo_block.appendRow([nodo_rec, QStandardItem("")])
                summ_map = {c: s for c, s in _items_de_registro(info)}
                filas_txt.append(f"--- Data Record {ridx + 1} ---")
                for code, start, end in items:
                    summary = summ_map.get(code) or self._hex_rango(start, end)
                    n_item = QStandardItem(self._etiqueta_item(code))
                    n_item.setData((code, start, end, summary), Qt.ItemDataRole.UserRole)
                    nodo_rec.appendRow([n_item, QStandardItem(summary)])
                    filas_txt.append(f"{code:<10} [{start:>3}:{end:<3}]  {summary}")
        else:
            # Fallback (categorías sin deep-decode todavía): solo campos decodificados
            # del registro clickeado, sin offsets/resaltado.
            nodo_rec = QStandardItem("Data Record 1")
            nodo_block.appendRow([nodo_rec, QStandardItem("")])
            for code, summary in _items_de_registro(self.info):
                nodo_rec.appendRow([
                    QStandardItem(self._etiqueta_item(code)), QStandardItem(summary)])
                filas_txt.append(f"{code:<10} {summary}")
            if not filas_txt:
                nodo_rec.appendRow([
                    QStandardItem("(sin desglose para esta categoría)"), QStandardItem("")])

        self.tree.expandAll()
        self.tree.resizeColumnToContents(0)
        self.detail.setHtml(
            "<p style='color:#666'>Seleccioná un <b>Data Item</b> en el árbol para ver "
            "sus bytes (hex y binario) y su desglose.</p>")

    def _hex_rango(self, start: int, end: int) -> str:
        return " ".join(f"{b:02X}" for b in self.raw_bytes[start:end])

    def _on_sel(self, current, previous):
        if not current.isValid():
            self.hex_viewer.setExtraSelections([])
            return
        idx0 = current.sibling(current.row(), 0)
        item = self.tree_model.itemFromIndex(idx0)
        data = item.data(Qt.ItemDataRole.UserRole) if item is not None else None
        if data:
            code, start, end, summary = data
            self._resaltar(int(start), int(end))
            self.detail.setHtml(self._html_detalle_item(code, int(start), int(end), summary))
        else:
            self.hex_viewer.setExtraSelections([])
            self.detail.setHtml(
                "<p style='color:#666'>(seleccioná un Data Item para ver su detalle)</p>")

    def _html_detalle_item(self, code: str, start: int, end: int, summary: str) -> str:
        nombre = _item_name(code)
        data = self.raw_bytes[start:end]

        # Raw Data en Hexadecimal + ASCII: una columna por octeto
        oct_hdr = "<td bgcolor='#eef3e2'></td>" + "".join(
            f"<td align='center' bgcolor='#eef3e2'><b>Octet {i + 1}</b></td>"
            for i in range(len(data)))
        hex_cells = "<td><b>Hex</b></td>" + "".join(
            f"<td align='center'>{b:02X}</td>" for b in data)
        ascii_cells = "<td><b>ASCII</b></td>" + "".join(
            f"<td align='center'>{(chr(b) if 32 <= b < 127 else '.')}</td>" for b in data)
        hex_table = (
            "<table border='1' cellspacing='0' cellpadding='4'>"
            f"<tr>{oct_hdr}</tr><tr>{hex_cells}</tr>"
            f"<tr bgcolor='#fbfbf0'>{ascii_cells}</tr></table>")

        # Raw Data in Binary: una fila por octeto con sus 8 bits
        bin_rows = ""
        for i, b in enumerate(data):
            bits = "".join(f"<td align='center'>{(b >> k) & 1}</td>" for k in range(7, -1, -1))
            bin_rows += (
                f"<tr><td bgcolor='#eef3e2'><b>Octet {i + 1} — {b:02X}</b></td>{bits}</tr>")
        bin_table = f"<table border='1' cellspacing='0' cellpadding='3'>{bin_rows}</table>"

        # Detailed Description: subcampos (si hay decodificador para el Item)
        subf = _subfields(code, data)
        if subf:
            filas = "".join(
                f"<tr><td>{n}</td><td align='right'>{v}</td></tr>" for n, v in subf)
            det = ("<table border='1' cellspacing='0' cellpadding='4'>"
                   "<tr bgcolor='#8db84e'><td><b>Name</b></td><td><b>Value</b></td></tr>"
                   f"{filas}</table>")
        else:
            det = "<i style='color:#888'>(desglose de subcampos pendiente para este Item)</i>"

        titulo = f"Data Item {code}" + (f" - {nombre}" if nombre else "")
        return (
            f"<h3>{titulo}</h3>"
            f"<b>Summary</b><p>{summary or '—'}</p>"
            f"<b>Raw Data in Hexadecimal</b><br>{hex_table}<br>"
            f"<b>Raw Data in Binary</b><br>{bin_table}<br>"
            f"<b>Detailed Description</b><br>{det}<br><br>"
            "<b>References</b><p>Check Eurocontrol "
            "(<a href='https://www.eurocontrol.int'>www.eurocontrol.int</a>) "
            "for more ASTERIX information.</p>")

    def _resaltar(self, start: int, end: int):
        """Pinta en el hex viewer los bytes [start, end) del Item seleccionado."""
        fmt = QTextCharFormat()
        fmt.setBackground(QColor("#E91E63"))
        fmt.setForeground(QColor("white"))
        doc = self.hex_viewer.document()
        sels = []
        for i in range(start, end):
            line, col = divmod(i, 16)
            block = doc.findBlockByNumber(line)
            if not block.isValid():
                continue
            pos = block.position() + 6 + col * 3  # "AAAA  " = 6 chars; cada par = 3
            cur = QTextCursor(doc)
            cur.setPosition(pos)
            cur.setPosition(pos + 2, QTextCursor.MoveMode.KeepAnchor)
            sel = QTextEdit.ExtraSelection()
            sel.cursor = cur
            sel.format = fmt
            sels.append(sel)
        self.hex_viewer.setExtraSelections(sels)
        if sels:
            self.hex_viewer.setTextCursor(sels[0].cursor)
