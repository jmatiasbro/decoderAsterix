import os
import struct

def detect_and_parse(file_path):
    print(f"\nDetecting format for: {file_path}")
    file_size = os.path.getsize(file_path)
    if file_size < 32:
        print("File too small")
        return "too_small"
        
    with open(file_path, 'rb') as f:
        header1 = f.read(16)
        header2 = f.read(16)
        
        if len(header1) == 16 and len(header2) == 16:
            try:
                t1_sec, t1_usec = struct.unpack('<QQ', header1)
                t2_sec, t2_usec = struct.unpack('<QQ', header2)
                
                # Check timestamp ranges
                if 1000000000 < t1_sec < 3000000000 and 1000000000 < t2_sec < 3000000000:
                    # Let's read the first record header at offset 32
                    rec_header = f.read(16)
                    marker = f.read(8)
                    len_bytes = f.read(4)
                    
                    if len(rec_header) == 16 and len(marker) == 8 and len(len_bytes) == 4:
                        sec, usec = struct.unpack('<QQ', rec_header)
                        payload_len = struct.unpack('<I', len_bytes)[0]
                        
                        if 0 < payload_len < 65536:
                            # Read payload to verify
                            payload = f.read(payload_len)
                            if len(payload) == payload_len:
                                cat = payload[0]
                                asterix_len = (payload[1] << 8) | payload[2]
                                if cat in (1, 2, 21, 34, 48, 62) and asterix_len == payload_len:
                                    print("-> DETECTED: Wrapped ASTERIX format!")
                                    return "wrapped"
            except Exception as e:
                pass
                
    print("-> DETECTED: Pure Raw ASTERIX stream!")
    return "pure_raw"

detect_and_parse(r"c:\documentos\decode_asterix\20251111112025111112")
detect_and_parse(r"c:\documentos\decode_asterix\asterix_decoder-0.7.4\asterix\sample_data\cat048.raw")
