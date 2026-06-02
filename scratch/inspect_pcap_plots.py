import sys
import os
import struct
import dpkt
import glob

sys.path.append('c:/documentos/decode_asterix')
from decoder.asterix_router import AsterixRouter

def inspect_all_pcaps():
    pcap_files = glob.glob('c:/documentos/*.pcap') + glob.glob('c:/documentos/decode_asterix/*.pcap')
    pcap_files = list(set(os.path.abspath(f) for f in pcap_files))
    
    router = AsterixRouter()
    
    for filepath in pcap_files:
        print(f"=== Inspecting PCAP: {filepath} ===")
        try:
            f = open(filepath, 'rb')
            pcap = dpkt.pcap.Reader(f)
            matches = []
            
            for ts, buf in pcap:
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
                            if cat == 48:
                                mode_3a = rec.get('mode_3a')
                                if mode_3a is not None:
                                    mode_3a_oct = f"{mode_3a:04o}"
                                    if mode_3a_oct in ('7005', '2473'):
                                        matches.append(rec)
                except Exception as e:
                    pass
            f.close()
            
            if matches:
                print(f"--> Found {len(matches)} plots with Squawk 7005 or 2473 in {os.path.basename(filepath)}:")
                for i, m in enumerate(matches[:15]):
                    squawk_oct = f"{m.get('mode_3a'):04o}"
                    r = m.get('raw_range')
                    theta = m.get('raw_azimuth')
                    tod = m.get('timestamp')
                    sac_sic = f"{m.get('sac')}/{m.get('sic')}"
                    print(f"  [{i:02d}] TOD={tod:.3f}s, SAC/SIC={sac_sic}, Squawk={squawk_oct}, Range={r:.2f} NM, Azimuth={theta:.2f}°")
            else:
                print("  No matches.")
        except Exception as e:
            print(f"  Error reading file: {e}")

if __name__ == "__main__":
    inspect_all_pcaps()
