import struct
from typing import List, Dict, Any
from decoder.asterix_utils import read_fspec


def _skip_variable(payload: bytes, offset: int) -> int:
    while offset < len(payload):
        b = payload[offset]
        offset += 1
        if (b & 0x01) == 0:
            break
    return offset


def decode(payload: bytes, offset: int, block_length: int, category: int) -> List[Dict[str, Any]]:
    """
    Decodifica CAT002 (Legacy Monoradar Service Messages).

    Campos relevantes:
      FRN 1: I002/010 SAC/SIC (2B)
      FRN 2: I002/000 Message Type (1B)  1=North Mark, 2=Sector Change, 3=South Mark
      FRN 3: I002/020 Sector Number (1B) azimuth 360/256 deg/bit
      FRN 4: I002/030 Time of Day (3B)   1/128 s/bit
      FRN 5: I002/041 Antenna Rotation Period (2B) 1/128 s/bit
      FRN 6: I002/050 Station Config Status (variable FX)
      FRN 7: I002/060 Station Processing Mode (variable FX)
      FRN 8: I002/070 Message Count Values (repetitive 2B/item)
      FRN 9: I002/100 Generic Polar Window (8B)
      FRN10: I002/090 Truncated ToD (2B)
      FRN11: I002/080 Warning/Error (variable FX)
    """
    records = []
    end_offset = offset + block_length - 3

    uap_lengths = {
        1: 2,   # I002/010 SAC/SIC
        2: 1,   # I002/000 Message Type
        3: 1,   # I002/020 Sector Number
        4: 3,   # I002/030 Time of Day
        5: 2,   # I002/041 Antenna Rotation Period
        6: -1,  # I002/050 variable FX
        7: -1,  # I002/060 variable FX
        8: -2,  # I002/070 repetitive (2B items)
        9: 8,   # I002/100 Polar Window
        10: 2,  # I002/090 Truncated ToD
        11: -1, # I002/080 variable FX
    }

    while offset < end_offset:
        record = {'category': category, 'extra_data': {}}
        fspec, fspec_offset = read_fspec(payload, offset)
        if not fspec or not any(fspec):
            break
        offset = fspec_offset

        for frn_index, is_present in enumerate(fspec):
            frn = frn_index + 1
            if not is_present:
                continue
            try:
                if frn == 1:
                    record['sac'] = payload[offset]
                    record['sic'] = payload[offset + 1]
                elif frn == 2:
                    msg_type = payload[offset]
                    record['msg_type'] = msg_type
                    if msg_type == 1:
                        record['extra_data']['is_north_mark'] = True
                    elif msg_type == 2:
                        record['extra_data']['is_sector_change'] = True
                elif frn == 3:
                    sector = payload[offset]
                    record['sector_number'] = sector
                    record['azimuth'] = sector * (360.0 / 256.0)
                elif frn == 4:
                    tod_raw = struct.unpack('>I', b'\x00' + payload[offset:offset + 3])[0]
                    record['timestamp'] = tod_raw / 128.0
                elif frn == 5:
                    period_raw = struct.unpack('>H', payload[offset:offset + 2])[0]
                    period_s = period_raw / 128.0
                    record['rotation_period'] = period_s
                    if period_s > 0:
                        record['extra_data']['antenna_rpm'] = 60.0 / period_s

                length = uap_lengths.get(frn)
                if length is not None and length > 0:
                    offset += length
                elif length == -1:
                    offset = _skip_variable(payload, offset)
                elif length == -2:
                    if offset < len(payload):
                        rep = payload[offset]
                        offset += 1 + rep * 2
                # FRNs sin longitud definida (≥ 12): saltar 1 byte para no colgarse
                elif length is None and frn >= 12:
                    if offset < len(payload):
                        expl_len = payload[offset]
                        offset += expl_len if expl_len > 0 else 1
            except (IndexError, struct.error):
                break

        records.append(record)

    return records
