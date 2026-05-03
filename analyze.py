import sys

def analyze(filepath):
    with open(filepath, 'rb') as f:
        data = f.read()
    
    offset = 0x400
    print(f"File size: {len(data)}")
    
    # Try to find records. Let's scan from 0x400
    # Let's print the first few non-zero chunks after 0x400
    
    while offset < 0x2000 and offset < len(data):
        if data[offset] != 0:
            print(f"Non-zero at {hex(offset)}: {data[offset:offset+32].hex()}")
            offset += 16
        else:
            offset += 1
            
if __name__ == '__main__':
    analyze(r'c:\documentos\decode_asterix\rioja_viejo.S4RD')
