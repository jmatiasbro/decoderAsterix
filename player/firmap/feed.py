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


def _alert_ids(radar):
    ids = set()
    for c in getattr(radar, "conflictos_activos", []) or []:
        try:
            ids.add(c[0]); ids.add(c[1])
        except (IndexError, TypeError):
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
