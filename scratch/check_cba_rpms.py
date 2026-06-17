import sys
import os
import dpkt

sys.path.append('c:/documentos/decode_asterix')
from decoder.asterix_router import AsterixRouter

def check_rpms():
    filepath = 'c:/documentos/decode_asterix/cba_010626.pcap'
    if not os.path.exists(filepath):
        return
        
    router = AsterixRouter()
    rpms = []
    
    with open(filepath, 'rb') as f:
        pcap = dpkt.pcap.Reader(f)
        for ts, buf in pcap:
            try:
                eth = dpkt.ethernet.Ethernet(buf)
                if not isinstance(eth.data, dpkt.ip.IP): continue
                ip = eth.data
                if not isinstance(ip.data, dpkt.udp.UDP): continue
                udp = ip.data
                data = udp.data
                
                records = router.procesar_paquete_udp(data)
                if records:
                    for rec in records:
                        cat = rec.get('category')
                        extra = rec.get('extra_data', {})
                        if cat == 34 and 'antenna_rpm' in extra:
                            rpms.append((ts, extra['antenna_rpm']))
            except Exception:
                pass
                
    print(f"Total RPM packets decoded: {len(rpms)}")
    if rpms:
        print("First 20 RPM values:")
        for ts, rpm in rpms[:20]:
            print(f"  TS={ts:.3f}: {rpm:.3f} RPM")
        print("Last 20 RPM values:")
        for ts, rpm in rpms[-20:]:
            print(f"  TS={ts:.3f}: {rpm:.3f} RPM")
        val_list = [r for t, r in rpms]
        print(f"Min RPM: {min(val_list):.3f}")
        print(f"Max RPM: {max(val_list):.3f}")
        print(f"Avg RPM: {sum(val_list)/len(val_list):.3f}")

if __name__ == "__main__":
    check_rpms()
