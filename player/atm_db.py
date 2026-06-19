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
    # Superiores (upper): el nombre de la aerovía empieza con 'U'. El resto, inferiores.
    if categoria == "SUP":
        return "LEFT(identifier_name,1) = 'U'"
    if categoria == "INF":
        return "LEFT(identifier_name,1) <> 'U'"
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


def msaw_params():
    """MsawParams desde la tabla msaw_parameters (look-ahead, ROCD, cfl_thold)."""
    from player.msaw.model import MsawParams
    if not available():
        return MsawParams()
    row = _con().execute(
        "SELECT time_to_prediction, rocd, cfl_thold FROM msaw_parameters LIMIT 1").fetchone()
    if not row:
        return MsawParams()
    return MsawParams(time_to_prediction=int(row[0] or 120),
                      rocd=int(row[1] or 1500), cfl_thold=int(row[2] or 5))


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


# ── MSAW: zonas poligonales y perfiles de aproximación ──────────────────────

# parse_dms ya cubre el formato DMS entero del FDP; lo exponemos con el nombre
# usado por los readers/consumidores MSAW.
dms_to_dd = parse_dms


def _dms_dot_to_dd(s):
    """DMS con segundos decimales: '312228.69S' / '0641226.21W' -> DD, o None."""
    if not s or not isinstance(s, str):
        return None
    s = s.strip()
    if not s:
        return None
    hemi = s[-1].upper()
    body = s[:-1]
    intpart = body.split(".")[0]
    try:
        if len(intpart) == 6:         # DDMMSS(.ss) lat
            d, m = int(intpart[0:2]), int(intpart[2:4])
            sec = float(body[4:])
        elif len(intpart) == 7:       # DDDMMSS(.ss) lon
            d, m = int(intpart[0:3]), int(intpart[3:5])
            sec = float(body[5:])
        else:
            return parse_dms(s)
        dd = d + m / 60 + sec / 3600
        return round(-dd if hemi in ("S", "W") else dd, 6)
    except (ValueError, TypeError):
        return None


def minimums_zones():
    """[{identifier, msa_ft, coords:[(lat,lon)...]}] (msa en ft = altitude*100)."""
    if not available():
        return []
    try:
        rows = _con().execute("""
            SELECT TRIM(mzk.identifier) AS ident, mzk.altitude,
                   mzv.sequence_number, mzv.latitude_image, mzv.longitude_image
            FROM minimums_zones_kernel mzk
            JOIN minimums_zones_vertices mzv
              ON mzk.identifier = mzv.zone_identifier
            ORDER BY ident, mzv.sequence_number
        """).fetchall()
    except Exception:
        return []
    out = {}
    for ident, alt, _seq, lat_i, lon_i in rows:
        lat, lon = parse_dms(lat_i), parse_dms(lon_i)
        if lat is None or lon is None:
            continue
        z = out.setdefault(ident, {"identifier": ident,
                                   "msa_ft": int(float(alt) * 100), "coords": []})
        z["coords"].append((lat, lon))
    return [z for z in out.values() if len(z["coords"]) >= 3]


def apm_corridors(airport=None):
    """Corredores APM con near/far no nulos. Distancias en NM, slopes en °."""
    if not available():
        return []
    where = "WHERE TRIM(ap.airport_id) = ?" if airport else ""
    params = [airport] if airport else []
    try:
        rows = _con().execute(f"""
            SELECT TRIM(ap.airport_id), TRIM(ap.runway_id),
                   ap.min_distance, ap.max_distance, ap.half_wide,
                   ap.lower_slope, ap.upper_slope, ap.glide_slope,
                   ap.near_latitude, ap.near_longitude,
                   ap.far_latitude, ap.far_longitude,
                   ak.place_altitude
            FROM apm_profiles_kernel ap
            JOIN airports_kernel ak ON ap.airport_id = ak.identifier_name
            {where}
            ORDER BY ap.airport_id, ap.runway_id
        """, params).fetchall()
    except Exception:
        return []
    out = []
    for (apid, rwy, mind, maxd, hw, lo, up, gl,
         nlat, nlon, flat, flon, elev) in rows:
        if not (nlat and nlon and flat and flon):
            continue
        near = (_dms_dot_to_dd(nlat), _dms_dot_to_dd(nlon))
        far = (_dms_dot_to_dd(flat), _dms_dot_to_dd(flon))
        if None in near or None in far:
            continue
        out.append({
            "airport": apid, "runway": rwy,
            "near": near, "far": far,
            "min_dist": float(mind), "max_dist": float(maxd),
            "half_wide_nm": float(hw),
            "lower_slope": float(lo), "upper_slope": float(up),
            "glide_slope": float(gl) if gl is not None else None,
            "thr_elev_ft": int(elev or 0),
        })
    return out


def profile_corridors(airport=None):
    """[{profile, airport, runway, kind, points:[(lat,lon,min_ft,dlat,az)...]}]."""
    if not available():
        return []
    where = "WHERE TRIM(pk.airport) = ?" if airport else ""
    params = [airport] if airport else []
    try:
        rows = _con().execute(f"""
            SELECT TRIM(pk.name), TRIM(pk.airport), TRIM(pk.runway), TRIM(pk.kind),
                   pp.seq_num, pp.latitude, pp.longitude,
                   pp.altitude, pp.distance_lateral, pp.azimut
            FROM profiles_kernel pk
            JOIN profile_points pp ON pk.name = pp.perfil_id
            {where}
            ORDER BY pk.name, pp.seq_num
        """, params).fetchall()
    except Exception:
        return []
    out = {}
    for name, apid, rwy, kind, _seq, lat_i, lon_i, alt, dlat, az in rows:
        lat, lon = parse_dms(lat_i), parse_dms(lon_i)
        if lat is None or lon is None:
            continue
        p = out.setdefault(name, {"profile": name, "airport": apid,
                                  "runway": rwy, "kind": kind, "points": []})
        p["points"].append((lat, lon, int(float(alt) * 100),
                            float(dlat or 0.5), int(az or 0)))
    return [p for p in out.values() if len(p["points"]) >= 2]


def profile_parameters():
    """Tolerancias globales de perfiles (escalas aplicadas)."""
    default = {"tol_heading": 18, "tol_altitude_ft": 300,
               "tol_distance_nm": 0.5, "entorno_aerodrome_nm": 3}
    if not available():
        return default
    try:
        row = _con().execute(
            "SELECT tol_heading, tol_altitude, tol_distance, entorno_aerodrome "
            "FROM profile_parameters LIMIT 1").fetchone()
    except Exception:
        return default
    if not row:
        return default
    return {
        "tol_heading": int(row[0] or 18),
        "tol_altitude_ft": int(float(row[1] or 3) * 100),
        "tol_distance_nm": float(row[2] or 0.5),
        "entorno_aerodrome_nm": float(row[3] or 3),
    }
