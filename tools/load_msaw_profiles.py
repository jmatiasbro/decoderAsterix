"""Carga (idempotente) las tablas MSAW de zonas/perfiles en atm.duckdb.

Uso:
    python tools/load_msaw_profiles.py
"""
import os
import sys

import duckdb

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DB_PATH = os.path.join(ROOT, "data", "atm", "atm.duckdb")
SCHEMA_SQL = os.path.join(ROOT, "data", "atm", "msaw_profiles_schema-1.sql")
DATA_SQL = os.path.join(ROOT, "data", "atm", "msaw_profiles_data.sql")

TABLES = [
    "minimums_zones_vertices",
    "minimums_zones_kernel",
    "profile_points",
    "profiles_kernel",
    "profile_parameters",
    "apm_profiles_kernel",
]


def _exec_statements(con, sql_text):
    """Ejecuta sentencias separadas por ';', tolerando fallos de vistas."""
    for stmt in sql_text.split(";"):
        s = stmt.strip()
        if not s:
            continue
        try:
            con.execute(s)
        except Exception as e:
            if "VIEW" in s.upper():
                print(f"[WARN] vista omitida: {e}")
            else:
                raise


def main():
    if not os.path.exists(DB_PATH):
        sys.exit(f"No existe la DB: {DB_PATH}")
    schema = open(SCHEMA_SQL, encoding="utf-8").read()
    data = open(DATA_SQL, encoding="utf-8").read()
    con = duckdb.connect(DB_PATH, read_only=False)
    try:
        _exec_statements(con, schema)            # CREATE TABLE IF NOT EXISTS
        for t in TABLES:                          # idempotencia: limpiar antes
            con.execute(f"DELETE FROM {t}")
        _exec_statements(con, data)               # INSERT
        for t in TABLES:
            n = con.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
            print(f"{t}: {n} filas")
    finally:
        con.close()


if __name__ == "__main__":
    main()
