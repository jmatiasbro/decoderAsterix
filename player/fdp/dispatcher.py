"""FdpDispatcher — aplica tramas ADEXP ya parseadas a fdp.duckdb.

Sin Qt. Recibe el dict de decoder.adexp_parser.parsear_trama y enruta según
el TITLE del mensaje a la operación de base de datos correspondiente.
"""
from typing import Dict, Optional

# Mapeo campo ADEXP → columna de flight_plans
CAMPO_A_COLUMNA = {
    "ADEP":  "adep",
    "ADES":  "ades",
    "RFL":   "requested_fl",
    "ROUTE": "route",
    "EOBT":  "eobt",
    "COP":   "cop",
    "aircraft_type": "aircraft_type",
    "wtc":   "wtc",
}

# Títulos que crean/refrescan un plan completo
TITULOS_UPSERT = {"FPL", "IFPL", "EST", "ACT"}
# Títulos de modificación parcial
TITULOS_CHG    = {"CHG", "RCHG"}
# Títulos de cancelación
TITULOS_CNL    = {"CNL", "RCNL", "ICNL"}


class FdpDispatcher:
    """Enruta tramas ADEXP parseadas a operaciones sobre fdp.duckdb."""

    def __init__(self, conn):
        self.conn = conn

    # ------------------------------------------------------------------
    # Entrada pública
    # ------------------------------------------------------------------
    def procesar(self, data: Dict[str, str], raw: str = "") -> str:
        """Enruta según TITLE. Devuelve la acción aplicada (str)."""
        title = (data.get("TITLE") or "").upper()
        arcid = data.get("ARCID")

        self._log(title, arcid, raw)

        if not arcid:
            return "IGNORED_NO_ARCID"

        if title in TITULOS_CNL:
            self._cancel_flight_plan(arcid)
            return "CANCELLED"
        if title in TITULOS_CHG:
            self._update_flight_plan(data, raw)
            return "UPDATED"
        if title in TITULOS_UPSERT:
            self._upsert_flight_plan(data, raw)
            return "UPSERTED"
        return "IGNORED_UNKNOWN_TITLE"

    # ------------------------------------------------------------------
    # Operaciones DB
    # ------------------------------------------------------------------
    def _columnas_presentes(self, data: Dict[str, str]) -> Dict[str, str]:
        return {col: data[campo]
                for campo, col in CAMPO_A_COLUMNA.items()
                if campo in data and data[campo] is not None}

    def _upsert_flight_plan(self, data: Dict[str, str], raw: str = ""):
        """INSERT … ON CONFLICT DO UPDATE: refresca solo las columnas presentes."""
        arcid = data["ARCID"]
        cols  = self._columnas_presentes(data)
        cols["raw_msg"] = raw

        col_names = ["arcid"] + list(cols.keys())
        placeholders = ", ".join("?" for _ in col_names)
        valores = [arcid] + list(cols.values())

        set_clause = ", ".join(f"{c} = excluded.{c}" for c in cols.keys())
        set_clause += ", status = 'ACTIVE', updated_at = current_localtimestamp()"

        sql = (
            f"INSERT INTO flight_plans ({', '.join(col_names)}) "
            f"VALUES ({placeholders}) "
            f"ON CONFLICT (arcid) DO UPDATE SET {set_clause}"
        )
        self.conn.execute(sql, valores)

    def _update_flight_plan(self, data: Dict[str, str], raw: str = ""):
        """UPDATE dinámico solo de los campos presentes en la trama CHG."""
        arcid = data["ARCID"]
        cols  = self._columnas_presentes(data)
        if not cols:
            return
        set_clause = ", ".join(f"{c} = ?" for c in cols.keys())
        set_clause += ", updated_at = current_localtimestamp()"
        sql = f"UPDATE flight_plans SET {set_clause} WHERE arcid = ?"
        self.conn.execute(sql, list(cols.values()) + [arcid])

    def _cancel_flight_plan(self, arcid: str):
        self.conn.execute(
            "UPDATE flight_plans SET status = 'CANCELLED', "
            "updated_at = current_localtimestamp() WHERE arcid = ?",
            [arcid],
        )

    def _log(self, msg_type: str, arcid: Optional[str], raw: str):
        self.conn.execute(
            "INSERT INTO fdp_log (msg_type, arcid, raw) VALUES (?, ?, ?)",
            [msg_type, arcid, raw],
        )
