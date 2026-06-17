import struct
import math # Import math for trigonometric calculations
from typing import List, Dict, Any, Tuple

from decoder.asterix_utils import read_fspec


def _skip_variable_field(payload: bytes, offset: int) -> int:
    """Salta un campo de longitud variable leyendo sus bits FX."""
    while offset < len(payload):
        byte = payload[offset]
        offset += 1
        if (byte & 1) == 0:  # FX bit is 0
            break
    return offset


# Mapeo FRN → código de Item para el inspector (depende del UAP plot/track).
FRN_ITEM_PLOT = {
    1: "I001/010", 2: "I001/020", 3: "I001/040", 4: "I001/070", 5: "I001/090",
    6: "I001/130", 7: "I001/141", 8: "I001/131", 14: "I001/030",
}
FRN_ITEM_TRACK = {
    1: "I001/010", 2: "I001/020", 3: "I001/161", 4: "I001/040", 5: "I001/042",
    6: "I001/200", 7: "I001/070", 8: "I001/090", 9: "I001/141", 10: "I001/130",
}


def decode(payload: bytes, offset: int, block_length: int, category: int,
           record_offsets=None) -> List[Dict[str, Any]]:
    """
    Decodifica un bloque de datos ASTERIX CAT001 (Monoradar).

    Soporta UAPs de 'plot' y 'track'. Es autónoma y a prueba de bucles infinitos.
    """
    plots_locales = []
    cat = category
    end_offset = offset + block_length - 3

    # UAPs para CAT001 (plot y track)
    uap_plot = {
        1: 2, 2: -1, 3: 4, 4: 2, 5: 2, 6: -1, 7: 2,
        8: 2, 9: 1, 10: 1, 11: 2, 12: 4, 13: 2, 14: -1
    }
    uap_track = {
        1: 2, 2: -1, 3: 2, 4: 4, 5: 4, 6: 4, 7: 2,
        8: 2, 9: 2, 10: -1, 11: 1, 12: 1, 13: -1, 14: -1
    }

    _rec_idx = -1
    while offset < end_offset:
        offset_previo = offset
        _rec_idx += 1
        plot = {'category': cat}

        fspec, fspec_offset = read_fspec(payload, offset)
        if not fspec or not any(fspec):
            break

        # Determinar UAP (Plot vs Track) leyendo el campo I001/020 TYP
        # TYP bits 7-5 del primer byte de I001/020:
        #   0-3 → plot (no detection / SSR plot / PSR plot / CMB plot)
        #   4-6 → track (SSR track / PSR track / CMB track)
        is_track = False
        peek = fspec_offset
        if len(fspec) > 0 and fspec[0]:  # FRN 1 presente → saltar SAC/SIC (2B)
            peek += 2
        if len(fspec) > 1 and fspec[1] and peek < len(payload):  # FRN 2 = I001/020
            typ = (payload[peek] >> 5) & 0x07
            is_track = (typ >= 4)

        uap_lengths = uap_track if is_track else uap_plot
        plot['type'] = 'track' if is_track else 'plot'
        offset = fspec_offset

        for frn_index, is_present in enumerate(fspec):
            frn = frn_index + 1
            if not is_present:
                continue

            try:
                _ofs_ini = offset  # inicio de los datos de este Item (inspector)
                # Decodificación de campos principales
                if frn == 1:  # I001/010 Data Source Identifier
                    plot['sac'] = payload[offset]
                    plot['sic'] = payload[offset + 1]
                elif frn == 3 and is_track: # I001/161 Track Number
                    plot['track_number'] = struct.unpack('>H', payload[offset:offset+2])[0]
                elif frn == 3 and not is_track: # I001/040 Measured Position (Plot)
                    # RHO (Range) - 2 bytes, LSB = 1/256 NM
                    rho_raw = struct.unpack('>H', payload[offset:offset + 2])[0]
                    plot['raw_range'] = rho_raw / 256.0
                    # THETA (Azimuth) - 2 bytes, LSB = 360 / 2^16 degrees
                    theta_raw = struct.unpack('>H', payload[offset + 2:offset + 4])[0]
                    plot['raw_azimuth'] = theta_raw * (360.0 / 65536.0)
                elif frn == 4 and not is_track: # I001/070 Mode-3/A (Plot UAP)
                    mode3a_raw = struct.unpack('>H', payload[offset:offset + 2])[0]
                    plot['mode_3a'] = mode3a_raw & 0x0FFF
                elif frn == 4 and is_track: # I001/040 Measured Position (Track UAP)
                    rho_raw = struct.unpack('>H', payload[offset:offset + 2])[0]
                    plot['raw_range'] = rho_raw / 256.0
                    theta_raw = struct.unpack('>H', payload[offset + 2:offset + 4])[0]
                    plot['raw_azimuth'] = theta_raw * (360.0 / 65536.0)
                elif frn == 5 and not is_track: # I001/090 Mode-C Code / Altitude (Plot UAP FRN 5)
                    fl_raw_unsigned = struct.unpack('>H', payload[offset:offset + 2])[0]
                    fl_garbled = bool(fl_raw_unsigned & 0x4000)
                    if fl_garbled:
                        plot['garbled'] = True
                    fl_14bit = fl_raw_unsigned & 0x3FFF
                    if fl_14bit & 0x2000:
                        fl_14bit -= 0x4000
                    fl_val = fl_14bit * 0.25
                    plot['flight_level'] = fl_val
                    plot['altitude'] = fl_val * 100.0
                elif frn == 7 and is_track: # I001/070 Mode-3/A (Track UAP FRN 7)
                    mode3a_raw = struct.unpack('>H', payload[offset:offset + 2])[0]
                    plot['mode_3a'] = mode3a_raw & 0x0FFF
                elif frn == 7 and not is_track: # I001/141 Truncated Time of Day (Plot UAP FRN 7)
                    tod_raw = struct.unpack('>H', payload[offset:offset + 2])[0]
                    plot['timestamp'] = tod_raw / 128.0
                elif frn == 8 and is_track: # I001/090 Mode-C Code / Altitude (Track UAP FRN 8)
                    fl_raw_unsigned = struct.unpack('>H', payload[offset:offset + 2])[0]
                    fl_garbled = bool(fl_raw_unsigned & 0x4000)
                    if fl_garbled:
                        plot['garbled'] = True
                    fl_14bit = fl_raw_unsigned & 0x3FFF
                    if fl_14bit & 0x2000:
                        fl_14bit -= 0x4000
                    fl_val = fl_14bit * 0.25
                    plot['flight_level'] = fl_val
                    plot['altitude'] = fl_val * 100.0
                elif frn == 9 and is_track: # I001/141 Truncated Time of Day (Track UAP FRN 9)
                    tod_raw = struct.unpack('>H', payload[offset:offset + 2])[0]
                    plot['timestamp'] = tod_raw / 128.0

                # Avance del offset
                length = uap_lengths.get(frn)
                if length is not None and length > 0:
                    offset += length
                elif length == -1:
                    # Lógica para campos de longitud variable
                    if frn == 2: # I001/020 Target Report Descriptor
                        offset = _skip_variable_field(payload, offset)
                    elif frn == 6 and not is_track: # I001/130 Plot Characteristics
                        # Compuesto, el primer byte es sub-FSPEC
                        num_subfields = bin(payload[offset]).count('1')
                        offset += 1 + num_subfields
                    elif frn == 14 and not is_track: # I001/030 Warning/Error
                        offset = _skip_variable_field(payload, offset)
                    elif frn == 10 and is_track: # I001/130 Plot Characteristics
                        num_subfields = bin(payload[offset]).count('1')
                        offset += 1 + num_subfields
                    else:
                        offset = _skip_variable_field(payload, offset)
                else:
                    # Campo no en UAP o sin longitud definida
                    # Esto es un fallback, idealmente todos los FRN deberían estar en uap_lengths
                    if offset < len(payload): # Evitar IndexError si ya estamos al final
                        # If it's an SP or RE field, try to read its length
                        # This is a heuristic, as CAT001 UAP doesn't explicitly list SP/RE FRNs
                        if frn > 14: # Assuming FRNs beyond the defined UAP are SP/RE
                            field_len = payload[offset]
                            offset += field_len
                    else:
                        offset += 1

                if record_offsets is not None:
                    mapa = FRN_ITEM_TRACK if is_track else FRN_ITEM_PLOT
                    record_offsets.append(
                        (_rec_idx, mapa.get(frn, f"FRN{frn}"), _ofs_ini, offset))

            except (IndexError, struct.error) as e:
                print(f"[CAT 01 Error] Error de decodificación en FRN {frn}: {e}. Abortando plot.")
                offset = end_offset
                break

        # K2: NORMALIZACIÓN DE CLAVES
        plot['track_id'] = plot.get('track_number', f"CAT01_{plot.get('sac',0)}_{plot.get('sic',0)}_{plot.get('timestamp',0)}")
        plot['mode3a'] = f"{plot.get('mode_3a', 0):04o}" if 'mode_3a' in plot else '----'
        plot['flight_level'] = plot.get('flight_level')  # None si no está presente

        # G3: GEOMETRÍA (RHO/THETA -> LAT/LON)
        if 'raw_range' in plot and 'raw_azimuth' in plot:
            # Asumiendo origen radar RSMA Córdoba (ej. lat: -31.31, lon: -64.21)
            # Ajustar con las coordenadas reales de tu radar si se conocen.
            # ESTOS VALORES SON PLACEHOLDERS. EN UNA IMPLEMENTACIÓN REAL, DEBERÍAN
            # PROVENIR DE LA CONFIGURACIÓN DEL SENSOR (SAC/SIC)
            radar_lat = -31.315 # Reemplazar con el valor real si existe en el entorno
            radar_lon = -64.215

            dist_km = plot['raw_range'] * 1.852 # Convert NM to km
            bearing_rad = math.radians(plot['raw_azimuth'])

            # Fórmula simplificada de destino (proyección esférica básica)
            R = 6371.0 # Radio Tierra en km
            lat1 = math.radians(radar_lat)
            lon1 = math.radians(radar_lon)

            lat2 = math.asin(math.sin(lat1)*math.cos(dist_km/R) + math.cos(lat1)*math.sin(dist_km/R)*math.cos(bearing_rad))
            lon2 = lon1 + math.atan2(math.sin(bearing_rad)*math.sin(dist_km/R)*math.cos(lat1), math.cos(dist_km/R)-math.sin(lat1)*math.sin(lat2))

            plot['lat'] = math.degrees(lat2)
            plot['lon'] = math.degrees(lon2)
        plots_locales.append(plot)

        # --- DETECTOR DE ATASCOS ---
        if offset == offset_previo:
            print(f"[CAT 01 Warning] Bucle infinito evitado. Offset estancado en {offset}. Abortando bloque.")
            break

    return plots_locales