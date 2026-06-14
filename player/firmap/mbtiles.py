"""Lectura/escritura de cache de tiles en formato MBTiles (SQLite estándar).

MBTiles guarda las filas en esquema TMS (y invertido respecto a XYZ). Este módulo
expone una API en XYZ y hace la conversión internamente.
Spec: https://github.com/mapbox/mbtiles-spec
"""
import sqlite3


def _tms_y(z: int, y: int) -> int:
    return (2 ** z - 1) - y


class MBTilesReader:
    def __init__(self, path: str):
        self.conn = sqlite3.connect(path)

    def get_tile(self, z: int, x: int, y: int):
        """Devuelve los bytes del tile XYZ (z,x,y) o None si no existe."""
        cur = self.conn.execute(
            "SELECT tile_data FROM tiles "
            "WHERE zoom_level=? AND tile_column=? AND tile_row=?",
            (z, x, _tms_y(z, y)),
        )
        row = cur.fetchone()
        return row[0] if row else None

    def metadata(self) -> dict:
        try:
            cur = self.conn.execute("SELECT name, value FROM metadata")
            return {k: v for k, v in cur.fetchall()}
        except sqlite3.Error:
            return {}

    def close(self):
        self.conn.close()


class MBTilesWriter:
    def __init__(self, path: str):
        self.conn = sqlite3.connect(path)
        self._init_schema()

    def _init_schema(self):
        c = self.conn
        c.execute("CREATE TABLE IF NOT EXISTS metadata (name TEXT, value TEXT)")
        c.execute(
            "CREATE TABLE IF NOT EXISTS tiles "
            "(zoom_level INTEGER, tile_column INTEGER, tile_row INTEGER, tile_data BLOB)"
        )
        c.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS tile_index "
            "ON tiles (zoom_level, tile_column, tile_row)"
        )
        self.conn.commit()

    def set_metadata(self, **kv):
        for k, v in kv.items():
            self.conn.execute("DELETE FROM metadata WHERE name=?", (k,))
            self.conn.execute("INSERT INTO metadata (name, value) VALUES (?, ?)", (k, str(v)))
        self.conn.commit()

    def has_tile(self, z: int, x: int, y: int) -> bool:
        cur = self.conn.execute(
            "SELECT 1 FROM tiles WHERE zoom_level=? AND tile_column=? AND tile_row=?",
            (z, x, _tms_y(z, y)),
        )
        return cur.fetchone() is not None

    def put_tile(self, z: int, x: int, y: int, data: bytes):
        self.conn.execute(
            "INSERT OR REPLACE INTO tiles "
            "(zoom_level, tile_column, tile_row, tile_data) VALUES (?, ?, ?, ?)",
            (z, x, _tms_y(z, y), sqlite3.Binary(data)),
        )

    def commit(self):
        self.conn.commit()

    def close(self):
        self.conn.commit()
        self.conn.close()
