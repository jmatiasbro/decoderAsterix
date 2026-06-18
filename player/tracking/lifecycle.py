"""Ciclo de vida de pista monoradar (confirmación M-de-N + coasting por vueltas).

Determinista por ToD ASTERIX: nada de time.time(). Headless (sin Qt).
"""
import math

NM_M = 1852.0

TENTATIVE = "TENTATIVE"
CONFIRMED = "CONFIRMED"
COASTING = "COASTING"
DELETED = "DELETED"


def _squawk(plot):
    m = getattr(plot, "mode3a", None)
    s = f"{m:04o}" if isinstance(m, int) else str(m or "").strip()
    if s and s not in ("----", "0000"):
        return s
    return None


def identidad_codigo(plot):
    """Clave de identidad del plot, o None.

    SSR/PSR-SSR → squawk (Modo 3/A). ADS-B (cat 21) sin squawk → callsign;
    si falta → dirección Mode S.
    """
    sq = _squawk(plot)
    if sq:
        return sq
    if getattr(plot, "category", None) == 21:
        cs = (getattr(plot, "callsign", None) or "").strip().upper()
        if cs:
            return cs
        ms = (getattr(plot, "mode_s", None) or "").strip().upper()
        if ms and ms != "----":
            return ms
    return None
