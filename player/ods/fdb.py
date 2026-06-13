"""Construcción del Data Block ODS (FDB/LDB). Sin datos de plan de vuelo:
el nivel es FL actual + flecha de tendencia (no hay CFL/XFL).
"""
ARROW_UP = "↑"     # ↑
ARROW_DOWN = "↓"   # ↓
ARROW_LEVEL = "="
VRATE_THRESHOLD = 100.0  # ft/min para considerar climb/descent


def format_level(fl, vrate_ftmin) -> str:
    if fl is None:
        return ""
    try:
        fl_i = int(round(float(fl)))
    except (TypeError, ValueError):
        return ""
    arrow = ARROW_LEVEL
    if vrate_ftmin is not None:
        if vrate_ftmin > VRATE_THRESHOLD:
            arrow = ARROW_UP
        elif vrate_ftmin < -VRATE_THRESHOLD:
            arrow = ARROW_DOWN
    return f"FL{fl_i:03d}{arrow}"


def _squawk(plot) -> str:
    m = getattr(plot, "mode3a", None)
    if m is None:
        return ""
    s = f"{m:04o}" if isinstance(m, int) else str(m).strip()
    return "" if s in ("", "----", "0000") else s


def build_lines(plot, full: bool = True, vrate=None):
    """Devuelve líneas del data block.

    L1: callsign (o squawk si no hay). L2: FL+tendencia. L3 (solo FDB): GS.
    `vrate` (ft/min) permite pasar la tendencia cuando el plot no la expone como
    atributo (p. ej. RadarPlot con __slots__); si es None se lee del plot.
    """
    callsign = (getattr(plot, "callsign", "") or "").strip()
    squawk = _squawk(plot)
    l1 = callsign or squawk
    lines = []
    if l1:
        lines.append(l1)
    v = vrate if vrate is not None else getattr(plot, "vertical_rate_ftmin", None)
    lvl = format_level(getattr(plot, "flight_level", None), v)
    if lvl:
        lines.append(lvl)
    if full:
        gs = getattr(plot, "ground_speed", None)
        if gs is not None:
            try:
                lines.append(f"{int(round(float(gs)))}")
            except (TypeError, ValueError):
                pass
    return lines
