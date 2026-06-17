import sys
import os
import dpkt

sys.path.append('c:/documentos/decode_asterix')
from decoder.asterix_router import AsterixRouter

def inspect_cba():
    filepath = 'c:/documentos/decode_asterix/cba_010626.pcap'
    if not os.path.exists(filepath):
        print(f"Error: File {filepath} not found.")
        return
        
    router = AsterixRouter()
    counts = {}
    sensors = set()
    rpms = {}
    total_packets = 0
    
    with open(filepath, 'rb') as f:
        try:
            pcap = dpkt.pcap.Reader(f)
            for ts, buf in pcap:
                total_packets += 1
                try:
                    eth = dpkt.ethernet.Ethernet(buf)
                    if not isinstance(eth.data, dpkt.ip.IP): continue
                    ip = eth.data
                    if not isinstance(ip.data, dpkt.udp.UDP): continue
                    udp = ip.data
                    data = udp.data
                    if len(data) < 3: continue
                    
                    records = router.procesar_paquete_udp(data)
                    if records:
                        for rec in records:
                            cat = rec.get('category')
                            counts[cat] = counts.get(cat, 0) + 1
                            sac = rec.get('sac')
                            sic = rec.get('sic')
                            if sac is not None and sic is not None:
                                sensors.add((sac, sic))
                            extra = rec.get('extra_data', {})
                            if 'antenna_rpm' in extra:
                                rpms[(sac, sic)] = extra['antenna_rpm']
                except Exception as e:
                    pass
        except Exception as e:
            print(f"Error reading pcap: {e}")
            
    print(f"Total UDP Packets parsed: {total_packets}")
    print("Categories found:")
    for cat, count in counts.items():
        print(f"  Category {cat}: {count} records")
    print("Sensors found (SAC/SIC):")
    for s in sensors:
        rpm_str = f"{rpms[s]:.2f} RPM" if s in rpms else "No RPM detected"
        print(f"  Sensor {s[0]}/{s[1]}: {rpm_str}")

if __name__ == "__main__":
    inspect_cba()
