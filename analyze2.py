import sys
import struct

def analyze(filepath):
    with open(filepath, 'rb') as f:
        data = f.read()

    print(f"File size: {len(data)}")
    
    # search for potential ASTERIX CAT 048 (0x30) or CAT 034 (0x22)
    # ASTERIX frame: CAT (1 byte) + Length (2 bytes)
    # Length includes the 3 bytes.
    for i in range(0x1000, 0x3000):
        cat = data[i]
        if cat in (0x30, 0x22, 0x3E, 0x01, 0x02, 0x15):
            length = struct.unpack('>H', data[i+1:i+3])[0]
            if 3 < length < 1000:
                # check if next byte makes sense
                if i + length < len(data):
                    next_cat = data[i + length]
                    if next_cat in (0x30, 0x22, 0x3E, 0x01, 0x02, 0x15):
                        print(f"Possible consecutive ASTERIX at {hex(i)}: CAT={cat}, Len={length}, NextCAT={next_cat}")

    # Let's also look for a repeating header pattern.
    # We might have records starting with a timestamp and a length.
    print("Looking for repeating lengths...")
    for i in range(0x1000, 0x1100):
        if data[i] != 0:
            print(f"Data at {hex(i)}: {data[i:i+32].hex()}")
            break
            
if __name__ == '__main__':
    analyze(r'c:\documentos\decode_asterix\rioja_viejo.S4RD')
