import sys
import os
import struct
import dpkt

sys.path.append('c:/documentos/decode_asterix')
from decoder.asterix_utils import read_fspec

# Decodificador bajo nivel directo para análisis forense
def decode_cat48_raw(data, offset, length):
    """Decodifica un bloque CAT 48 en modo forense, extrayendo todos los campos."""
    end = offset + length - 3  # length incluye los 3 bytes de cabecera
    result = {}
    
    try:
        fspec, f_offset = read_fspec(data, offset)
        offset = f_offset
        result['fspec_frns'] = [i+1 for i, v in enumerate(fspec) if v]
        
        for frn_idx, is_present in enumerate(fspec):
            frn = frn_idx + 1
            if not is_present:
                continue

            if offset >= len(data):
                break

            if frn == 1:  # I048/010 SAC/SIC
                result['sac'] = data[offset]
                result['sic'] = data[offset+1]
                offset += 2

            elif frn == 2:  # I048/140 Time-of-Day
                tod_raw = struct.unpack('>I', b'\x00' + data[offset:offset+3])[0]
                result['tod'] = tod_raw / 128.0
                offset += 3

            elif frn == 3:  # I048/020 Target Descriptor
                b0 = data[offset]
                result['typ_psr'] = bool(b0 & 0x80)
                result['typ_ssr'] = bool(b0 & 0x40)
                result['typ_combined'] = bool(b0 & 0x20)
                result['sim'] = bool(b0 & 0x10)
                result['rdp'] = bool(b0 & 0x04)
                result['spi'] = bool(b0 & 0x02)
                while offset < len(data):
                    b = data[offset]
                    offset += 1
                    if (b & 1) == 0:
                        break

            elif frn == 4:  # I048/040 Measured Position
                rho_raw = struct.unpack('>H', data[offset:offset+2])[0]
                theta_raw = struct.unpack('>H', data[offset+2:offset+4])[0]
                result['rho'] = rho_raw / 256.0
                result['theta'] = theta_raw * (360.0 / 65536.0)
                offset += 4

            elif frn == 5:  # I048/070 Mode 3/A
                raw = struct.unpack('>H', data[offset:offset+2])[0]
                result['mode3a'] = f"{raw & 0x0FFF:04o}"
                offset += 2

            elif frn == 6:  # I048/090 Flight Level
                fl_raw = struct.unpack('>h', data[offset:offset+2])[0]
                result['fl'] = fl_raw * 0.25
                offset += 2

            elif frn == 7:  # I048/130 Plot Characteristics - Compound
                sub_fspec, new_offset = read_fspec(data, offset)
                offset = new_offset
                num_subfields = sum(1 for v in sub_fspec if v)
                offset += num_subfields

            elif frn == 8:  # I048/220 Aircraft Address
                result['icao'] = data[offset:offset+3].hex().upper()
                offset += 3

            elif frn == 9:  # I048/240 Aircraft ID
                offset += 6

            elif frn == 10:  # I048/250 Mode S MB Data
                rep = data[offset]
                offset += 1 + rep * 8

            elif frn == 11:  # I048/161 Track Number
                offset += 2

            elif frn == 12:  # I048/042 Cartesian Position
                offset += 4

            elif frn == 13:  # I048/200 Velocity Polar
                offset += 4

            elif frn == 14:  # I048/170 Track Status
                while offset < len(data):
                    b = data[offset]; offset += 1
                    if (b & 1) == 0: break

            elif frn == 15:  # I048/210 Track Quality
                offset += 4

            elif frn == 16:  # I048/030 Warning/Error
                warnings = []
                while offset < len(data):
                    b = data[offset]; offset += 1
                    we_code = (b >> 1) & 0x7F
                    warnings.append(we_code)
                    if (b & 1) == 0: break
                result['warning_codes'] = warnings

            elif frn == 17:  # I048/080 Mode 3/A Confidence
                offset += 2

            elif frn == 18:  # I048/100 Mode C Confidence
                offset += 4

            elif frn == 19:  # I048/110 Height 3D
                offset += 2

            elif frn == 20:  # I048/120 Doppler - Compound
                sub_fspec, new_offset = read_fspec(data, offset)
                offset = new_offset
                if len(sub_fspec) > 0 and sub_fspec[0]:
                    offset += 2  # CAL
                if len(sub_fspec) > 1 and sub_fspec[1]:
                    if offset < len(data):
                        rep = data[offset]
                        offset += 1 + rep * 6  # RDS

            elif frn == 21:  # I048/230 Comm/ACAS
                offset += 2

            elif frn >= 27:  # SP / RE - Explicit
                if offset < len(data):
                    sp_len = data[offset]
                    if frn == 27:
                        result['sp_raw'] = data[offset:offset+sp_len].hex()
                    offset += sp_len
    except Exception as e:
        result['parse_error'] = str(e)

    return result


WARNING_CODES = {
    0: "No definido",
    1: "Multipath Reply (MTR)",
    2: "Sidelobe Reply",
    3: "Split Plot",
    4: "Second Time Around Reply",
    5: "Angel",
    6: "Terrestrial Vehicle",
    7: "Fixed PSR Plot",
    8: "Slow PSR Plot",
    9: "Low Quality PSR Plot",
    10: "Phantom SSR Plot",
    11: "Non-Matching Mode 3/A",
    12: "Mode-C Abnormal",
    13: "Target in Clutter",
    14: "Max Doppler in Zero Filter",
    15: "Transponder Anomaly",
    16: "Duplicated/Illegal Mode S Address",
    17: "Mode S Error Correction",
    18: "Long Range Echo",
}

def analyze_azimuth_249(filepath, azimuth_center=249.7, az_margin=0.5):
    """Analiza todos los plots alrededor de un acimut específico en un PCAP."""
    print(f"\n{'='*60}")
    print(f"FILE: {os.path.basename(filepath)}")
    print(f"Analizando acimut {azimuth_center}° ± {az_margin}° (zona de interés)")
    print(f"{'='*60}")
    
    if not os.path.exists(filepath):
        print(f"  Archivo no encontrado: {filepath}")
        return

    f = open(filepath, 'rb')
    pcap = dpkt.pcap.Reader(f)
    
    plots_in_zone = []
    
    for ts, buf in pcap:
        try:
            eth = dpkt.ethernet.Ethernet(buf)
            if not isinstance(eth.data, dpkt.ip.IP): continue
            udp = eth.data.data
            if not isinstance(udp, dpkt.udp.UDP): continue
            data = udp.data
            if len(data) < 3: continue

            offset = 0
            while offset < len(data):
                if offset + 3 > len(data): break
                cat = data[offset]
                length = (data[offset+1] << 8) | data[offset+2]
                if length < 3 or offset + length > len(data): break

                if cat == 48:
                    rec = decode_cat48_raw(data, offset + 3, length)
                    theta = rec.get('theta')
                    if theta is not None:
                        diff = abs(theta - azimuth_center)
                        if diff > 180: diff = 360 - diff
                        if diff <= az_margin:
                            rec['_pcap_ts'] = ts
                            plots_in_zone.append(rec)

                offset += length
        except Exception:
            pass
    f.close()

    print(f"Total plots en zona ({azimuth_center}° ± {az_margin}°): {len(plots_in_zone)}")
    
    if not plots_in_zone:
        print("  Sin blancos en esa zona.")
        return
    
    # Ordenar por ToD para ver la secuencia temporal
    plots_in_zone.sort(key=lambda x: x.get('tod', 0))
    
    print(f"\n{'TOD':>10} | {'Rho(NM)':>8} | {'Theta(°)':>9} | {'Squawk':>7} | {'FL':>5} | {'Tipo':>10} | {'Warnings':>40}")
    print("-" * 105)
    
    for p in plots_in_zone[:60]:  # Mostrar hasta 60 plots
        tod = p.get('tod', 0)
        rho = p.get('rho', 0)
        theta = p.get('theta', 0)
        mode3a = p.get('mode3a', '----')
        fl = p.get('fl', '---')
        
        tipo = 'PSR' if p.get('typ_psr') and not p.get('typ_ssr') else \
               'SSR' if p.get('typ_ssr') and not p.get('typ_psr') else \
               'COM' if p.get('typ_combined') else '???'
        
        w_codes = p.get('warning_codes', [])
        warnings_str = ', '.join(WARNING_CODES.get(c, f"?{c}") for c in w_codes) if w_codes else ''
        
        fl_str = f"{fl:.0f}" if fl != '---' else '---'
        print(f"{tod:>10.3f} | {rho:>8.3f} | {theta:>9.4f} | {mode3a:>7} | {fl_str:>5} | {tipo:>10} | {warnings_str}")

    # Resumen de Squawks únicos en la zona
    squawks = [p.get('mode3a') for p in plots_in_zone if p.get('mode3a')]
    from collections import Counter
    sq_counts = Counter(squawks)
    print(f"\nSquawks en zona: {dict(sorted(sq_counts.items(), key=lambda x: -x[1]))}")

    # Resumen de Warning codes en la zona
    all_warnings = []
    for p in plots_in_zone:
        all_warnings.extend(p.get('warning_codes', []))
    w_counts = Counter(all_warnings)
    print(f"Warning codes en zona: { {WARNING_CODES.get(k, f'?{k}'): v for k, v in sorted(w_counts.items(), key=lambda x: -x[1])} }")

if __name__ == "__main__":
    pcaps = [
        'c:/documentos/decode_asterix/MTR_2026_04_17_17-28-16.pcap',
        'c:/documentos/decode_asterix/MTR_2026_04_16_16-28-16.pcap',
        'c:/documentos/decode_asterix/260429.pcap',
        'c:/documentos/decode_asterix/Martescordoba_radar2.pcap',
    ]
    for f in pcaps:
        analyze_azimuth_249(f)
