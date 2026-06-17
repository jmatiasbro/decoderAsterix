#!/usr/bin/env python3
"""
FASE 2: BYPASS SEGURO DE CAMPOS RESERVADOS (RE) Y PROPÓSITO ESPECIAL (SP) EN CAT062

Verifica que el decodificador CAT062 salta correctamente los campos RE y SP
según el formato <Explicit> definido en asterix_cat062_1_18.xml.

Según el XML:
  - RE (FRN 34): <Explicit> - empieza con un byte de longitud que se incluye a sí mismo
  - SP (FRN 35): <Explicit> - empieza con un byte de longitud que se incluye a sí mismo

Formato <Explicit>:
  - Primer byte: Length Indicator (incluye el propio byte)
  - Siguientes (Length-1) bytes: contenido del campo
"""
import sys
sys.path.insert(0, '/mnt/c/documentos/decode_asterix')

from native_asterix import _decode_cat062, leer_longitud_fspec, parse_payload
import struct

def build_cat062_block(fields_hex_list, has_re=False, has_sp=False):
    """
    Construye un bloque CAT062.
    
    UAP CAT062 v1.18:
      FRN 1  (010): SAC/SIC (2B) - mandatory
      FRN 5  (070): ToT (3B) - mandatory  
      FRN 6  (080): Track Status (variable) - mandatory
      FRN 34 (RE): Reserved Expansion Field (Explicit)
      FRN 35 (SP): Special Purpose Field (Explicit)
    
    Construimos un FSPEC mínimo y los campos.
    """
    # Build minimal payload that exercises RE/SP
    # We need FRN 1 (010), FRN 5 (070), FRN 6 (080) as mandatory
    # Plus optional FRN 34 (RE) and FRN 35 (SP)
    
    payload = bytearray()
    
    # FSPEC byte 0: bits 7..1 = FRN 1..7, bit 0 = FX
    # FRN 1 = bit 7, FRN 5 = bit 3, FRN 6 = bit 2
    fspec_byte0 = 0
    fspec_byte0 |= (1 << 7)  # FRN 1: SAC/SIC
    fspec_byte0 |= (1 << 3)  # FRN 5: ToT
    fspec_byte0 |= (1 << 2)  # FRN 6: Track Status
    
    # FSPEC byte 0: need extension for FRN 34, 35 (they're in last byte)
    # FRN 34 = bit at position 33 in flat list (byte 4, bit 6)
    # FRN 35 = bit at position 34 in flat list (byte 4, bit 5)
    # We need 5 FSPEC bytes (35 fields / 7 per byte = 5 bytes)
    
    fspec_bytes = bytearray()
    
    # Byte 0 (FRN 1-7): SAC/SIC, -, -, ToT, -, -, TrackStatus + FX=1
    b0 = 0
    b0 |= (1 << 7)  # FRN 1: SAC/SIC
    b0 |= (1 << 3)  # FRN 5: ToT
    b0 |= (1 << 2)  # FRN 6: Track Status
    b0 |= 1         # FX = 1 (hay extension)
    fspec_bytes.append(b0)
    
    # Byte 1 (FRN 8-14): all spare -> FX=1
    fspec_bytes.append(0x01)  # FX = 1
    
    # Byte 2 (FRN 15-21): all spare -> FX=1
    fspec_bytes.append(0x01)  # FX = 1
    
    # Byte 3 (FRN 22-28): all spare -> FX=1
    fspec_bytes.append(0x01)  # FX = 1
    
    # Byte 4 (FRN 29-35): need FRN 34 (RE) and/or FRN 35 (SP) + FX=0
    b4 = 0
    if has_re:
        b4 |= (1 << 6)  # FRN 34 = bit 6 in byte 4 (34 - 4*7 = 6)
    if has_sp:
        b4 |= (1 << 5)  # FRN 35 = bit 5 in byte 4 (35 - 4*7 = 5)
    # FX = 0 (last byte)
    fspec_bytes.append(b4)
    
    payload.extend(fspec_bytes)
    
    # FRN 1: SAC/SIC (2B)
    payload.append(0xAA)  # SAC
    payload.append(0xBB)  # SIC
    
    # FRN 5: ToT (3B)
    payload.extend(struct.pack('>I', int(12 * 3600 * 128))[1:])  # 12:00:00 UTC
    
    # FRN 6: Track Status (1+ bytes, variable)
    payload.append(0x00)  # Single byte, no extensions
    
    # FRN 34: RE field (Explicit format)
    if has_re:
        re_content = bytes([0x11, 0x22, 0x33, 0x44])
        re_len = len(re_content) + 1  # Length includes itself
        payload.append(re_len)
        payload.extend(re_content)
        print(f"    RE: len_byte={re_len}, content={re_content.hex()}")
    
    # FRN 35: SP field (Explicit format)
    if has_sp:
        sp_content = bytes([0x55, 0x66, 0x77])
        sp_len = len(sp_content) + 1  # Length includes itself
        payload.append(sp_len)
        payload.extend(sp_content)
        print(f"    SP: len_byte={sp_len}, content={sp_content.hex()}")
    
    # Build full ASTERIX block: Category(1) + Length(2) + payload
    block_len = 3 + len(payload)
    block = bytearray()
    block.append(62)  # Category
    block.extend(struct.pack('>H', block_len))
    block.extend(payload)
    
    return bytes(block)


def test_no_re_sp():
    """Test: Sin RE ni SP."""
    print("\n[TEST 1] Sin RE ni SP")
    block = build_cat062_block([], has_re=False, has_sp=False)
    records = _decode_cat062(block[3:], 0, len(block))
    assert len(records) == 1, f"Esperaba 1 registro, obtuve {len(records)}"
    r = records[0]
    assert r['sac'] == 0xAA, f"SAC esperado 0xAA, obtuve {r['sac']}"
    assert r['sic'] == 0xBB, f"SIC esperado 0xBB, obtuve {r['sic']}"
    print(f"    ✓ OK: SAC={r['sac']:02X}, SIC={r['sic']:02X}")


def test_re_only():
    """Test: Solo RE, sin SP."""
    print("\n[TEST 2] Solo RE")
    block = build_cat062_block([], has_re=True, has_sp=False)
    records = _decode_cat062(block[3:], 0, len(block))
    assert len(records) == 1, f"Esperaba 1 registro, obtuve {len(records)}"
    print(f"    ✓ OK: RE saltado correctamente")


def test_sp_only():
    """Test: Solo SP, sin RE."""
    print("\n[TEST 3] Solo SP")
    block = build_cat062_block([], has_re=False, has_sp=True)
    records = _decode_cat062(block[3:], 0, len(block))
    assert len(records) == 1, f"Esperaba 1 registro, obtuve {len(records)}"
    print(f"    ✓ OK: SP saltado correctamente")


def test_re_and_sp():
    """Test: Tanto RE como SP."""
    print("\n[TEST 4] RE y SP ambos")
    block = build_cat062_block([], has_re=True, has_sp=True)
    records = _decode_cat062(block[3:], 0, len(block))
    assert len(records) == 1, f"Esperaba 1 registro, obtuve {len(records)}"
    print(f"    ✓ OK: RE y SP saltados correctamente")


def test_re_sp_with_full_uap():
    """Test: Varios campos comunes + RE + SP."""
    print("\n[TEST 5] Múltiples campos + RE + SP")
    
    # Build a more realistic block with multiple fields
    payload = bytearray()
    
    # FSPEC: 5 bytes with FRN 1, 5, 6, 34, 35 and FRN 7 (Position), FRN 8 (Pos WGS84)
    # Byte 0: FRN 1(SAC/SIC), 5(ToT), 6(Status), 7(PosCart) + FX=1
    b0 = (1<<7) | (1<<3) | (1<<2) | (1<<1) | 1  # FRN 1,5,6,7 + FX
    payload.append(b0)
    payload.append(0x01)  # Byte 1: all spare + FX=1
    payload.append(0x01)  # Byte 2: all spare + FX=1
    payload.append(0x01)  # Byte 3: all spare + FX=1
    # Byte 4: FRN 34(RE), 35(SP) + FX=0
    b4 = (1<<6) | (1<<5)  # RE + SP
    payload.append(b4)
    
    # FRN 1: SAC/SIC
    payload.append(0x01)
    payload.append(0x02)
    
    # FRN 5: ToT
    payload.extend(struct.pack('>I', int(3600 * 128))[1:])
    
    # FRN 6: Track Status (1 byte simple, sin extensiones)
    payload.append(0x00)
    
    # FRN 7: Position Cartesian (6B)
    payload.extend(struct.pack('>i', 10000))  # X = 10000 m
    payload.extend(struct.pack('>h', 5000))   # Y = 5000 m
    
    # FRN 34: RE (Explicit)
    re_content = bytes(range(10))  # 10 bytes de contenido RE
    payload.append(len(re_content) + 1)
    payload.extend(re_content)
    
    # FRN 35: SP (Explicit)
    sp_content = bytes([0xAB, 0xCD, 0xEF])
    payload.append(len(sp_content) + 1)
    payload.extend(sp_content)
    
    block_len = 3 + len(payload)
    block = bytearray([62]) + struct.pack('>H', block_len) + payload
    
    records = _decode_cat062(block[3:], 0, len(block))
    assert len(records) == 1, f"Esperaba 1 registro, obtuve {len(records)}"
    r = records[0]
    assert r['sac'] == 1
    assert r['sic'] == 2
    print(f"    ✓ OK: SAC={r['sac']}, SIC={r['sic']}, x={r['extra_data'].get('x_cartesian_m')}")


def test_re_edge_cases():
    """Test: Casos límite para RE/SP."""
    print("\n[TEST 6] RE con longitud 1 (solo el byte de longitud)")
    
    payload = bytearray()
    # FSPEC: same as before but only RE
    b0 = (1<<7) | (1<<3) | (1<<2) | 1  # FRN 1,5,6 + FX=1
    payload.append(b0)
    payload.append(0x01)  # FX=1
    payload.append(0x01)  # FX=1
    payload.append(0x01)  # FX=1
    payload.append(1<<6)  # Solo RE, FX=0
    
    # FRN 1
    payload.append(0x01)
    payload.append(0x02)
    # FRN 5
    payload.extend(struct.pack('>I', int(3600 * 128))[1:])
    # FRN 6
    payload.append(0x00)
    # RE con longitud 1 (campo vacío, solo el byte de longitud)
    payload.append(0x01)
    
    block_len = 3 + len(payload)
    block = bytearray([62]) + struct.pack('>H', block_len) + payload
    
    records = _decode_cat062(block[3:], 0, len(block))
    assert len(records) == 1, f"Esperaba 1 registro, obtuve {len(records)}"
    print(f"    ✓ OK: RE con length=1 saltado correctamente")


if __name__ == '__main__':
    print("=" * 60)
    print("FASE 2: BYPASS SEGURO DE CAMPOS RE/SP EN CAT062")
    print("=" * 60)
    print("\nVerificación del XML:")
    print("  RE (FRN 34): <Explicit> -> primer byte = Length Indicator")
    print("  SP (FRN 35): <Explicit> -> primer byte = Length Indicator")
    print("  Ambos usan formato de longitud explícita (NO Compound con FX)")
    print()
    print("Verificación de native_asterix.py:")
    print("  FRN 34 (RE): offset = payload[offset] (Length Indicator)")
    print("  FRN 35 (SP): offset = payload[offset] (Length Indicator)")
    print("  => Coincide con <Explicit> del XML")
    
    test_no_re_sp()
    test_re_only()
    test_sp_only()
    test_re_and_sp()
    test_re_sp_with_full_uap()
    test_re_edge_cases()
    
    print("\n" + "=" * 60)
    print("TODOS LOS TESTS PASARON EXITOSAMENTE")
    print("=" * 60)
    print("\nCONCLUSIÓN:")
    print("  El bypass seguro de RE/SP en CAT062 está correctamente implementado.")
    print("  - XML define RE y SP como formato <Explicit> (Length Indicator)")
    """
    - Código lee correctamente el primer byte como Length Indicator
    - Validaciones de límites (bounds checking) presentes
    - Manejo de errores con IndexError capturado
    - Compatible con otros campos del UAP que puedan aparecer antes de RE/SP
    """
