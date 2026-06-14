"""Adaptador: convierte los plots vivos del radar_widget en tracks para la
vista FIR. Reusa la proyección inversa, el armador de datablock (FDB + filtro +
A/F) y la clasificación/paleta ODS. Sin estado propio.
"""
import math


def _heading(plot):
    ta = getattr(plot, "track_angle", None)
    if ta is not None:
        return float(ta) % 360.0
    vx = getattr(plot, "_smooth_vx", None)
    vy = getattr(plot, "_smooth_vy", None)
    if vx and vy:  # x este, y norte
        return math.degrees(math.atan2(vx, vy)) % 360.0
    return 0.0


def build_tracks(radar):
    """Devuelve la lista de tracks (dicts) para FirMapView.set_tracks()."""
    proy = getattr(radar, "proy", None)
    if proy is None or not getattr(proy, "activo", False) or getattr(proy, "proj", None) is None:
        return []
    focused = getattr(radar, "focused_target_id", None)
    from player.ods import track_state as _ts, palette as _pal

    out = []
    for plot in list(getattr(radar, "tracks", {}).values()):
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
                "lat": lat, "lon": lon,
                "heading": _heading(plot),
                "lines": lines,
                "color": rgb,
                "selected": (plot.id == focused),
            })
        except Exception:
            continue
    return out
