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
        segs.append(("T", MSA_LAYER, lbl[0], lbl[1], f"{s.msa_ft}'"))
    return segs


def msa_segments():
    """raw_segments de todas las TMA (FIR Córdoba)."""
    from player.msaw.data import msa_zones
    segs = []
    for z in msa_zones():
        segs += zone_segments(z)
    return segs


# ── Fase 2: zonas MSA poligonales + corredores de aproximación ──────────────

MSA_POLY_LAYER = "MSA_POLY"
APM_LAYER = "APM_CORR"
PROFILE_LAYER = "PROF_CORR"

MSA_POLY_COLOR = "#B0907F"   # terracota tenue (distinto de los sectores)
APM_COLOR = "#7FB08A"        # verde tenue (aproximación)
PROFILE_COLOR = "#9A8AB0"    # violeta tenue (perfiles por waypoint)


def _centroid(coords):
    n = len(coords)
    return (sum(c[0] for c in coords) / n, sum(c[1] for c in coords) / n)


def polygon_segments(zones):
    """raw_segments de zonas MSA poligonales (polígono cerrado + etiqueta MSA).

    `zones`: [{identifier, msa_ft, coords:[(lat,lon)...]}] (atm_db.minimums_zones()).
    """
    segs = []
    for z in zones:
        coords = z.get("coords") or []
        if len(coords) < 3:
            continue
        segs.append(("M", MSA_POLY_LAYER, coords[0][0], coords[0][1]))
        for la, lo in coords[1:]:
            segs.append(("L", MSA_POLY_LAYER, la, lo))
        segs.append(("L", MSA_POLY_LAYER, coords[0][0], coords[0][1]))   # cierre
        clat, clon = _centroid(coords)
        segs.append(("T", MSA_POLY_LAYER, clat, clon,
                     f"{int(z.get('msa_ft', 0))}'"))
    return segs


def apm_corridor_segments(corridors):
    """raw_segments de corredores APM (trapecio near→far + etiqueta de pista).

    `corridors`: salida de atm_db.apm_corridors().
    """
    from player.msaw.model import bearing_true
    segs = []
    for c in corridors:
        near, far = c.get("near"), c.get("far")
        if not near or not far:
            continue
        hw = float(c.get("half_wide_nm", 1.0))
        brg = bearing_true(near[0], near[1], far[0], far[1])
        # esquinas a ±90° del eje en cada extremo
        nl = _dest(near[0], near[1], (brg - 90) % 360, hw)
        nr = _dest(near[0], near[1], (brg + 90) % 360, hw)
        fl = _dest(far[0], far[1], (brg - 90) % 360, hw)
        fr = _dest(far[0], far[1], (brg + 90) % 360, hw)
        segs.append(("M", APM_LAYER, nl[0], nl[1]))
        for la, lo in (nr, fr, fl, nl):                  # trapecio cerrado
            segs.append(("L", APM_LAYER, la, lo))
        segs.append(("T", APM_LAYER, far[0], far[1],
                     f"{c.get('airport','')}/{c.get('runway','')}"))
    return segs


def profile_corridor_segments(profiles):
    """raw_segments de corredores por waypoints (polilínea + altitud por punto).

    `profiles`: salida de atm_db.profile_corridors().
    """
    segs = []
    for p in profiles:
        pts = p.get("points") or []
        if len(pts) < 2:
            continue
        segs.append(("M", PROFILE_LAYER, pts[0][0], pts[0][1]))
        for la, lo, *_ in pts[1:]:
            segs.append(("L", PROFILE_LAYER, la, lo))
        for la, lo, min_ft, *_ in pts:
            segs.append(("T", PROFILE_LAYER, la, lo, f"{int(min_ft)}"))
    return segs


def msa_polygon_segments():
    """raw_segments de todas las zonas MSA poligonales desde la DB."""
    from player import atm_db
    return polygon_segments(atm_db.minimums_zones())


def approach_corridor_segments():
    """raw_segments de corredores APM + perfiles por waypoint desde la DB."""
    from player import atm_db
    return (apm_corridor_segments(atm_db.apm_corridors())
            + profile_corridor_segments(atm_db.profile_corridors()))
