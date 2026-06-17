"""
analysis/rdqc_thresholds.py — umbrales de calidad ICAO Doc 8071 Vol III (Tablas 3-1/3-2).

Carga config/rdqc_thresholds.json y clasifica cada métrica en una severidad
('ok'/'warn'/'bad') según el perfil activo (monopulso o ventana deslizante).
La capa de presentación mapea la severidad a colores.
"""
import os
import json

_DEFAULT_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "config", "rdqc_thresholds.json")


def load_profile(path: str = None):
    """Devuelve (label_perfil, {key: spec}) del perfil activo. Tolerante a fallos."""
    path = path or _DEFAULT_PATH
    try:
        with open(path, encoding="utf-8") as f:
            cfg = json.load(f)
        prof = cfg["profiles"][cfg["active_profile"]]
        return prof.get("label", cfg["active_profile"]), prof.get("metrics", {})
    except (OSError, KeyError, ValueError):
        return "", {}


def severity(spec: dict, value) -> str:
    """'ok' | 'warn' | 'bad' | None. None si no hay spec o valor."""
    if spec is None or value is None:
        return None
    direction = spec.get("dir")
    green = spec.get("green")
    orange = spec.get("orange")
    if green is None:
        return None
    x = abs(value) if direction == "abs_lower" else value
    if direction == "higher":
        if x >= green:
            return "ok"
        if orange is not None and x >= orange:
            return "warn"
        return "bad"
    # lower / abs_lower
    if x <= green:
        return "ok"
    if orange is not None and x <= orange:
        return "warn"
    return "bad"
