import sys
from scapy.all import rdpcap, UDP, Raw
import asterix

try:
    pkts = rdpcap('260429.pcap')
    udp_pkts = [p for p in pkts if UDP in p and Raw in p]

    cats = set()
    cats_first_byte = set()
    invalid = 0

    for p in udp_pkts:
        payload = bytes(p[Raw].load)
        if payload:
            cats_first_byte.add(payload[0])
        try:
            recs = asterix.parse(payload)
            for r in recs:
                cats.add(r.get('category'))
        except Exception as e:
            invalid += 1

    print(f"Categories from parse: {cats}")
    print(f"First bytes found (decimal): {cats_first_byte}")
    print(f"Invalid parses: {invalid} out of {len(udp_pkts)}")
except Exception as e:
    print(f"Error: {e}")
