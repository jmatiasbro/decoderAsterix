import struct
from typing import List, Dict, Any
from decoder.asterix_utils import read_fspec


def _skip_variable_field(payload: bytes, offset: int) -> int:
    """Salta un campo de longitud variable leyendo sus bits FX."""
    while offset < len(payload):
        byte = payload[offset]
        offset += 1
        if (byte & 1) == 0:
            break
    return offset


# Mapeo FRN → código de Item para el inspector (UAP EUROCONTROL CAT065 ed. 1.4)
FRN_ITEM_65 = {
    1: "I065/010",
    2: "I065/000",
    3: "I065/015",
    4: "I065/030",
    5: "I065/020",
    6: "I065/040",
    7: "I065/050",
    13: "RE",
    14: "SP",
}

# I065/000 Message Type
MSG_TYPE = {1: "SDPS Status", 2: "End of Batch", 3: "Service Status Report"}

# I065/050 Service Status Report
SERVICE_REPORT = {
    1: "Service degradation", 2: "Service degradation ended",
    3: "Main radar out of service", 4: "Service interrupted by the operator",
    5: "Service interrupted due to contingency",
    6: "Ready for service restart after contingency",
    7: "Service ended by the operator", 8: "Failure of user main radar",
    9: "Service restarted by the operator", 10: "Main radar becoming operational",
    11: "Main radar becoming degraded",
    12: "Service continuity interrupted due to disconnection with adjacent unit",
    13: "Service continuity restarted", 14: "Service synchronised on backup radar",
    15: "Service synchronised on main radar",
    16: "Main and backup radar, if any, failed",
}

NOGO = {0: "Operational", 1: "Degraded", 2: "Not currently connected", 3: "Unknown"}
PSS = {0: "Not applicable", 1: "SDPS-1 selected", 2: "SDPS-2 selected", 3: "SDPS-3 selected"}


def decode(payload: bytes, offset: int, block_length: int, category: int, record_offsets=None) -> List[Dict[str, Any]]:
    """Decodifica un bloque ASTERIX CAT065 (SDPS Service Status Reports)."""
    records = []
    end_offset = offset + block_length - 3

    # Longitudes de UAP. -1 variable, -2 repetitivo, -3 explícito (RE/SP).
    uap_lengths = {
        1: 2,   # I065/010 Data Source Identifier
        2: 1,   # I065/000 Message Type
        3: 1,   # I065/015 Service Identification
        4: 3,   # I065/030 Time of Message
        5: 1,   # I065/020 Batch Number
        6: 1,   # I065/040 SDPS Configuration and Status
        7: 1,   # I065/050 Service Status Report
        13: -3,  # RE
        14: -3,  # SP
    }

    _rec_idx = -1
    while offset < end_offset:
        _rec_idx += 1
        plot = {'category': category, 'extra_data': {}}
        fspec, fspec_offset = read_fspec(payload, offset)
        if not fspec or not any(fspec):
            break
        offset = fspec_offset

        for frn_index, is_present in enumerate(fspec):
            frn = frn_index + 1
            if not is_present:
                continue

            _ofs_ini = offset
            try:
                if frn == 1:  # I065/010 Data Source Identifier
                    plot['sac'] = payload[offset]
                    plot['sic'] = payload[offset + 1]
                elif frn == 2:  # I065/000 Message Type
                    mt = payload[offset]
                    plot['msg_type'] = mt
                    plot['extra_data']['message_type'] = MSG_TYPE.get(mt, f"Unknown ({mt})")
                elif frn == 3:  # I065/015 Service Identification
                    plot['service_id'] = payload[offset]
                    plot['extra_data']['service_id'] = payload[offset]
                elif frn == 4:  # I065/030 Time of Message (LSB = 1/128 s)
                    tod_raw = struct.unpack('>I', b'\x00' + payload[offset:offset + 3])[0]
                    plot['timestamp'] = tod_raw * 0.0078125
                elif frn == 5:  # I065/020 Batch Number
                    plot['batch_number'] = payload[offset]
                    plot['extra_data']['batch_number'] = payload[offset]
                elif frn == 6:  # I065/040 SDPS Configuration and Status
                    b = payload[offset]
                    nogo = (b >> 6) & 0x03
                    ovl = (b >> 5) & 0x01
                    tsv = (b >> 4) & 0x01
                    pss = (b >> 2) & 0x03
                    sttn = (b >> 1) & 0x01
                    plot['sdps_nogo'] = nogo
                    plot['extra_data'].update({
                        'sdps_nogo': NOGO.get(nogo, nogo),
                        'sdps_overload': bool(ovl),
                        'sdps_time_invalid': bool(tsv),
                        'sdps_pss': PSS.get(pss, pss),
                        'sdps_track_renumber': sttn,
                    })
                elif frn == 7:  # I065/050 Service Status Report
                    rep = payload[offset]
                    plot['service_report'] = rep
                    plot['extra_data']['service_report'] = SERVICE_REPORT.get(rep, f"Unknown ({rep})")

                # Avanzar offset
                length = uap_lengths.get(frn)
                if length is not None and length > 0:
                    offset += length
                elif length == -1:
                    offset = _skip_variable_field(payload, offset)
                elif length == -2:
                    rep = payload[offset]
                    offset += 1 + rep * 2
                elif length == -3:  # RE / SP (explícito: 1er octeto = longitud incl. sí mismo)
                    expl_len = payload[offset]
                    offset += expl_len if expl_len > 0 else 1
                else:
                    # FRN sin asignación en el UAP (spare): no se puede avanzar con seguridad
                    break

                if record_offsets is not None:
                    record_offsets.append(
                        (_rec_idx, FRN_ITEM_65.get(frn, f"FRN{frn}"), _ofs_ini, offset))

            except Exception:
                break

        records.append(plot)

    return records
