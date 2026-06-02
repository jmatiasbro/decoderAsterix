import os
import struct

file_path = r"c:\documentos\decode_asterix\20251111112025111112"

def parse_file(path):
    print(f"Parsing {path}...")
    file_size = os.path.getsize(path)
    
    with open(path, 'rb') as f:
        # Read the first 32 bytes (start/end timestamp headers)
        header1 = f.read(16)
        header2 = f.read(16)
        
        if len(header1) < 16 or len(header2) < 16:
            print("File too short for headers")
            return
            
        t1_sec, t1_usec = struct.unpack('<QQ', header1)
        t2_sec, t2_usec = struct.unpack('<QQ', header2)
        print(f"Header 1 (Start time): {t1_sec}.{t1_usec:06d}")
        print(f"Header 2 (End time):   {t2_sec}.{t2_usec:06d}")
        
        count = 0
        cat_counts = {}
        bytes_read = 32
        
        while bytes_read < file_size:
            rec_header = f.read(16)
            if len(rec_header) < 16:
                if len(rec_header) > 0:
                    print(f"Trailing bytes in header: {len(rec_header)}")
                break
            bytes_read += 16
            
            sec, usec = struct.unpack('<QQ', rec_header)
            
            marker = f.read(8)
            if len(marker) < 8:
                print("Truncated marker")
                break
            bytes_read += 8
            
            len_bytes = f.read(4)
            if len(len_bytes) < 4:
                print("Truncated length")
                break
            bytes_read += 4
            
            payload_len = struct.unpack('<I', len_bytes)[0]
            
            payload = f.read(payload_len)
            if len(payload) < payload_len:
                print(f"Truncated payload (expected {payload_len}, got {len(payload)})")
                break
            bytes_read += payload_len
            
            if payload_len >= 3:
                cat = payload[0]
                cat_counts[cat] = cat_counts.get(cat, 0) + 1
            
            count += 1
            if count <= 5:
                print(f"Record {count}: Sec={sec}, Usec={usec}, Len={payload_len}, CAT={payload[0] if payload_len > 0 else 'N/A'}")
                
        print(f"\nSuccessfully parsed {count} records.")
        print("Category distribution:")
        for cat, cnt in sorted(cat_counts.items()):
            print(f"  CAT {cat:03d}: {cnt} packets")
            
parse_file(file_path)
