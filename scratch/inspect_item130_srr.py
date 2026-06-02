import sys
import os
import struct
import dpkt

sys.path.append('c:/documentos/decode_asterix')
from decoder.asterix_utils import read_fspec

def analyze_item130_srr(filepath, target_sac, target_sic, limit=20):
    print(f"\n=========================================")
    print(f"Item I048/130 SRR for Sensor {target_sac}/{target_sic} in {os.path.basename(filepath)}")
    print(f"=========================================")
    if not os.path.exists(filepath):
        print("Not found")
        return
        
    f = open(filepath, 'rb')
    pcap = dpkt.pcap.Reader(f)
    
    plots_counted = 0
    srr_distribution = {}
    examples = []
    
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
                    # Parse Category 48 Record block
                    # Skip header (3 bytes)
                    curr_off = offset + 3
                    end_offset = offset + length
                    
                    while curr_off < end_offset:
                        fspec, fspec_offset = read_fspec(data, curr_off)
                        if not fspec: break
                        
                        plot_curr_off = fspec_offset
                        
                        # Let's check SAC/SIC (FRN 1, 2 bytes)
                        sac, sic = None, None
                        if len(fspec) >= 1 and fspec[0]:
                            sac = data[plot_curr_off]
                            sic = data[plot_curr_off + 1]
                            plot_curr_off += 2
                            
                        # If this matches our target sensor
                        is_target = (sac == target_sac and sic == target_sic)
                        
                        # FRN 2: Target Report Descriptor (variable)
                        if len(fspec) >= 2 and fspec[1]:
                            # skip variable target report descriptor
                            while plot_curr_off < len(data):
                                b = data[plot_curr_off]
                                plot_curr_off += 1
                                if (b & 1) == 0: break
                                
                        # FRN 3: Measured Position in Polar (4 bytes)
                        if len(fspec) >= 3 and fspec[2]:
                            plot_curr_off += 4
                            
                        # FRN 4: Mode-3/A Code (2 bytes)
                        if len(fspec) >= 4 and fspec[3]:
                            plot_curr_off += 2
                            
                        # FRN 5: Time of Day (3 bytes)
                        if len(fspec) >= 5 and fspec[4]:
                            plot_curr_off += 3
                            
                        # FRN 6: Flight Level (2 bytes)
                        fl_val = None
                        if len(fspec) >= 6 and fspec[5]:
                            fl_raw = struct.unpack('>h', data[plot_curr_off:plot_curr_off+2])[0]
                            fl_val = fl_raw * 0.25
                            plot_curr_off += 2
                            
                        # FRN 7: Item I048/130 Radar Plot Characteristics (variable)
                        srr_val = None
                        if len(fspec) >= 7 and fspec[6]:
                            sub_fspec, sub_fspec_offset = read_fspec(data, plot_curr_off)
                            # Subfield 1: SRR (Number of Received Replies)
                            if len(sub_fspec) >= 1 and sub_fspec[0]:
                                srr_val = data[sub_fspec_offset]
                                
                            num_present = sum(1 for present in sub_fspec if present)
                            plot_curr_off = sub_fspec_offset + num_present
                            
                        if is_target:
                            plots_counted += 1
                            if srr_val is not None:
                                srr_distribution[srr_val] = srr_distribution.get(srr_val, 0) + 1
                                if len(examples) < limit:
                                    examples.append({
                                        'fl': fl_val,
                                        'srr': srr_val
                                    })
                            else:
                                srr_distribution['None'] = srr_distribution.get('None', 0) + 1
                                
                        # skip remaining fields to advance to next plot in block
                        # The block UAP structure makes it safer to just break after parsing or parse length
                        # But wait, in CAT 48, each plot starts with a new FSPEC. 
                        # Since we don't parse everything, let's break and advance by length of the UDP block 
                        # (since this is just a quick statistical sampler, we will sample the FIRST plot of each UDP message!)
                        break
                        
                offset += length
        except Exception as e:
            pass
            
    f.close()
    
    print(f"Total target plots sampled: {plots_counted}")
    print(f"SRR Distribution (Replies Count): {srr_distribution}")
    print(f"\nFirst {len(examples)} Plot Examples:")
    for idx, ex in enumerate(examples):
        print(f"  [{idx:02d}] FL={ex['fl']} | SRR (Replies)={ex['srr']}")

if __name__ == "__main__":
    # 1. New PCAP (MTR_2026_04_16_16-28-16.pcap): 226/213
    analyze_item130_srr('c:/documentos/decode_asterix/MTR_2026_04_16_16-28-16.pcap', 226, 213)
    
    # 2. Older PCAP (captura_260130.pcap): 226/214
    analyze_item130_srr('c:/documentos/captura_260130.pcap', 226, 214)
