import sys
import os
import dpkt

# Add root folder to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from decoder.asterix_utils import read_fspec
from decoder.decoders import cat048

pcap_path = "c:/documentos/decode_asterix/Martescordoba_radar2.pcap"
if not os.path.exists(pcap_path):
    pcap_path = "c:/documentos/Martescordoba_radar2.pcap"

print(f"[*] Parsing {pcap_path}...")

with open(pcap_path, 'rb') as f:
    pcap = dpkt.pcap.Reader(f)
    pkt_count = 0
    cat48_count = 0
    plots_processed = 0
    plots_with_velocity = 0
    
    for ts, buf in pcap:
        pkt_count += 1
        try:
            eth = dpkt.ethernet.Ethernet(buf)
            if not isinstance(eth.data, dpkt.ip.IP):
                continue
            ip = eth.data
            if not isinstance(ip.data, dpkt.udp.UDP):
                continue
            udp = ip.data
            
            payload = udp.data
            pointer = 0
            while pointer < len(payload):
                if pointer + 3 > len(payload):
                    break
                cat = payload[pointer]
                msg_len = (payload[pointer + 1] << 8) | payload[pointer + 2]
                if msg_len <= 0 or pointer + msg_len > len(payload):
                    break
                
                if cat == 48:
                    cat48_count += 1
                    # Directly call cat048.decode
                    plots = cat048.decode(payload[pointer:], 3, msg_len, cat)
                    for plot in plots:
                        plots_processed += 1
                        extra = plot.get('extra_data', {})
                        if 'ground_speed_nms' in extra or 'track_angle' in extra:
                            plots_with_velocity += 1
                            if plots_with_velocity <= 5:
                                print(f"  [FOUND] Plot {plots_processed}: {plot}")
                                
                pointer += msg_len
        except Exception as e:
            print(f"[ERROR at packet {pkt_count}]: {e}")
            continue

print(f"[+] Total packets: {pkt_count}")
print(f"[+] CAT 48 messages: {cat48_count}")
print(f"[+] Total plots decoded: {plots_processed}")
print(f"[+] Plots with velocity: {plots_with_velocity}")
