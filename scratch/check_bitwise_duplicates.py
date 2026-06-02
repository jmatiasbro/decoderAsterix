import sys
import os
import hashlib
import dpkt

def check_duplicates(filepath):
    print(f"=== Checking Bitwise Duplicates in: {os.path.basename(filepath)} ===")
    if not os.path.exists(filepath):
        print("Not found")
        return
        
    f = open(filepath, 'rb')
    pcap = dpkt.pcap.Reader(f)
    
    seen_payloads = {}
    duplicate_count = 0
    total_udp = 0
    
    # We will sample the first 20000 UDP packets
    for ts, buf in pcap:
        try:
            eth = dpkt.ethernet.Ethernet(buf)
            if not isinstance(eth.data, dpkt.ip.IP): continue
            ip = eth.data
            if not isinstance(ip.data, dpkt.udp.UDP): continue
            udp = ip.data
            payload = udp.data
            
            total_udp += 1
            payload_hash = hashlib.md5(payload).hexdigest()
            
            if payload_hash in seen_payloads:
                prev_ts = seen_payloads[payload_hash]
                diff_ms = (ts - prev_ts) * 1000.0
                duplicate_count += 1
                if duplicate_count <= 10:
                    print(f"  Duplicate #{duplicate_count}: packet hash={payload_hash} repeated after {diff_ms:.3f} ms")
            else:
                seen_payloads[payload_hash] = ts
                
            if total_udp >= 30000:
                break
        except Exception:
            pass
            
    f.close()
    
    pct = (duplicate_count / total_udp * 100.0) if total_udp > 0 else 0.0
    print(f"\nAnalysis Summary:")
    print(f"  - Total UDP packets analyzed: {total_udp}")
    print(f"  - Bitwise Identical duplicates: {duplicate_count} ({pct:.2f}%)")
    
if __name__ == "__main__":
    check_duplicates('c:/documentos/decode_asterix/MTR_2026_04_16_16-28-16.pcap')
