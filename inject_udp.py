"""Inyector de PCAP por UDP."""
import dpkt, socket, time, sys

PCAP  = sys.argv[1] if len(sys.argv) > 1 else "baires.pcap"
HOST  = "127.0.0.1"
PORT  = int(sys.argv[2]) if len(sys.argv) > 2 else 8600
PPS   = int(sys.argv[3]) if len(sys.argv) > 3 else 2000

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
payloads = []
with open(PCAP, "rb") as f:
    for _, buf in dpkt.pcap.Reader(f):
        try:
            eth = dpkt.ethernet.Ethernet(buf)
            ip  = eth.data
            if not isinstance(ip, dpkt.ip.IP): continue
            udp = ip.data
            if not isinstance(udp, dpkt.udp.UDP): continue
            payloads.append(bytes(udp.data))
        except Exception:
            continue

total = len(payloads)
print(f"Inyectando {total} paquetes @ {PPS} PPS a {HOST}:{PORT}...")
interval = 1.0 / PPS
for i, p in enumerate(payloads):
    sock.sendto(p, (HOST, PORT))
    if i % 5000 == 0:
        print(f"  {i}/{total}")
    time.sleep(interval)
print("Listo.")
