import sys
import os
import dpkt

sys.path.append('c:/documentos/decode_asterix')
from decoder.asterix_router import AsterixRouter

def find_yellow():
    filepath = 'c:/documentos/decode_asterix/cba_010626.pcap'
    if not os.path.exists(filepath):
        return
        
    router = AsterixRouter()
    target_squawks = {'0375', '1541', '5202'}
    print(f"Searching for mode_3a in {target_squawks}...")
    
    found = []
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
                        mode3a = rec.get('mode_3a')
                        # Convert mode_3a to string octal if it's an int
                        if isinstance(mode3a, int):
                            mode3a_str = f"{mode3a:04o}"
                        else:
                            mode3a_str = str(mode3a) if mode3a is not None else ""
                        
                        if mode3a_str in target_squawks:
                            found.append(rec)
                            if len(found) >= 10:
                                break
                if len(found) >= 10:
                    break
            except Exception:
                pass
                
    for i, rec in enumerate(found):
        print(f"Record {i}:")
        for k, v in rec.items():
            print(f"  {k}: {v}")

if __name__ == "__main__":
    find_yellow()
