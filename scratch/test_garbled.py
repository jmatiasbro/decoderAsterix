"""Test de decodificación del bit de Garbling en CAT 048."""
import struct
from decoder.decoders.cat048 import decode

# Construir un paquete CAT 048 mínimo con FRN 1,5 presentes
# FSPEC: FRN1=1, FRN2=0, FRN3=0, FRN4=0, FRN5=1, FRN6=0, FRN7=0, FX=0
# = 0b10001000 = 0x88
fspec = bytes([0x88])

# FRN 1: I048/010 Data Source Identifier - SAC=10, SIC=20
data_source = struct.pack('BB', 10, 20)

# Test 1: No garbled - Code 2335 octal = 0x49D
mode3a_code = 0x049D
mode3a_bytes = struct.pack('>H', mode3a_code)
payload = fspec + data_source + mode3a_bytes
block_length = len(payload) + 3

result = decode(payload, 0, block_length, 48)
print("Test 1 - Sin garbling:")
for p in result:
    code = p.get('mode_3a', 0)
    garbled = p.get('garbled', False)
    validated = p.get('mode3a_validated', 'N/A')
    print(f"  code=0x{code:03X} ({code:04o}), garbled={garbled}, validated={validated}")

# Test 2: Garbled - bit G=1 (bit 15 = 0x4000)
mode3a_garbled = 0x049D | 0x4000
mode3a_bytes2 = struct.pack('>H', mode3a_garbled)
payload2 = fspec + data_source + mode3a_bytes2
result2 = decode(payload2, 0, block_length, 48)
print("Test 2 - Con garbling en Mode-3/A:")
for p in result2:
    code = p.get('mode_3a', 0)
    garbled = p.get('garbled', False)
    validated = p.get('mode3a_validated', 'N/A')
    print(f"  code=0x{code:03X} ({code:04o}), garbled={garbled}, validated={validated}")

# Test 3: Not validated + Garbled
mode3a_invalid = 0x049D | 0x4000 | 0x8000
mode3a_bytes3 = struct.pack('>H', mode3a_invalid)
payload3 = fspec + data_source + mode3a_bytes3
result3 = decode(payload3, 0, block_length, 48)
print("Test 3 - Garbled + Not Validated:")
for p in result3:
    code = p.get('mode_3a', 0)
    garbled = p.get('garbled', False)
    validated = p.get('mode3a_validated', 'N/A')
    print(f"  code=0x{code:03X} ({code:04o}), garbled={garbled}, validated={validated}")

# Test 4: Con Flight Level garbled
# FSPEC: FRN1=1, FRN2=0, FRN3=0, FRN4=0, FRN5=1, FRN6=1, FRN7=0, FX=0
# = 0b10001100 = 0x8C
fspec4 = bytes([0x8C])
mode3a_ok = struct.pack('>H', 0x049D)  # Mode 3/A sin garble
fl_garbled = struct.pack('>H', (350 * 4) | 0x4000)  # FL350 con bit G=1
payload4 = fspec4 + data_source + mode3a_ok + fl_garbled
block_length4 = len(payload4) + 3
result4 = decode(payload4, 0, block_length4, 48)
print("Test 4 - Flight Level garbled (Mode 3/A ok):")
for p in result4:
    code = p.get('mode_3a', 0)
    garbled = p.get('garbled', False)
    fl = p.get('flight_level', 'N/A')
    print(f"  code={code:04o}, fl={fl}, garbled={garbled}")

print("\nTodos los tests completados!")
