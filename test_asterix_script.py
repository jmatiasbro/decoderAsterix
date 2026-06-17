import asterix
from scapy.all import rdpcap, UDP

def test():
    packets = rdpcap("260429.pcap")
    for i, pkt in enumerate(packets):
        if UDP in pkt:
            payload = bytes(pkt[UDP].payload)
            try:
                parsed = asterix.parse(payload)
                for record in parsed:
                    print(record)
                    return
            except Exception as e:
                pass

test()
