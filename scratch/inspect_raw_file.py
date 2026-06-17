import os

file_path = r"c:\documentos\decode_asterix\20251111112025111112"
print(f"File exists: {os.path.exists(file_path)}")
if os.path.exists(file_path):
    print(f"File size: {os.path.getsize(file_path)}")
    with open(file_path, 'rb') as f:
        head = f.read(1000)
    print("First 100 bytes in hex:")
    print(head[:100].hex(' '))
    print("\nFirst 100 bytes in ASCII:")
    print("".join(chr(b) if 32 <= b < 127 else '.' for b in head[:100]))
