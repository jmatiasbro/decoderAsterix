import sys
import os
import dpkt

sys.path.append(r"c:\documentos\decode_asterix")
from decoder.asterix_router import AsterixRouter

filepath = 'c:/documentos/decode_asterix/cba_010626.pcap'
router = AsterixRouter()

print(f"Reading file: {filepath}")
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
            if len(data) < 3: continue
            
            records = router.procesar_paquete_udp(data)
            if records:
                for rec in records:
                    cat = rec.get('category')
                    mode_3a = rec.get('mode_3a')
                    # format Mode 3A to octal string if present
                    if mode_3a is not None:
                        mode_3a_str = f"{mode_3a:04o}"
                        if mode_3a_str == "1747":
                            # This is our target!
                            print(f"Time: {rec.get('timestamp') or rec.get('time')}, CAT: {cat}, SAC/SIC: {rec.get('sac')}/{rec.get('sic')}, Azimuth: {rec.get('raw_azimuth') or rec.get('azimuth')}, Range: {rec.get('raw_range') or rec.get('range')}")
        except Exception as e:
            pass
