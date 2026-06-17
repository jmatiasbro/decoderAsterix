#!/usr/bin/env python3
"""
FIX CRÍTICO: Reescribe _decode_cat062 con el UAP correcto del XML.

El código actual tiene el mapeo FRN completamente desalineado.
"""

REWRITE = '''
def _decode_cat062(payload: bytes, offset: int, length: int) -> List[Dict[str, Any]]:
    """
    Decodifica CAT 062 (SDPS Track Messages) v1.18 según UAP del XML asterix_cat062_1_18.xml.
    
    UAP correcto:
      1:  I062/010 SAC/SIC (2B)
      2:  Spare
      3:  I062/015 Service ID (1B)
      4:  I062/070 ToT (3B)
      5:  I062/105 WGS-84 Pos (8B)
      6:  I062/100 Cartesian Pos (6B)
      7:  I062/185 Velocity (4B)     ← KEY: velocity es FRN 7!
      --- FX ---
      8:  I062/210 Acceleration (2B)
      9:  I062/060 Mode 3/A (2B)
      10: I062/245 Target ID (7B)
      11: I062/380 Aircraft Derived (1+)
      12: I062/040 Track Number (2B)
      13: I062/080 Track Status (1+)
      14: I062/290 Track Ages (1+)
      --- FX ---
      15: I062/200 Mode/Move (1B)
      16: I062/295 Track Data Ages (1+)
      17: I062/136 Measured FL (2B)
      18: I062/130 Geo Alt (2B)
      19: I062/135 Baro Alt (2B)
      20: I062/220 Climb/Descent (2B)
      21: I062/390 Flight Plan (1+)
      --- FX ---
      22: I062/270 Target Size (1+)
      23: I062/300 Fleet ID (1B)
      24: I062/110 Mode 5 Data (1+)
      25: I062/120 Mode 2 Code (2B)
      26: I062/510 Comp Track (3+)
      --- FX ---
      27: I062/500 Est Accuracies (1+)
      28: I062/340 Measured Info (1+)
      --- FX ---
      29-33: Spare
      34: RE (Explicit)
      35: SP (Explicit)
    """
    records = []
    end_offset = offset + length - 3
    while offset < end_offset:
        start_offset = offset
        record = {
            'category': 62,
            'sac': None, 'sic': None,
            'latitude': None, 'longitude': None,
            'altitude': None,
            'mode_3a': None,
            'track_number': None,
            'callsign': None,
            'mode_s': None,
            'flight_level': None,
            'valid_position': False,
            'extra_data': {}
        }
        current_frn = 0

        try:
            fspec, offset = read_fspec(payload, offset)
            
            # === FRN 1 (fspec[0]): I062/010 Data Source Identifier (2B) ===
            current_frn = 1
            if len(fspec) > 0 and fspec[0]:
                if offset + 2 > len(payload): raise IndexError("Buffer too small for I062/010")
                record['sac'] = payload[offset]
                record['sic'] = payload[offset + 1]
                offset += 2
            
            # === FRN 2 (fspec[1]): Spare ===
            current_frn = 2
            # No data - just recognized as present
            
            # === FRN 3 (fspec[2]): I062/015 Service Identification (1B) ===
            current_frn = 3
            if len(fspec) > 2 and fspec[2]:
                if offset + 1 > len(payload): raise IndexError("Buffer too small for I062/015")
                record['extra_data']['service_id'] = payload[offset]
                offset += 1
            
            # === FRN 4 (fspec[3]): I062/070 Time of Track Information (3B) ===
            current_frn = 4
            if len(fspec) > 3 and fspec[3]:
                if offset + 3 > len(payload): raise IndexError("Buffer too small for I062/070")
                tod_raw = struct.unpack('>I', b'\\x00' + payload[offset:offset+3])[0]
                record['timestamp'] = tod_raw / 128.0
                offset += 3
            
            # === FRN 5 (fspec[4]): I062/105 Calculated Position WGS-84 (8B) ===
            current_frn = 5
            if len(fspec) > 4 and fspec[4]:
                if offset + 8 > len(payload): raise IndexError("Buffer too small for I062/105")
                lat_raw, lon_raw = struct.unpack('>ii', payload[offset:offset+8])
                lat_deg = lat_raw * (180.0 / 33554432.0)
                lon_deg = lon_raw * (180.0 / 33554432.0)
                record['latitude'], record['longitude'] = lat_deg, lon_deg
                record['valid_position'] = True
                offset += 8
            
            # === FRN 6 (fspec[5]): I062/100 Calculated Track Position Cartesian (6B) ===
            current_frn = 6
            if len(fspec) > 5 and fspec[5]:
                if offset + 6 > len(payload): raise IndexError("Buffer too small for I062/100")
                x_raw = int.from_bytes(payload[offset:offset+3], 'big', signed=True)
                y_raw = int.from_bytes(payload[offset+3:offset+6], 'big', signed=True)
                record['extra_data']['x_cartesian_m'] = x_raw * 0.5
                record['extra_data']['y_cartesian_m'] = y_raw * 0.5
                offset += 6
            
            # === FRN 7 (fspec[6]): I062/185 Calculated Track Velocity Cartesian (4B) ===
            current_frn = 7
            if len(fspec) > 6 and fspec[6]:
                if offset + 4 > len(payload): raise IndexError("Buffer too small for I062/185")
                vx_raw, vy_raw = struct.unpack('>hh', payload[offset:offset+4])
                vx = vx_raw * 0.25
                vy = vy_raw * 0.25
                ground_speed_ms = math.sqrt(vx*vx + vy*vy)
                track_angle_deg = math.degrees(math.atan2(vx, vy))
                if track_angle_deg < 0: track_angle_deg += 360.0
                record['extra_data']['ground_speed_kts'] = ground_speed_ms * 1.94384
                record['extra_data']['track_angle'] = track_angle_deg
                offset += 4
            
            # === FRN 8 (fspec[7]): I062/210 Calculated Acceleration (2B) ===
            current_frn = 8
            if len(fspec) > 7 and fspec[7]:
                if offset + 2 > len(payload): raise IndexError("Buffer too small for I062/210")
                offset += 2
            
            # === FRN 9 (fspec[8]): I062/060 Track Mode 3/A Code (2B) ===
            current_frn = 9
            if len(fspec) > 8 and fspec[8]:
                if offset + 2 > len(payload): raise IndexError("Buffer too small for I062/060")
                raw_val = struct.unpack('>H', payload[offset:offset+2])[0]
                record['mode_3a'] = raw_val & 0x0FFF
                offset += 2
            
            # === FRN 10 (fspec[9]): I062/245 Target Identification (7B) ===
            current_frn = 10
            if len(fspec) > 9 and fspec[9]:
                if offset + 7 > len(payload): raise IndexError("Buffer too small for I062/245")
                record['callsign'] = _decode_callsign(payload[offset+1:offset+7])
                offset += 7
            
            # === FRN 11 (fspec[10]): I062/380 Aircraft Derived Data (Compound, 1+) ===
            current_frn = 11
            if len(fspec) > 10 and fspec[10]:
                if offset >= len(payload): raise IndexError("Buffer too small for I062/380 FSPEC")
                sub_fspec, offset = read_fspec(payload, offset)
                for i in range(len(sub_fspec)):
                    if not sub_fspec[i]:
                        continue
                    if i == 6:  # TIS - Variable (FX loop)
                        if offset >= len(payload): raise IndexError("Buffer too small for I062/380 TIS")
                        while offset < len(payload):
                            sb = payload[offset]
                            offset += 1
                            if (sb & 0x01) == 0: break
                    elif i == 7:  # TID - Repetitive (15B c/u)
                        if offset + 1 > len(payload): raise IndexError("Buffer too small for I062/380 TID rep")
                        rep = payload[offset]
                        offset += 1
                        if offset + rep * 15 > len(payload): raise IndexError(f"Buffer too small for I062/380 TID ({rep}x15B)")
                        offset += rep * 15
                    elif i == 24:  # MB - Mode S MB Data (Repetitive, 8B c/u)
                        if offset + 1 > len(payload): raise IndexError("Buffer too small for I062/380 MB rep")
                        rep = payload[offset]
                        offset += 1
                        if offset + rep * 8 > len(payload): raise IndexError(f"Buffer too small for I062/380 MB ({rep}x8B)")
                        offset += rep * 8
                    else:
                        fixed_lengths = {
                            0: 3, 1: 6, 2: 2, 3: 2, 4: 2, 5: 2,
                            8: 2, 9: 2, 10: 2, 11: 2, 12: 2,
                            13: 2, 14: 1, 15: 1, 16: 1, 17: 2,
                            18: 1, 19: 1, 20: 8, 21: 2, 22: 1,
                            25: 2, 26: 2, 27: 2,
                        }
                        skip_len = fixed_lengths.get(i, 1)
                        if offset + skip_len > len(payload):
                            raise IndexError(f"Buffer too small for I062/380 subfield {i+1} ({skip_len}B)")
                        offset += skip_len
            
            # === FRN 12 (fspec[11]): I062/040 Track Number (2B) ===
            current_frn = 12
            if len(fspec) > 11 and fspec[11]:
                if offset + 2 > len(payload): raise IndexError("Buffer too small for I062/040")
                record['track_number'] = struct.unpack('>H', payload[offset:offset+2])[0]
                offset += 2
            
            # === FRN 13 (fspec[12]): I062/080 Track Status (Variable, 1+) ===
            current_frn = 13
            if len(fspec) > 12 and fspec[12]:
                while offset < len(payload):
                    sb = payload[offset]
                    offset += 1
                    if (sb & 0x01) == 0: break
                if offset > len(payload): raise IndexError("Buffer too small for I062/080")
            
            # === FRN 14 (fspec[13]): I062/290 System Track Update Ages (Compound, 1+) ===
            current_frn = 14
            if len(fspec) > 13 and fspec[13]:
                if offset + 1 > len(payload): raise IndexError("Buffer too small for I062/290")
                sub_byte = payload[offset]
                indicator_start = offset
                offset += 1
                while (sub_byte & 0x01):
                    if offset >= len(payload): raise IndexError("Buffer too small for I062/290 FX")
                    sub_byte = payload[offset]
                    offset += 1
                indicator_end = offset
                num_fields = 0
                for i in range(indicator_start, indicator_end):
                    num_fields += bin(payload[i]).count('1', 1)
                if offset + num_fields > len(payload): raise IndexError("Buffer too small for I062/290 ages")
                offset += num_fields
            
            # === FRN 15 (fspec[14]): I062/200 Mode of Movement (1B) ===
            current_frn = 15
            if len(fspec) > 14 and fspec[14]:
                if offset + 1 > len(payload): raise IndexError("Buffer too small for I062/200")
                offset += 1
            
            # === FRN 16 (fspec[15]): I062/295 Track Data Ages (Compound, 1+) ===
            current_frn = 16
            if len(fspec) > 15 and fspec[15]:
                if offset + 1 > len(payload): raise IndexError("Buffer too small for I062/295")
                sub_byte = payload[offset]
                indicator_start = offset
                offset += 1
                while (sub_byte & 0x01):
                    if offset >= len(payload): raise IndexError("Buffer too small for I062/295 FX")
                    sub_byte = payload[offset]
                    offset += 1
                indicator_end = offset
                num_fields = 0
                for i in range(indicator_start, indicator_end):
                    num_fields += bin(payload[i]).count('1', 1)
                if offset + num_fields > len(payload): raise IndexError("Buffer too small for I062/295")
                offset += num_fields
            
            # === FRN 17 (fspec[16]): I062/136 Measured Flight Level (2B) ===
            current_frn = 17
            if len(fspec) > 16 and fspec[16]:
                if offset + 2 > len(payload): raise IndexError("Buffer too small for I062/136")
                fl_raw = struct.unpack('>h', payload[offset:offset+2])[0]
                record['flight_level'] = fl_raw * 0.25
                offset += 2
            
            # === FRN 18 (fspec[17]): I062/130 Calculated Track Geometric Altitude (2B) ===
            current_frn = 18
            if len(fspec) > 17 and fspec[17]:
                if offset + 2 > len(payload): raise IndexError("Buffer too small for I062/130")
                alt_raw = struct.unpack('>h', payload[offset:offset+2])[0]
                record['altitude'] = alt_raw * 6.25
                offset += 2
            
            # === FRN 19 (fspec[18]): I062/135 Calculated Track Barometric Altitude (2B) ===
            current_frn = 19
            if len(fspec) > 18 and fspec[18]:
                if offset + 2 > len(payload): raise IndexError("Buffer too small for I062/135")
                alt_raw = struct.unpack('>H', payload[offset:offset+2])[0]
                baro_alt = (alt_raw & 0x7FFF)
                if baro_alt & 0x4000: baro_alt -= 0x8000
                baro_ft = baro_alt * 25.0
                if record['altitude'] is None: record['altitude'] = baro_ft
                record['flight_level'] = baro_ft / 100.0
                offset += 2
            
            # === FRN 20 (fspec[19]): I062/220 Calculated Rate of Climb/Descent (2B) ===
            current_frn = 20
            if len(fspec) > 19 and fspec[19]:
                if offset + 2 > len(payload): raise IndexError("Buffer too small for I062/220")
                roc_raw = struct.unpack('>h', payload[offset:offset+2])[0]
                record['extra_data']['vertical_rate_ftmin'] = roc_raw * 6.25
                offset += 2
            
            # === FRN 21 (fspec[20]): I062/390 Flight Plan Related Data (Compound, 1+) ===
            current_frn = 21
            if len(fspec) > 20 and fspec[20]:
                if offset >= len(payload): raise IndexError("Buffer too small for I062/390")
                indicator_start = offset
                while offset < len(payload):
                    sb = payload[offset]
                    offset += 1
                    if (sb & 0x01) == 0: break
                if offset > len(payload): raise IndexError("Buffer too small for I062/390 FX")
                indicator_end = offset
                subfield_lengths = [2, 7, 4, 1, 4, 1, 4, 4, 3, 2, 2, -1, 6, 1, 7, 7, 2, 7]
                bit_idx = 0
                for byte_idx in range(indicator_start, indicator_end):
                    byte_val = payload[byte_idx]
                    for bit_pos in range(7, 0, -1):
                        if byte_val & (1 << bit_pos):
                            if bit_idx < len(subfield_lengths):
                                length = subfield_lengths[bit_idx]
                                if length == -1:  # TOD: Repetitive
                                    if offset + 1 > len(payload): raise IndexError("I062/390 TOD rep")
                                    rep = payload[offset]
                                    offset += 1
                                    if offset + rep * 4 > len(payload): raise IndexError(f"I062/390 TOD {rep}x4B")
                                    offset += rep * 4
                                else:
                                    if offset + length > len(payload): raise IndexError(f"I062/390 subfield {bit_idx} {length}B")
                                    offset += length
                            else:
                                if offset + 1 > len(payload): break
                                offset += 1
                        bit_idx += 1
            
            # === FRN 22 (fspec[21]): I062/270 Target Size and Orientation (Variable, 1+) ===
            current_frn = 22
            if len(fspec) > 21 and fspec[21]:
                while offset < len(payload):
                    sb = payload[offset]
                    offset += 1
                    if (sb & 0x01) == 0: break
                if offset > len(payload): raise IndexError("Buffer too small for I062/270")
            
            # === FRN 23 (fspec[22]): I062/300 Vehicle Fleet Identification (1B) ===
            current_frn = 23
            if len(fspec) > 22 and fspec[22]:
                if offset + 1 > len(payload): raise IndexError("Buffer too small for I062/300")
                offset += 1
            
            # === FRN 24 (fspec[23]): I062/110 Mode 5 Data (Compound, 1+) ===
            current_frn = 24
            if len(fspec) > 23 and fspec[23]:
                if offset + 1 > len(payload): raise IndexError("Buffer too small for I062/110")
                sub_byte = payload[offset]
                offset += 1
                if sub_byte & 0x80: offset += 1
                if sub_byte & 0x40: offset += 4
                if sub_byte & 0x20: offset += 6
                if sub_byte & 0x10: offset += 2
                if sub_byte & 0x08: offset += 2
                if sub_byte & 0x04: offset += 1
                if sub_byte & 0x02: offset += 1
                while sub_byte & 0x01:
                    if offset >= len(payload): raise IndexError("I062/110 FX")
                    sub_byte = payload[offset]
                    offset += 1
                    if sub_byte & 0x80: offset += 1
                    if sub_byte & 0x40: offset += 4
                    if sub_byte & 0x20: offset += 6
                    if sub_byte & 0x10: offset += 2
                    if sub_byte & 0x08: offset += 2
                    if sub_byte & 0x04: offset += 1
                    if sub_byte & 0x02: offset += 1
            
            # === FRN 25 (fspec[24]): I062/120 Track Mode 2 Code (2B) ===
            current_frn = 25
            if len(fspec) > 24 and fspec[24]:
                if offset + 2 > len(payload): raise IndexError("Buffer too small for I062/120")
                offset += 2
            
            # === FRN 26 (fspec[25]): I062/510 Composed Track Number (3+) ===
            current_frn = 26
            if len(fspec) > 25 and fspec[25]:
                if offset + 3 > len(payload): raise IndexError("Buffer too small for I062/510")
                # Variable con FX en bit 1 del 3er byte
                offset += 3
                while offset < len(payload):
                    # Check FX bit (bit 1 of last byte read)
                    fx_byte = payload[offset - 1]
                    if (fx_byte & 0x01) == 0: break
                    if offset + 3 > len(payload): raise IndexError("I062/510 FX")
                    offset += 3
            
            # === FRN 27 (fspec[26]): I062/500 Estimated Accuracies (Compound, 1+) ===
            current_frn = 27
            if len(fspec) > 26 and fspec[26]:
                if offset + 1 > len(payload): raise IndexError("Buffer too small for I062/500")
                sub_byte = payload[offset]
                indicator_start = offset
                offset += 1
                while (sub_byte & 0x01):
                    if offset >= len(payload): raise IndexError("I062/500 FX")
                    sub_byte = payload[offset]
                    offset += 1
                indicator_end = offset
                num_fields = 0
                for i in range(indicator_start, indicator_end):
                    num_fields += bin(payload[i]).count('1', 1)
                if offset + num_fields > len(payload): raise IndexError("I062/500 fields")
                offset += num_fields
            
            # === FRN 28 (fspec[27]): I062/340 Measured In DIF (Compound, 1+) ===
            current_frn = 28
            if len(fspec) > 27 and fspec[27]:
                if offset + 1 > len(payload): raise IndexError("Buffer too small for I062/340")
                sub_byte = payload[offset]
                indicator_start = offset
                offset += 1
                while (sub_byte & 0x01):
                    if offset >= len(payload): raise IndexError("I062/340 FX")
                    sub_byte = payload[offset]
                    offset += 1
                indicator_end = offset
                num_fields = 0
                for i in range(indicator_start, indicator_end):
                    num_fields += bin(payload[i]).count('1', 1)
                if offset + num_fields > len(payload): raise IndexError("I062/340 fields")
                offset += num_fields
            
            # === FRN 29-33 (fspec[28]..fspec[32]): Spare - no data ===
            for frn_idx_inner in range(28, 33):
                if len(fspec) > frn_idx_inner and fspec[frn_idx_inner]:
                    pass
            
            # === FRN 34 (fspec[33]): RE - Reserved Expansion Field (Explicit) ===
            current_frn = 34
            if len(fspec) > 33 and fspec[33]:
                if offset >= len(payload): raise IndexError("Buffer too small for RE")
                re_len = payload[offset]
                if re_len < 1: raise IndexError(f"Invalid RE len: {re_len}")
                if offset + re_len > len(payload): raise IndexError(f"RE {re_len}B exceeds payload")
                offset += re_len
            
            # === FRN 35 (fspec[34]): SP - Special Purpose Field (Explicit) ===
            current_frn = 35
            if len(fspec) > 34 and fspec[34]:
                if offset >= len(payload): raise IndexError("Buffer too small for SP")
                sp_len = payload[offset]
                if sp_len < 1: raise IndexError(f"Invalid SP len: {sp_len}")
                if offset + sp_len > len(payload): raise IndexError(f"SP {sp_len}B exceeds payload")
                offset += sp_len
            
            records.append(record)
            break

        except (struct.error, IndexError) as e:
            print(f"⚠️ [CAT 62] Offset Drift detectado en FRN {current_frn}. Error: {e}")
            records.append(record)
            break

        if offset == start_offset:
            break

    return records
'''

if __name__ == '__main__':
    print("FIX GENERADO. Copiar el bloque de reemplazo al archivo native_asterix.py")
    print(REWRITE)
