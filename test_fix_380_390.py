#!/usr/bin/env python3
"""
FASE 3: TEST DE VERIFICACIÓN - Mapeo FRN corregido para CAT062
Verifica que _decode_cat062 usa el UAP correcto del XML asterix_cat062_1_18.xml
"""
import sys
sys.path.insert(0, '/mnt/c/documentos/decode_asterix')
from native_asterix import _decode_cat062
import struct

def build_fspec_bytes(active_frns):
    max_frn = max(active_frns) if active_frns else 0
    num_bytes = (max_frn + 6) // 7
    if num_bytes < 1: num_bytes = 1
    result = bytearray()
    for byte_idx in range(num_bytes):
        byte_val = 0
        for frn in active_frns:
            b = (frn - 1) // 7
            if b == byte_idx:
                bit_pos = 7 - ((frn - 1) % 7)
                byte_val |= (1 << bit_pos)
        if byte_idx < num_bytes - 1:
            byte_val |= 1
        result.append(byte_val)
    return bytes(result)

def test_basic_fields():
    print("\n[TEST 1] FRN 1+4+7 (SAC/SIC, ToT, Velocity)")
    payload = bytearray(build_fspec_bytes([1, 4, 7]))
    payload.extend([0x01, 0x02])
    payload.extend(struct.pack('>I', int(3600 * 128))[1:])
    payload.extend(struct.pack('>hh', 400, 300))
    records = _decode_cat062(payload, 0, 3 + len(payload))
    assert len(records) == 1
    gs = records[0]['extra_data']['ground_speed_kts']
    assert 200 < gs < 300, f"GS={gs}"
    print(f"    ✓ OK: GS={gs:.1f} kts")

def test_380():
    print("\n[TEST 2] FRN 1+4+7+11 (380 con ADR+ID)")
    payload = bytearray(build_fspec_bytes([1, 4, 7, 11]))
    payload.extend([0x01, 0x02])
    payload.extend(struct.pack('>I', int(3600 * 128))[1:])
    payload.extend(struct.pack('>hh', 400, 300))
    sub = build_fspec_bytes([1, 2])
    payload.extend(sub)
    payload.extend([0xAB, 0xCD, 0xEF])
    payload.extend(b'CALL12')
    r = _decode_cat062(payload, 0, 3 + len(payload))
    assert len(r) == 1
    gs = r[0]['extra_data']['ground_speed_kts']
    assert 200 < gs < 300, f"GS={gs}"
    print(f"    ✓ OK: GS={gs:.1f} kts")

def test_390():
    print("\n[TEST 3] FRN 1+4+7+21 (390 con CSN)")
    payload = bytearray(build_fspec_bytes([1, 4, 7, 21]))
    payload.extend([0x01, 0x02])
    payload.extend(struct.pack('>I', int(3600 * 128))[1:])
    payload.extend(struct.pack('>hh', 400, 0))
    payload.append(1<<6)
    payload.extend(b'AAL1234')
    r = _decode_cat062(payload, 0, 3 + len(payload))
    assert len(r) == 1
    gs = r[0]['extra_data']['ground_speed_kts']
    assert 150 < gs < 250, f"GS={gs}"
    print(f"    ✓ OK: GS={gs:.1f} kts")

def test_380_390():
    print("\n[TEST 4] FRN 1+4+7+11+21 (380+390+velocidad)")
    payload = bytearray(build_fspec_bytes([1, 4, 7, 11, 21]))
    payload.extend([0x03, 0x04])
    payload.extend(struct.pack('>I', int(7200 * 128))[1:])
    payload.extend(struct.pack('>hh', 600, 800))
    sub = build_fspec_bytes([1])
    payload.extend(sub)
    payload.extend([0xAA, 0xBB, 0xCC])
    payload.append(1<<6)
    payload.extend(b'N123456')
    r = _decode_cat062(payload, 0, 3 + len(payload))
    assert len(r) == 1
    gs = r[0]['extra_data']['ground_speed_kts']
    assert 400 < gs < 600, f"GS={gs}"
    print(f"    ✓ OK: GS={gs:.1f} kts")

def test_re_sp():
    print("\n[TEST 5] FRN 1+4+7+34+35 (RE+SP+velocidad)")
    payload = bytearray(build_fspec_bytes([1, 4, 7, 34, 35]))
    payload.extend([0x01, 0x02])
    payload.extend(struct.pack('>I', int(3600 * 128))[1:])
    payload.extend(struct.pack('>hh', 800, 600))
    payload.append(6)
    payload.extend([0x11, 0x22, 0x33, 0x44, 0x55])
    payload.append(4)
    payload.extend([0x66, 0x77, 0x88])
    r = _decode_cat062(payload, 0, 3 + len(payload))
    assert len(r) == 1
    gs = r[0]['extra_data']['ground_speed_kts']
    assert 300 < gs < 500, f"GS={gs}"
    print(f"    ✓ OK: GS={gs:.1f} kts")

def test_full():
    print("\n[TEST 6] FRN 1+4+5+6+7 (WGS84+Cartesian+Velocity)")
    payload = bytearray(build_fspec_bytes([1, 4, 5, 6, 7]))
    payload.extend([0x01, 0x02])
    payload.extend(struct.pack('>I', int(3600 * 128))[1:])
    payload.extend(struct.pack('>ii', 7456541, -559240))
    payload.extend(struct.pack('>i', 10000))
    payload.extend(struct.pack('>h', 5000))
    payload.extend(struct.pack('>hh', 400, 300))
    r = _decode_cat062(payload, 0, 3 + len(payload))
    assert len(r) == 1
    assert r[0]['valid_position'] == True
    gs = r[0]['extra_data']['ground_speed_kts']
    assert 200 < gs < 300, f"GS={gs}"
    print(f"    ✓ OK: lat={r[0]['latitude']:.2f}, lon={r[0]['longitude']:.2f}, GS={gs:.1f} kts")

if __name__ == '__main__':
    print("=" * 60)
    print("FASE 3: VERIFICACIÓN MAPEO FRN CORRECTO")
    print("=" * 60)
    for t in [test_basic_fields, test_380, test_390, test_380_390, test_re_sp, test_full]:
        try:
            t()
        except Exception as e:
            print(f"    ❌ FAIL: {e}")
            import traceback; traceback.print_exc(); sys.exit(1)
    print("\n" + "=" * 60)
    print("TODOS LOS TESTS PASARON EXITOSAMENTE")
    print("=" * 60)