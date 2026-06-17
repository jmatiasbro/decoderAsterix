file_path = r"c:\documentos\decode_asterix\20251111112025111112"

with open(file_path, 'rb') as f:
    data = f.read(1000)

for i in range(0, len(data), 16):
    chunk = data[i:i+16]
    hex_str = chunk.hex(' ')
    ascii_str = "".join(chr(b) if 32 <= b < 127 else '.' for b in chunk)
    print(f"{i:04d} (0x{i:03x}): {hex_str:<47}  | {ascii_str}")
