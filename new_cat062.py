def _decode_cat062(payload: bytes, offset: int, length: int) -> List[Dict[str, Any]]:
    """
    Decodifica CAT 062 (SDPS Track Messages) v1.18 según UAP:
    """
    records = []
    end_offset = offset + length - 3
    while offset < end_offset:
        try:
            start_offset = offset
            fspec, offset = read_fspec(payload, offset)
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
            
            # FRN 1 (fspec[0]): I062/010 Data Source Identifier (2B)
            if len(fspec) > 0 and fspec[0]:
                if offset + 2 > len(payload):
                    print(f"⚠️ [CAT 62] Offset fuera de límites intentando leer Data Source Identifier. Offset: {offset}, Payload len: {len(payload)}")
                    break
                record['sac'] = payload[offset]
                record['sic'] = payload[offset + 1]
                offset += 2
            
            # FRN 2 (fspec[1]): I062/015 Service Identification (1B)
            if len(fspec) > 1 and fspec[1]:
                if offset + 1 > len(payload):
                    print(f"⚠️ [CAT 62] Offset fuera de límites intentando leer Service Identification. Offset: {offset}, Payload len: {len(payload)}")
                    break
                record['extra_data']['service_id'] = payload[offset]
                offset += 1
            
            # FRN 3 (fspec[2]): I062/040 Track Number (2B) MANDATORY
            if len(fspec) > 2 and fspec[2]:
                if offset + 2 > len(payload):
                    print(f"⚠️ [CAT 62] Offset fuera de límites intentando leer Track Number. Offset: {offset}, Payload len: {len(payload)}")
                    break
                record['track_number'] = struct.unpack('>H', payload[offset:offset+2])[0]
                offset += 2
            
            # FRN 4 (fspec[3]): I062/060 Track Mode 3/A Code (2B)
            if len(fspec) > 3 and fspec[3]:
                if offset + 2 > len(payload):
                    print(f"⚠️ [CAT 62] Offset fuera de límites intentando leer Track Mode 3/A Code. Offset: {offset}, Payload len: {len(payload)}")
                    break
                raw_val = struct.unpack('>H', payload[offset:offset+2])[0]
                v_bit = (raw_val >> 15) & 1
                g_bit = (raw_val >> 14) & 1
                ch_bit = (raw_val >> 13) & 1
                mode_3a = raw_val & 0x0FFF
                record['mode_3a'] = mode_3a
                record['extra_data']['mode_3a_v'] = v_bit
                record['extra_data']['mode_3a_g'] = g_bit
                record['extra_data']['mode_3a_ch'] = ch_bit
                offset += 2
            
            # FRN 5 (fspec[4]): I062/070 Time of Track Information (3B) MANDATORY
            if len(fspec) > 4 and fspec[4]:
                if offset + 3 > len(payload):
                    print(f"⚠️ [CAT 62] Offset fuera de límites intentando leer Time of Track Information. Offset: {offset}, Payload len: {len(payload)}")
                    break
                tod_raw = struct.unpack('>I', b'\x00' + payload[offset:offset+3])[0]
                record['timestamp'] = tod_raw / 128.0
                offset += 3
            
            # FRN 6 (fspec[5]): I062/080 Track Status (Variable) MANDATORY
            if len(fspec) > 5 and fspec[5]:
                # Track Status has FX-bit extension pattern
                # First byte: MON, SPI, MRH, SRC[3bits], CNF, FX
                # Subsequent bytes follow until FX=0 in bit 1
                track_status_start = offset
                while offset < len(payload):
                    sb = payload[offset]
                    offset += 1
                    # Check specific status bits
                    if offset == track_status_start + 1:
                        # First byte: extract CNF bit (bit 2)
                        cnf_bit = (sb >> 1) & 1
                        record['extra_data']['cnf'] = cnf_bit  # 0=confirmed, 1=tentative
                        mon_bit = (sb >> 7) & 1
                        record['extra_data']['mon'] = mon_bit  # 0=multisensor, 1=monosensor
                    if (sb & 0x01) == 0:
                        break  # FX = 0, end of Track Status
            
            # FRN 7 (fspec[6]): I062/100 Calculated Track Position Cartesian (6B)
            if len(fspec) > 6 and fspec[6]:
                if offset + 6 > len(payload):
                    print(f"⚠️ [CAT 62] Offset fuera de límites intentando leer Calculated Track Position Cartesian. Offset: {offset}, Payload len: {len(payload)}")
                    break
                x_raw = int.from_bytes(payload[offset:offset+3], 'big', signed=True)
                y_raw = int.from_bytes(payload[offset+3:offset+6], 'big', signed=True)
                record['extra_data']['x_cartesian_m'] = x_raw * 0.5
                record['extra_data']['y_cartesian_m'] = y_raw * 0.5
                offset += 6
            
            # FRN 8 (fspec[7]): I062/105 Calculated Position WGS-84 (8B)
            if len(fspec) > 7 and fspec[7]:
                if offset + 8 > len(payload):
                    print(f"⚠️ [CAT 62] Offset fuera de límites intentando leer Calculated Position WGS-84. Offset: {offset}, Payload len: {len(payload)}")
                    break
                lat_raw, lon_raw = struct.unpack('>ii', payload[offset:offset+8])
                lat_deg = lat_raw * (180.0 / 33554432.0)  # LSB = 180/2^25
                lon_deg = lon_raw * (180.0 / 33554432.0)
                if -90 <= lat_deg <= 90 and -180 <= lon_deg <= 180:
                    record['latitude'] = lat_deg
                    record['longitude'] = lon_deg
                    record['valid_position'] = True
                offset += 8
            
            # FRN 9 (fspec[8]): I062/110 Mode 5 Data (Compound + FX extents)
            if len(fspec) > 8 and fspec[8]:
                if offset + 1 > len(payload):
                    print(f"⚠️ [CAT 62] Offset fuera de límites intentando leer Mode 5 Data. Offset: {offset}, Payload len: {len(payload)}")
                    break
                sub_byte = payload[offset]
                offset += 1
                # Parse compound subfields (simplified - skip to stay in sync)
                sub_field_present = sub_byte
                if sub_byte & 0x80:
                    offset += 1  # SUM
                if sub_byte & 0x40:
                    offset += 4  # PMN
                if sub_byte & 0x20:
                    offset += 6  # POS
                if sub_byte & 0x10:
                    offset += 2  # GA
                if sub_byte & 0x08:
                    offset += 2  # EM1
                if sub_byte & 0x04:
                    offset += 1  # TOS
                if sub_byte & 0x02:
                    offset += 1  # XP
                # Account for FX extensions in compound
                while (sub_byte & 0x01) and offset < len(payload):
                    sub_byte = payload[offset]
                    offset += 1
                    if sub_byte & 0x80: offset += 1
                    if sub_byte & 0x40: offset += 4
                    if sub_byte & 0x20: offset += 6
                    if sub_byte & 0x10: offset += 2
                    if sub_byte & 0x08: offset += 2
                    if sub_byte & 0x04: offset += 1
                    if sub_byte & 0x02: offset += 1
            
            # FRN 10 (fspec[9]): I062/120 Track Mode 2 Code (2B)
            if len(fspec) > 9 and fspec[9]:
                if offset + 2 > len(payload):
                    print(f"⚠️ [CAT 62] Offset fuera de límites intentando leer Track Mode 2 Code. Offset: {offset}, Payload len: {len(payload)}")
                    break
                offset += 2
            
            # FRN 11 (fspec[10]): I062/130 Calculated Track Geometric Altitude (2B)
            if len(fspec) > 10 and fspec[10]:
                if offset + 2 > len(payload):
                    print(f"⚠️ [CAT 62] Offset fuera de límites intentando leer Calculated Track Geometric Altitude. Offset: {offset}, Payload len: {len(payload)}")
                    break
                alt_raw = struct.unpack('>h', payload[offset:offset+2])[0]
                # LSB = 6.25 ft, range -1500 to 150000 ft
                altitude_ft = alt_raw * 6.25
                record['altitude'] = altitude_ft
                if record['flight_level'] is None:
                    record['flight_level'] = altitude_ft / 100.0
                offset += 2
            
            # FRN 12 (fspec[11]): I062/135 Calculated Track Barometric Altitude (2B)
            if len(fspec) > 11 and fspec[11]:
                if offset + 2 > len(payload):
                    print(f"⚠️ [CAT 62] Offset fuera de límites intentando leer Calculated Track Barometric Altitude. Offset: {offset}, Payload len: {len(payload)}")
                    break
                alt_raw = struct.unpack('>H', payload[offset:offset+2])[0]
                qnh_bit = (alt_raw >> 15) & 1
                baro_alt = (alt_raw & 0x7FFF)
                if baro_alt & 0x4000:
                    baro_alt -= 0x8000
                baro_ft = baro_alt * 25.0
                if record['altitude'] is None:
                    record['altitude'] = baro_ft
                if record['flight_level'] is None:
                    record['flight_level'] = baro_ft / 100.0
                offset += 2
            
            # FRN 13 (fspec[12]): I062/136 Measured Flight Level (2B)
            if len(fspec) > 12 and fspec[12]:
                if offset + 2 > len(payload):
                    print(f"⚠️ [CAT 62] Offset fuera de límites intentando leer Measured Flight Level. Offset: {offset}, Payload len: {len(payload)}")
                    break
                fl_raw = struct.unpack('>h', payload[offset:offset+2])[0]
                fl_value = fl_raw * 25.0 / 100.0  # LSB=25ft, convert to FL
                record['flight_level'] = fl_value
                if record['altitude'] is None:
                    record['altitude'] = fl_value * 100.0
                offset += 2
            
            # FRN 14 (fspec[13]): I062/185 Calculated Track Velocity Cartesian (4B)
            if len(fspec) > 13 and fspec[13]:
                if offset + 4 > len(payload):
                    print(f"⚠️ [CAT 62] Offset fuera de límites intentando leer Velocidad. Offset: {offset}, Payload len: {len(payload)}")
                    break
                vx_raw, vy_raw = struct.unpack('>hh', payload[offset:offset+4])
                vx = vx_raw * 0.25  # m/s
                vy = vy_raw * 0.25  # m/s
                # Convert Vx, Vy to ground speed and track angle
                ground_speed_ms = math.sqrt(vx*vx + vy*vy)
                track_angle_deg = math.degrees(math.atan2(vx, vy))
                if track_angle_deg < 0:
                    track_angle_deg += 360.0
                record['extra_data']['ground_speed_kts'] = ground_speed_ms * 1.94384  # m/s to knots
                record['extra_data']['track_angle'] = track_angle_deg
                record['extra_data']['vx'] = vx
                record['extra_data']['vy'] = vy
                offset += 4
            
            # FRN 15 (fspec[14]): I062/200 Mode of Movement (1B)
            if len(fspec) > 14 and fspec[14]:
                if offset + 1 > len(payload):
                    print(f"⚠️ [CAT 62] Offset fuera de límites intentando leer Mode of Movement. Offset: {offset}, Payload len: {len(payload)}")
                    break
                offset += 1
            
            # FRN 16 (fspec[15]): I062/210 Calculated Acceleration (2B)
            if len(fspec) > 15 and fspec[15]:
                if offset + 2 > len(payload):
                    print(f"⚠️ [CAT 62] Offset fuera de límites intentando leer Calculated Acceleration. Offset: {offset}, Payload len: {len(payload)}")
                    break
                offset += 2
            
            # FRN 17 (fspec[16]): I062/220 Calculated Rate of Climb/Descent (2B)
            if len(fspec) > 16 and fspec[16]:
                if offset + 2 > len(payload):
                    print(f"⚠️ [CAT 62] Offset fuera de límites intentando leer Calculated Rate of Climb/Descent. Offset: {offset}, Payload len: {len(payload)}")
                    break
                roc_raw = struct.unpack('>h', payload[offset:offset+2])[0]
                record['extra_data']['vertical_rate_ftmin'] = roc_raw * 6.25
                offset += 2
            
            # FRN 18 (fspec[17]): I062/245 Target Identification (7B)
            if len(fspec) > 17 and fspec[17]:
                if offset + 7 > len(payload):
                    print(f"⚠️ [CAT 62] Offset fuera de límites intentando leer Target Identification. Offset: {offset}, Payload len: {len(payload)}")
                    break
                sti = (payload[offset] >> 6) & 0x03  # STI bits (bits 7-6)
                sti_str = {0: "downlinked", 1: "not_downlinked", 
                           2: "reg_not_downlinked", 3: "invalid"}.get(sti, "unknown")
                record['callsign'] = _decode_callsign(payload[offset+1:offset+7])
                offset += 7
            
            # FRN 19 (fspec[18]): I062/270 Target Size and Orientation (Variable)
            if len(fspec) > 18 and fspec[18]:
                while offset < len(payload):
                    sb = payload[offset]
                    offset += 1
                    if (sb & 0x01) == 0:
                        break
            
            # FRN 20 (fspec[19]): I062/290 System Track Update Ages (Compound)
            if len(fspec) > 19 and fspec[19]:
                if offset + 1 > len(payload):
                    print(f"⚠️ [CAT 62] Offset fuera de límites intentando leer System Track Update Ages. Offset: {offset}, Payload len: {len(payload)}")
                    break
                sub_byte = payload[offset]
                offset += 1
                # Process FX-chain of the compound indicator
                while (sub_byte & 0x01) and offset < len(payload):
                    sub_byte = payload[offset]
                    offset += 1
                # Now process each age subfield (each 1-2 bytes)
                # TRK age (1B), PSR age (1B), SSR age (1B), MDS age (1B)
                # ADS age (2B), ES age (1B), VDL age (1B), etc.
                # Simplified: skip length of first indicator byte
                age_fields = payload[offset-1] if offset > 0 else 0
                # Count present subfields from the indicator
                present_fields = 0
                for bit_idx in range(7, 1, -1):
                    if (age_fields >> bit_idx) & 1:
                        present_fields += 1
                # Skip 1-2 bytes per age field (simplified: skip 1 byte each)
                for _ in range(present_fields):
                    if offset < len(payload):
                        offset += 1
            
            # FRN 21 (fspec[20]): I062/300 Track Mode 3/A Code (2B)
            if len(fspec) > 20 and fspec[20]:
                if offset + 2 > len(payload):
                    print(f"⚠️ [CAT 62] Offset fuera de límites intentando leer Track Mode 3/A Code (FRN 21). Offset: {offset}, Payload len: {len(payload)}")
                    break
                mode3a_val = struct.unpack('>H', payload[offset:offset+2])[0]
                squawk = mode3a_val & 0x0FFF
                if record['mode_3a'] is None:
                    record['mode_3a'] = squawk
                offset += 2
            
            # FRN 22 (fspec[21]): I062/380 Aircraft Derived Data (Variable)
            if len(fspec) > 21 and fspec[21]:
                # We first need to read fspec
                try:
                    sub_fspec, offset = read_fspec(payload, offset)
                except Exception:
                    print(f"⚠️ [CAT 62] Offset fuera de límites leyendo fspec en Aircraft Derived Data. Offset: {offset}, Payload len: {len(payload)}")
                    break
                sub_lengths = {
                    0: 3, 1: 6, 2: 2, 3: 2, 4: 2, 5: 2, 6: 2, 7: 2, 8: 2, 9: 2,
                    10: 2, 11: 2, 12: 2, 13: 2, 14: 1, 15: 1, 16: 1, 17: 2, 18: 1, 19: 1, 20: 8, 21: 1, 22: 1
                }
                for i in range(len(sub_fspec)):
                    if sub_fspec[i]:
                        if i == 0:
                            # Subfield #1: Aircraft Address (3 bytes)
                            if offset + 3 > len(payload):
                                print(f"⚠️ [CAT 62] Offset fuera de límites en Aircraft Address. Offset: {offset}")
                                break
                            val = struct.unpack('>I', b'\x00' + payload[offset:offset+3])[0]
                            record['mode_s'] = f"{val:06X}"
                            offset += 3
                        elif i == 1:
                            # Subfield #2: Aircraft Identification (6 bytes)
                            if offset + 6 > len(payload):
                                print(f"⚠️ [CAT 62] Offset fuera de límites en Aircraft Identification. Offset: {offset}")
                                break
                            offset += 6
                        elif i == 7:
                            # Subfield #8: Mode 3/A Code (2 bytes)
                            if offset + 2 > len(payload):
                                print(f"⚠️ [CAT 62] Offset fuera de límites en Mode 3/A Code. Offset: {offset}")
                                break
                            raw_val = struct.unpack('>H', payload[offset:offset+2])[0] & 0x0FFF
                            if record['mode_3a'] is None:
                                record['mode_3a'] = raw_val
                            offset += 2
                        elif i == 17:
                            # Subfield #18: Flight Level (2 bytes)
                            if offset + 2 > len(payload):
                                print(f"⚠️ [CAT 62] Offset fuera de límites en Flight Level. Offset: {offset}")
                                break
                            fl_raw = struct.unpack('>h', payload[offset:offset+2])[0]
                            record['flight_level'] = fl_raw / 4.0
                            offset += 2
                        elif i == 20:
                            # Subfield #21: Position in WGS-84 (8 bytes)
                            if offset + 8 <= len(payload):
                                lat_raw = int.from_bytes(payload[offset:offset+4], 'big', signed=True)
                                lon_raw = int.from_bytes(payload[offset+4:offset+8], 'big', signed=True)
                                lat_deg = lat_raw * (180.0 / 8388608.0)  # LSB = 180/2^23
                                lon_deg = lon_raw * (180.0 / 8388608.0)
                                if -90 <= lat_deg <= 90 and -180 <= lon_deg <= 180:
                                    record['latitude'] = lat_deg
                                    record['longitude'] = lon_deg
                                    record['valid_position'] = True
                                offset += 8
                            else:
                                print(f"⚠️ [CAT 62] Offset fuera de límites en Position WGS-84. Offset: {offset}")
                                break
                        else:
                            skip_len = sub_lengths.get(i, 1)
                            if offset + skip_len > len(payload):
                                print(f"⚠️ [CAT 62] Offset fuera de límites en Aircraft Derived Data. Offset: {offset}")
                                break
                            offset += skip_len
            
            # FRN 23 (fspec[22]): I062/390 Flight Plan Related Data (Compound)
            if len(fspec) > 22 and fspec[22]:
                if offset + 1 > len(payload):
                    print(f"⚠️ [CAT 62] Offset fuera de límites intentando leer Flight Plan Related Data. Offset: {offset}, Payload len: {len(payload)}")
                    break
                sub_byte = payload[offset]
                offset += 1
                # Simplified skip
                while (sub_byte & 0x01) and offset < len(payload):
                    sub_byte = payload[offset]
                    offset += 1
            
            # Record complete: add to results
            # Provide fallback SAC/SIC if missing
            if record['sac'] is None:
                record['sac'] = 0
            if record['sic'] is None:
                record['sic'] = 0
            
            # Ensure timestamp exists (fallback to 0)
            if record.get('timestamp') is None:
                record['timestamp'] = 0.0
            
            records.append(record)
            break
        except Exception as e:
            import traceback
            print(f"[ERROR CRÍTICO CAT 62] Fallo decodificando. Error: {e}")
            print(traceback.format_exc())
            break
    return records
