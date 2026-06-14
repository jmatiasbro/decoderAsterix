"""Construye `raw_segments` (formato VideoMapManager) desde la base ATM, para
agregar aerovías, procedimientos y fixes como capas del PPI.

Segmento: ('M'|'L', layer, lat, lon) polilínea; ('S'|'T', layer, lat, lon, text)
símbolo/etiqueta. `layer='AEROVIAS'` enruta al path de aerovías del renderer.
"""
from player import atm_db

AIRWAY_LAYER = "AEROVIAS"
FIX_LAYER = "FIX"


def _polyline(points):
    return [("M" if i == 0 else "L", AIRWAY_LAYER, lat, lon)
            for i, (lat, lon) in enumerate(points)]


def airway_segments(categoria: str):
    segs = []
    for w in atm_db.airways(categoria):
        segs += _polyline(w["points"])
    return segs


def procedure_segments(icao: str, kind: str):
    segs = []
    for p in atm_db.procedures(icao, kind):
        segs += _polyline(p["points"])
    return segs


def fix_segments(kinds=None, symbols=True, names=True):
    segs = []
    for f in atm_db.fixes(kinds):
        if symbols:
            segs.append(("S", FIX_LAYER, f["lat"], f["lon"], f["name"]))
        if names:
            segs.append(("T", FIX_LAYER, f["lat"], f["lon"], f["name"]))
    return segs
