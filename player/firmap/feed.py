"""Adaptador: convierte los plots vivos del radar_widget en tracks para la
vista FIR. Reusa la proyección inversa, el armador de datablock (FDB + filtro +
A/F) y la clasificación/paleta ODS. Sin estado propio.
"""
import math


def _heading(plot, hist=None):
    """Rumbo en grados (0=N, horario). Prioriza track_angle; si no, velocidad
    suavizada; si no, el rumbo del movimiento (últimos 2 puntos de historia)."""
    ta = getattr(plot, "track_angle", None)
    if ta is not None:
        return float(ta) % 360.0
    vx = getattr(plot, "_smooth_vx", None)
    vy = getattr(plot, "_smooth_vy", None)
    if vx and vy:  # x este, y norte
        return math.degrees(math.atan2(vx, vy)) % 360.0
    if hist and len(hist) >= 2:
        pts = list(hist)
        dx = pts[-1].x - pts[-2].x
        dy = pts[-1].y - pts[-2].y
        if dx or dy:
            return math.degrees(math.atan2(dx, dy)) % 360.0
    return 0.0


def _hex_to_rgb(h):
    s = (h or "").lstrip("#")
    if len(s) == 6:
        try:
            return tuple(int(s[i:i + 2], 16) for i in (0, 2, 4))
        except ValueError:
            pass
    return (0, 229, 255)


def build_maps(radar):
    """Polilíneas y puntos (lat/lon) de las capas visibles del map_manager, para
    dibujar sobre la vista satelital. Cada capa usa su propio color (las aerovías
    SUP/INF/RNAV ya vienen con color distinto desde el map_manager)."""
    mm = getattr(radar, "map_manager", None)
    if mm is None:
        return {"lines": [], "points": []}
    lines, points = [], []
    for layer in mm.get_visible_layers():
        base = _hex_to_rgb(getattr(layer, "color", None))
        is_area = str(getattr(layer, "name", "")).startswith("AREA::")
        cur = None
        for seg in getattr(layer, "raw_segments", []):
            if len(seg) < 2:
                continue
            t = seg[0]
            if t in ("S", "T") and len(seg) >= 5:
                points.append({"lat": seg[2], "lon": seg[3], "text": seg[4],
                               "symbol": t == "S", "color": base})
                continue
            if t == "M" and len(seg) >= 4:
                if cur and len(cur) >= 2:
                    lines.append({"pts": cur, "color": base, "fill": is_area})
                cur = [(seg[2], seg[3])]
            elif t == "L" and len(seg) >= 4:
                if cur is None:
                    cur = []
                cur.append((seg[2], seg[3]))
            elif t == "C" and cur:
                cur.append(cur[0])
        if cur and len(cur) >= 2:
            lines.append({"pts": cur, "color": base, "fill": is_area})
    return {"lines": lines, "points": points}


def _alert_ids(radar):
    ids = set()
    for c in getattr(radar, "conflictos_activos", []) or []:
        try:
            ids.add(c[0]); ids.add(c[1])
        except (IndexError, TypeError):
            pass
    for a in getattr(radar, "apw_activos", []) or []:
        try:
            ids.add(a.track_id)
        except AttributeError:
            pass
    for a in getattr(radar, "msaw_activos", []) or []:
        try:
            ids.add(a.track_id)
        except AttributeError:
            pass
    return ids


def _trail(radar, proy, plot, max_pts=10):
    hist = getattr(radar, "history", {}).get(plot.id)
    if not hist:
        return []
    pts = []
    for hp in list(hist)[-max_pts:]:
        try:
            lat, lon = proy.xy_to_latlon(hp.x, hp.y)
            if lat is not None and not (lat == 0.0 and lon == 0.0):
                pts.append((lat, lon))
        except Exception:
            continue
    return pts


def build_tracks(radar):
    """Devuelve la lista de tracks (dicts) para FirMapView.set_tracks()."""
    proy = getattr(radar, "proy", None)
    # `activo` ya garantiza que la proyección esté construida (StereographicLocal
    # usa _proj privado; NO chequear proy.proj, que no existe -> siempre vacío).
    if proy is None or not getattr(proy, "activo", False):
        return []
    focused = getattr(radar, "focused_target_id", None)
    alerts = _alert_ids(radar)
    from player.ods import track_state as _ts, palette as _pal

    # Igual que el PPI: combinar tracks confirmados + pendientes (en vista técnica
    # con barrido activo, los plots viven en pending_tracks hasta ser iluminados).
    plots = {}
    plots.update(getattr(radar, "pending_tracks", {}) or {})
    plots.update(getattr(radar, "tracks", {}) or {})

    out = []
    for plot in list(plots.values()):
        try:
            if not plot.is_alive():
                continue
            lat, lon = proy.xy_to_latlon(plot.x, plot.y)
            if lat is None or lon is None or (lat == 0.0 and lon == 0.0):
                continue
            lines = radar._build_plot_label_lines(plot)
            try:
                estado = _ts.classify(plot, False)
                rgb = _pal.state_rgb(estado, selected=False)
            except Exception:
                rgb = _pal.TOOL_RBL
            out.append({
                "id": plot.id,
                "lat": lat, "lon": lon,
                "heading": _heading(plot, getattr(radar, "history", {}).get(plot.id)),
                "lines": lines,
                "color": rgb,
                "selected": (plot.id == focused),
                "alert": (plot.id in alerts),
                "trail": _trail(radar, proy, plot),
            })
        except Exception:
            continue
    return out
