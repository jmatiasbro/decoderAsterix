"""
bds.py — Decodificación de registros Mode S Comm-B (BDS) presentes en el
Mode S MB Data (I048/250 / I062/380-MB). Soporta los registros más comunes:
BDS 4,0 (Selected vertical intention), 5,0 (Track and turn), 6,0 (Heading and speed).

El bloque MB en I048/250 es: REP (1 octeto) + REP × (7 octetos de registro + 1 octeto
con BDS1/BDS2). Los bits se numeran 1..56 desde el MSB del registro.
"""
from typing import Dict, List, Tuple


def _bit(mb: bytes, i: int) -> int:
    """Bit i (1-indexado, MSB primero) del registro de 7 octetos."""
    return (mb[(i - 1) // 8] >> (7 - ((i - 1) % 8))) & 1


def _bits(mb: bytes, start: int, length: int) -> int:
    v = 0
    for i in range(start, start + length):
        v = (v << 1) | _bit(mb, i)
    return v


def _signed(v: int, length: int) -> int:
    if v & (1 << (length - 1)):
        v -= (1 << length)
    return v


def decode_bds40(mb: bytes) -> Dict[str, str]:
    """BDS 4,0 — Selected vertical intention."""
    out: Dict[str, str] = {}
    if _bit(mb, 1):
        out["MCP/FCU Selected Alt (ft)"] = f"{_bits(mb, 2, 12) * 16}"
    if _bit(mb, 14):
        out["FMS Selected Alt (ft)"] = f"{_bits(mb, 15, 12) * 16}"
    if _bit(mb, 27):
        out["Barometric Setting (mb)"] = f"{_bits(mb, 28, 12) * 0.1 + 800.0:.1f}"
    return out


def decode_bds50(mb: bytes) -> Dict[str, str]:
    """BDS 5,0 — Track and turn report."""
    out: Dict[str, str] = {}
    if _bit(mb, 1):
        out["Roll Angle (deg)"] = f"{_signed(_bits(mb, 2, 10), 10) * (45.0 / 256.0):.2f}"
    if _bit(mb, 12):
        out["True Track Angle (deg)"] = f"{_signed(_bits(mb, 13, 11), 11) * (90.0 / 512.0):.2f}"
    if _bit(mb, 24):
        out["Ground Speed (kt)"] = f"{_bits(mb, 25, 10) * 2}"
    if _bit(mb, 35):
        out["Track Angle Rate (deg/s)"] = f"{_signed(_bits(mb, 36, 10), 10) * (8.0 / 256.0):.2f}"
    if _bit(mb, 46):
        out["True Airspeed (kt)"] = f"{_bits(mb, 47, 10) * 2}"
    return out


def decode_bds60(mb: bytes) -> Dict[str, str]:
    """BDS 6,0 — Heading and speed report."""
    out: Dict[str, str] = {}
    if _bit(mb, 1):
        hdg = _signed(_bits(mb, 2, 11), 11) * (90.0 / 512.0)
        if hdg < 0:
            hdg += 360.0
        out["Magnetic Heading (deg)"] = f"{hdg:.2f}"
    if _bit(mb, 13):
        out["Indicated Airspeed (kt)"] = f"{_bits(mb, 14, 10)}"
    if _bit(mb, 24):
        out["Mach"] = f"{_bits(mb, 25, 10) * 0.004:.3f}"
    if _bit(mb, 35):
        out["Baro Alt Rate (ft/min)"] = f"{_signed(_bits(mb, 36, 10), 10) * 32}"
    if _bit(mb, 46):
        out["Inertial Vert Vel (ft/min)"] = f"{_signed(_bits(mb, 47, 10), 10) * 32}"
    return out


_REGISTROS = {
    (4, 0): ("Selected vertical intention", decode_bds40),
    (5, 0): ("Track and turn report", decode_bds50),
    (6, 0): ("Heading and speed report", decode_bds60),
}


def parse_mb(data: bytes) -> List[Tuple[str, str, Dict[str, str], str]]:
    """Parsea el bloque I048/250 (REP + reportes). Devuelve por reporte:
    (código 'BDS1,BDS2', nombre, {campo: valor}, hex_crudo_del_registro)."""
    out: List[Tuple[str, str, Dict[str, str], str]] = []
    if not data:
        return out
    rep = data[0]
    off = 1
    for _ in range(rep):
        if off + 8 > len(data):
            break
        mb = data[off:off + 7]
        bcode = data[off + 7]
        off += 8
        b1, b2 = bcode >> 4, bcode & 0x0F
        nombre, fn = _REGISTROS.get((b1, b2), ("(registro no decodificado)", None))
        fields = fn(mb) if fn else {}
        out.append((f"{b1},{b2}", nombre, fields, mb.hex().upper()))
    return out
