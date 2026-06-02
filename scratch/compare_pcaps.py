import sys
import os
import struct
import dpkt

sys.path.append('c:/documentos/decode_asterix')
from decoder.asterix_utils import read_fspec

def analyze_pcap_rotations(filepath):
    print(f"\n=========================================")
    print(f"Analyzing Rotations for: {os.path.basename(filepath)}")
    print(f"=========================================")
    if not os.path.exists(filepath):
        print("Not found")
        return
        
    f = open(filepath, 'rb')
    pcap = dpkt.pcap.Reader(f)
    
    cat_counts = {}
    records = []
    
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
                
                if cat == 34:
                    fspec, fspec_offset = read_fspec(data, offset + 3)
                    
                    sac, sic = None, None
                    if len(fspec) >= 1 and fspec[0]:
                        sac = data[fspec_offset]
                        sic = data[fspec_offset+1]
                        
                    msg_type = None
                    if len(fspec) >= 2 and fspec[1]:
                        msg_type = data[fspec_offset + 2]
                        
                    sector = None
                    if len(fspec) >= 4 and fspec[3]:
                        sector_offset = fspec_offset + 6
                        sector = data[sector_offset]
                        
                    records.append({
                        'sac': sac,
                        'sic': sic,
                        'msg_type': msg_type,
                        'sector': sector
                    })
                offset += length
        except Exception as e:
            pass
    f.close()
    
    print(f"Total packets scanned: {sum(cat_counts.values())}")
    print(f"Categories present: {cat_counts}")
    
    # Group records by SAC/SIC to handle multi-sensor files correctly!
    records_by_sensor = {}
    for r in records:
        key = (r['sac'], r['sic'])
        if key not in records_by_sensor:
            records_by_sensor[key] = []
        records_by_sensor[key].append(r)
        
    for sensor, s_records in sorted(records_by_sensor.items()):
        north_markers = [i for i, r in enumerate(s_records) if r['msg_type'] == 1]
        print(f"\nSensor {sensor[0]}/{sensor[1]}:")
        print(f"  - Total CAT 34 packets: {len(s_records)}")
        print(f"  - Total North Markers: {len(north_markers)}")
        
        if len(north_markers) > 1:
            spacings = []
            for j in range(len(north_markers) - 1):
                idx1 = north_markers[j]
                idx2 = north_markers[j+1]
                between = s_records[idx1+1:idx2]
                spacings.append(len(between))
            
            # Print unique spacing counts
            spacing_counts = {}
            for sp in spacings:
                spacing_counts[sp] = spacing_counts.get(sp, 0) + 1
            print(f"  - Sector crossing packets between North Markers (unique spacing counts):")
            for sp, count in sorted(spacing_counts.items()):
                print(f"      {sp} sector crossings: {count} times")

if __name__ == "__main__":
    analyze_pcap_rotations('c:/documentos/decode_asterix/MTR_2026_04_16_16-28-16.pcap')
    analyze_pcap_rotations('c:/documentos/captura_260130.pcap')
    analyze_pcap_rotations('c:/documentos/baires.pcap')
