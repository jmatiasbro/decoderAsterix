"""Zonas MSA de la FIR Córdoba (SACF) según cartas ENR 1.6 de ANAC.

Centros (ARP/VOR) tomados de la base ATM por ICAO; radiales MAGNÉTICOS y MSA
transcritos de las cartas de Altitud Mínima de Vigilancia ATC-OACI. Radio 25 NM.
La declinación magnética oeste es aproximada por región (~5–6° W) y ajustable.
"""
from player.msaw.model import MsaZone, MsaSector

# Sectores por ICAO: (desde°, hasta°, msa_ft) en sentido horario, radial magnético.
_SECTORS = {
    "SACO": [(19, 199, 4100), (199, 19, 8300)],
    "SANT": [(340, 170, 3500), (170, 340, 11500)],
    "SASA": [(20, 160, 6000), (160, 250, 9500), (250, 20, 16500)],
    "SASJ": [(10, 180, 5000), (180, 10, 14000)],
    "SANL": [(350, 170, 4500), (170, 350, 13000)],
    "SANC": [(40, 210, 5000), (210, 40, 14500)],
    "SANE": [(0, 360, 2500)],                       # omnidireccional
    "SAOC": [(280, 10, 5500), (10, 280, 3000)],
}

# Declinación magnética OESTE aproximada por aeropuerto (grados, ajustable).
_DECL_W = {"SACO": 6.0, "SANT": 5.0, "SASA": 5.0, "SASJ": 5.0,
           "SANL": 5.5, "SANC": 5.5, "SANE": 5.0, "SAOC": 6.0}

# Altitud de transición (ft) por carta.
_TRANS_ALT = {"SACO": 3500, "SANT": 4000, "SASA": 5500, "SASJ": 5000,
              "SANL": 4500, "SANC": 4500, "SANE": 3000, "SAOC": 3000}

RADIUS_NM = 25.0


def msa_zones():
    """[MsaZone] de la FIR Córdoba, anclando el centro a la base ATM (ARP)."""
    from player import atm_db
    ap = atm_db.airports() if atm_db.available() else {}
    zones = []
    for icao, secs in _SECTORS.items():
        info = ap.get(icao)
        if not info:
            continue
        zones.append(MsaZone(
            icao=icao, center=(info["lat"], info["lon"]), radius_nm=RADIUS_NM,
            elev_ft=int(info.get("alt_ft") or 0), trans_alt_ft=_TRANS_ALT.get(icao, 0),
            mag_decl_w=_DECL_W.get(icao, 5.0),
            sectors=[MsaSector(d, h, m) for (d, h, m) in secs],
        ))
    return zones
