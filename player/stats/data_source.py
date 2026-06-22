"""Fuente unificada de filas de plots para el constructor de estadísticas.

Dos implementaciones tras la misma interfaz:
- SessionSource: filas Plot.to_dict() de la sesión en memoria.
- DuckDBSource: tabla asterix_plots de pass_analytics.duckdb.
Ambas devuelven filas con las mismas claves normalizadas (NORMALIZED_KEYS).
Python puro, sin pandas.
"""
from abc import ABC, abstractmethod

NORMALIZED_KEYS = ("sac_sic", "timestamp", "lat", "lon", "flight_level",
                   "mode3a", "raw_range", "raw_azimuth",
                   "category", "callsign", "mode_s", "altitude_ft",
                   "ground_speed", "track_angle", "vertical_rate",
                   "garbled", "frequency", "pd")


def _filter(rows, radars, t_min, t_max):
    out = rows
    if radars:
        rset = set(radars)
        out = [r for r in out if r.get("sac_sic") in rset]
    if t_min is not None:
        out = [r for r in out if (r.get("timestamp") or 0) >= t_min]
    if t_max is not None:
        out = [r for r in out if (r.get("timestamp") or 0) <= t_max]
    return out


class DataSource(ABC):
    @abstractmethod
    def load(self, *, radars=None, t_min=None, t_max=None):
        """Lista de dicts con claves NORMALIZED_KEYS."""

    @abstractmethod
    def radars(self):
        """Lista ordenada y única de sac_sic disponibles."""


class SessionSource(DataSource):
    def __init__(self, records):
        self._rows = [self._norm(r) for r in (records or [])]

    @staticmethod
    def _norm(r):
        return {
            "sac_sic": r.get("sac_sic"),
            "timestamp": r.get("timestamp", r.get("time")),
            "lat": r.get("lat"),
            "lon": r.get("lon"),
            "flight_level": r.get("flight_level"),
            "mode3a": r.get("mode3a"),
            "raw_range": r.get("raw_range"),
            "raw_azimuth": r.get("raw_azimuth"),
            "category": r.get("category"),
            "callsign": r.get("callsign"),
            # SOLO la dirección Mode S real (24 bits). El fallback a track_id metía
            # el squawk (Mode 3/A) cuando no había dirección — la dimensión "Mode S"
            # mostraba códigos SSR octales en vez de aircraft addresses.
            "mode_s": r.get("mode_s") or r.get("target_address"),
            "altitude_ft": r.get("altitude_ft"),
            "ground_speed": r.get("ground_speed"),
            "track_angle": r.get("track_angle"),
            "vertical_rate": r.get("vertical_rate"),
            "garbled": r.get("garbled"),
            "frequency": r.get("frequency"),
            "pd": r.get("pd"),
        }

    def load(self, *, radars=None, t_min=None, t_max=None):
        return _filter(list(self._rows), radars, t_min, t_max)

    def radars(self):
        return sorted({r["sac_sic"] for r in self._rows if r["sac_sic"]})


import duckdb


class DuckDBSource(DataSource):
    def __init__(self, db_path="pass_analytics.duckdb", conn=None):
        # `conn`: conexión DuckDB viva del app (repo_db.conn). Si se provee, se
        # reutiliza —los mismos datos que ve el PASS— evitando abrir una segunda
        # conexión, que DuckDB rechaza si la config (read_only) difiere.
        self.db_path = db_path
        self._conn = conn

    def _query(self, sql, params=()):
        if self._conn is not None:
            cur = self._conn.cursor()
            try:
                cur.execute(sql, params)
                cols = [d[0] for d in cur.description]
                return [dict(zip(cols, row)) for row in cur.fetchall()]
            finally:
                cur.close()
        with duckdb.connect(self.db_path, read_only=True) as con:
            cur = con.execute(sql, params)
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]

    def load(self, *, radars=None, t_min=None, t_max=None):
        where, params = [], []
        if radars:
            where.append("sac_sic IN (" + ",".join(["?"] * len(radars)) + ")")
            params += list(radars)
        if t_min is not None:
            where.append("timestamp >= ?"); params.append(t_min)
        if t_max is not None:
            where.append("timestamp <= ?"); params.append(t_max)
        clause = (" WHERE " + " AND ".join(where)) if where else ""
        sql = ("SELECT sac_sic, timestamp, lat, lon, flight_level, mode3a, "
               "raw_range, raw_azimuth, category, callsign, NULLIF(mode_s, '') AS mode_s, altitude_ft, "
               "ground_speed, track_angle, vertical_rate, garbled, frequency, pd FROM asterix_plots" + clause)
        return self._query(sql, params)

    def radars(self):
        rows = self._query("SELECT DISTINCT sac_sic FROM asterix_plots "
                           "WHERE sac_sic IS NOT NULL ORDER BY sac_sic")
        return [r["sac_sic"] for r in rows]
