"""Acceso read-only a la base de datos ATM (data/atm/atm.duckdb).

Expone aeropuertos, aerovías, procedimientos (SID/STAR/IAP) y fixes ya
geometrizados (lat/lon decimal) para alimentar el menú Mapas y el perfil.
Si la base no existe, `available()` devuelve False y los getters dan vacío
(la app sigue con sus fuentes previas).
"""
import os
import threading
import contextlib

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


def _close():
    """Cierra la conexión read-only (necesario antes de escribir: DuckDB es
    single-writer y no admite una RW con una RO abierta del mismo proceso)."""
    global _conn
    if _conn is not None:
        try:
            _conn.close()
        except Exception:
            pass
        _conn = None


@contextlib.contextmanager
def _writer():
    """Conexión read-write corta. Cierra la RO antes y la deja cerrada al salir
    (se reabre perezosamente en la próxima lectura)."""
    import duckdb
    with _lock:
        _close()
        w = duckdb.connect(DB_PATH, read_only=False)
        try:
            yield w
        finally:
            w.close()


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
# ---- Áreas restringidas / prohibidas / peligrosas ----
_DAY_COLS = ["monday_activity", "tuesday_activity", "wednesday_activity",
             "thursday_activity", "friday_activity", "saturday_activity", "sunday_activity"]


def _restricted_vertices(name):
    """[(sequence_number, lat, lon)] del área, parseando DMS (lat_dec viene '00')."""
    rows = _con().execute(
        "SELECT sequence_number, latitude_image, longitude_image "
        "FROM restricted_vertices WHERE TRIM(airspace_identity)=? ORDER BY sequence_number",
        [name]).fetchall()
    out = []
    for seq, lat_i, lon_i in rows:
        lat, lon = parse_dms(lat_i), parse_dms(lon_i)
        if lat is not None and lon is not None:
            out.append((seq, lat, lon))
    return out


def restricted_airspaces(kinds=None):
    """[Area] desde la DB. `kinds`: subconjunto de {'R','P','D'} o None=todas.

    Las áreas de la base se modelan como permanentes (con días de semana si la
    base los trae). Círculo: vértice sequence_number=0 = centro + circle_radius (NM).
    """
    if not available():
        return []
    from player.areas.model import Area, Vigencia
    sql = ("SELECT TRIM(identifier_name), area_kind, lower_altitude, upper_altitude, "
           "contour_figure, circle_radius, permanent, prediction_time, " + ", ".join(_DAY_COLS) +
           " FROM restricted_airspaces")
    params = []
    if kinds:
        ph = ",".join("?" for _ in kinds)
        sql += f" WHERE area_kind IN ({ph})"
        params = list(kinds)
    out = []
    for row in _con().execute(sql, params).fetchall():
        name = row[0]
        kind = (row[1] or "").strip()
        lo, up = int(row[2] or 0), int(row[3] or 999)
        fig = (row[4] or "").strip()
        radius = float(row[5] or 0.0)
        pred_time = int(row[7]) if row[7] is not None else 120
        days = {i for i, flag in enumerate(row[8:15]) if (flag or "").strip().upper() == "Y"}
        vig = Vigencia(permanente=True, dias=days)
        verts = _restricted_vertices(name)
        if fig == "C":
            center = next(((la, lo2) for seq, la, lo2 in verts if seq == 0), None)
            if center is None and verts:
                center = (verts[0][1], verts[0][2])
            if center is None or radius <= 0.0:
                continue
            out.append(Area(name=name, kind=kind, shape="circle", lower_fl=lo,
                            upper_fl=up, center=center, radius_nm=radius,
                            vigencia=vig, origen="db", prediction_time=pred_time))
        else:
            pts = [(la, lo2) for _seq, la, lo2 in verts]
            if len(pts) < 3:
                continue
            out.append(Area(name=name, kind=kind, shape="poly", lower_fl=lo,
                            upper_fl=up, vertices=pts, vigencia=vig, origen="db",
                            prediction_time=pred_time))
    return out


def _dms_image(val, is_lon: bool) -> str:
    """Decimal -> imagen DMS entera compatible con parse_dms ('DDMMSSH')."""
    hemi = ("E" if val >= 0 else "W") if is_lon else ("N" if val >= 0 else "S")
    v = abs(val)
    deg = int(v)
    m = int((v - deg) * 60)
    s = int(round(((v - deg) * 60 - m) * 60))
    if s >= 60:
        s -= 60
        m += 1
    if m >= 60:
        m -= 60
        deg += 1
    return (f"{deg:03d}{m:02d}{s:02d}{hemi}" if is_lon
            else f"{deg:02d}{m:02d}{s:02d}{hemi}")


def delete_area(name: str):
    """Borra un área (filas en restricted_airspaces + restricted_vertices)."""
    nm = (name or "").strip()
    if not nm:
        return
    with _writer() as w:
        w.execute("DELETE FROM restricted_vertices WHERE TRIM(airspace_identity)=?", [nm])
        w.execute("DELETE FROM restricted_airspaces WHERE TRIM(identifier_name)=?", [nm])


def write_area(area):
    """Inserta/reemplaza un área en la DB como permanente (upsert por nombre).

    Polígono: vértices 1..n. Círculo: vértice 0 = centro + circle_radius (NM).
    Genera los campos DMS imagen (lat_dec/lon_dec quedan en decimal informativo).
    """
    nm = (area.name or "").strip()
    if not nm:
        raise ValueError("El área necesita un nombre")
    v = area.vigencia
    day_vals = ["Y" if i in v.dias else "N" for i in range(7)]
    sched = "Y" if (v.desde and v.hasta) else "N"
    st = v.desde.strftime("%H%M") if v.desde else None
    et = v.hasta.strftime("%H%M") if v.hasta else None
    fig = "C" if area.shape == "circle" else "P"
    radius = float(area.radius_nm or 0.0)

    if area.shape == "circle":
        if not area.center:
            raise ValueError("Círculo sin centro")
        verts = [(0, area.center[0], area.center[1])]
    else:
        if len(area.vertices) < 3:
            raise ValueError("Polígono con menos de 3 vértices")
        verts = [(i + 1, la, lo) for i, (la, lo) in enumerate(area.vertices)]

    cols = ("identifier_name, area_kind, lower_altitude, upper_altitude, lower_unit, "
            "upper_unit, contour_figure, circle_radius, radius_unit, scheduled_flag, "
            "permanent, prediction_time, starting_time, ending_time, "
            + ", ".join(_DAY_COLS))
    ph = ", ".join("?" for _ in range(14 + 7))
    row = [nm, area.kind, int(area.lower_fl), int(area.upper_fl), "F", "F", fig,
           radius, "N", sched, "Y", 120, st, et] + day_vals

    with _writer() as w:
        w.execute("DELETE FROM restricted_vertices WHERE TRIM(airspace_identity)=?", [nm])
        w.execute("DELETE FROM restricted_airspaces WHERE TRIM(identifier_name)=?", [nm])
        w.execute(f"INSERT INTO restricted_airspaces ({cols}) VALUES ({ph})", row)
        for seq, la, lo in verts:
            w.execute(
                "INSERT INTO restricted_vertices "
                "(airspace_identity, sequence_number, latitude_image, longitude_image, "
                "lat_dec, lon_dec, visual) VALUES (?,?,?,?,?,?,?)",
                [nm, seq, _dms_image(la, False), _dms_image(lo, True),
                 f"{la:.6f}", f"{lo:.6f}", 1])


# update == upsert
update_area = write_area


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
