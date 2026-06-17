import os

paths = [
    r"c:\documentos\decode_asterix\.venv\Lib\python3.8\site-packages\asterix\sample_data\cat048.raw",
    r"c:\documentos\decode_asterix\asterix_decoder-0.7.4\asterix\sample_data\cat048.raw"
]

for p in paths:
    print(f"Path exists: {p} -> {os.path.exists(p)}")
    if os.path.exists(p):
        print(f"Size: {os.path.getsize(p)}")
        with open(p, 'rb') as f:
            head = f.read(100)
        print("Hex of head:")
        print(head.hex(' '))
