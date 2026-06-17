import sys
import os
import dpkt
import glob

# Add root folder to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from decoder.asterix_utils import read_fspec

pcap_patterns = [
    "c:/documentos/*.pcap",
    "c:/documentos/decode_asterix/*.pcap"
]
pcap_paths = []
for pat in pcap_patterns:
    pcap_paths.extend(glob.glob(pat))

# Deduplicate paths
pcap_paths = sorted(list(set(os.path.abspath(p) for p in pcap_paths)))

print(f"[*] Found PCAPs: {pcap_paths}")

for pcap_path in pcap_paths:
    print(f"\n[*] Analyzing PCAP: {os.path.basename(pcap_path)}")
    frn_counts = {}
    
    try:
        with open(pcap_path, 'rb') as f:
            pcap = dpkt.pcap.Reader(f)
            pkt_count = 0
            cat48_count = 0
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
                            # Decode FSPEC
                            fspec, fspec_offset = read_fspec(payload[pointer:], 3)
                            for frn_idx, is_present in enumerate(fspec):
                                if is_present:
                                    frn = frn_idx + 1
                                    frn_counts[frn] = frn_counts.get(frn, 0) + 1
                                    
                        pointer += msg_len
                except Exception:
                    continue
        if cat48_count > 0:
            print(f"  [+] Total packets: {pkt_count}")
            print(f"  [+] CAT 48 messages found: {cat48_count}")
            print("  [+] FRN frequencies in CAT 48 FSPEC:")
            for frn in sorted(frn_counts.keys()):
                count = frn_counts[frn]
                pct = (count / cat48_count) * 100
                print(f"    FRN {frn:02d}: {count:5d} ({pct:5.1f}%)")
        else:
            print("  [+] No CAT 48 messages found.")
    except Exception as e:
        print(f"  [ERROR] Error reading: {e}")
