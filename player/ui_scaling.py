"""Dimensionamiento responsivo según la resolución del monitor activo.

Los tamaños fijos del proyecto se diseñaron pensando en 1920x1080. `escalar_ventana`
los toma como base y los reescala proporcionalmente a la pantalla donde aparece la
ventana: crece en monitores grandes (4K) y se achica para entrar en los chicos
(p. ej. 1366x768), siempre clampeado al área disponible.
"""
from PyQt6.QtGui import QGuiApplication

# Resolución base de diseño.
BASE_W, BASE_H = 1920, 1080


def escalar_ventana(widget, base_w, base_h, centrar=True, max_frac=0.96):
    """Redimensiona `widget` proporcional a la pantalla donde está.

    base_w/base_h: tamaño de diseño a 1920x1080. El factor es el mínimo entre el
    ratio de ancho y alto disponibles (mantiene proporción y evita desbordar).
    """
    scr = widget.screen() or QGuiApplication.primaryScreen()
    if scr is None:
        widget.resize(int(base_w), int(base_h))
        return
    geo = scr.availableGeometry()
    factor = min(geo.width() / BASE_W, geo.height() / BASE_H)
    w = min(int(base_w * factor), int(geo.width() * max_frac))
    h = min(int(base_h * factor), int(geo.height() * max_frac))
    widget.resize(w, h)
    if centrar:
        widget.move(geo.x() + (geo.width() - w) // 2,
                    geo.y() + (geo.height() - h) // 2)
