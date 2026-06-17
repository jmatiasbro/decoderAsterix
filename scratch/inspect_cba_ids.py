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
                    if mode_3a is not None:
                        mode_3a_str = f"{mode_3a:04o}"
                        if mode_3a_str == "1747":
                            # Mimic target_id logic from radar_widget.py
                            mode_s_addr = rec.get('mode_s') or ""
                            sensor_id = f"{rec.get('sac')}/{rec.get('sic')}"
                            suffix = f"_{sensor_id}"
                            
                            is_mock_mode_s = mode_s_addr.startswith("0AD5B") or (rec.get('callsign') or "").strip().upper().startswith("ADSB")
                            
                            if mode_s_addr and mode_s_addr != '----' and not is_mock_mode_s:
                                target_id = f"{mode_s_addr}"
                            elif mode_s_addr and is_mock_mode_s:
                                target_id = f"{mode_s_addr}{suffix}"
                            elif mode_3a is not None:
                                target_id = f"{mode_3a_str}{suffix}"
                            else:
                                target_id = "unknown"
                                
                            print(f"Time: {rec.get('timestamp') or rec.get('time')}, TargetID: {target_id}, ModeS: {rec.get('mode_s')}, TrackNum: {rec.get('track_number')}")
        except Exception as e:
            pass
