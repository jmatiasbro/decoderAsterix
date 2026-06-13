"""Clasificación de un plot/track en su estado de presentación ODS.

El símbolo se elige por origen/calidad de la información, no por categoría ASTERIX.
`is_coasting` lo decide el llamador (depende del tiempo de simulación vs. scan rate).
"""

PSR_ONLY = "PSR_ONLY"          # primario no correlado
SSR = "SSR"                    # secundario / Mode-S correlado
COMBINED = "COMBINED"          # PSR + SSR
ADSB = "ADSB"                  # ADS-B (CAT021)
SYSTEM_TRACK = "SYSTEM_TRACK"  # track de sistema (CAT062 / tracker)
COASTING = "COASTING"          # track sin actualización reciente


def _det_type(plot):
    """TYP de I048/020 si está disponible (0..7); None si no."""
    rd = getattr(plot, "raw_dict", None) or {}
    t = rd.get("det_type")
    if t is None and isinstance(rd.get("extra_data"), dict):
        t = rd["extra_data"].get("det_type")
    return t


def _tiene_squawk(plot):
    m = getattr(plot, "mode3a", None)
    if m is None:
        return False
    s = f"{m:04o}" if isinstance(m, int) else str(m).strip()
    return s not in ("", "----", "0000")


def classify(plot, is_coasting: bool) -> str:
    if is_coasting:
        return COASTING
    cat = getattr(plot, "category", None)
    if cat == 62:
        return SYSTEM_TRACK
    if cat == 21:
        return ADSB
    # CAT048 / CAT001: distinguir por detección
    typ = _det_type(plot)
    if typ in (3, 6, 7):  # combinaciones PSR+SSR en I048/020
        return COMBINED
    if typ == 1:          # PSR only
        return PSR_ONLY
    # Sin det_type fiable: inferir por presencia de código/dirección
    if _tiene_squawk(plot) or getattr(plot, "mode_s", None):
        return SSR
    return PSR_ONLY
