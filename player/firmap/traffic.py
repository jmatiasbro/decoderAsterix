"""Capa de tráfico para la vista FIR: iconos de avión + datablocks sobre el mapa.

Desacoplado del pipeline: cada track es un dict
  {lat, lon, heading, lines:[str,...], color:(r,g,b), selected:bool}
Quien lo llama (demo o la app en F4) arma `lines` (callsign / nivel / etc.) y el
color por estado. Acá solo se dibuja.
"""
from PyQt6.QtCore import Qt, QPointF
from PyQt6.QtGui import QPainter, QColor, QPen, QBrush, QFont, QPainterPath


def plane_path() -> QPainterPath:
    """Silueta cenital de avión apuntando al NORTE (proa = -y). Escala ~±9 px."""
    p = QPainterPath()
    p.moveTo(0, -9)
    p.lineTo(1.6, -3); p.lineTo(9, 1.5); p.lineTo(9, 3); p.lineTo(1.6, 1)
    p.lineTo(1.4, 6); p.lineTo(4, 8.5); p.lineTo(4, 9.5); p.lineTo(0, 7.8)
    p.lineTo(-4, 9.5); p.lineTo(-4, 8.5); p.lineTo(-1.4, 6); p.lineTo(-1.6, 1)
    p.lineTo(-9, 3); p.lineTo(-9, 1.5); p.lineTo(-1.6, -3)
    p.closeSubpath()
    return p


_PLANE = None
_DEFAULT_COLOR = (120, 200, 255)


def draw_traffic(painter: QPainter, view, tracks, margin: float = 40.0):
    """Dibuja `tracks` sobre `view` (que expone _lonlat_to_screen y width/height)."""
    global _PLANE
    if _PLANE is None:
        _PLANE = plane_path()
    w, h = view.width(), view.height()
    font = QFont("Consolas", 8)
    painter.setFont(font)
    fm = painter.fontMetrics()
    for tr in tracks:
        sp = view._lonlat_to_screen(tr["lat"], tr["lon"])
        if not (-margin <= sp.x() <= w + margin and -margin <= sp.y() <= h + margin):
            continue
        rgb = tr.get("color") or _DEFAULT_COLOR
        col = QColor(rgb[0], rgb[1], rgb[2])
        # Estela (puntos históricos, color tenue)
        trail = tr.get("trail") or []
        if len(trail) >= 2:
            painter.save()
            tcol = QColor(rgb[0], rgb[1], rgb[2], 110)
            painter.setPen(QPen(tcol, 1.0))
            prev = None
            for (la, lo) in trail:
                q = view._lonlat_to_screen(la, lo)
                if prev is not None:
                    painter.drawLine(prev, q)
                prev = q
            painter.restore()
        # Halo STCA (rojo de alerta)
        if tr.get("alert"):
            painter.save()
            painter.setPen(QPen(QColor(230, 60, 60), 1.6))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(sp, 13.0, 13.0)
            painter.restore()
        # Icono rotado por proa
        painter.save()
        painter.translate(sp)
        painter.rotate(float(tr.get("heading") or 0.0))
        painter.setPen(QPen(QColor(8, 14, 20), 0.8))
        painter.setBrush(QBrush(col))
        painter.drawPath(_PLANE)
        painter.restore()
        # Recuadro de selección
        if tr.get("selected"):
            painter.save()
            painter.setPen(QPen(QColor(255, 255, 255), 1.0))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(int(sp.x() - 12), int(sp.y() - 12), 24, 24)
            painter.restore()
        # Datablock con leader y sombra (legibilidad sobre satelital)
        lines = tr.get("lines") or []
        if not lines:
            continue
        lx, ly = sp.x() + 12, sp.y() - 10
        painter.setPen(QPen(QColor(20, 28, 36, 170)))
        painter.drawLine(sp, QPointF(lx, ly))
        for i, ln in enumerate(lines):
            ty = ly + i * (fm.height() - 2)
            painter.setPen(QColor(0, 0, 0, 200))
            painter.drawText(QPointF(lx + 1, ty + 1), str(ln))
            painter.setPen(QColor(225, 240, 255))
            painter.drawText(QPointF(lx, ty), str(ln))
