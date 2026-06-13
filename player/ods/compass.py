"""Geometría de la rosa de rumbos y marcas de alcance (ODS). Pura."""
from dataclasses import dataclass


@dataclass(frozen=True)
class BearingTick:
    deg: int
    major: bool
    label: str


def bearing_ticks(major_every: int = 30, minor_every: int = 10):
    ticks = []
    for d in range(0, 360, minor_every):
        major = (d % major_every == 0)
        label = ""
        if major:
            label = "360" if d == 0 else f"{d:03d}"
        ticks.append(BearingTick(d, major, label))
    return ticks


def range_marks(radius_px: float, range_nm: float, step_nm: float):
    """Devuelve [(nm, radio_px), ...] para cada anillo hasta range_nm."""
    out = []
    nm = step_nm
    while nm <= range_nm + 1e-6:
        out.append((nm, radius_px * (nm / range_nm)))
        nm += step_nm
    return out
