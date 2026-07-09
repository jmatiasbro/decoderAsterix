"""Diálogo de auditoría de eventos de Safety Nets (STCA / APW / MSAW).

Consulta la tabla safety_events del DuckDBRepository, muestra un timeline
de transiciones ONSET/CLEAR con duración calculada, y permite saltar al
instante del evento en el reproductor PCAP.
"""

import csv
import datetime
from pathlib import Path

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QTimeEdit, QPushButton, QTableWidget, QTableWidgetItem,
    QHeaderView, QFileDialog, QMessageBox, QFrame, QSizePolicy,
)
from PyQt6.QtCore import Qt, pyqtSignal, QTime
from PyQt6.QtGui import QColor, QBrush, QFont


_COLS = ["Hora UTC", "Subsistema", "Tipo", "Nivel", "Descripción", "Duración (s)"]

_COLOR_VIOLATION = QColor("#4D0000")
_COLOR_PREDICTION = QColor("#3D3200")
_COLOR_CLEAR      = QColor("#1A2A1A")
_COLOR_DEFAULT    = QColor("#0B0E14")

_FG_VIOLATION = QColor("#FF6666")
_FG_PREDICTION = QColor("#FFE566")
_FG_CLEAR      = QColor("#88CC88")
_FG_DEFAULT    = QColor("#CCCCCC")


def _fmt_ts(ts: float) -> str:
    try:
        return datetime.datetime.utcfromtimestamp(ts).strftime("%H:%M:%S")
    except Exception:
        return str(ts)


def _ts_a_seg(t: QTime) -> float:
    return t.hour() * 3600 + t.minute() * 60 + t.second()


class SafetyAuditDialog(QDialog):
    """Visor histórico de alertas STCA / APW / MSAW con seek al reproductor."""

    seek_to_ts = pyqtSignal(float)

    def __init__(self, repo_db, parent=None):
        super().__init__(parent, Qt.WindowType.Window
                         | Qt.WindowType.WindowTitleHint
                         | Qt.WindowType.WindowSystemMenuHint
                         | Qt.WindowType.WindowMinimizeButtonHint
                         | Qt.WindowType.WindowCloseButtonHint)
        self.setWindowTitle("Auditoría Safety Nets")
        self.resize(900, 520)
        self._repo = repo_db
        self._filas_raw = []   # cache de filas para exportar CSV

        self._build_ui()
        self._aplicar_estilo()
        self._cargar_sesiones()
        self._buscar()  # poblar de entrada; evita tabla vacía al abrir

    # ------------------------------------------------------------------
    # Construcción UI
    # ------------------------------------------------------------------

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(6)

        # ── Filtros ───────────────────────────────────────────────────
        filtros = QHBoxLayout()
        filtros.setSpacing(6)

        filtros.addWidget(QLabel("Subsistema:"))
        self.combo_sub = QComboBox()
        self.combo_sub.addItems(["Todos", "STCA", "APW", "MSAW"])
        self.combo_sub.setFixedWidth(90)
        filtros.addWidget(self.combo_sub)

        filtros.addWidget(QLabel("Sesión:"))
        self.combo_sesion = QComboBox()
        self.combo_sesion.setMinimumWidth(180)
        filtros.addWidget(self.combo_sesion)

        filtros.addWidget(QLabel("Desde:"))
        self.time_desde = QTimeEdit()
        self.time_desde.setDisplayFormat("HH:mm:ss")
        self.time_desde.setFixedWidth(80)
        filtros.addWidget(self.time_desde)

        filtros.addWidget(QLabel("Hasta:"))
        self.time_hasta = QTimeEdit()
        self.time_hasta.setDisplayFormat("HH:mm:ss")
        self.time_hasta.setTime(QTime(23, 59, 59))
        self.time_hasta.setFixedWidth(80)
        filtros.addWidget(self.time_hasta)

        self.btn_buscar = QPushButton("Buscar")
        self.btn_buscar.setFixedWidth(70)
        self.btn_buscar.clicked.connect(self._buscar)
        filtros.addWidget(self.btn_buscar)

        filtros.addStretch(1)
        self.lbl_total = QLabel("— eventos —")
        self.lbl_total.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        filtros.addWidget(self.lbl_total)

        root.addLayout(filtros)

        # Separador
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color: #3A3F4B;")
        root.addWidget(sep)

        # ── Tabla ─────────────────────────────────────────────────────
        self.tabla = QTableWidget(0, len(_COLS))
        self.tabla.setHorizontalHeaderLabels(_COLS)
        self.tabla.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.tabla.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.tabla.setAlternatingRowColors(False)
        self.tabla.verticalHeader().setVisible(False)
        self.tabla.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        for c in (0, 1, 2, 3, 5):
            self.tabla.horizontalHeader().setSectionResizeMode(c, QHeaderView.ResizeMode.ResizeToContents)
        self.tabla.setSortingEnabled(True)
        root.addWidget(self.tabla, 1)

        # ── Botones inferiores ────────────────────────────────────────
        botones = QHBoxLayout()
        botones.setSpacing(8)

        self.btn_ir = QPushButton("▶  Ir al instante en Reproductor")
        self.btn_ir.clicked.connect(self._ir_al_instante)
        botones.addWidget(self.btn_ir)

        self.btn_csv = QPushButton("Exportar CSV…")
        self.btn_csv.clicked.connect(self._exportar_csv)
        botones.addWidget(self.btn_csv)

        botones.addStretch(1)

        self.btn_refrescar = QPushButton("Refrescar sesiones")
        self.btn_refrescar.clicked.connect(self._cargar_sesiones)
        botones.addWidget(self.btn_refrescar)

        self.btn_cerrar = QPushButton("Cerrar")
        self.btn_cerrar.clicked.connect(self.close)
        botones.addWidget(self.btn_cerrar)

        root.addLayout(botones)

    def _aplicar_estilo(self):
        self.setStyleSheet("""
            QDialog, QWidget {
                background-color: #0B0E14;
                color: #CCCCCC;
                font-family: 'Segoe UI', Arial, sans-serif;
                font-size: 12px;
            }
            QTableWidget {
                background-color: #111520;
                gridline-color: #2A2F3B;
                border: 1px solid #2A2F3B;
            }
            QHeaderView::section {
                background-color: #1A1F2B;
                color: #AAAAAA;
                border: 1px solid #2A2F3B;
                padding: 4px;
                font-weight: bold;
            }
            QTableWidget::item:selected {
                background-color: #1A4A6A;
                color: #FFFFFF;
            }
            QComboBox, QTimeEdit {
                background-color: #1A1F2B;
                color: #CCCCCC;
                border: 1px solid #3A3F4B;
                padding: 2px 4px;
                border-radius: 3px;
            }
            QPushButton {
                background-color: #1A2A3A;
                color: #CCCCCC;
                border: 1px solid #3A4F6A;
                padding: 4px 10px;
                border-radius: 3px;
            }
            QPushButton:hover {
                background-color: #1E3A5A;
                color: #FFFFFF;
            }
            QLabel { color: #AAAAAA; }
        """)

    # ------------------------------------------------------------------
    # Lógica
    # ------------------------------------------------------------------

    def _cargar_sesiones(self):
        if self._repo is None:
            return
        try:
            rows = self._repo.query("SELECT DISTINCT sesion_id FROM safety_events ORDER BY sesion_id")
            self.combo_sesion.blockSignals(True)
            prev = self.combo_sesion.currentText()
            self.combo_sesion.clear()
            self.combo_sesion.addItem("Todas")
            for (sid,) in rows:
                if sid:
                    self.combo_sesion.addItem(sid)
            idx = self.combo_sesion.findText(prev)
            self.combo_sesion.setCurrentIndex(max(0, idx))
            self.combo_sesion.blockSignals(False)
        except Exception as e:
            print(f"[AuditDialog] Error cargando sesiones: {e}")

    def _buscar(self):
        if self._repo is None:
            self.lbl_total.setText("Sin conexión a BD")
            return

        sub     = self.combo_sub.currentText()
        sesion  = self.combo_sesion.currentText()
        ts_d    = _ts_a_seg(self.time_desde.time())
        ts_h    = _ts_a_seg(self.time_hasta.time())

        rows = self._repo.query_safety_events(
            subsistema=None if sub == "Todos" else sub,
            sesion_id=None if sesion == "Todas" else sesion,
        )

        # Filtro por hora-del-día (0..86399 s) sobre el mismo instante que muestra
        # la columna "Hora UTC": ts % 86400 == hora del día tanto si ts es ToD
        # ASTERIX (seg-del-día) como epoch. No se ancla a "hoy" (dependía del huso
        # horario y ocultaba todo el histórico de sesiones previas).
        if (ts_d, ts_h) != (0, 86399):
            rows = [r for r in rows if ts_d <= (r[0] % 86400) <= ts_h]

        duraciones = self._calcular_duraciones(rows)
        self._poblar_tabla(rows, duraciones)

    def _calcular_duraciones(self, rows) -> dict:
        """Devuelve {idx_onset: duracion_s} pareando ONSETs con el primer CLEAR posterior."""
        # rows ordenadas por ts_wall ASC (garantizado por query_safety_events)
        # Índices: 0=ts,1=ts_wall,2=sub,3=trans,4=clave,5=nivel,6=origen,7=desc,8=sesion
        pending: dict[tuple, tuple] = {}  # (sub, clave) → (idx, ts)
        duraciones: dict[int, float] = {}

        for idx, r in enumerate(rows):
            _, ts_wall, sub, trans, clave = r[0], r[1], r[2], r[3], r[4]
            key = (sub, clave)
            if trans == "ONSET":
                pending[key] = (idx, ts_wall)
            elif trans == "CLEAR" and key in pending:
                onset_idx, onset_ts_wall = pending.pop(key)
                duraciones[onset_idx] = round(ts_wall - onset_ts_wall, 1)

        return duraciones

    def _poblar_tabla(self, rows, duraciones: dict):
        self.tabla.setSortingEnabled(False)
        self.tabla.setRowCount(0)
        self._filas_raw = list(rows)

        for idx, r in enumerate(rows):
            ts, _, sub, trans, clave, nivel, _, desc, sesion = r
            dur = duraciones.get(idx)
            dur_txt = f"{dur:.1f}" if dur is not None else ("activo" if trans == "ONSET" else "—")

            fila = [_fmt_ts(ts), sub, trans, nivel or "", desc or "", dur_txt]
            row_n = self.tabla.rowCount()
            self.tabla.insertRow(row_n)

            bg, fg = self._colores(trans, nivel)
            for col, txt in enumerate(fila):
                item = QTableWidgetItem(str(txt))
                item.setForeground(QBrush(fg))
                item.setBackground(QBrush(bg))
                if col == 0:
                    item.setData(Qt.ItemDataRole.UserRole, ts)
                self.tabla.setItem(row_n, col, item)

        self.tabla.setSortingEnabled(True)
        total = len(rows)
        onset = sum(1 for r in rows if r[3] == "ONSET")
        self.lbl_total.setText(f"{total} eventos  ({onset} alertas)")

    def _colores(self, transicion: str, nivel: str):
        if transicion == "CLEAR":
            return _COLOR_CLEAR, _FG_CLEAR
        if nivel == "CRITICAL":
            return _COLOR_VIOLATION, _FG_VIOLATION
        if nivel == "WARNING":
            return _COLOR_PREDICTION, _FG_PREDICTION
        return _COLOR_DEFAULT, _FG_DEFAULT

    def _ir_al_instante(self):
        fila = self.tabla.currentRow()
        if fila < 0:
            QMessageBox.information(self, "Ir al instante", "Seleccioná una fila primero.")
            return
        item = self.tabla.item(fila, 0)
        if item is None:
            return
        ts = item.data(Qt.ItemDataRole.UserRole)
        if ts is not None:
            self.seek_to_ts.emit(float(ts))

    def _exportar_csv(self):
        if not self._filas_raw:
            QMessageBox.information(self, "Exportar", "Realizá una búsqueda primero.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Guardar CSV de auditoría", "safety_events_audit.csv",
            "CSV (*.csv)")
        if not path:
            return
        try:
            with open(path, "w", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                w.writerow(["ts_epoch", "ts_utc", "ts_wall_epoch", "subsistema",
                             "transicion", "clave", "nivel", "origen", "descripcion", "sesion_id"])
                for r in self._filas_raw:
                    ts, ts_wall, sub, trans, clave, nivel, origen, desc, sesion = r
                    w.writerow([ts, _fmt_ts(ts), ts_wall, sub, trans, clave,
                                 nivel or "", origen or "", desc or "", sesion or ""])
            QMessageBox.information(self, "Exportar", f"Guardado en:\n{path}")
        except Exception as e:
            QMessageBox.critical(self, "Error al exportar", str(e))
