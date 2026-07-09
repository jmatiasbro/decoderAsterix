"""Lookup puntual de planes de vuelo FDP por ARCID/callsign.

Pensado para consultas esporádicas desde el hilo de UI (p. ej. al abrir el
diálogo de detalle de un track). NO usar en el render por frame.

Robusto ante base/tabla ausente: si fdp.duckdb no existe o aún no tiene la
tabla flight_plans, devuelve None sin crear nada ni lanzar excepción.
"""
import duckdb
from pathlib import Path
from threading import Lock

_DB = Path(__file__).resolve().parent.parent.parent / "data" / "fdp" / "fdp.duckdb"

_COLS = ["arcid", "adep", "ades", "aircraft_type", "wtc",
         "requested_fl", "route", "eobt", "cop", "status"]
_SQL = (f"SELECT {', '.join(_COLS)} FROM flight_plans "
        "WHERE UPPER(arcid) = ?")

_conn = None
_lock = Lock()


def buscar_plan(arcid: str):
    """Devuelve el plan de vuelo como dict, o None si no hay match/base."""
    if not arcid:
        return None
    key = str(arcid).strip().upper()
    if not key or not _DB.exists():
        return None

    global _conn
    with _lock:
        try:
            if _conn is None:
                _conn = duckdb.connect(str(_DB))
            row = _conn.execute(_SQL, [key]).fetchone()
        except Exception:
            return None

    return dict(zip(_COLS, row)) if row else None
