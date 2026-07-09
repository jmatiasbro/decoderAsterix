"""Parser ADEXP — EUROCONTROL SPEC-107 Ed. 3.3.

Función pública: parsear_trama(msg: str) -> dict

Claves del dict resultante:
- Campos ADEXP en mayúsculas (TITLE, ARCID, ADEP, ADES, RFL, ROUTE, EOBT,
  EQPT, COP, ARCTYP, WKTRC, etc.)
- Campos lista (-BEGIN X … -END X) guardados en '_LIST_X' como str crudo.
- Campos derivados: 'aircraft_type' y 'wtc' (desde EQPT o ARCTYP/WKTRC).
"""
import re
from typing import Dict

# Bloques -BEGIN KEYWORD ... -END KEYWORD (re.DOTALL para multilinea)
_RE_LIST = re.compile(
    r"-BEGIN\s+([A-Z0-9]+)\s(.*?)-END\s+\1",
    re.DOTALL,
)

# Campos -KEYWORD valor; el valor termina antes del siguiente [ \t\r\n]-KEYWORD
_RE_FIELD = re.compile(
    r"-([A-Z0-9]+)[ \t\r\n]+(.*?)(?=[ \t\r\n]-[A-Z0-9]+[ \t\r\n]|$)",
    re.DOTALL,
)


def parsear_trama(msg: str) -> Dict[str, str]:
    """Parsea una trama ADEXP cruda y devuelve dict con claves en mayúsculas."""
    result: Dict[str, str] = {}

    # 1. Extraer y eliminar bloques lista para que sus keywords internos
    #    no contaminen el parser de campos simples.
    def _guardar_lista(m: re.Match) -> str:
        nombre = m.group(1)
        result[f"_LIST_{nombre}"] = m.group(2).strip()
        return " "

    clean = _RE_LIST.sub(_guardar_lista, msg)

    # 2. Parsear todos los campos -KEYWORD valor
    for m in _RE_FIELD.finditer(clean):
        keyword = m.group(1)
        value = " ".join(m.group(2).split())   # normalizar whitespace interno
        result[keyword] = value

    # 3. Derivar aircraft_type y wtc
    #    Fuente 1: EQPT en formato ICAO "B738/M-SDE1FGHIRWXY"
    eqpt = result.get("EQPT", "")
    if eqpt and "/" in eqpt:
        partes = eqpt.split("/")
        result.setdefault("aircraft_type", partes[0])
        wtc_raw = partes[1].split("-")[0] if len(partes) > 1 else ""
        if wtc_raw:
            result.setdefault("wtc", wtc_raw[0].upper())

    #    Fuente 2: campos explícitos ARCTYP / WKTRC
    if "aircraft_type" not in result and "ARCTYP" in result:
        result["aircraft_type"] = result["ARCTYP"]
    if "wtc" not in result and "WKTRC" in result:
        result["wtc"] = result["WKTRC"]

    return result
