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

pcap_paths = sorted(list(set(os.path.abspath(p) for p in pcap_paths)))

for pcap_path in pcap_paths:
    try:
        with open(pcap_path, 'rb') as f:
            pcap = dpkt.pcap.Reader(f)
            cat48_with_frn13 = 0
            pkt_count = 0
            for ts, buf in pcap:
                pkt_count += 1
                if pkt_count > 5000: # check first 5k packets
                    break
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
                            fspec, fspec_offset = read_fspec(payload[pointer:], 3)
                            if len(fspec) >= 13 and fspec[12]: # FRN 13 is present
                                cat48_with_frn13 += 1
                        pointer += msg_len
                except Exception:
                    continue
            if cat48_with_frn13 > 0:
                print(f"[FOUND] PCAP {os.path.basename(pcap_path)} has {cat48_with_frn13} messages with FRN 13 in first 5000 packets!")
    except Exception as e:
        print(f"[ERROR] Reading {pcap_path}: {e}")
