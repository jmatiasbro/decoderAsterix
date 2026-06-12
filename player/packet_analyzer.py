"""
packet_analyzer.py — Visor histórico de plots ASTERIX con filtros en caliente.

Lee desde la tabla `asterix_plots` (DuckDB, poblada durante el decode) y permite
filtrar por categoría, SAC/SIC, callsign, track/Mode-S y rango horario. El doble
clic sobre una fila 'teletransporta' el playback al instante de ese plot.
"""
from typing import List, Optional, Any

from PyQt6.QtCore import Qt, QAbstractTableModel, QModelIndex, QTime
from PyQt6.QtGui import QIntValidator, QColor
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QCheckBox, QLineEdit,
    QComboBox, QPushButton, QDialogButtonBox, QLabel, QTableView, QTimeEdit,
    QAbstractItemView, QHeaderView, QMessageBox,
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


class PlotsTableModel(QAbstractTableModel):
    """Modelo liviano sobre filas crudas (list[tuple]) para miles de registros.

    La primera columna del dato crudo es el timestamp (ToD en segundos); se
    muestra formateada pero se conserva el valor para el seek por doble clic.
    """
    HEADERS = ["Hora", "Cat", "SAC/SIC", "Track / Mode-S", "Callsign",
               "FL", "Az°", "Rng NM"]

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
        return len(self.HEADERS)

    def timestamp_at(self, row: int) -> Optional[float]:
        if 0 <= row < len(self._rows):
            return self._rows[row][0]
        return None

    def data(self, index: QModelIndex, role=Qt.ItemDataRole.DisplayRole) -> Any:
        if not index.isValid():
            return None
        row = self._rows[index.row()]
        col = index.column()
        if role == Qt.ItemDataRole.DisplayRole:
            # row: (timestamp, category, sac_sic, track_id, callsign, fl, az, rng)
            if col == 0:
                return _fmt_tod(row[0])
            if col == 5:
                return str(row[5])
            if col in (6, 7):
                try:
                    return f"{float(row[col]):.2f}"
                except (TypeError, ValueError):
                    return ""
            return str(row[col]) if row[col] is not None else ""
        if role == Qt.ItemDataRole.TextAlignmentRole:
            if col in (1, 5, 6, 7):
                return int(Qt.AlignmentFlag.AlignCenter)
        return None

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            return self.HEADERS[section]
        return None


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

        # Track / Mode-S / Squawk
        self.track_in = QLineEdit()
        self.track_in.setPlaceholderText("Mode-S / squawk / track number")
        layout.addRow("Track / Mode-S:", self.track_in)

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
            "t_from": _qtime_a_tod(self.time_from.time()),
            "t_to": _qtime_a_tod(self.time_to.time()),
        }


class AsterixAnalyzerWindow(QDialog):
    """Ventana del analizador: tabla + botón de filtros. Doble clic = seek."""

    LIMIT = 5000

    def __init__(self, repo_db, worker=None, parent=None):
        super().__init__(parent)
        self.repo_db = repo_db
        self.worker = worker
        self.setWindowTitle("Analizador de Paquetes ASTERIX")
        self.resize(820, 560)
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
        barra.addWidget(self.lbl_estado)
        barra.addStretch()
        barra.addWidget(btn_filtros)
        v.addLayout(barra)

        self.modelo_tabla = PlotsTableModel(self)
        self.tabla = QTableView()
        self.tabla.setModel(self.modelo_tabla)
        self.tabla.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tabla.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tabla.setAlternatingRowColors(True)
        self.tabla.verticalHeader().setVisible(False)
        self.tabla.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.tabla.doubleClicked.connect(self._on_doble_clic)
        v.addWidget(self.tabla)

        hint = QLabel("Doble clic en una fila → la pantalla táctica salta a ese instante.")
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

    def aplicar_filtros_base_datos(self, criterios: Optional[dict]):
        query = ("SELECT timestamp, category, sac_sic, track_id, callsign, "
                 "flight_level, raw_azimuth, raw_range FROM asterix_plots WHERE 1=1")
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
            query += " AND timestamp BETWEEN ? AND ?"
            params.extend([criterios["t_from"], criterios["t_to"]])

        query += f" ORDER BY timestamp ASC LIMIT {self.LIMIT}"

        rows = self.repo_db.query(query, params) if params else self.repo_db.query(query)
        self.modelo_tabla.update_data(rows)
        n = len(rows)
        tope = " (tope alcanzado)" if n >= self.LIMIT else ""
        self.lbl_estado.setText(f"{n} registros{tope}")

    def _on_doble_clic(self, index: QModelIndex):
        if not index.isValid() or self.worker is None:
            return
        t = self.modelo_tabla.timestamp_at(index.row())
        if t is None:
            return
        if not hasattr(self.worker, "seek_to_time"):
            QMessageBox.information(self, "Seek", "El reproductor no soporta seek por tiempo.")
            return
        self.worker.seek_to_time(float(t))
