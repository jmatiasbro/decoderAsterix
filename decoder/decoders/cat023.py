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

FRN_ITEM_23 = {
    1: "I023/010",
    2: "I023/020",
    3: "RE",
    4: "SP"
}

def decode(payload: bytes, offset: int, block_length: int, category: int, record_offsets=None) -> List[Dict[str, Any]]:
    """
    Decodifica un bloque de datos ASTERIX CAT023 (System Monitoring Messages).
    """
    records = []
    end_offset = offset + block_length - 3

    # Longitudes de UAP de CAT023. -1 para variable, -2 para repetitivo, -3 para explícito
    uap_lengths = {
        1: 2,  # I023/010 Data Source Identifier
        2: 1,  # I023/020 System Status
        3: -3, # RE
        4: -3  # SP
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
        system_state = None
        ups_active = None

        for frn_index, is_present in enumerate(fspec):
            frn = frn_index + 1
            if not is_present:
                continue

            _ofs_ini = offset
            try:
                if frn == 1:  # I023/010 Data Source Identifier
                    sac = payload[offset]
                    sic = payload[offset + 1]
                    plot['sac'] = sac
                    plot['sic'] = sic
                elif frn == 2:  # I023/020 System Status
                    sys_status = payload[offset]
                    system_state = (sys_status >> 6) & 0x03
                    ups_active = bool(sys_status & 0x04)
                    plot['system_state'] = system_state
                    plot['ups_active'] = ups_active
                    plot['extra_data']['system_state'] = system_state
                    plot['extra_data']['ups_active'] = ups_active

                # Avanzar offset
                length = uap_lengths.get(frn)
                if length is not None and length > 0:
                    offset += length
                elif length == -1:  # variable
                    offset = _skip_variable_field(payload, offset)
                elif length == -2:  # repetitive (REP)
                    rep = payload[offset]
                    offset += 1 + rep * 2
                elif length == -3:  # RE or SP
                    expl_len = payload[offset]
                    offset += expl_len

                if record_offsets is not None:
                    record_offsets.append(
                        (_rec_idx, FRN_ITEM_23.get(frn, f"FRN{frn}"), _ofs_ini, offset))

            except Exception as e:
                break

        records.append(plot)

    return records
