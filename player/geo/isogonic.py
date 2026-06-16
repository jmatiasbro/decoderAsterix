"""Marching squares puro: convierte una grilla escalar (declinación) en
polilíneas por nivel. Sin dependencias externas.

`values[i][j]` corresponde al nodo (lat_min + i*step, lon_min + j*step).
Devuelve {nivel: [polilinea, ...]} con polilinea = [(lat, lon), ...].
Cada polilínea es un segmento de 2 puntos (sin unir): suficiente para
dibujar como cartografía.
"""
import math


def _auto_levels(values):
    flat = [v for row in values for v in row if v is not None]
    if not flat:
        return []
    lo, hi = min(flat), max(flat)
    return [float(n) for n in range(math.ceil(lo + 1e-9), math.floor(hi - 1e-9) + 1)]


def _interp(p1, v1, p2, v2, level):
    if v2 == v1:
        return p1
    t = (level - v1) / (v2 - v1)
    return (p1[0] + t * (p2[0] - p1[0]), p1[1] + t * (p2[1] - p1[1]))


def contour_lines(values, lat_min, lon_min, step, levels=None):
    n_lat = len(values)
    n_lon = len(values[0]) if n_lat else 0
    if levels is None:
        levels = _auto_levels(values)
    out = {float(lv): [] for lv in levels}
    for i in range(n_lat - 1):
        for j in range(n_lon - 1):
            # esquinas: TL, TR, BR, BL  (lat crece con i, lon crece con j)
            tl = (lat_min + i * step, lon_min + j * step)
            tr = (lat_min + i * step, lon_min + (j + 1) * step)
            br = (lat_min + (i + 1) * step, lon_min + (j + 1) * step)
            bl = (lat_min + (i + 1) * step, lon_min + j * step)
            vtl, vtr = values[i][j], values[i][j + 1]
            vbr, vbl = values[i + 1][j + 1], values[i + 1][j]
            if None in (vtl, vtr, vbr, vbl):
                continue
            edges = [(tl, vtl, tr, vtr), (tr, vtr, br, vbr),
                     (br, vbr, bl, vbl), (bl, vbl, tl, vtl)]
            for lv in levels:
                lv = float(lv)
                cross = []
                for (pa, va, pb, vb) in edges:
                    if (va <= lv < vb) or (vb <= lv < va):
                        cross.append(_interp(pa, va, pb, vb, lv))
                # 2 cruces -> un segmento; 4 cruces (silla) -> dos pares por orden
                for k in range(0, len(cross) - 1, 2):
                    out[lv].append([cross[k], cross[k + 1]])
    return out
