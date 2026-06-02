import sys
import os
import struct
import dpkt
import glob

sys.path.append('c:/documentos/decode_asterix')
from decoder.asterix_router import AsterixRouter

def analyze_all_cat48_pcaps():
    pcap_files = glob.glob('c:/documentos/*.pcap') + glob.glob('c:/documentos/decode_asterix/*.pcap')
    pcap_files = list(set(os.path.abspath(f) for f in pcap_files))
    
    router = AsterixRouter()
    
    for filepath in pcap_files:
        filename = os.path.basename(filepath)
        print(f"\n==========================================")
        print(f"FILE: {filename}")
        print(f"==========================================")
        
        try:
            f = open(filepath, 'rb')
            pcap = dpkt.pcap.Reader(f)
        except Exception as e:
            print(f"Error opening file: {e}")
            continue
            
        total_udp = 0
        cat48_count = 0
        cat34_count = 0
        other_cats = {}
        
        # We will track which items are present in FSPEC for CAT 048
        frn_presence = {}
        
        # Search for Squawks 7005 and 2473
        squawk_7005_count = 0
        squawk_2473_count = 0
        
        sample_squawks = set()
        
        limit = 50000  # Scan up to 50k packets to be fast
        count = 0
        
        for ts, buf in pcap:
            count += 1
            if count > limit:
                break
                
            try:
                eth = dpkt.ethernet.Ethernet(buf)
                if not isinstance(eth.data, dpkt.ip.IP): continue
                ip = eth.data
                if not isinstance(ip.data, dpkt.udp.UDP): continue
                udp = ip.data
                data = udp.data
                if len(data) < 3: continue
                
                total_udp += 1
                
                # Check category directly from raw bytes
                offset = 0
                while offset < len(data):
                    if offset + 3 > len(data): break
                    cat = data[offset]
                    length = (data[offset+1] << 8) | data[offset+2]
                    if length < 3 or offset + length > len(data): break
                    
                    if cat == 48:
                        cat48_count += 1
                        # Let's read the FSPEC bits to see what fields are actually present in this PCAP
                        fspec_bytes = []
                        f_offset = offset + 3
                        while f_offset < offset + length:
                            b = data[f_offset]
                            fspec_bytes.append(b)
                            f_offset += 1
                            if (b & 1) == 0:
                                break
                        
                        # Count active FRNs
                        for byte_idx, b_val in enumerate(fspec_bytes):
                            for bit_idx in range(7):
                                if b_val & (1 << (7 - bit_idx)):
                                    frn = byte_idx * 7 + bit_idx + 1
                                    frn_presence[frn] = frn_presence.get(frn, 0) + 1
                                    
                        # Let's decode the Mode-3/A (FRN 5) if present
                        # We use the router to get decoded fields easily
                        records = router.procesar_paquete_udp(data[offset:offset+length])
                        if records:
                            for r in records:
                                m3a = r.get('mode_3a')
                                if m3a is not None:
                                    m3a_oct = f"{m3a:04o}"
                                    sample_squawks.add(m3a_oct)
                                    if m3a_oct == '7005':
                                        squawk_7005_count += 1
                                    elif m3a_oct == '2473':
                                        squawk_2473_count += 1
                                        
                    elif cat == 34:
                        cat34_count += 1
                    else:
                        other_cats[cat] = other_cats.get(cat, 0) + 1
                        
                    offset += length
            except Exception as e:
                pass
                
        f.close()
        
        print(f"Scan complete (scanned {min(count, limit)} packets).")
        print(f"Total UDP Packets: {total_udp}")
        print(f"CAT 34 (Service Messages) count: {cat34_count}")
        print(f"CAT 48 (Target Reports) count: {cat48_count}")
        print(f"Other Categories: {other_cats}")
        
        if cat48_count > 0:
            print("\nFSPEC FRN field presence in CAT 48:")
            for frn in sorted(frn_presence.keys()):
                pct = (frn_presence[frn] / cat48_count) * 100
                field_name = {
                    1: "I048/010 SAC/SIC",
                    2: "I048/140 Time-of-Day",
                    3: "I048/020 Target Descriptor",
                    4: "I048/040 Measured Position (Polar)",
                    5: "I048/070 Mode 3/A",
                    6: "I048/090 Flight Level",
                    7: "I048/130 Plot Characteristics",
                    8: "I048/220 Aircraft Address",
                    9: "I048/240 Aircraft ID",
                    10: "I048/250 Mode S MB Data",
                    11: "I048/161 Track Number",
                    12: "I048/042 Calc Position (Cartesian)",
                    13: "I048/200 Calc Track Velocity (Polar)",
                    14: "I048/170 Track Status",
                    15: "I048/210 Track Quality",
                    16: "I048/030 Warning/Error",
                    17: "I048/080 Mode-3/A Confidence",
                    18: "I048/100 Mode-C Confidence",
                    19: "I048/110 Height by 3D Radar",
                    20: "I048/120 Radial Doppler Speed",
                    21: "I048/230 Comm/ACAS Capability",
                    22: "I048/260 ACAS RA Report",
                    23: "I048/055 Mode-1 Confidence",
                    24: "I048/050 Mode-2 Confidence",
                    25: "I048/065 Mode-1 Code",
                    26: "I048/060 Mode-2 Code",
                    27: "Special Purpose Field (SP)",
                    28: "Reserved Expansion Field (RE)",
                }.get(frn, f"FRN {frn}")
                print(f"  - FRN {frn:02d} ({field_name}): {frn_presence[frn]} times ({pct:.1f}%)")
                
            print(f"\nTarget Squawk occurrences in this segment:")
            print(f"  - Squawk '7005': {squawk_7005_count}")
            print(f"  - Squawk '2473': {squawk_2473_count}")
            print(f"  - Sample of other Squawks present: {sorted(list(sample_squawks))[:15]}")

if __name__ == "__main__":
    analyze_all_cat48_pcaps()
