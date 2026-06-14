"""Acceso read-only a la base de datos ATM (data/atm/atm.duckdb).

Expone aeropuertos, aerovías, procedimientos (SID/STAR/IAP) y fixes ya
geometrizados (lat/lon decimal) para alimentar el menú Mapas y el perfil.
Si la base no existe, `available()` devuelve False y los getters dan vacío
(la app sigue con sus fuentes previas).
"""
import os
import threading

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "data", "atm", "atm.duckdb")

_conn = None
_lock = threading.Lock()


def available() -> bool:
    return os.path.exists(DB_PATH)


def _con():
    global _conn
    if _conn is None:
        import duckdb
        _conn = duckdb.connect(DB_PATH, read_only=True)
    return _conn


def parse_dms(image: str):
    """'325755S' -> -32.9653 ; '0640721W' -> -64.1225. None si inválido."""
    if not image:
        return None
    s = image.strip()
    if not s:
        return None
    hemi = s[-1].upper()
    digits = s[:-1]
    if hemi in ("S", "N"):
        if len(digits) < 6:
            return None
        dd, mm, ss = digits[0:2], digits[2:4], digits[4:6]
    elif hemi in ("E", "W"):
        if len(digits) < 7:
            return None
        dd, mm, ss = digits[0:3], digits[3:5], digits[5:7]
    else:
        return None
    try:
        val = int(dd) + int(mm) / 60.0 + int(ss) / 3600.0
    except ValueError:
        return None
    if hemi in ("S", "W"):
        val = -val
    return val


def _fix_coords():
    """Dict {identifier_name(trim): (lat, lon)} de todos los fixpoints."""
    rows = _con().execute(
        "SELECT TRIM(identifier_name), latitude_image, longitude_image FROM fixpoints_kernel"
    ).fetchall()
    out = {}
    for name, lat_i, lon_i in rows:
        lat, lon = parse_dms(lat_i), parse_dms(lon_i)
        if lat is not None and lon is not None:
            out[name] = (lat, lon)
    return out


def airports():
    """{ICAO: {lat, lon, alt_ft, transition_level}} ordenado por ICAO."""
    if not available():
        return {}
    rows = _con().execute(
        "SELECT TRIM(k.identifier_name), k.latitude_image, k.longitude_image, "
        "       k.place_altitude, e.transition_level "
        "FROM airports_kernel k "
        "LEFT JOIN airport_environment e ON TRIM(k.identifier_name)=TRIM(e.identifier_name) "
        "ORDER BY 1"
    ).fetchall()
    out = {}
    for icao, lat_i, lon_i, alt, tl in rows:
        lat, lon = parse_dms(lat_i), parse_dms(lon_i)
        if lat is None or lon is None:
            continue
        out[icao] = {"lat": lat, "lon": lon, "alt_ft": alt, "transition_level": tl}
    return out


# ---- Aerovías ----
def _airway_category_clause(categoria: str) -> str:
    if categoria == "RNAV":
        return "TRIM(rnp_type) <> ''"
    if categoria == "SUP":
        return "TRIM(rnp_type) = '' AND LEFT(identifier_name,1) = 'U'"
    if categoria == "INF":
        return "TRIM(rnp_type) = '' AND LEFT(identifier_name,1) <> 'U'"
    return "1=1"


def airways(categoria: str):
    """[{'name', 'points':[(lat,lon),...]}] de la categoría (SUP/INF/RNAV)."""
    if not available():
        return []
    coords = _fix_coords()
    names = [r[0] for r in _con().execute(
        f"SELECT TRIM(identifier_name) FROM airways_kernel "
        f"WHERE {_airway_category_clause(categoria)} ORDER BY 1").fetchall()]
    out = []
    for name in names:
        pts = _con().execute(
            "SELECT TRIM(fixpoint_identity) FROM airways_pathpoints "
            "WHERE TRIM(airway_identity)=? ORDER BY sequence_number", [name]).fetchall()
        line = [coords[p[0]] for p in pts if p[0] in coords]
        if len(line) >= 2:
            out.append({"name": name, "points": line})
    return out


# ---- Procedimientos ----
_PROC = {
    "SID": ("departure_pathpoints", "route_identity"),
    "STAR": ("arrival_pathpoints", "route_identity"),
    "IAP": ("approach_pathpoints", "route_identity"),
}


def procedures(icao: str, kind: str):
    """[{'name', 'points'}] de los procedimientos `kind` del aeropuerto `icao`."""
    if not available() or kind not in _PROC:
        return []
    coords = _fix_coords()
    table, rcol = _PROC[kind]
    if kind == "IAP":
        # approach_pathpoints no tiene airport; se filtra por approach_routes
        routes = [r[0] for r in _con().execute(
            "SELECT DISTINCT TRIM(identifier_name) FROM approach_routes "
            "WHERE TRIM(airport_identity)=? ORDER BY 1", [icao]).fetchall()]
    else:
        routes = [r[0] for r in _con().execute(
            f"SELECT DISTINCT TRIM({rcol}) FROM {table} "
            f"WHERE TRIM(airport_identity)=? ORDER BY 1", [icao]).fetchall()]
    out = []
    for rid in routes:
        if kind == "IAP":
            pts = _con().execute(
                f"SELECT TRIM(fixpoint_identity) FROM {table} "
                f"WHERE TRIM({rcol})=? ORDER BY sequence_number", [rid]).fetchall()
        else:
            pts = _con().execute(
                f"SELECT TRIM(fixpoint_identity) FROM {table} "
                f"WHERE TRIM({rcol})=? AND TRIM(airport_identity)=? "
                f"ORDER BY sequence_number", [rid, icao]).fetchall()
        line = [coords[p[0]] for p in pts if p[0] in coords]
        if len(line) >= 2:
            out.append({"name": rid, "points": line})
    return out


def airports_with_procedures():
    """ICAOs que tienen al menos un SID/STAR/IAP, ordenados."""
    if not available():
        return []
    icaos = set()
    for tbl in ("departure_procedures", "arrival_procedures", "approach_routes"):
        for r in _con().execute(f"SELECT DISTINCT TRIM(airport_identity) FROM {tbl}").fetchall():
            icaos.add(r[0])
    return sorted(icaos)


# ---- Fixes ----
def fixes(kinds=None):
    """[{'name','lat','lon','kind'}] de fixpoints, filtrando por kind_specifier."""
    if not available():
        return []
    sql = ("SELECT TRIM(identifier_name), kind_specifier, latitude_image, longitude_image "
           "FROM fixpoints_kernel")
    params = []
    if kinds:
        ph = ",".join("?" for _ in kinds)
        sql += f" WHERE TRIM(kind_specifier) IN ({ph})"
        params = list(kinds)
    out = []
    for name, kind, lat_i, lon_i in _con().execute(sql, params).fetchall():
        lat, lon = parse_dms(lat_i), parse_dms(lon_i)
        if lat is not None and lon is not None:
            out.append({"name": name, "lat": lat, "lon": lon, "kind": (kind or "").strip()})
    return out
