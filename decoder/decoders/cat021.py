import struct
from typing import List, Dict, Any

from decoder.asterix_utils import read_fspec, _decode_callsign


def _skip_variable_field(payload: bytes, offset: int) -> int:
    """Salta un campo de longitud variable leyendo sus bits FX."""
    while offset < len(payload):
        byte = payload[offset]
        offset += 1
        if (byte & 1) == 0:  # FX bit is 0
            break
    return offset
def decode_cat021_v026(payload: bytes, offset: int, block_length: int, category: int) -> List[Dict[str, Any]]:
    """
    Decodifica un bloque de datos ASTERIX CAT021 v0.26 (ADS-B heredado para Paraná 226/103).
    """
    plots_locales = []
    cat = category
    end_offset = offset + block_length - 3

    # Longitudes de campos para v0.26 (Eurocontrol ASTERIX CAT 021 Edición 0.26)
    uap_lengths_v026 = {
        1: 2,   # 010 (Data Source Identifier)
        2: 2,   # 040 (Target Report Descriptor)
        3: 3,   # 030 (Time of Transmission)
        4: 8,   # 130 (WGS-84 position)
        5: 3,   # 080 (Target Address)
        6: 2,   # 140 (Geometric Altitude)
        7: 2,   # 090 (Figure of Merit)
        8: 1,   # 210 (Link Technology)
        9: 2,   # 230 (Roll Angle)
        10: 2,  # 145 (Flight Level)
        11: 2,  # 150 (Air Speed)
        12: 2,  # 151 (True Air Speed)
        13: 2,  # 152 (Magnetic Heading)
        14: 2,  # 155 (Barometric Vertical Rate)
        15: 2,  # 157 (Geometric Vertical Rate)
        16: 4,  # 160 (Ground Vector)
        17: -1, # 165 (Rate of Turn) - variable
        18: 6,  # 170 (Target Identification)
        19: 1,  # 095 (Velocity Accuracy)
        20: 1,  # 032 (Time of Day Accuracy)
        21: 1,  # 200 (Emitter Category)
        22: 1,  # 020 (Sector/Emitter Category)
        23: -1, # 220 (Met Information) - variable
        24: 2,  # 146 (Intermediate State Flight Level)
        25: 2,  # 148 (Final State Flight Level)
        26: -1, # 110 (Trajectory Intent) - variable
        27: 2,  # 070 (Mode 3/A Code)
        28: 1,  # 131 (Signal Amplitude)
        34: 19, # RE (Reserved Expansion Field)
        35: -2, # SP (Special Purpose Field)
    }

    while offset < end_offset:
        offset_previo = offset
        plot = {'category': cat}
        plot_salvado = False

        fspec, fspec_offset = read_fspec(payload, offset)
        if not fspec or not any(fspec):
            break
        offset = fspec_offset

        for frn_index, is_present in enumerate(fspec):
            frn = frn_index + 1
            if not is_present:
                continue

            try:
                # Decodificación de campos principales v0.26
                if frn == 1:  # I021/010 Data Source Identifier
                    plot['sac'] = payload[offset]
                    plot['sic'] = payload[offset + 1]
                elif frn == 3:  # I021/030 Time of Message Transmission
                    tod_raw = struct.unpack('>I', b'\x00' + payload[offset:offset + 3])[0]
                    plot['timestamp'] = tod_raw / 128.0
                elif frn == 4:  # I021/130 Position in WGS-84 (v0.26: 8 bytes)
                    lat_raw = int.from_bytes(payload[offset:offset+4], 'big', signed=True)
                    lon_raw = int.from_bytes(payload[offset+4:offset+8], 'big', signed=True)
                    plot['latitude'] = lat_raw * 180.0 / (2**25)
                    plot['longitude'] = lon_raw * 180.0 / (2**25)
                elif frn == 5:  # I021/080 Target Address
                    plot['mode_s'] = payload[offset:offset+3].hex().upper()
                elif frn == 10: # I021/145 Flight Level
                    fl_raw = struct.unpack('>h', payload[offset:offset+2])[0]
                    if fl_raw != -32768:
                        fl_val = fl_raw * 0.25
                        if fl_val >= 0.0:
                            plot['flight_level'] = fl_val
                elif frn == 18: # I021/170 Target Identification
                    plot['callsign'] = _decode_callsign(payload[offset:offset+6])
                elif frn == 27: # I021/070 Mode-3/A Code
                    mode3a_raw = struct.unpack('>H', payload[offset:offset + 2])[0]
                    plot['mode_3a'] = mode3a_raw & 0x0FFF

                # Avance del offset
                length_code = uap_lengths_v026.get(frn)

                if length_code is None:
                    if plot and ('latitude' in plot or 'mode_s' in plot or 'callsign' in plot):
                        plot['category'] = 21
                        plot['partial_decode'] = True
                        plots_locales.append(plot)
                        plot_salvado = True
                    offset = end_offset
                    break
                elif length_code > 0:
                    offset += length_code
                elif length_code == -1:
                    offset = _skip_variable_field(payload, offset)
                elif length_code == -2:
                    if offset < len(payload):
                        field_len = payload[offset]
                        offset += field_len

            except (IndexError, struct.error):
                if plot and ('latitude' in plot or 'mode_s' in plot or 'callsign' in plot):
                    plot['category'] = 21
                    plot['partial_decode'] = True
                    plots_locales.append(plot)
                    plot_salvado = True
                offset = end_offset
                break

        if not plot_salvado:
            plots_locales.append(plot)

        if offset == offset_previo:
            break

    return plots_locales


def decode(payload: bytes, offset: int, block_length: int, category: int) -> List[Dict[str, Any]]:
    """
    Decodifica un bloque de datos ASTERIX CAT021 (ADS-B).

    Función autónoma, sin 'self', retorna una lista de plots y es a prueba de
    bucles infinitos.
    """
    # -------------------------------------------------------------
    # DETECTOR DE VERSIÓN: PARANÁ 226/103 USA CAT 21 v0.26 HEREDADO
    # -------------------------------------------------------------
    try:
        temp_fspec, temp_fspec_offset = read_fspec(payload, offset)
        if temp_fspec and len(payload) >= temp_fspec_offset + 2:
            sac = payload[temp_fspec_offset]
            sic = payload[temp_fspec_offset + 1]
            if sac == 226 and sic == 103:
                return decode_cat021_v026(payload, offset, block_length, category)
    except Exception:
        pass
    # -------------------------------------------------------------

    plots_locales = []
    cat = category
    end_offset = offset + block_length - 3

    # UAP para CAT021 v2.4 (basado en EUROCONTROL-SPEC-0149-12 Ed 2.4)
    uap_lengths = {
        # Campos de longitud fija
        1: 2, 2: -1, 3: 2, 4: 1, 5: 3, 6: 6, 7: 8,
        8: 3, 9: 2, 10: 2, 11: 3, 12: 3, 13: 4, 14: 3,
        15: 4, 16: 2, 18: 1, 19: 2, 20: 2, 21: 2,
        22: 2, 23: 1, 24: 2, 25: 2, 26: 4, 27: 2, 28: 3,
        29: 6, 30: 1, 32: 2, 33: 2,
        35: 7,      # FIX: I021/271 ACAS RA Report es 7 bytes
        40: 7, 41: 1,

        # Campos de longitud variable (FX)
        17: -1, 31: -1, 34: -1,
        36: -1,     # FIX: I021/280 Surface Capabilities es variable

        # Campos de longitud explícita (SP/RE)
        38: -2,     # I021/SP Special Purpose Field
        39: -2,     # I021/RE Reserved Expansion Field

        # Campos repetitivos
        42: -3,     # FIX: I021/250 Mode S MB Data
    }

    while offset < end_offset:
        offset_previo = offset
        plot = {'category': cat}
        plot_salvado = False  # FASE 1: Bandera de salvataje parcial

        fspec, fspec_offset = read_fspec(payload, offset)
        if not fspec or not any(fspec):
            break
        offset = fspec_offset

        for frn_index, is_present in enumerate(fspec):
            frn = frn_index + 1
            if not is_present:
                continue

            try:
                # Decodificación de campos principales
                if frn == 1:  # I021/010 Data Source Identifier
                    plot['sac'] = payload[offset]
                    plot['sic'] = payload[offset + 1]
                elif frn == 5:  # I021/071 Time of Applicability for Position
                    tod_raw = struct.unpack('>I', b'\x00' + payload[offset:offset + 3])[0]
                    plot['timestamp'] = tod_raw / 128.0
                elif frn == 6:  # I021/130 Position in WGS-84
                    lat_raw = int.from_bytes(payload[offset:offset+3], 'big', signed=True)
                    lon_raw = int.from_bytes(payload[offset+3:offset+6], 'big', signed=True)
                    plot['latitude'] = lat_raw * 180.0 / (2**23)
                    plot['longitude'] = lon_raw * 180.0 / (2**23)
                elif frn == 11: # I021/080 Target Address
                    plot['mode_s'] = payload[offset:offset+3].hex().upper()
                elif frn == 19: # I021/070 Mode-3/A Code
                    mode3a_raw = struct.unpack('>H', payload[offset:offset + 2])[0]
                    plot['mode_3a'] = mode3a_raw & 0x0FFF
                elif frn == 21: # I021/145 Flight Level
                    fl_raw = struct.unpack('>h', payload[offset:offset+2])[0]
                    if fl_raw != -32768:
                        fl_val = fl_raw * 0.25
                        if fl_val >= 0.0:
                            plot['flight_level'] = fl_val
                elif frn == 29: # I021/170 Target Identification
                    plot['callsign'] = _decode_callsign(payload[offset:offset+6])

                # Avance del offset
                length_code = uap_lengths.get(frn)

                if length_code is None:
                    # Fallback para FRNs desconocidos para evitar bucles infinitos.
                    # SP/RE deben estar en el UAP. Si no, se manejan aquí.
                    if frn == 38 or frn == 39: # SP o RE
                        if offset < len(payload):
                            field_len = payload[offset]
                            offset += field_len
                        else:
                            break # Evitar IndexError
                    else:
                        # FASE 1: SALVATAJE PARCIAL ANTES DE ABORTAR
                        if plot and ('latitude' in plot or 'mode_s' in plot or 'callsign' in plot):
                            plot['category'] = 21
                            plot['partial_decode'] = True
                            plots_locales.append(plot)
                            plot_salvado = True
                        offset = end_offset # Forzar salida
                        break
                elif length_code > 0:
                    # Campo de longitud fija
                    offset += length_code
                elif length_code == -1:
                    # Campo de longitud variable (basado en FX)
                    offset = _skip_variable_field(payload, offset)
                elif length_code == -2:
                    # Campo de longitud explícita (SP/RE)
                    if offset < len(payload):
                        field_len = payload[offset]
                        offset += field_len
                else:
                    # Campo repetitivo (actualmente solo I021/250)
                    if frn == 42 and offset < len(payload):
                        rep = payload[offset]
                        offset += 1 + (rep * 7) # REP + N * (7 bytes de datos)

            except (IndexError, struct.error) as e:
                # FASE 1: SALVATAJE PARCIAL ANTES DE ABORTAR POR ERROR
                if plot and ('latitude' in plot or 'mode_s' in plot or 'callsign' in plot):
                    plot['category'] = 21
                    plot['partial_decode'] = True
                    plots_locales.append(plot)
                    plot_salvado = True
                offset = end_offset
                break

        # FASE 2: Solo agregar si NO fue salvado parcialmente
        if not plot_salvado:
            plots_locales.append(plot)

        # --- DETECTOR DE ATASCOS ---
        if offset == offset_previo:
            print(f"[CAT 21 Warning] Bucle infinito evitado. Offset estancado en {offset}. Abortando bloque.")
            break

    return plots_locales