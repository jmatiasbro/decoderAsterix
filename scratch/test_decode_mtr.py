import sys
import os
import struct
import dpkt

sys.path.append('c:/documentos/decode_asterix')
from decoder.asterix_router import AsterixRouter

def verify_mtr_decoding(filepath):
    print(f"=== Verifying MTR Decoding: {filepath} ===")
    if not os.path.exists(filepath):
        print("Error: File not found")
        return
        
    f = open(filepath, 'rb')
    pcap = dpkt.pcap.Reader(f)
    
    router = AsterixRouter()
    
    total_udp_packets = 0
    total_decoded_plots = 0
    plots_by_category = {}
    sample_plots = []
    
    for ts, buf in pcap:
        try:
            eth = dpkt.ethernet.Ethernet(buf)
            if not isinstance(eth.data, dpkt.ip.IP): continue
            ip = eth.data
            if not isinstance(ip.data, dpkt.udp.UDP): continue
            udp = ip.data
            data = udp.data
            if len(data) < 3: continue
            
            total_udp_packets += 1
            
            # Decode using our router
            records = router.procesar_paquete_udp(data)
            if records:
                for rec in records:
                    cat = rec.get('category')
                    plots_by_category[cat] = plots_by_category.get(cat, 0) + 1
                    total_decoded_plots += 1
                    
                    if cat == 48 and len(sample_plots) < 10:
                        sample_plots.append(rec)
        except Exception as e:
            print(f"Error parsing packet: {e}")
            
    f.close()
    
    print("\n--- Decoding Summary ---")
    print(f"Total UDP Packets parsed: {total_udp_packets}")
    print(f"Total ASTERIX plots/records decoded: {total_decoded_plots}")
    print(f"Decoded counts by category: {plots_by_category}")
    
    if sample_plots:
        print("\n--- First 10 Sample CAT 048 Plots ---")
        for i, p in enumerate(sample_plots):
            sac = p.get('sac')
            sic = p.get('sic')
            squawk = p.get('mode_3a')
            fl = p.get('flight_level')
            r = p.get('raw_range')
            theta = p.get('raw_azimuth')
            print(f"[{i:02d}] SAC/SIC={sac}/{sic} Squawk={squawk} FL={fl} R={r} Theta={theta}")

if __name__ == "__main__":
    verify_mtr_decoding('c:/documentos/decode_asterix/MTR_2026_04_16_16-28-16.pcap')
