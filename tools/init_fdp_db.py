"""Crea o inicializa data/fdp/fdp.duckdb aplicando fdp_schema.sql."""
import duckdb
from pathlib import Path

ROOT   = Path(__file__).resolve().parent.parent
SCHEMA = ROOT / "data" / "fdp" / "fdp_schema.sql"
DB     = ROOT / "data" / "fdp" / "fdp.duckdb"


def init():
    DB.parent.mkdir(parents=True, exist_ok=True)
    sql = SCHEMA.read_text(encoding="utf-8")
    with duckdb.connect(str(DB)) as conn:
        conn.execute(sql)
    print(f"fdp.duckdb listo en {DB}")


if __name__ == "__main__":
    init()
