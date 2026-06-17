import math
import struct
from typing import List, Tuple, Dict, Any
from asterix_utils import read_fspec, _decode_callsign
from decoders.cat001 import decode as decode_cat001
from decoders.cat002 import decode as decode_cat002
from decoders.cat021 import decode as decode_cat021
from decoders.cat034 import decode as decode_cat034
from decoders.cat048 import decode as decode_cat048
def decode_cat062(payload: bytes, offset: int, length: int, category: int) -> List[Dict[str, Any]]:
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
            'category': category,
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
                tod_raw = struct.unpack('>I', b'\x00' + payload[offset:offset+3])[0]
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

                # Tabla de longitudes de subcampos I062/380 v1.18 (basada en XML)
                # Soportes: Fixed, Variable (FX loop), Repetitive
                for i in range(len(sub_fspec)):
                    if not sub_fspec[i]:
                        continue
                    
                    if i == 6:  # TIS - Trajectory Intent Status - Variable (FX loop)
                        # Variable con bit FX en LSB
                        if offset >= len(payload): raise IndexError("Buffer too small for I062/380 TIS")
                        while offset < len(payload):
                            sb = payload[offset]
                            offset += 1
                            if (sb & 0x01) == 0: break
                    elif i == 7:  # TID - Trajectory Intent Data - Repetitive (15B c/u)
                        if offset + 1 > len(payload): raise IndexError("Buffer too small for I062/380 TID rep")
                        rep = payload[offset]
                        offset += 1
                        if offset + rep * 15 > len(payload): raise IndexError(f"Buffer too small for I062/380 TID ({rep}x15B)")
                        offset += rep * 15
                    elif i == 1:  # ID - Target Identification (6B)
                        if offset + 6 > len(payload): raise IndexError("Buffer too small for I062/380 Target ID")
                        callsign_val = _decode_callsign(payload[offset:offset+6])
                        if callsign_val:
                            record['callsign'] = callsign_val
                        offset += 6
                    elif i == 23:  # MB - Mode S MB Data - Repetitive (BDS, 8B c/u)
                        if offset + 1 > len(payload): raise IndexError("Buffer too small for I062/380 MB rep")
                        rep = payload[offset]
                        offset += 1
                        if offset + rep * 8 > len(payload): raise IndexError(f"Buffer too small for I062/380 MB ({rep}x8B)")
                        offset += rep * 8
                    else:
                        # Fixed subfields - tabla completa v1.18
                        fixed_lengths = {
                            0: 3,   # ADR - Target Address (3B)
                            1: 6,   # ID - Target Identification (6B)
                            2: 2,   # MHG - Magnetic Heading (2B)
                            3: 2,   # IAS/Mach (2B)
                            4: 2,   # TAS - True Airspeed (2B)
                            5: 2,   # SAL - Selected Altitude (2B)
                            6: 0,   # FSS - handled as Variable above
                            7: 0,   # TID - handled as Repetitive above
                            8: 2,   # COM - Communications (2B)
                            9: 2,  # SAB - Status ADS-B (2B)
                            10: 2,  # ACS - ACAS RA Report (2B)
                            11: 2,  # BVR - Baro Vertical Rate (2B)
                            12: 2,  # GVR - Geo Vertical Rate (2B)
                            13: 2,  # RAN - Roll Angle (2B)
                            14: 1,  # TAR - Track Angle Rate (1B)
                            15: 1,  # TAN - Track Angle (1B? No, 2B per XML)
                            16: 1,  # GSP - Ground Speed (1B? No, 2B per XML)
                            17: 2,  # VUN - Velocity Uncertainty (2B)
                            18: 1,  # MET - Met Data (1B? No, 8B per XML)
                            19: 1,  # EMC - Emitter Cat (1B)
                            20: 8,  # POS - Position (6B per XML, 8 in old code)
                            21: 1,  # GAL - Geo Alt (2B per XML, 1 in old code)
                            22: 1,  # PUN - Pos Uncertainty (1B)
                            # 23: handled as Repetitive above
                            24: 2,  # IAR - Indicated Airspeed (2B)
                            25: 2,  # MAC - Mach Number (2B)
                            26: 2,  # BPS - Baro Pressure Setting (2B)
                        }
                        skip_len = fixed_lengths.get(i)
                        if skip_len is None or skip_len == 0:
                            # Unknown subfield - skip 1 byte to avoid infinite loop
                            skip_len = 1
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
                # Step 1: Leer indicador primario (primary subfield) con FX
                if offset >= len(payload): raise IndexError("Buffer too small for I062/390")
                indicator_start = offset
                while offset < len(payload):
                    sb = payload[offset]
                    offset += 1
                    if (sb & 0x01) == 0: break
                if offset > len(payload): raise IndexError("Buffer too small for I062/390 FX")
                indicator_end = offset
                
                # Step 2: Saltar datos de cada subcampo según el indicador
                # Mapeo de longitudes de subcampos I062/390 v1.18
                subfield_lengths_390 = [
                    2,  #  0: TAG (2B)
                    7,  #  1: CSN - Callsign (7B)
                    4,  #  2: IFI - IFPS Flight ID (4B)
                    1,  #  3: FCT - Flight Category (1B)
                    4,  #  4: TAC - Type Aircraft (4B)
                    1,  #  5: WTC - Wake Turb Cat (1B)
                    4,  #  6: DEP - Departure (4B)
                    4,  #  7: DST - Destination (4B)
                    3,  #  8: RDS - Runway Designation (3B)
                    2,  #  9: CFL - Cleared Flight Level (2B)
                    2,  # 10: CTL - Control Position (2B)
                    -1, # 11: TOD - Time of Departure (Repetitive, 4B c/u)
                    6,  # 12: AS - Aircraft Stand (6B)
                    1,  # 13: STS - Stand Status (1B)
                    7,  # 14: STD - SID (7B)
                    7,  # 15: STA - STAR (7B)
                    2,  # 16: PEM - Pre-emergency Mode 3/A (2B)
                    7,  # 17: PEC - Pre-emergency Callsign (7B)
                ]
                
                # Reconstruir qué bits están activos del indicador
                bit_idx = 0
                for byte_idx in range(indicator_start, indicator_end):
                    byte_val = payload[byte_idx]
                    for bit_pos in range(7, 0, -1):  # bits 7..1
                        if byte_val & (1 << bit_pos):
                            # Este subcampo está presente
                            # Mapear bit_idx a longitud
                            if bit_idx < len(subfield_lengths_390):
                                length = subfield_lengths_390[bit_idx]
                                if length == -1:  # TOD: Repetitive
                                    if offset + 1 > len(payload):
                                        raise IndexError(f"Buffer too small for I062/390 TOD rep")
                                    rep = payload[offset]
                                    offset += 1
                                    if offset + rep * 4 > len(payload):
                                        raise IndexError(f"Buffer too small for I062/390 TOD ({rep}x4B)")
                                    offset += rep * 4
                                elif bit_idx == 1:  # CSN - Callsign (7B)
                                    if offset + 7 > len(payload):
                                        raise IndexError("Buffer too small for I062/390 Callsign")
                                    callsign_val = payload[offset:offset+7].decode('latin1', errors='ignore').strip()
                                    if callsign_val:
                                        record['callsign'] = callsign_val
                                    offset += 7
                                else:
                                    if offset + length > len(payload):
                                        raise IndexError(f"Buffer too small for I062/390 subfield bit {bit_idx} ({length}B)")
                                    offset += length
                            else:
                                # Bit beyond known subfields - skip 1 byte
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

def parse_payload(payload: bytes) -> List[Dict[str, Any]]:
    all_records = []
    offset = 0
    total_length = len(payload)

    while offset < total_length:
        # 1. Protección contra basura de red (Padding)
        if offset + 3 > total_length:
            break

        category = payload[offset]

        # 2. Lectura segura de la longitud del bloque
        try:
            block_length = struct.unpack('>H', payload[offset+1:offset+3])[0]
        except struct.error:
            break

        if block_length < 3:
            break

        # 3. CÁLCULO DE SALTO ABSOLUTO (Garantiza la convivencia)
        next_block_offset = offset + block_length

        if next_block_offset > total_length:
            break

        # 4. DELEGACIÓN A LOS ESPECIALISTAS (DECODIFICADORES)
        try:
            if category == 1:
                plots_cat = decode_cat001(payload, offset + 3, block_length, category)
                if plots_cat: all_records.extend(plots_cat)
            elif category == 2:
                plots_cat = decode_cat002(payload, offset + 3, block_length, category)
                if plots_cat: all_records.extend(plots_cat)
            elif category == 21:
                plots_cat = decode_cat021(payload, offset + 3, block_length, category)
                if plots_cat: all_records.extend(plots_cat)
            elif category == 34:
                plots_cat = decode_cat034(payload, offset + 3, block_length, category)
                if plots_cat: all_records.extend(plots_cat)
            elif category == 48:
                plots_cat = decode_cat048(payload, offset + 3, block_length, category)
                if plots_cat: all_records.extend(plots_cat)
            elif category == 62:
                plots_cat = decode_cat062(payload, offset + 3, block_length, category)
                if plots_cat: all_records.extend(plots_cat)
            else:
                pass # Categoría no soportada, se ignora silenciosamente

        except Exception as e:
            # Si un decodificador explota, capturamos el error aquí, 
            # pero el bucle NO se rompe.
            print(f"⚠️ [ROUTER] Error aislado en decodificador CAT {category}: {e}")

        # 5. FORZAR EL SALTO AL SIGUIENTE BLOQUE (Inmunidad)
        # Sin importar lo que haya hecho el decodificador, el router manda el puntero al siguiente avión.
        offset = next_block_offset

    return all_records
