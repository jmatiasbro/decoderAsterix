import sys
import os
import struct
import dpkt

sys.path.append('c:/documentos/decode_asterix')
from decoder.asterix_utils import read_fspec

def analyze_pcap(filepath):
    print(f"=== Analyzing PCAP: {filepath} ===")
    if not os.path.exists(filepath):
        print("Error: File not found")
        return
        
    f = open(filepath, 'rb')
    pcap = dpkt.pcap.Reader(f)
    
    cat_counts = {}
    cat_34_types = {}
    cat_34_records = []
    
    # We will also look at Category 01 if present
    cat_01_counts = 0
    
    total_packets = 0
    
    for ts, buf in pcap:
        try:
            eth = dpkt.ethernet.Ethernet(buf)
            if not isinstance(eth.data, dpkt.ip.IP): continue
            ip = eth.data
            if not isinstance(ip.data, dpkt.udp.UDP): continue
            udp = ip.data
            data = udp.data
            if len(data) < 3: continue
            
            offset = 0
            while offset < len(data):
                if offset + 3 > len(data): break
                cat = data[offset]
                length = (data[offset+1] << 8) | data[offset+2]
                if length < 3: break
                
                cat_counts[cat] = cat_counts.get(cat, 0) + 1
                total_packets += 1
                
                if cat == 34:
                    fspec, fspec_offset = read_fspec(data, offset + 3)
                    
                    # Parse SAC/SIC if present (FRN 1)
                    sac, sic = None, None
                    if len(fspec) >= 1 and fspec[0]:
                        sac = data[fspec_offset]
                        sic = data[fspec_offset+1]
                        
                    # Parse Msg Type if present (FRN 2)
                    msg_type = None
                    if len(fspec) >= 2 and fspec[1]:
                        msg_type = data[fspec_offset + 2]
                        cat_34_types[msg_type] = cat_34_types.get(msg_type, 0) + 1
                        
                    # Parse Time of Day if present (FRN 3, len 3)
                    tod = None
                    if len(fspec) >= 3 and fspec[2]:
                        tod_offset = fspec_offset + 3 # 2 bytes SAC/SIC, 1 byte Msg Type
                        tod_raw = struct.unpack('>I', b'\x00' + data[tod_offset:tod_offset+3])[0]
                        tod = tod_raw * 0.0078125
                        
                    # Parse Sector Number if present (FRN 4, len 1)
                    sector = None
                    if len(fspec) >= 4 and fspec[3]:
                        sector_offset = fspec_offset + 6
                        sector = data[sector_offset]
                        
                    # Parse Antenna Rotation Speed if present (FRN 5, len 2)
                    rot_s = None
                    if len(fspec) >= 5 and fspec[4]:
                        rot_offset = fspec_offset + 6
                        if len(fspec) >= 4 and fspec[3]:
                            rot_offset += 1 # skip sector number
                        rot_s_raw = struct.unpack('>H', data[rot_offset:rot_offset+2])[0]
                        rot_s = rot_s_raw * 0.0078125
                        
                    cat_34_records.append({
                        'sac': sac,
                        'sic': sic,
                        'msg_type': msg_type,
                        'tod': tod,
                        'sector': sector,
                        'rot_period': rot_s
                    })
                elif cat == 1:
                    cat_01_counts += 1
                    
                offset += length
        except Exception as e:
            pass
            
    f.close()
    
    print(f"Total Asterix Packets: {total_packets}")
    print(f"Categories present: {cat_counts}")
    print(f"CAT 34 Message Types present: {cat_34_types}")
    print(f"CAT 34 Records count: {len(cat_34_records)}")
    
    if len(cat_34_records) > 0:
        # Let's inspect the sequence of CAT 34 records
        print("\n--- Sequence of first 40 CAT 34 Records ---")
        for i, r in enumerate(cat_34_records[:40]):
            msg_name = "North Marker" if r['msg_type'] == 1 else "Sector Crossing" if r['msg_type'] == 2 else f"Unknown ({r['msg_type']})"
            print(f"[{i:02d}] SAC/SIC={r['sac']}/{r['sic']} Type={msg_name} (tod={r['tod']:.3f}s, sector={r['sector']}, rot_period={r['rot_period']})")
            
        # Let's analyze spacing between North Markers (msg_type == 1)
        north_markers = [i for i, r in enumerate(cat_34_records) if r['msg_type'] == 1]
        print(f"\nTotal North Markers detected: {len(north_markers)}")
        
        if len(north_markers) > 1:
            print("\n--- Analysing packets between North Markers ---")
            for j in range(min(5, len(north_markers) - 1)):
                idx1 = north_markers[j]
                idx2 = north_markers[j+1]
                between = cat_34_records[idx1+1:idx2]
                types_between = [r['msg_type'] for r in between]
                sectors_between = [r['sector'] for r in between if r['sector'] is not None]
                time_diff = cat_34_records[idx2]['tod'] - cat_34_records[idx1]['tod']
                print(f"Giro {j+1} -> {j+2}:")
                print(f"  - Time elapsed: {time_diff:.3f}s")
                print(f"  - Count of CAT 34 packets in-between: {len(between)}")
                print(f"  - Sector crossing counts: {types_between.count(2)}")
                print(f"  - Sectors encountered: {sectors_between}")
                print(f"  - Other msg types: {[t for t in types_between if t != 2]}")

if __name__ == "__main__":
    analyze_pcap('c:/documentos/decode_asterix/MTR_2026_04_16_16-28-16.pcap')
