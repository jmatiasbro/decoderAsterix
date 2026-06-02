import math
import struct
from typing import List, Tuple, Dict, Any

# REGLA ESTRICTA DE LECTURA FX:
def leer_longitud_fspec(payload: bytes, offset: int) -> Tuple[int, List[int]]:
    """
    Lee un FSPEC o Sub-FSPEC evaluando el bit FX (LSB).
    Retorna la cantidad de bytes que ocupó el FSPEC y la lista de bits activos (1-based FRN).
    
    REGLA ESTRICTA:
      - Cada byte aporta 7 bits de campo (bits 7..1) + 1 bit FX (bit 0)
      - Si FX=1 → hay más bytes de extensión
      - Si FX=0 → último byte del FSPEC
      - Los bits activos se reportan como números de FRN (1-based):
        FRN 1 = bit 7 del byte 0, FRN 2 = bit 6 del byte 0, ..., FRN 7 = bit 1 del byte 0,
        FRN 8 = bit 7 del byte 1, ..., etc.
    """
    bytes_leidos = 0
    bits_activos = []
    
    while offset + bytes_leidos < len(payload):
        byte_actual = payload[offset + bytes_leidos]
        bytes_leidos += 1
        
        # Analizar los primeros 7 bits (bits 7..1)
        for i in range(7):
            if (byte_actual & (1 << (7 - i))) != 0:
                # FRN = (bytes_leidos - 1) * 7 + i + 1
                bits_activos.append((bytes_leidos - 1) * 7 + i + 1)
                
        # Evaluar el bit FX (Bit 0)
        if (byte_actual & 1) == 0:
            break  # No hay más bytes de extensión
            
    return bytes_leidos, bits_activos


def read_fspec(payload: bytes, offset: int) -> Tuple[List[bool], int]:
    """
    Lee un FSPEC y retorna lista plana de booleanos + offset actualizado.
    Wrapper sobre leer_longitud_fspec para compatibilidad.
    """
    bytes_leidos, bits_activos = leer_longitud_fspec(payload, offset)
    
    # Convertir bits_activos (1-based FRN) a lista plana de booleanos
    max_frn = max(bits_activos) if bits_activos else 0
    fspec_len = max(bytes_leidos * 7, max_frn)
    fspec = [False] * fspec_len
    for bit in bits_activos:
        if bit <= fspec_len:
            fspec[bit - 1] = True
    
    return fspec, offset + bytes_leidos

def _decode_callsign(data: bytes) -> str:
    # Corrección de alfabeto ICAO 6-bit: agregamos espacio en índice 32 y alineamos dígitos 0-9 para que comiencen exactamente en el índice 48
    chars = "?ABCDEFGHIJKLMNOPQRSTUVWXYZ????  ???????????????0123456789??????"
    val = struct.unpack('>Q', b'\x00\x00' + data)[0]
    callsign = ""
    for i in range(8):
        char_idx = (val >> (42 - i * 6)) & 0x3F
        callsign += chars[char_idx] if char_idx < len(chars) else "?"
    return callsign.strip()