import sys
import os
import struct
import dpkt

sys.path.append('c:/documentos/decode_asterix')
from decoder.asterix_utils import read_fspec

def dump_sectors_for_sensor(filepath, target_sac, target_sic, num_turns=2):
    print(f"\n=========================================")
    print(f"Sectors for Sensor {target_sac}/{target_sic} in {os.path.basename(filepath)}")
    print(f"=========================================")
    if not os.path.exists(filepath):
        print("Not found")
        return
        
    f = open(filepath, 'rb')
    pcap = dpkt.pcap.Reader(f)
    
    records = []
    for ts, buf in pcap:
        try:
            eth = dpkt.ethernet.Ethernet(buf)
            if not isinstance(eth.data, dpkt.ip.IP): continue
            ip = eth.data
            if not isinstance(ip.data, dpkt.udp.UDP): continue
            udp = ip.data
            data = udp.data
            
            offset = 0
            while offset < len(data):
                if offset + 3 > len(data): break
                cat = data[offset]
                length = (data[offset+1] << 8) | data[offset+2]
                if length < 3: break
                
                if cat == 34:
                    fspec, fspec_offset = read_fspec(data, offset + 3)
                    sac, sic = None, None
                    if len(fspec) >= 1 and fspec[0]:
                        sac = data[fspec_offset]
                        sic = data[fspec_offset+1]
                        
                    if sac == target_sac and sic == target_sic:
                        msg_type = None
                        if len(fspec) >= 2 and fspec[1]:
                            msg_type = data[fspec_offset + 2]
                            
                        sector = None
                        if len(fspec) >= 4 and fspec[3]:
                            sector_offset = fspec_offset + 6
                            sector = data[sector_offset]
                            
                        records.append({
                            'msg_type': msg_type,
                            'sector': sector
                        })
                offset += length
        except Exception as e:
            pass
    f.close()
    
    # Let's find North Markers
    nm_indices = [i for i, r in enumerate(records) if r['msg_type'] == 1]
    
    if len(nm_indices) < num_turns + 1:
        print(f"Found only {len(nm_indices)} North Markers, showing all records.")
        for idx, r in enumerate(records[:100]):
            msg_name = "North Marker" if r['msg_type'] == 1 else "Sector Crossing"
            print(f"  [{idx:03d}] Type={msg_name}, Sector={r['sector']}")
        return
        
    for turn_idx in range(num_turns):
        idx1 = nm_indices[turn_idx]
        idx2 = nm_indices[turn_idx+1]
        print(f"\n--- TURN {turn_idx+1} (from index {idx1} to {idx2}) ---")
        print(f"Start North Marker: Index {idx1}")
        for idx in range(idx1 + 1, idx2):
            r = records[idx]
            print(f"  [{idx:03d}] Sector Crossing: Sector = {r['sector']}")
        print(f"End North Marker: Index {idx2}")

if __name__ == "__main__":
    # 1. New PCAP (MTR_2026_04_16_16-28-16.pcap): 226/213 (has 31 sector crossings)
    dump_sectors_for_sensor('c:/documentos/decode_asterix/MTR_2026_04_16_16-28-16.pcap', 226, 213, num_turns=2)
    
    # 2. Older PCAP (captura_260130.pcap): 226/214 (has 32 sector crossings)
    dump_sectors_for_sensor('c:/documentos/captura_260130.pcap', 226, 214, num_turns=2)
    
    # 3. Older PCAP (captura_260130.pcap): 226/212 (alternates between 1 and 63 sector crossings)
    dump_sectors_for_sensor('c:/documentos/captura_260130.pcap', 226, 212, num_turns=2)
