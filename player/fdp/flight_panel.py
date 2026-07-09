"""Panel de vuelos activos FDP — dock que lista flight_plans de fdp.duckdb.

Se refresca bajo demanda (señal mensaje_procesado del FdpWorker). Lee la base
con una conexión propia de solo lectura abierta en el hilo de UI.
"""
import duckdb

from PyQt6.QtWidgets import (
    QDockWidget, QWidget, QVBoxLayout, QTableWidget, QTableWidgetItem,
    QHeaderView, QLabel,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QBrush, QFont


_COLS = ["ARCID", "ADEP", "ADES", "Tipo", "WTC", "RFL", "EOBT", "Estado"]

_SQL = ("SELECT arcid, adep, ades, aircraft_type, wtc, requested_fl, "
        "eobt, status FROM flight_plans ORDER BY status, arcid")

_FG_CANCELLED = QColor("#888888")
_FG_ACTIVE    = QColor("#CCCCCC")


class FlightPanel(QDockWidget):
    """Dock con la tabla de planes de vuelo recibidos por FDP."""

    def __init__(self, db_path: str, parent=None):
        super().__init__("Vuelos FDP", parent)
        self.setObjectName("dock_fdp_vuelos")
        self._db_path = db_path
        self._conn = None

        cont = QWidget()
        lay = QVBoxLayout(cont)
        lay.setContentsMargins(6, 6, 6, 6)
        lay.setSpacing(4)

        self.lbl_total = QLabel("— vuelos —")
        lay.addWidget(self.lbl_total)

        self.tabla = QTableWidget(0, len(_COLS))
        self.tabla.setHorizontalHeaderLabels(_COLS)
        self.tabla.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.tabla.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.tabla.verticalHeader().setVisible(False)
        self.tabla.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents)
        self.tabla.setSortingEnabled(True)
        lay.addWidget(self.tabla)

        self.setWidget(cont)
        self._aplicar_estilo()

    def _aplicar_estilo(self):
        self.setStyleSheet("""
            QWidget { background-color: #0B0E14; color: #CCCCCC;
                      font-family: 'Segoe UI', Arial; font-size: 11px; }
            QTableWidget { background-color: #111520; gridline-color: #2A2F3B;
                           border: 1px solid #2A2F3B; }
            QHeaderView::section { background-color: #1A1F2B; color: #AAAAAA;
                           border: 1px solid #2A2F3B; padding: 3px; font-weight: bold; }
            QLabel { color: #AAAAAA; }
        """)

    def _get_conn(self):
        if self._conn is None:
            # Conexión propia en el hilo UI. DuckDB permite varias conexiones a la
            # misma base dentro del proceso (el worker tiene la suya en su hilo);
            # no se usa read_only para no chocar con la config read-write del worker.
            self._conn = duckdb.connect(self._db_path)
        return self._conn

    def refrescar(self):
        """Relee flight_plans y repuebla la tabla."""
        try:
            rows = self._get_conn().execute(_SQL).fetchall()
        except Exception as e:
            self.lbl_total.setText(f"Error leyendo FDP: {e}")
            return

        self.tabla.setSortingEnabled(False)
        self.tabla.setRowCount(0)
        activos = 0
        for r in rows:
            arcid, adep, ades, tipo, wtc, rfl, eobt, status = r
            if status != "CANCELLED":
                activos += 1
            fila = [arcid, adep, ades, tipo, wtc, rfl, eobt, status]
            n = self.tabla.rowCount()
            self.tabla.insertRow(n)
            cancelado = (status == "CANCELLED")
            for col, val in enumerate(fila):
                item = QTableWidgetItem("" if val is None else str(val))
                item.setForeground(QBrush(_FG_CANCELLED if cancelado else _FG_ACTIVE))
                if cancelado:
                    f = item.font(); f.setStrikeOut(True); item.setFont(f)
                self.tabla.setItem(n, col, item)
        self.tabla.setSortingEnabled(True)
        self.lbl_total.setText(f"{len(rows)} vuelos  ({activos} activos)")

    def closeEvent(self, event):
        if self._conn is not None:
            try:
                self._conn.close()
            except Exception:
                pass
            self._conn = None
        super().closeEvent(event)
