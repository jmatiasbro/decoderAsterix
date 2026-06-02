import struct
from typing import List, Dict, Any
from decoder.asterix_utils import read_fspec

def _skip_variable_field(payload: bytes, offset: int) -> int:
    """Salta un campo de longitud variable leyendo sus bits FX."""
    while offset < len(payload):
        byte = payload[offset]
        offset += 1
        if (byte & 1) == 0:  # FX bit is 0
            break
    return offset

def decode(payload: bytes, offset: int, block_length: int, category: int) -> List[Dict[str, Any]]:
    """
    Decodifica un bloque de datos ASTERIX CAT034.
    """
    records = []
    end_offset = offset + block_length - 3

    # Longitudes de UAP de CAT034. -1 para variable, -2 para repetitivo, -3 para explícito
    uap_lengths = {
        1: 2,  # I034/010 Data Source Identifier
        2: 1,  # I034/000 Message Type
        3: 3,  # I034/030 Time of Day
        4: 1,  # I034/020 Sector Number
        5: 2,  # I034/041 Antenna Rotation Speed
        6: -1, # I034/050 System Configuration and Status (variable)
        7: -1, # I034/060 System Processing Mode (variable)
        8: -2, # I034/070 Message Count Values (repetitive)
        9: 8,  # I034/100 Generic Polar Window
        10: 1, # I034/110 Data Filter
        11: 8, # I034/120 3D POS (WGS-84 position)
        12: 2, # I034/090 Collimation Error
        13: -3, # RE
        14: -3  # SP
    }

    while offset < end_offset:
        plot = {'category': category, 'extra_data': {}}
        fspec, fspec_offset = read_fspec(payload, offset)
        if not fspec or not any(fspec):
            break
        offset = fspec_offset

        sac = None
        sic = None
        msg_type = None
        timestamp = None
        sector_number = None
        azimuth = None
        rotation_period = None

        for frn_index, is_present in enumerate(fspec):
            frn = frn_index + 1
            if not is_present:
                continue

            try:
                if frn == 1:  # I034/010 Data Source Identifier
                    sac = payload[offset]
                    sic = payload[offset + 1]
                    plot['sac'] = sac
                    plot['sic'] = sic
                elif frn == 2:  # I034/000 Message Type
                    msg_type = payload[offset]
                    plot['msg_type'] = msg_type
                    if msg_type == 1:
                        plot['extra_data']['is_north_mark'] = True
                elif frn == 3:  # I034/030 Time of Day
                    tod_raw = struct.unpack('>I', b'\x00' + payload[offset:offset + 3])[0]
                    timestamp = tod_raw * 0.0078125
                    plot['timestamp'] = timestamp
                elif frn == 4:  # I034/020 Sector Number
                    sector_number = payload[offset]
                    azimuth = sector_number * 1.40625
                    plot['sector_number'] = sector_number
                    plot['azimuth'] = azimuth
                elif frn == 5:  # I034/041 Antenna Rotation Speed
                    rot_s_raw = struct.unpack('>H', payload[offset:offset + 2])[0]
                    rotation_period = rot_s_raw * 0.0078125
                    plot['rotation_period'] = rotation_period
                    if rotation_period > 0:
                        # Convert period (seconds/rotation) to RPM (rotations/minute)
                        plot['extra_data']['antenna_rpm'] = 60.0 / rotation_period

                # Avanzar offset
                length = uap_lengths.get(frn)
                if length is not None and length > 0:
                    offset += length
                elif length == -1:  # variable
                    offset = _skip_variable_field(payload, offset)
                elif length == -2:  # repetitive (REP followed by 2-byte items)
                    rep = payload[offset]
                    offset += 1 + rep * 2
                elif length == -3:  # RE or SP (explicit, starts with length octet)
                    expl_len = payload[offset]
                    offset += expl_len
            except Exception as e:
                # En caso de error, avanzar el bloque y romper
                break

        records.append(plot)

    return records
