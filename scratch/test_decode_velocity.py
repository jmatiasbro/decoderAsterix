import sys
import os
import dpkt

# Add root folder to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from decoder.asterix_router import AsterixRouter

import glob

pcap_patterns = [
    "c:/documentos/*.pcap",
    "c:/documentos/decode_asterix/*.pcap"
]
pcap_paths = []
for pat in pcap_patterns:
    pcap_paths.extend(glob.glob(pat))

print(f"[*] Found PCAPs: {pcap_paths}")
router = AsterixRouter()

for pcap_path in pcap_paths:
    print(f"\n[*] Reading pcap file: {pcap_path}")
    cat_counts = {}
    velocity_plots = []
    
    try:
        with open(pcap_path, 'rb') as f:
            pcap = dpkt.pcap.Reader(f)
            pkt_count = 0
            for ts, buf in pcap:
                pkt_count += 1
                if pkt_count > 15000:  # scan first 15k packets of each pcap
                    break
                # Extract UDP payload
                try:
                    eth = dpkt.ethernet.Ethernet(buf)
                    if not isinstance(eth.data, dpkt.ip.IP):
                        continue
                    ip = eth.data
                    if not isinstance(ip.data, dpkt.udp.UDP):
                        continue
                    udp = ip.data
                    
                    plots = router.procesar_paquete_udp(udp.data, silent=True)
                    for plot in plots:
                        cat = plot.get('category')
                        cat_counts[cat] = cat_counts.get(cat, 0) + 1
                        
                        if cat == 48:
                            extra = plot.get('extra_data', {})
                            if 'ground_speed_nms' in extra or 'track_angle' in extra:
                                velocity_plots.append((plot, extra))
                except Exception:
                    continue
                    
        print(f"[+] Total packets read: {pkt_count}")
        print(f"[+] Category counts: {cat_counts}")
        print(f"[+] CAT 48 Velocity plots decoded: {len(velocity_plots)}")
        if velocity_plots:
            for idx, (plot, extra) in enumerate(velocity_plots[:5]):
                sac_sic = plot.get('sac_sic')
                cat = plot.get('category')
                callsign = plot.get('callsign', 'N/A')
                gs_nms = extra.get('ground_speed_nms')
                ta = extra.get('track_angle')
                gs_kts = gs_nms * 3600.0 if gs_nms is not None else None
                print(f"  [{idx}] SAC/SIC: {sac_sic} (CAT {cat}) | Callsign: {callsign} | GS: {gs_kts:.1f} kt | Heading: {ta:.1f}°")
            break # Found CAT 48 velocity, we can stop

    except Exception as e:
        print(f"[ERROR] Error processing {pcap_path}: {e}")

