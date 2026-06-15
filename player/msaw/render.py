"""Render de los sectores MSA como capa de referencia (anillo + radiales +
etiqueta de MSA por sector), en formato raw_segments del map_manager.

Sólo visualización: usa las mismas MsaZone que el motor. Los radiales son
magnéticos; se convierten a verdadero (true = magnético − declinación_W) para
que coincidan con el dibujo sobre norte verdadero.
"""
import math

MSA_LAYER = "MSA"
MSA_COLOR = "#7FA8B0"        # gris-cian tenue (referencia, no compite con tracks)


def _dest(lat, lon, brg_true, nm):
    """Punto a `nm` y rumbo verdadero `brg_true` (aprox. equirectangular)."""
    b = math.radians(brg_true)
    dlat = (nm / 60.0) * math.cos(b)
    dlon = (nm / (60.0 * max(0.01, math.cos(math.radians(lat))))) * math.sin(b)
    return (lat + dlat, lon + dlon)


def _ring(center, radius, n=72):
    return [_dest(center[0], center[1], 360.0 * i / n, radius) for i in range(n + 1)]


def zone_segments(zone):
    """raw_segments de una MsaZone: anillo + radiales de corte + etiquetas."""
    if not zone.center or not zone.sectors:
        return []
    segs = []
    c, R = zone.center, zone.radius_nm
    ring = _ring(c, R)
    segs.append(("M", MSA_LAYER, ring[0][0], ring[0][1]))
    for la, lo in ring[1:]:
        segs.append(("L", MSA_LAYER, la, lo))

    omni = len(zone.sectors) == 1
    for s in zone.sectors:
        if not omni:
            bt = (s.desde - zone.mag_decl_w) % 360.0           # radial de corte
            e = _dest(c[0], c[1], bt, R)
            segs.append(("M", MSA_LAYER, c[0], c[1]))
            segs.append(("L", MSA_LAYER, e[0], e[1]))
            span = (s.hasta - s.desde) % 360.0
            mid = (s.desde + span / 2.0) % 360.0
            lbl = _dest(c[0], c[1], (mid - zone.mag_decl_w) % 360.0, R * 0.6)
        else:
            lbl = c
        segs.append(("T", MSA_LAYER, lbl[0], lbl[1], f"MSA {s.msa_ft}"))
    return segs


def msa_segments():
    """raw_segments de todas las TMA (FIR Córdoba)."""
    from player.msaw.data import msa_zones
    segs = []
    for z in msa_zones():
        segs += zone_segments(z)
    return segs
