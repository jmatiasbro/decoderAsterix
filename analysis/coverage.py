"""Cálculo de cobertura real de radar por nivel de vuelo (FL).

Lógica extraída de analysis/exporters.py::export_coverage_map_kmz para poder
reusarla en pantalla (polar + mapa) y en exportación, sin acoplarla al KMZ.
Python puro + numpy. Sin pandas.
"""
import math
from dataclasses import dataclass, field

FL_BANDS = (50, 100, 150, 200, 250, 300)


def classify_fl(fl_str):
    """Devuelve la banda FL (50..300) para un flight_level, o None si no aplica."""
    if fl_str is None or fl_str == "---":
        return None
    try:
        fl = float(fl_str)
    except (ValueError, TypeError):
        return None
    if fl > 450.0:        # viene en pies -> normalizar a FL
        fl = fl / 100.0
    if 25 <= fl < 75:
        return 50
    if 75 <= fl < 125:
        return 100
    if 125 <= fl < 175:
        return 150
    if 175 <= fl < 225:
        return 200
    if 225 <= fl < 275:
        return 250
    if fl >= 275:
        return 300
    return None
