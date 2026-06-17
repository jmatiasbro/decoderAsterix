import sys
import os
import struct
import dpkt

sys.path.append('c:/documentos/decode_asterix')
from decoder.asterix_utils import read_fspec

def search_mysterious_plots(filepath, squawks=["5613", "3452", "3202", "3163"]):
    print(f"=== Searching for Squawks {squawks} in: {os.path.basename(filepath)} ===")
    if not os.path.exists(filepath):
        print("Not found")
        return
        
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
            
            offset = 0
            while offset < len(data):
                if offset + 3 > len(data): break
                cat = data[offset]
                length = (data[offset+1] << 8) | data[offset+2]
                if length < 3: break
                
                if cat == 48:
                    curr_off = offset + 3
                    end_offset = offset + length
                    
                    while curr_off < end_offset:
                        fspec, fspec_offset = read_fspec(data, curr_off)
                        if not fspec: break
                        
                        plot_curr_off = fspec_offset
                        
                        # FRN 1: SAC/SIC
                        sac, sic = None, None
                        if len(fspec) >= 1 and fspec[0]:
                            sac = data[plot_curr_off]
                            sic = data[plot_curr_off+1]
                            plot_curr_off += 2
                            
                        # FRN 2: Target Descriptor
                        if len(fspec) >= 2 and fspec[1]:
                            while plot_curr_off < len(data):
                                b = data[plot_curr_off]
                                plot_curr_off += 1
                                if (b & 1) == 0: break
                                
                        # FRN 3: Position (4 bytes)
                        rho, theta = None, None
                        if len(fspec) >= 3 and fspec[2]:
                            rho_raw = (data[plot_curr_off] << 8) | data[plot_curr_off+1]
                            theta_raw = (data[plot_curr_off+2] << 8) | data[plot_curr_off+3]
                            rho = rho_raw / 256.0
                            theta = theta_raw * (360.0 / 65536.0)
                            plot_curr_off += 4
                            
                        # FRN 4: Mode-3/A (2 bytes)
                        squawk = None
                        if len(fspec) >= 4 and fspec[3]:
                            m3a_raw = struct.unpack('>H', data[plot_curr_off:plot_curr_off+2])[0]
                            squawk = f"{m3a_raw & 0x0FFF:04o}"
                            plot_curr_off += 2
                            
                        # FRN 5: Time of Day (3 bytes)
                        tod = None
                        if len(fspec) >= 5 and fspec[4]:
                            tod_raw = struct.unpack('>I', b'\x00' + data[plot_curr_off:plot_curr_off+3])[0]
                            tod = tod_raw * 0.0078125
                            plot_curr_off += 3
                            
                        if squawk in squawks:
                            matches.append({
                                'pcap_ts': ts,
                                'tod': tod,
                                'squawk': squawk,
                                'rho': rho,
                                'theta': theta
                            })
                        break
                offset += length
        except Exception:
            pass
    f.close()
    
    # Sort matches by timestamp
    matches = sorted(matches, key=lambda x: x['pcap_ts'])
    
    print(f"\nFound {len(matches)} matching plots:")
    for idx, m in enumerate(matches):
        tod_str = f"{m['tod']:.3f}s" if m['tod'] is not None else "None"
        print(f"  [{idx:03d}] PCAP_TS={m['pcap_ts']:.6f} | ToD={tod_str} | Squawk={m['squawk']} | Dist={m['rho']:.3f}NM | Az={m['theta']:.3f}°")

if __name__ == "__main__":
    search_mysterious_plots('c:/documentos/decode_asterix/MTR_2026_04_16_16-28-16.pcap')
