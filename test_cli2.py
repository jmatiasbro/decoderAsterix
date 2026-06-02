from scapy.all import PcapReader, UDP
from native_asterix import parse_payload

def test():
    reader = PcapReader("Martescordoba_radar2.pcap")
    for i, pkt in enumerate(reader):
        if UDP in pkt:
            payload = bytes(pkt[UDP].payload)
            if len(payload) > 10:
                records = parse_payload(payload)
                if records:
                    print(f"Packet {i}: {len(records)} records")
                    return
    print("No records found!")
test()
