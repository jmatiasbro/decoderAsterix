"""Relajación de colisiones de etiquetas (anti-solape) por repulsión de fuerzas.
Extraído de radar_widget para poder testearlo sin Qt.
"""
import math


def resolve_shifts(centers: dict, min_dist: float = 50.0, passes: int = 2) -> dict:
    """centers: {id: (cx, cy, ancho)} en píxeles. Devuelve {id: [dx, dy]}."""
    shifts = {tid: [0.0, 0.0] for tid in centers}
    ids = list(centers.keys())
    for _ in range(passes):
        for i in range(len(ids)):
            t1 = ids[i]
            c1x, c1y, _w1 = centers[t1]
            for j in range(i + 1, len(ids)):
                t2 = ids[j]
                c2x, c2y, _w2 = centers[t2]
                dx = (c1x + shifts[t1][0]) - (c2x + shifts[t2][0])
                dy = (c1y + shifts[t1][1]) - (c2y + shifts[t2][1])
                dist = math.sqrt(dx * dx + dy * dy)
                if dist < min_dist:
                    if dist < 1.0:
                        dist = 1.0
                    angle = math.atan2(dy, dx)
                    force = (min_dist - dist) * 0.5
                    rx, ry = force * math.cos(angle), force * math.sin(angle)
                    shifts[t1][0] += rx
                    shifts[t1][1] += ry
                    shifts[t2][0] -= rx
                    shifts[t2][1] -= ry
    return shifts
