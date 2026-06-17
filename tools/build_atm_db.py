"""Construye la base DuckDB de datos ATM (FDP INDRA / EANA) desde el schema +
los INSERTs. Rebuild idempotente (borra y recrea).

Uso:
  python tools/build_atm_db.py
  python tools/build_atm_db.py --out data/atm/atm.duckdb \\
        --schema data/atm/atm_schema_duckdb.sql --data data/atm/atm_data_duckdb.sql
"""
import argparse
import os
import re
import sys

import duckdb

DEF_DIR = os.path.join("data", "atm")

# Quita las cláusulas FOREIGN KEY (con su coma previa). El dump original de
# PostgreSQL no tenía FKs; varias de las agregadas referencian columnas no-únicas
# y DuckDB las rechaza. Mantenemos PRIMARY KEY. Las relaciones siguen siendo
# implícitas por convención de nombres.
_FK_RE = re.compile(
    r",\s*FOREIGN KEY\s*\([^)]*\)\s*REFERENCES\s+[^\s(]+\s*\([^)]*\)",
    re.IGNORECASE | re.DOTALL,
)


def strip_foreign_keys(sql: str) -> str:
    return _FK_RE.sub("", sql)


# DuckDB no reconoce 'PRAGMA foreign_keys' (Postgres-ismo). Quitar esas líneas.
_PRAGMA_RE = re.compile(r"^\s*PRAGMA\s+foreign_keys\b[^;]*;", re.IGNORECASE | re.MULTILINE)


def strip_unsupported_pragmas(sql: str) -> str:
    return _PRAGMA_RE.sub("", sql)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(DEF_DIR, "atm.duckdb"))
    ap.add_argument("--schema", default=os.path.join(DEF_DIR, "atm_schema_duckdb.sql"))
    ap.add_argument("--data", default=os.path.join(DEF_DIR, "atm_data_duckdb.sql"))
    args = ap.parse_args()

    if os.path.exists(args.out):
        os.remove(args.out)

    con = duckdb.connect(args.out)
    for label, path in [("schema", args.schema), ("data", args.data)]:
        with open(path, encoding="utf-8") as f:
            sql = f.read()
        if label == "schema":
            sql = strip_foreign_keys(sql)
        else:
            sql = strip_unsupported_pragmas(sql)
        try:
            con.execute(sql)
            print(f"[{label}] ejecutado OK ({path})")
        except Exception as e:
            print(f"[{label}] ERROR: {e}")
            con.close()
            sys.exit(1)

    # Conteo por tabla
    tables = [r[0] for r in con.execute(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema='main' AND table_type='BASE TABLE' ORDER BY table_name"
    ).fetchall()]
    print(f"\n{len(tables)} tablas:")
    total = 0
    for t in tables:
        n = con.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]
        total += n
        print(f"  {t:<32} {n:>7,}")
    print(f"  {'TOTAL filas':<32} {total:>7,}")
    con.close()
    print(f"\nListo -> {args.out}")


if __name__ == "__main__":
    main()
