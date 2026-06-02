import struct
import math # Import math for trigonometric calculations
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


def decode(payload: bytes, offset: int, block_length: int, category: int) -> List[Dict[str, Any]]:
    """
    Decodifica un bloque de datos ASTERIX CAT048.

    Esta función es autónoma, no utiliza 'self' y retorna una lista de plots.
    Incluye un detector de atascos para evitar bucles infinitos.

    Args:
        payload: El payload del paquete UDP.
        offset: El offset donde comienzan los datos de CAT048 (después del header).
        block_length: La longitud total del bloque ASTERIX.
        category: La categoría ASTERIX (ej. 48).

    Returns:
        Una lista de diccionarios, donde cada diccionario es un plot decodificado.
    """
    plots_locales = []
    cat = category
    end_offset = offset + block_length - 3

    # UAP para CAT048 (basado en EUROCONTROL-SPEC-0149-4 v1.25)
    # El valor es la longitud en bytes. -1 para variable.
    uap_lengths = {
        1: 2, 2: 3, 3: -1, 4: 4, 5: 2, 6: 2, 7: -1,
        8: 3, 9: 6, 10: -1, 11: 2, 12: 4, 13: 4, 14: -1,
        15: 4, 16: -1, 17: 2, 18: 4, 19: 2, 20: -1, 21: 2,
        22: 7, 23: 1, 24: 2, 25: 1, 26: 2,
        # FRNs 27-35 son para RE y SP, manejados explícitamente
    }

    while offset < end_offset:
        offset_previo = offset
        plot = {'category': cat}

        fspec, fspec_offset = read_fspec(payload, offset)
        if not fspec or not any(fspec):
            break  # No hay FSPEC, fin de los registros
        offset = fspec_offset
        offset = fspec_offset # FASE 1: Se actualiza el offset después de leer el FSPEC.

        for frn_index, is_present in enumerate(fspec):
            frn = frn_index + 1
            if not is_present:
                continue

            try:
                # Decodificación de campos principales
                if frn == 1:  # I048/010 Data Source Identifier
                    plot['sac'] = payload[offset]
                    plot['sic'] = payload[offset + 1]
                elif frn == 2:  # I048/140 Time-of-Day
                    tod_raw = struct.unpack('>I', b'\x00' + payload[offset:offset + 3])[0]
                    plot['timestamp'] = tod_raw / 128.0
                elif frn == 4:  # I048/040 Measured Position in Polar Coordinates
                    # RHO (Range) - 2 bytes, LSB = 1/256 NM
                    rho_raw = struct.unpack('>H', payload[offset:offset + 2])[0]
                    plot['raw_range'] = rho_raw / 256.0
                    # THETA (Azimuth) - 2 bytes, LSB = 360 / 2^16 degrees
                    theta_raw = struct.unpack('>H', payload[offset + 2:offset + 4])[0]
                    plot['raw_azimuth'] = theta_raw * (360.0 / 65536.0)
                elif frn == 5:  # I048/070 Mode-3/A Code (2 bytes)
                    # Layout: Bit 16=V(validated), Bit 15=G(garbled), Bit 14=L(source), Bit 13=0, Bits 12-1=code
                    mode3a_raw = struct.unpack('>H', payload[offset:offset + 2])[0]
                    plot['mode_3a'] = mode3a_raw & 0x0FFF  # 12 bits del código SSR octal
                    plot['garbled'] = bool(mode3a_raw & 0x4000)  # Bit 15 (G): Garbled code
                    plot['mode3a_validated'] = not bool(mode3a_raw & 0x8000)  # Bit 16 (V): 0=validated
                elif frn == 6:  # I048/090 Flight Level in Binary Representation (2 bytes)
                    # Layout: Bit 16=V(validated), Bit 15=G(garbled), Bits 14-1=FL (signed, LSB=1/4 FL)
                    fl_raw_unsigned = struct.unpack('>H', payload[offset:offset + 2])[0]
                    fl_garbled = bool(fl_raw_unsigned & 0x4000)  # Bit 15 (G): Flight Level garbled
                    # Si Mode-3/A O Flight Level están garbled, marcar como garbled
                    if fl_garbled:
                        plot['garbled'] = True
                    # Extraer 14 bits de FL como signed (complemento a 2 de 14 bits)
                    fl_14bit = fl_raw_unsigned & 0x3FFF
                    if fl_14bit & 0x2000:  # bit de signo del campo de 14 bits
                        fl_14bit -= 0x4000
                    fl_val = fl_14bit * 0.25
                    if fl_val >= 0.0:
                        plot['flight_level'] = fl_val
                # I048/080 Mode-C Code is not explicitly extracted here, but could be added if needed.
                elif frn == 8:  # I048/220 Aircraft Address
                    plot['mode_s'] = payload[offset:offset + 3].hex().upper()
                elif frn == 9:  # I048/240 Aircraft Identification
                    plot['callsign'] = _decode_callsign(payload[offset:offset + 6])
                elif frn == 11: # I048/161 Track Number
                    plot['track_number'] = struct.unpack('>H', payload[offset:offset+2])[0]

                # Avance del offset
                length = uap_lengths.get(frn)
                if length is not None and length > 0:
                    offset += length
                elif length == -1:
                    # Lógica para campos de longitud variable
                    if frn == 3: # I048/020 Target Report Descriptor
                        # Bit layout del primer byte:
                        #   Bits 8-6: TYP (tipo de detección)
                        #   Bit 5: SIM (simulated), Bit 4: RDP, Bit 3: SPI
                        #   Bit 2: RAB (Report from Aircraft Beacon) — NO es garbling
                        #   Bit 1: FX (extension)
                        first_byte = payload[offset]
                        plot['rab'] = bool(first_byte & 0x02)  # RAB: 0=transponder, 1=field monitor
                        plot['spi'] = bool(first_byte & 0x04)  # SPI: Special Position Identification
                        # Extraer TYP (tipo de detección) - bits 8-6
                        typ = (first_byte >> 5) & 0x07
                        plot['detection_type'] = typ  # 0=no detection, 1=PSR only, 2=SSR only, 3=Combined, 5=Mode S All-Call, etc.
                        offset = _skip_variable_field(payload, offset)
                    elif frn == 7: # I048/130 Radar Plot Characteristics
                        # Es compuesto, el primer byte es un sub-FSPEC
                        sub_fspec, new_offset_after_fspec = read_fspec(payload, offset)
                        # Contamos los subcampos presentes. El estándar indica que cada uno
                        # de los subcampos de I048/130 tiene una longitud de 1 byte.
                        num_present_subfields = sum(1 for present in sub_fspec if present)
                        offset = new_offset_after_fspec + num_present_subfields
                    elif frn == 10: # I048/250 Mode S MB Data
                        rep = payload[offset]
                        offset += 1 + (rep * 8)
                    elif frn == 14: # I048/170 Track Status
                        offset = _skip_variable_field(payload, offset)
                    elif frn == 16: # I048/030 Warning/Error
                        offset = _skip_variable_field(payload, offset)
                    elif frn == 20: # I048/120 Radial Doppler Speed
                        # Es un campo compuesto (Compound Data Item)
                        sub_fspec, new_offset = read_fspec(payload, offset)
                        offset = new_offset
                        
                        # Subcampo 1: CAL (Calculated Doppler Speed) -> 2 bytes fixed length
                        if len(sub_fspec) > 0 and sub_fspec[0]:
                            offset += 2
                        
                        # Subcampo 2: RDS (Raw Doppler Speed) -> Repetitivo de bloques de 6 bytes
                        if len(sub_fspec) > 1 and sub_fspec[1]:
                            if offset < len(payload):
                                rep = payload[offset]
                                offset += 1 + (rep * 6)
                    else:
                        # Fallback para campos variables no implementados
                        offset = _skip_variable_field(payload, offset)
                else:
                    # Campo no en UAP o sin longitud definida, se asume 1 byte para no atascar
                    if frn > 26: # SP o RE
                        field_len = payload[offset]
                        offset += field_len
                    else:
                        offset += 1

            except (IndexError, struct.error) as e:
                print(f"[CAT 48 Error] Error de decodificación en FRN {frn}: {e}. Abortando plot.")
                offset = end_offset # Forzar salida del bucle
                break

        # FASE 2: Se agrega el plot solo si contiene campos decodificados.
        if len(plot) > 1:
            plots_locales.append(plot)
        # --- DETECTOR DE ATASCOS ---
        if offset == offset_previo:
            print(f"[CAT 48 Warning] Bucle infinito evitado. Offset estancado en {offset}. Abortando bloque.")
            break

    return plots_locales