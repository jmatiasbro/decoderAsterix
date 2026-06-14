"""Capa de cartografía para la vista FIR: polilíneas (aerovías, límites) y
puntos/fixes sobre el mapa satelital. Recibe el dict de feed.build_maps():
  {"lines": [{"pts":[(lat,lon),...], "color":(r,g,b)}, ...],
   "points": [{"lat","lon","text","symbol":bool,"color":(r,g,b)}, ...]}
"""
from PyQt6.QtCore import Qt, QPointF
from PyQt6.QtGui import QColor, QPen, QFont, QBrush, QPolygonF


def draw_maps(painter, view, maps, margin: float = 120.0):
    if not maps:
        return
    w, h = view.width(), view.height()
    # Intensidad Visual (0..1): atenúa toda la cartografía sobre el satelital.
    mi = max(0.0, min(1.0, getattr(view, "_map_intensity", 1.0)))
    if mi <= 0.0:
        return
    a_line = int(200 * mi)
    a_sym = int(170 * mi)         # fixes menos invasivos
    a_txt = int(180 * mi)
    # Polilíneas (las áreas se rellenan tenue)
    for ln in maps.get("lines", []):
        pts = ln.get("pts") or []
        if len(pts) < 2:
            continue
        r, g, b = ln["color"]
        scr = [view._lonlat_to_screen(la, lo) for (la, lo) in pts]
        painter.setPen(QPen(QColor(r, g, b, a_line), 1.4))
        if ln.get("fill"):
            painter.setBrush(QBrush(QColor(r, g, b, int(45 * mi))))
            painter.drawPolygon(QPolygonF(scr))
            painter.setBrush(Qt.BrushStyle.NoBrush)
        else:
            for i in range(1, len(scr)):
                painter.drawLine(scr[i - 1], scr[i])
    # Puntos / fixes
    font = QFont("Consolas", 7)
    painter.setFont(font)
    for pt in maps.get("points", []):
        sp = view._lonlat_to_screen(pt["lat"], pt["lon"])
        if not (-margin <= sp.x() <= w + margin and -margin <= sp.y() <= h + margin):
            continue
        r, g, b = pt["color"]
        if pt.get("symbol"):
            painter.setPen(QPen(QColor(r, g, b, a_sym), 1.0))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(sp, 2.2, 2.2)
        else:
            painter.setPen(QColor(0, 0, 0, int(a_txt * 0.85)))
            painter.drawText(QPointF(sp.x() + 5, sp.y() - 2), str(pt["text"]))
            painter.setPen(QColor(r, g, b, a_txt))
            painter.drawText(QPointF(sp.x() + 4, sp.y() - 3), str(pt["text"]))
