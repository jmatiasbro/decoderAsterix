import sys

with open('/mnt/c/documentos/decode_asterix/native_asterix.py', 'r') as f:
    content = f.read()

start_str = "def _decode_cat062(payload: bytes, offset: int, length: int) -> List[Dict[str, Any]]:"
end_str = "return records\ndef parse_payload"

start_idx = content.find(start_str)
end_idx = content.find(end_str, start_idx)

if start_idx == -1 or end_idx == -1:
    print("Could not find function")
    sys.exit(1)

new_cat062 = """def _decode_cat062(payload: bytes, offset: int, length: int) -> List[Dict[str, Any]]:
    records = []
    end_offset = offset + length - 3
    while offset < end_offset:
        try:
            start_offset = offset
            fspec, offset = read_fspec(payload, offset)
            record = {'category': 62, 'sac': None, 'sic': None, 'latitude': None, 'longitude': None, 'altitude': None, 'mode_3a': None, 'track_number': None, 'callsign': None, 'mode_s': None, 'valid_position': False, 'extra_data': {}}
            
            # 0: I062/010 Data Source Identifier
            if len(fspec) > 0 and fspec[0]:
                record['sac'], record['sic'] = payload[offset], payload[offset + 1]
                offset += 2
            # 1: SPARE
            if len(fspec) > 1 and fspec[1]: pass
            # 2: I062/015 Service Identification
            if len(fspec) > 2 and fspec[2]:
                record['extra_data']['service_id'] = payload[offset]
                offset += 1
            # 3: I062/070 Time of Track Information
            if len(fspec) > 3 and fspec[3]:
                tod_raw = struct.unpack('>I', b'\\x00' + payload[offset:offset+3])[0]
                record['timestamp'] = tod_raw / 128.0
                offset += 3
            # 4: I062/105 Calculated Position In WGS-84 Co-ordinates (8 bytes)
            if len(fspec) > 4 and fspec[4]:
                lat, lon = struct.unpack('>ii', payload[offset:offset+8])
                lat_deg = lat * (180.0 / 33554432.0)
                lon_deg = lon * (180.0 / 33554432.0)
                if -90 <= lat_deg <= 90 and -180 <= lon_deg <= 180:
                    record['latitude'] = lat_deg
                    record['longitude'] = lon_deg
                    record['valid_position'] = True
                offset += 8
            # 5: I062/100 Calculated Position In Cartesian Co-ordinates (6 bytes)
            if len(fspec) > 5 and fspec[5]:
                offset += 6
            # 6: I062/185 Calculated Track Velocity In Cartesian Co-ordinates (4 bytes)
            if len(fspec) > 6 and fspec[6]:
                offset += 4
            
            # Octet 2
            # 7: I062/210 Calculated Acceleration (2 bytes)
            if len(fspec) > 7 and fspec[7]:
                offset += 2
            # 8: I062/060 Track Status (Variable)
            if len(fspec) > 8 and fspec[8]:
                while (payload[offset] & 1) != 0: offset += 1
                offset += 1
            # 9: I062/245 Target Identification (7 bytes)
            if len(fspec) > 9 and fspec[9]:
                record['callsign'] = _decode_callsign(payload[offset+1:offset+7])
                offset += 7
            # 10: I062/380 Aircraft Derived Data (Variable)
            if len(fspec) > 10 and fspec[10]:
                sub_fspec, offset = read_fspec(payload, offset)
                sub_lengths = {
                    0: 3, 1: 6, 2: 2, 3: 2, 4: 2, 5: 2, 6: 2, 7: 2, 8: 2, 9: 2,
                    10: 2, 11: 2, 12: 2, 13: 2, 14: 1, 15: 1, 16: 1, 17: 2, 18: 1, 19: 1, 20: 8, 21: 1, 22: 1
                }
                for i in range(len(sub_fspec)):
                    if sub_fspec[i]:
                        if i == 0:
                            val = struct.unpack('>I', b'\\x00' + payload[offset:offset+3])[0]
                            record['mode_s'] = f"{val:06X}"
                            offset += 3
                        elif i == 1:
                            offset += 6
                        elif i == 7:
                            record['mode_3a'] = struct.unpack('>H', payload[offset:offset+2])[0] & 0x0FFF
                            offset += 2
                        elif i == 17:
                            record['flight_level'] = struct.unpack('>h', payload[offset:offset+2])[0] / 4.0
                            offset += 2
                        else:
                            offset += sub_lengths.get(i, 1)
            # 11: I062/040 Track Number (2 bytes)
            if len(fspec) > 11 and fspec[11]:
                record['track_number'] = struct.unpack('>H', payload[offset:offset+2])[0]
                offset += 2
            
            # Subfields complete. Breaking packet since we got everything for the AsterixPlot.
            records.append(record)
            break
        except Exception as e:
            import traceback
            print(f"[ERROR CRÍTICO CAT 62] Fallo decodificando. Error: {e}")
            break
    return records
"""

new_content = content[:start_idx] + new_cat062 + content[end_idx:]

with open('/mnt/c/documentos/decode_asterix/native_asterix.py', 'w') as f:
    f.write(new_content)
print("Patched native_asterix.py")
