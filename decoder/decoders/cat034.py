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

# Mapeo FRN → código de Item para el inspector
FRN_ITEM_34 = {
    1: "I034/010",
    2: "I034/000",
    3: "I034/030",
    4: "I034/020",
    5: "I034/041",
    6: "I034/050",
    7: "I034/060",
    8: "I034/070",
    9: "I034/100",
    10: "I034/110",
    11: "I034/120",
    12: "I034/090",
    13: "RE",
    14: "SP"
}

def decode(payload: bytes, offset: int, block_length: int, category: int, record_offsets=None) -> List[Dict[str, Any]]:
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

    _rec_idx = -1
    while offset < end_offset:
        _rec_idx += 1
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

            _ofs_ini = offset
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
                elif frn == 6:  # I034/050 System Configuration and Status
                    status_byte = payload[offset]
                    plot['com_fault'] = bool(status_byte & 0x80)
                    plot['ext_fault'] = bool(status_byte & 0x40)
                    plot['ant_fault'] = bool(status_byte & 0x20)
                    plot['channel_ab'] = "Channel A" if (status_byte & 0x10) else "Channel B"

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

                if record_offsets is not None:
                    record_offsets.append(
                        (_rec_idx, FRN_ITEM_34.get(frn, f"FRN{frn}"), _ofs_ini, offset))

            except Exception as e:
                # En caso de error, avanzar el bloque y romper
                break

        records.append(plot)

    return records
