import asterix
from scapy.all import PcapReader, UDP
from main_pyqt import raw_decode_cat48

parsed_count = 0
for p in PcapReader('260429.pcap'):
    if UDP in p:
        payload = bytes(p[UDP].payload)
        if len(payload) <= 10: continue
        
        records = []
        try:
            records = asterix.parse(payload)
        except Exception:
            start_idx = payload.find(b'\x30')
            if start_idx > 0:
                try:
                    records = asterix.parse(payload[start_idx:])
                except Exception:
                    records = raw_decode_cat48(payload[start_idx:])
            elif payload[0] == 0x30:
                records = raw_decode_cat48(payload)
        
        if records:
            parsed_count += len(records)

print('Total records parsed:', parsed_count)
