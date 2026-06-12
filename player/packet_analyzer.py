"""
packet_analyzer.py — Visor histórico de plots ASTERIX con filtros en caliente.

Lee desde la tabla `asterix_plots` (DuckDB, poblada durante el decode) y permite
filtrar por categoría, SAC/SIC, callsign, track/Mode-S y rango horario. El doble
clic sobre una fila 'teletransporta' el playback al instante de ese plot.
"""
import math
from typing import List, Optional, Any

from PyQt6.QtCore import (
    Qt, QAbstractTableModel, QModelIndex, QTime, QRect, QSortFilterProxyModel,
    pyqtSignal,
)
from PyQt6.QtGui import QIntValidator, QColor
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QCheckBox, QLineEdit,
    QComboBox, QPushButton, QDialogButtonBox, QLabel, QTableView, QTimeEdit,
    QAbstractItemView, QHeaderView, QMessageBox, QStyle, QStyleOptionHeader,
)


def _fmt_tod(t: float) -> str:
    """Segundos-del-día (ToD) -> HH:MM:SS."""
    try:
        s = int(t) % 86400
        return f"{s // 3600:02d}:{(s % 3600) // 60:02d}:{s % 60:02d}"
    except (TypeError, ValueError):
        return "--:--:--"


def _tod_a_qtime(t: float) -> QTime:
    s = int(t) % 86400
    return QTime(s // 3600, (s % 3600) // 60, s % 60)


def _qtime_a_tod(qt: QTime) -> int:
    return qt.hour() * 3600 + qt.minute() * 60 + qt.second()


# Categorías ASTERIX a las que aplica cada columna del analizador.
_ALL = frozenset({1, 21, 48, 62})

# Especificación de columnas: (header, sql, kind, alineación-izquierda?, cats).
#   sql   -> expresión en el SELECT (orden idéntico al de COLUMNS)
#   kind  -> 'tod' | 'int' | 'str' | 'f0' | 'f1' | 'f2' | 'f5'
#   cats  -> categorías para las que la columna es relevante (visibilidad dinámica)
# La columna 0 (timestamp) es además la clave de seek por doble clic.
COLUMNS = [
    ("TX (ToD)",  "timestamp",     "tod", False, _ALL),
    ("RX (cap)",  "rx_time",       "tod", False, _ALL),
    ("Cat",       "category",      "int", False, _ALL),
    ("SAC/SIC",   "sac_sic",       "str", False, _ALL),
    ("Track#",    "track_number",  "int", False, frozenset({1, 48, 62})),
    ("Mode-S",    "mode_s",        "str", False, frozenset({48, 62, 21})),
    ("Callsign",  "callsign",      "str", True,  frozenset({48, 62, 21})),
    ("SSR",       "mode3a",        "str", False, _ALL),
    ("FL",        "flight_level",  "str", False, _ALL),
    ("Alt ft",    "altitude_ft",   "f0",  False, frozenset({48, 21})),
    ("GS kt",     "ground_speed",  "f0",  False, frozenset({48, 62, 21})),
    ("Hdg°",      "track_angle",   "f1",  False, frozenset({48, 62, 21})),
    ("V/R ft/m",  "vertical_rate", "f0",  False, frozenset({62, 21})),
    ("Az°",       "raw_azimuth",   "f2",  False, frozenset({1, 48})),
    ("Rng NM",    "raw_range",     "f2",  False, frozenset({1, 48})),
    ("Lat",       "lat",           "f5",  False, _ALL),
    ("Lon",       "lon",           "f5",  False, _ALL),
]
SELECT_COLS = ", ".join(c[1] for c in COLUMNS)
_IDX = {c[1]: i for i, c in enumerate(COLUMNS)}


def _fmt_val(v, kind: str) -> str:
    if v is None:
        return ""
    try:
        if kind == "tod":
            return _fmt_tod(v)
        if kind == "int":
            return str(int(v))
        if kind == "f0":
            return f"{float(v):.0f}"
        if kind == "f1":
            return f"{float(v):.1f}"
        if kind == "f2":
            return f"{float(v):.2f}"
        if kind == "f5":
            return f"{float(v):.5f}"
        return str(v)
    except (TypeError, ValueError):
        return ""


class PlotsTableModel(QAbstractTableModel):
    """Modelo liviano sobre filas crudas (list[tuple]) para miles de registros.

    Las columnas vienen de COLUMNS (orden = orden del SELECT). La columna 0 es el
    timestamp (ToD); se muestra formateada pero se conserva crudo para el seek.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._rows: List[tuple] = []

    def update_data(self, rows: List[tuple]):
        self.beginResetModel()
        self._rows = rows or []
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._rows)

    def columnCount(self, parent=QModelIndex()) -> int:
        return len(COLUMNS)

    def timestamp_at(self, row: int) -> Optional[float]:
        if 0 <= row < len(self._rows):
            return self._rows[row][0]
        return None

    def value_at(self, row: int, col: int) -> Any:
        if 0 <= row < len(self._rows) and 0 <= col < len(COLUMNS):
            return self._rows[row][col]
        return None

    def data(self, index: QModelIndex, role=Qt.ItemDataRole.DisplayRole) -> Any:
        if not index.isValid():
            return None
        row = self._rows[index.row()]
        col = index.column()
        if role == Qt.ItemDataRole.DisplayRole:
            return _fmt_val(row[col], COLUMNS[col][2])
        if role == Qt.ItemDataRole.EditRole:
            # Valor crudo para ordenar correctamente (numérico donde corresponda)
            return row[col]
        if role == Qt.ItemDataRole.TextAlignmentRole:
            if not COLUMNS[col][3]:  # no es columna de texto alineada a la izquierda
                return int(Qt.AlignmentFlag.AlignCenter)
        return None

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            return COLUMNS[section][0]
        return None


class ColumnFilterProxy(QSortFilterProxyModel):
    """Proxy de filtrado por columna (substring, case-insensitive) + orden."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._filters: dict = {}
        self.setSortRole(Qt.ItemDataRole.EditRole)

    def set_filter(self, col: int, text: str):
        text = (text or "").strip().lower()
        if text:
            self._filters[col] = text
        else:
            self._filters.pop(col, None)
        self.invalidateFilter()

    def filterAcceptsRow(self, row, parent):
        src = self.sourceModel()
        for col, txt in self._filters.items():
            idx = src.index(row, col, parent)
            val = str(src.data(idx, Qt.ItemDataRole.DisplayRole) or "").lower()
            if txt not in val:
                return False
        return True


class FilterHeader(QHeaderView):
    """Cabecera con una fila de cajas de filtro (una por columna) embebidas.

    Permite filtrar directamente desde la cabecera de la tabla y ordenar
    haciendo clic en el título de la columna.
    """
    filterChanged = pyqtSignal(int, str)

    def __init__(self, parent=None):
        super().__init__(Qt.Orientation.Horizontal, parent)
        self._editors = []
        self._padding = 4
        self.setSectionsClickable(True)
        self.setSortIndicatorShown(False)  # dibujamos la flecha nosotros (al lado del título)
        self.setMinimumSectionSize(70)
        self.sectionResized.connect(self._reposicionar)
        self.sectionMoved.connect(lambda *a: self._reposicionar())

    def _band_h(self) -> int:
        """Alto de la banda del título (la fila de filtros va debajo)."""
        return super().sizeHint().height()

    def paintSection(self, painter, rect, logicalIndex):
        """Dibuja el chrome de la sección + título y flecha de orden en la banda
        superior, dejando libre la banda inferior para la caja de filtro."""
        if not rect.isValid():
            return
        opt = QStyleOptionHeader()
        self.initStyleOption(opt)
        opt.rect = rect
        opt.section = logicalIndex
        opt.text = ""
        opt.sortIndicator = QStyleOptionHeader.SortIndicator.None_
        painter.save()
        self.style().drawControl(QStyle.ControlElement.CE_Header, opt, painter, self)
        painter.restore()

        title = ""
        model = self.model()
        if model is not None:
            val = model.headerData(logicalIndex, Qt.Orientation.Horizontal,
                                   Qt.ItemDataRole.DisplayRole)
            title = "" if val is None else str(val)
        if self.sortIndicatorSection() == logicalIndex:
            asc = self.sortIndicatorOrder() == Qt.SortOrder.AscendingOrder
            title += "  ▲" if asc else "  ▼"

        band = QRect(rect.left() + 3, rect.top() + 2,
                     rect.width() - 6, self._band_h() - 2)
        painter.save()
        painter.setPen(QColor("#C8D2E0"))
        f = painter.font()
        f.setPointSize(8)
        painter.setFont(f)
        painter.drawText(
            band,
            int(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter),
            title)
        painter.restore()

    def set_columns(self, count: int):
        for e in self._editors:
            e.deleteLater()
        self._editors = []
        for i in range(count):
            le = QLineEdit(self.viewport())
            le.setPlaceholderText("filtrar…")
            le.setClearButtonEnabled(True)
            le.setStyleSheet("QLineEdit{font-size:8pt; padding:1px 3px;}")
            le.textChanged.connect(lambda txt, c=i: self.filterChanged.emit(c, txt))
            le.show()
            self._editors.append(le)
        self._reposicionar()

    def sizeHint(self):
        s = super().sizeHint()
        if self._editors:
            s.setHeight(s.height() + self._editors[0].sizeHint().height() + self._padding)
        return s

    def _reposicionar(self, *args):
        if not self._editors:
            return
        h = self._editors[0].sizeHint().height()
        y = super().sizeHint().height() + self._padding // 2
        for i, le in enumerate(self._editors):
            x = self.sectionViewportPosition(i)
            w = self.sectionSize(i)
            le.setGeometry(x + 1, y, max(0, w - 2), h)
            le.setVisible(not self.isSectionHidden(i))

    def updateGeometries(self):
        super().updateGeometries()
        self._reposicionar()


class AsterixFilterDialog(QDialog):
    """Diálogo modal de filtros. `obtener_criterios()` devuelve un dict limpio."""

    def __init__(self, sac_sic_opts: List[str], t_min: float, t_max: float, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Filtros Avanzados de Archivo")
        self.setModal(True)
        self._init_ui(sac_sic_opts, t_min, t_max)

    def _init_ui(self, sac_sic_opts, t_min, t_max):
        layout = QFormLayout(self)

        # Categorías
        cat_box = QHBoxLayout()
        self.cats = {1: QCheckBox("Cat 01"), 21: QCheckBox("Cat 21"),
                     48: QCheckBox("Cat 48"), 62: QCheckBox("Cat 62")}
        for cb in self.cats.values():
            cat_box.addWidget(cb)
        layout.addRow("Categorías:", cat_box)

        # SAC/SIC (combo con los valores reales del archivo)
        self.sac_sic_combo = QComboBox()
        self.sac_sic_combo.addItem("(todos)", "")
        for v in sac_sic_opts:
            self.sac_sic_combo.addItem(v, v)
        layout.addRow("SAC/SIC:", self.sac_sic_combo)

        # Callsign
        self.callsign_in = QLineEdit()
        self.callsign_in.setPlaceholderText("ej: AR1234")
        layout.addRow("Callsign:", self.callsign_in)

        # Track / Mode-S
        self.track_in = QLineEdit()
        self.track_in.setPlaceholderText("Mode-S (ICAO) / track number")
        layout.addRow("Track / Mode-S:", self.track_in)

        # Código SSR / Squawk (Mode 3-A)
        self.ssr_in = QLineEdit()
        self.ssr_in.setPlaceholderText("ej: 2375")
        self.ssr_in.setMaxLength(4)
        layout.addRow("Código SSR (squawk):", self.ssr_in)

        # Rango horario
        self.time_from = QTimeEdit()
        self.time_from.setDisplayFormat("HH:mm:ss")
        self.time_from.setTime(_tod_a_qtime(t_min))
        self.time_to = QTimeEdit()
        self.time_to.setDisplayFormat("HH:mm:ss")
        self.time_to.setTime(_tod_a_qtime(t_max))
        rango = QHBoxLayout()
        rango.addWidget(QLabel("desde"))
        rango.addWidget(self.time_from)
        rango.addWidget(QLabel("hasta"))
        rango.addWidget(self.time_to)
        layout.addRow("Horario (UTC):", rango)

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, self)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addRow(self.buttons)

    def obtener_criterios(self) -> dict:
        return {
            "categories": [cat for cat, cb in self.cats.items() if cb.isChecked()],
            "sac_sic": self.sac_sic_combo.currentData() or "",
            "callsign": self.callsign_in.text().strip().upper(),
            "track": self.track_in.text().strip().upper(),
            "ssr": self.ssr_in.text().strip(),
            "t_from": _qtime_a_tod(self.time_from.time()),
            "t_to": _qtime_a_tod(self.time_to.time()),
        }


class AsterixAnalyzerWindow(QDialog):
    """Ventana del analizador: tabla + botón de filtros. Doble clic = seek."""

    # Doble clic en una fila: reposicionar la consola a ese instante (sin filtro).
    seek_solicitado = pyqtSignal(float)
    # Reproducir solo las aeronaves filtradas: (t_inicial, lat_c, lon_c, radio_nm, set[claves]).
    reproducir_filtrado = pyqtSignal(float, float, float, float, object)

    LIMIT = 5000

    def __init__(self, repo_db, worker=None, parent=None):
        super().__init__(parent)
        self.repo_db = repo_db
        self.worker = worker
        self.setWindowTitle("Analizador de Paquetes ASTERIX")
        self.resize(1080, 600)
        self.setModal(False)
        self._init_ui()
        self.aplicar_filtros_base_datos(None)  # carga inicial sin filtros

    def _init_ui(self):
        v = QVBoxLayout(self)

        barra = QHBoxLayout()
        self.lbl_estado = QLabel("—")
        self.lbl_estado.setStyleSheet("color:#8A93A6;")
        btn_filtros = QPushButton(" Configurar Filtros")
        btn_filtros.clicked.connect(self.abrir_filtros_dialog)
        self.btn_reproducir = QPushButton(" ▶ Reproducir filtrado")
        self.btn_reproducir.setToolTip(
            "Reproduce en la consola únicamente los plots actualmente filtrados.")
        self.btn_reproducir.clicked.connect(self._reproducir_filtrado)
        barra.addWidget(self.lbl_estado)
        barra.addStretch()
        barra.addWidget(self.btn_reproducir)
        barra.addWidget(btn_filtros)
        v.addLayout(barra)

        self.modelo_tabla = PlotsTableModel(self)
        self.proxy = ColumnFilterProxy(self)
        self.proxy.setSourceModel(self.modelo_tabla)

        self.tabla = QTableView()
        self.tabla.setModel(self.proxy)
        self.tabla.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tabla.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tabla.setAlternatingRowColors(True)
        self.tabla.setSortingEnabled(True)
        self.tabla.verticalHeader().setVisible(False)

        # Cabecera con cajas de filtro por columna + orden por clic
        self._header = FilterHeader(self.tabla)
        self.tabla.setHorizontalHeader(self._header)
        # Ancho por contenido: las columnas se ajustan al dato más largo
        self._header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self._header.setStretchLastSection(True)
        self._header.set_columns(self.modelo_tabla.columnCount())
        self._header.filterChanged.connect(self.proxy.set_filter)
        # Mantener las cajas alineadas al hacer scroll horizontal
        self.tabla.horizontalScrollBar().valueChanged.connect(self._header._reposicionar)

        self.tabla.doubleClicked.connect(self._on_doble_clic)
        v.addWidget(self.tabla)

        hint = QLabel("Filtrá en la cabecera de cada columna · clic en el título ordena · "
                      "doble clic en una fila → la consola salta a ese instante · "
                      "“Reproducir filtrado” → la consola reproduce solo lo filtrado.")
        hint.setStyleSheet("color:#6B7A8D; font-size:8pt;")
        v.addWidget(hint)

    # ---- datos ----
    def _distinct_sac_sic(self) -> List[str]:
        rows = self.repo_db.query(
            "SELECT DISTINCT sac_sic FROM asterix_plots WHERE sac_sic != '' ORDER BY sac_sic")
        return [r[0] for r in rows]

    def _rango_tiempo(self):
        rows = self.repo_db.query(
            "SELECT MIN(timestamp), MAX(timestamp) FROM asterix_plots")
        if rows and rows[0][0] is not None:
            return rows[0][0], rows[0][1]
        return 0.0, 86399.0

    def abrir_filtros_dialog(self):
        t_min, t_max = self._rango_tiempo()
        dlg = AsterixFilterDialog(self._distinct_sac_sic(), t_min, t_max, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.aplicar_filtros_base_datos(dlg.obtener_criterios())

    def _cats_presentes(self) -> set:
        """Categorías presentes en el archivo (define qué columnas mostrar)."""
        rows = self.repo_db.query("SELECT DISTINCT category FROM asterix_plots")
        return {int(r[0]) for r in rows if r[0] is not None}

    def _actualizar_columnas_visibles(self):
        """Muestra/oculta columnas según las categorías del archivo."""
        cats = self._cats_presentes() or set(_ALL)
        for i, col in enumerate(COLUMNS):
            visible = bool(col[4] & cats)
            self.tabla.setColumnHidden(i, not visible)
        self._header._reposicionar()

    def aplicar_filtros_base_datos(self, criterios: Optional[dict]):
        query = (f"SELECT {SELECT_COLS} FROM asterix_plots WHERE 1=1")
        params: List[Any] = []

        if criterios:
            if criterios["categories"]:
                cats = ",".join(str(int(c)) for c in criterios["categories"])
                query += f" AND category IN ({cats})"
            if criterios["sac_sic"]:
                query += " AND sac_sic = ?"
                params.append(criterios["sac_sic"])
            if criterios["callsign"]:
                query += " AND callsign LIKE ?"
                params.append(f"%{criterios['callsign']}%")
            if criterios["track"]:
                query += " AND upper(track_id) LIKE ?"
                params.append(f"%{criterios['track']}%")
            if criterios.get("ssr"):
                query += " AND mode3a LIKE ?"
                params.append(f"%{criterios['ssr']}%")
            query += " AND timestamp BETWEEN ? AND ?"
            params.extend([criterios["t_from"], criterios["t_to"]])

        query += f" ORDER BY timestamp ASC LIMIT {self.LIMIT}"

        rows = self.repo_db.query(query, params) if params else self.repo_db.query(query)
        self.modelo_tabla.update_data(rows)
        # Visibilidad de columnas según las categorías del archivo
        self._actualizar_columnas_visibles()
        # Ancho de columnas según el contenido (que entren los datos)
        self.tabla.resizeColumnsToContents()
        self._header._reposicionar()
        n = len(rows)
        tope = " (tope alcanzado)" if n >= self.LIMIT else ""
        self.lbl_estado.setText(f"{n} registros{tope}")

    def _targets_visibles(self):
        """Devuelve (t0, lat_c, lon_c, radio_nm, keys) de las filas visibles. Las `keys`
        son la identidad de aeronave (callsign / Mode-S / track#); se filtra por atributo
        (no por plot_id) porque la deduplicación fusiona el callsign en otro plot.
        El centroide y el radio encuadran TODAS las posiciones filtradas (sirve para
        reproducir una o varias aeronaves a la vez)."""
        keys = set()
        t0 = None
        coords = []
        for r in range(self.proxy.rowCount()):
            src_row = self.proxy.mapToSource(self.proxy.index(r, 0)).row()
            t = self.modelo_tabla.timestamp_at(src_row)
            if t is not None and (t0 is None or t < t0):
                t0 = t
            la = self.modelo_tabla.value_at(src_row, _IDX["lat"])
            lo = self.modelo_tabla.value_at(src_row, _IDX["lon"])
            if la is not None and lo is not None and abs(la) > 0.1 and abs(lo) > 0.1:
                coords.append((float(la), float(lo)))
            cs = self.modelo_tabla.value_at(src_row, _IDX["callsign"])
            ms = self.modelo_tabla.value_at(src_row, _IDX["mode_s"])
            tn = self.modelo_tabla.value_at(src_row, _IDX["track_number"])
            ss = self.modelo_tabla.value_at(src_row, _IDX["sac_sic"])
            if cs:
                keys.add(("cs", str(cs).strip().upper()))
            if ms:
                keys.add(("ms", str(ms).strip()))
            if tn is not None:
                keys.add(("tn", str(ss), str(tn)))
        lat_c = lon_c = 0.0
        radio_nm = 0.0
        if coords:
            lat_c = sum(c[0] for c in coords) / len(coords)
            lon_c = sum(c[1] for c in coords) / len(coords)
            coslat = math.cos(math.radians(lat_c))
            radio_nm = max(
                math.hypot((la - lat_c) * 60.0, (lo - lon_c) * 60.0 * coslat)
                for la, lo in coords)
        return t0, lat_c, lon_c, radio_nm, keys

    def _reproducir_filtrado(self):
        t0, lat_c, lon_c, radio_nm, keys = self._targets_visibles()
        if not keys:
            QMessageBox.information(
                self, "Reproducir filtrado",
                "Las filas filtradas no tienen identificador de aeronave "
                "(callsign / Mode-S / track#) para reproducir individualmente.")
            return
        self.reproducir_filtrado.emit(float(t0 or 0.0), lat_c, lon_c, radio_nm, keys)
        self.showMinimized()

    def _on_doble_clic(self, index: QModelIndex):
        if not index.isValid():
            return
        # El índice viene del proxy: mapear a la fila del modelo origen
        src = self.proxy.mapToSource(index)
        t = self.modelo_tabla.timestamp_at(src.row())
        if t is None:
            return
        self.seek_solicitado.emit(float(t))
