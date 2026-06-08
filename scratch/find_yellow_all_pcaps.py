import sys
import os
import dpkt
import glob

sys.path.append('c:/documentos/decode_asterix')
from decoder.asterix_router import AsterixRouter

def find_yellow_all():
    pcap_files = glob.glob('c:/documentos/*.pcap') + glob.glob('c:/documentos/decode_asterix/*.pcap')
    pcap_files = list(set(os.path.abspath(f) for f in pcap_files))
    
    router = AsterixRouter()
    target_squawks = {'0375', '1541', '5202'}
    
    for filepath in pcap_files:
        print(f"Checking PCAP: {os.path.basename(filepath)}")
        found = False
        with open(filepath, 'rb') as f:
            try:
                pcap = dpkt.pcap.Reader(f)
                for ts, buf in pcap:
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
                            if isinstance(mode3a, int):
                                mode3a_str = f"{mode3a:04o}"
                            else:
                                mode3a_str = str(mode3a) if mode3a is not None else ""
                            
                            if mode3a_str in target_squawks:
                                print(f"  -> FOUND in {os.path.basename(filepath)}:")
                                print(f"     Category: {rec.get('category')}, SAC/SIC: {rec.get('sac')}/{rec.get('sic')}, Mode3A: {mode3a_str}")
                                for k, v in rec.items():
                                    if k not in ('raw_bytes', 'payload'):
                                        print(f"       {k}: {v}")
                                found = True
                                break
                    if found:
                        break
            except Exception as e:
                print(f"  Error reading: {e}")

if __name__ == "__main__":
    find_yellow_all()
