"""
Decodificador ASTERIX CAT062 (System Track).

Wrapper que delega la decodificación a native_asterix.decode_cat062
para mantener la interfaz uniforme: decode(payload, offset, block_length, category).
"""

from typing import List, Dict, Any
from decoder.native_asterix import decode_cat062 as _decode_cat062


def decode(payload: bytes, offset: int, block_length: int, category: int,
           record_offsets=None) -> List[Dict[str, Any]]:
    """
    Decodifica un bloque de datos ASTERIX CAT062 (SDPS Track).

    Args:
        payload: El payload completo del bloque ASTERIX (incluye CAT + LEN).
        offset: Offset donde comienzan los datos después de CAT/LEN (típicamente 3).
        block_length: Longitud total del bloque ASTERIX.
        category: La categoría ASTERIX (62).

    Returns:
        Lista de diccionarios con los registros decodificados.
    """
    return _decode_cat062(payload, offset, block_length, category,
                          record_offsets=record_offsets)