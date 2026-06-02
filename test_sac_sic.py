import asterix
from scapy.all import PcapReader, UDP

recs = []
for p in PcapReader('260429.pcap'):
    if UDP in p:
        payload = bytes(p[UDP].payload)
        if len(payload) <= 10: continue
        try:
            recs = asterix.parse(payload)
            if recs: break
        except: pass

print(recs)
