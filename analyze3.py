import sys

def analyze(filepath):
    with open(filepath, 'rb') as f:
        data = f.read()

    print(f"File size: {len(data)}")
    
    offset = 0x1a00
    while offset < len(data) and data[offset] == 0:
        offset += 1
        
    print(f"Next non-zero byte after 0x1A00 is at {hex(offset)}")
    if offset < len(data):
        print(f"Data: {data[offset:offset+64].hex()}")

    # Find the actual ASTERIX data! Let's search for 0x30 0x00, 0x3e 0x00, 0x22 0x00
    asterix_starts = []
    for i in range(offset, min(len(data), offset + 10000)):
        if data[i] in (0x30, 0x3E, 0x22) and data[i+1] == 0x00:
            length = data[i+2]
            if 3 < length < 255:
                asterix_starts.append((i, data[i], length))
                
    print(f"Found ASTERIX-like headers: {asterix_starts[:10]}")

if __name__ == '__main__':
    analyze(r'c:\documentos\decode_asterix\rioja_viejo.S4RD')
