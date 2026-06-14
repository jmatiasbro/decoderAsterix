"""Construcción del Data Block ODS (FDB/LDB). Sin datos de plan de vuelo:
el nivel es FL actual + flecha de tendencia (no hay CFL/XFL).
"""
ARROW_UP = "↑"     # ↑
ARROW_DOWN = "↓"   # ↓
ARROW_LEVEL = "="
VRATE_THRESHOLD = 100.0  # ft/min para considerar climb/descent


def trend_arrow(vrate_ftmin) -> str:
    """Flecha de tendencia vertical por vrate (ft/min)."""
    if vrate_ftmin is None:
        return ARROW_LEVEL
    if vrate_ftmin > VRATE_THRESHOLD:
        return ARROW_UP
    if vrate_ftmin < -VRATE_THRESHOLD:
        return ARROW_DOWN
    return ARROW_LEVEL


def format_level(fl, vrate_ftmin) -> str:
    if fl is None:
        return ""
    try:
        fl_i = int(round(float(fl)))
    except (TypeError, ValueError):
        return ""
    return f"FL{fl_i:03d}{trend_arrow(vrate_ftmin)}"


def _squawk(plot) -> str:
    m = getattr(plot, "mode3a", None)
    if m is None:
        return ""
    s = f"{m:04o}" if isinstance(m, int) else str(m).strip()
    return "" if s in ("", "----", "0000") else s


def _mode_s_addr(plot) -> str:
    adr = getattr(plot, "mode_s", None)
    if adr is None:
        return ""
    s = str(adr).strip()
    return "" if s in ("", "----") else s


def build_lines(plot, full: bool = True, vrate=None, fields=None, level_str=None):
    """Devuelve líneas del data block.

    L1: callsign [+ dirección Mode S] (o squawk si no hay callsign).
    L2: nivel+tendencia. L3 (solo FDB): GS.
    `vrate` (ft/min) permite pasar la tendencia cuando el plot no la expone como
    atributo (p. ej. RadarPlot con __slots__); si es None se lee del plot.
    `fields` (dict del filtro de etiquetas): si es None, todos los campos visibles
    (comportamiento histórico); si se pasa, cada campo se gatea por su toggle.
    `level_str`: cadena de nivel ya formateada (p. ej. "A035↑"/"F330↑" con TA+QNH);
    si es None se usa el FL crudo (`format_level`).
    """
    def on(key: str) -> bool:
        return True if fields is None else bool(fields.get(key, True))

    callsign = (getattr(plot, "callsign", "") or "").strip() if on("identific_aeronave") else ""
    squawk = _squawk(plot) if on("codigo_a") else ""
    l1 = callsign or squawk
    if on("direccion_aeronave"):
        adr = _mode_s_addr(plot)
        if adr:
            l1 = f"{l1} {adr}".strip()
    lines = []
    if l1:
        lines.append(l1)
    if on("codigo_c") or on("altitud_adsb"):
        if level_str is not None:
            lvl = level_str
        else:
            v = vrate if vrate is not None else getattr(plot, "vertical_rate_ftmin", None)
            lvl = format_level(getattr(plot, "flight_level", None), v)
        if lvl:
            lines.append(lvl)
    if full and on("velocidad"):
        gs = getattr(plot, "ground_speed", None)
        if gs is not None:
            try:
                lines.append(f"{int(round(float(gs)))}")
            except (TypeError, ValueError):
                pass
    return lines
