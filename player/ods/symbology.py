"""Simbología de posición ODS. El tamaño es en PÍXELES de pantalla (constante,
no escala con el zoom); el centroide del símbolo es la posición exacta del track.
"""
from dataclasses import dataclass
from .track_state import PSR_ONLY, SSR, COMBINED, ADSB, SYSTEM_TRACK, COASTING

SHAPES = {"plus", "square", "diamond", "filled_square", "track", "x"}


@dataclass(frozen=True)
class SymbolSpec:
    shape: str
    size_px: float
    dashed: bool = False
    pen_px: float = 1.4


_SPECS = {
    PSR_ONLY:     SymbolSpec("plus", 5.0),
    SSR:          SymbolSpec("square", 5.0),
    COMBINED:     SymbolSpec("filled_square", 5.0),
    ADSB:         SymbolSpec("diamond", 5.5),
    SYSTEM_TRACK: SymbolSpec("track", 5.0, pen_px=1.6),
    COASTING:     SymbolSpec("square", 5.0, dashed=True),
}


def symbol_spec(state: str) -> SymbolSpec:
    return _SPECS.get(state, _SPECS[PSR_ONLY])


def draw_symbol(painter, spec: SymbolSpec, x_px: float, y_px: float, qcolor):
    """Dibuja el símbolo en coordenadas de PANTALLA (sin scale activo).

    El llamador debe haber restaurado la transformación a píxeles (identity);
    ver integración en radar_widget (_draw_oaci_track).
    """
    from PyQt6.QtCore import QPointF, Qt
    from PyQt6.QtGui import QPen, QBrush
    s = spec.size_px
    pen = QPen(qcolor)
    pen.setWidthF(spec.pen_px)
    if spec.dashed:
        pen.setStyle(Qt.PenStyle.DashLine)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    c = QPointF(x_px, y_px)
    sh = spec.shape
    if sh == "plus":
        painter.drawLine(QPointF(x_px - s, y_px), QPointF(x_px + s, y_px))
        painter.drawLine(QPointF(x_px, y_px - s), QPointF(x_px, y_px + s))
    elif sh == "x":
        painter.drawLine(QPointF(x_px - s, y_px - s), QPointF(x_px + s, y_px + s))
        painter.drawLine(QPointF(x_px - s, y_px + s), QPointF(x_px + s, y_px - s))
    elif sh in ("square", "filled_square"):
        if sh == "filled_square":
            painter.setBrush(QBrush(qcolor))
        painter.drawRect(int(x_px - s), int(y_px - s), int(2 * s), int(2 * s))
    elif sh == "diamond":
        painter.drawPolygon(QPointF(x_px, y_px - s), QPointF(x_px + s, y_px),
                            QPointF(x_px, y_px + s), QPointF(x_px - s, y_px))
    elif sh == "track":
        painter.drawRect(int(x_px - s), int(y_px - s), int(2 * s), int(2 * s))
        painter.setBrush(QBrush(qcolor))
        painter.drawEllipse(c, 1.2, 1.2)
