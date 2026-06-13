"""Paleta EUROCONTROL ODS para la vista controlador.

Principios (ED-128 / ISO 9241): fondo gris neutro oscuro, datos normales de baja
saturación casi monocromos, color saturado reservado a alertas, intensidad por
capa ajustable por el controlador.
"""
from .track_state import PSR_ONLY, SSR, COMBINED, ADSB, SYSTEM_TRACK, COASTING

# Fondo gris neutro (no azul-negro). RGB.
BG = (18, 18, 18)

# Color por estado de track (RGB), baja saturación.
STATE_RGB = {
    SYSTEM_TRACK: (208, 216, 208),  # blanco-verdoso: track confirmado
    COMBINED:     (200, 208, 200),
    SSR:          (150, 200, 160),  # verde apagado: secundario correlado
    ADSB:         (150, 190, 210),  # cian apagado: ADS-B
    PSR_ONLY:     (140, 150, 140),  # gris-verde tenue: primario no correlado
    COASTING:     (120, 110, 90),   # ámbar muy apagado: sin actualización
}

# Colores reservados de alerta (saturados).
ALERT_STCA = (230, 60, 60)    # rojo
ALERT_MSAW = (235, 170, 40)   # ámbar
SELECTED = (255, 255, 255)    # blanco puro para el track seleccionado

# Intensidad por capa (0..1) por defecto; el controlador la ajusta.
LAYER_DEFAULT = {
    "map": 0.35, "rings": 0.30, "labels": 0.90, "history": 0.55,
    "symbols": 1.0, "compass": 0.45,
}


def _clamp(v, lo, hi):
    return lo if v < lo else hi if v > hi else v


def state_rgb(state: str, selected: bool = False):
    if selected:
        return SELECTED
    return STATE_RGB.get(state, STATE_RGB[PSR_ONLY])


def layer_alpha(layer: str, intensity: float) -> int:
    """Alpha 0..255 a partir de la intensidad 0..1 de la capa."""
    return int(round(_clamp(intensity, 0.0, 1.0) * 255))
