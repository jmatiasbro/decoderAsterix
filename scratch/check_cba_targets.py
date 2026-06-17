import sys
import os
import dpkt

sys.path.append('c:/documentos/decode_asterix')
from decoder.asterix_router import AsterixRouter

def check_targets():
    filepath = 'c:/documentos/decode_asterix/cba_010626.pcap'
    if not os.path.exists(filepath):
        print(f"Error: File {filepath} not found.")
        return
        
    router = AsterixRouter()
    target_info = {}
    
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
                        if cat in (1, 2, 21, 34, 48, 62):
                            sac = rec.get('sac')
                            sic = rec.get('sic')
                            mode3a = rec.get('mode_3a')
                            key = (cat, sac, sic)
                            if key not in target_info:
                                target_info[key] = {
                                    'count': 0,
                                    'mode3as': set(),
                                    'example': None
                                }
                            target_info[key]['count'] += 1
                            if mode3a is not None:
                                target_info[key]['mode3as'].add(f"{mode3a:04o}" if isinstance(mode3a, int) else str(mode3a))
                            if target_info[key]['example'] is None:
                                target_info[key]['example'] = rec
            except Exception:
                pass
                
    print("Target/Message distribution by (Category, SAC, SIC):")
    for key, info in target_info.items():
        example_modes = list(info['mode3as'])[:5]
        print(f"Category {key[0]}, SAC/SIC {key[1]}/{key[2]}: {info['count']} records. Examples of Mode 3/A: {example_modes}")

if __name__ == "__main__":
    check_targets()
