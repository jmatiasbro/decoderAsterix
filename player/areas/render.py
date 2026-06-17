"""raw_segments y colores por tipo de área para el map_manager.

Se reusa el pipeline de cartografía existente: cada categoría (R/P/D) es una
capa "AREA::{kind}" con su color. El renderer (PPI/ODS) y la vista FIR la pintan
como contorno cerrado + relleno tenue + etiqueta (nombre + banda de niveles).
"""
from player.areas.model import UNLIMITED_FL

AREA_LAYER = "AREA"

# Color por tipo (vale para PPI técnico, ODS y satelital).
AREA_COLORS = {
    "P": "#FF3B3B",    # Prohibida  → rojo
    "R": "#FFB040",    # Restringida→ ámbar
    "D": "#FF8C1A",    # Peligrosa  → naranja
    "C": "#39C5FF",    # Personalizada
}


def _fl(v):
    return "UNL" if v is None or v >= UNLIMITED_FL else f"{int(v):03d}"


def _centroid(pts):
    n = len(pts)
    if n == 0:
        return None
    return (sum(p[0] for p in pts) / n, sum(p[1] for p in pts) / n)


def _label(a):
    return f"{a.name.strip()} {_fl(a.lower_fl)}/{_fl(a.upper_fl)}"


def area_segments(areas):
    """raw_segments de una lista de Area (una categoría) en formato VideoMap."""
    segs = []
    for a in areas:
        pl = a.polilinea()
        if len(pl) < 2:
            continue
        lat0, lon0 = pl[0]
        segs.append(("M", AREA_LAYER, lat0, lon0))
        for lat, lon in pl[1:]:
            segs.append(("L", AREA_LAYER, lat, lon))
        segs.append(("C", AREA_LAYER))
        c = _centroid(pl[:-1] if pl[0] == pl[-1] else pl)
        if c:
            segs.append(("T", AREA_LAYER, c[0], c[1], _label(a)))
    return segs
