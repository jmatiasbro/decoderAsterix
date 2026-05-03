"""
ASTERIX Category Decoders

Módulo para decodificar diferentes categorías de mensajes ASTERIX.
Soporta: CAT 001, 002, 021, 034, 048
"""

import struct
from dataclasses import dataclass
from typing import List, Dict, Optional, Tuple, Set


@dataclass
class AsterixRecord:
    """Estructura para almacenar un registro ASTERIX decodificado."""
    category: int
    sac: int
    sic: int
    target_address: Optional[int] = None
    target_id: Optional[str] = None
    track_number: Optional[int] = None
    timestamp: Optional[float] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    altitude: Optional[float] = None
    mode_3a: Optional[int] = None
    azimuth: Optional[float] = None
    range_slant: Optional[float] = None
    flight_level: Optional[int] = None
    radar_position: Optional[Tuple[float, float, float]] = None  # lat, lon, elev
    extra_data: Dict = None

    def __post_init__(self):
        if self.extra_data is None:
            self.extra_data = {}


class BitStream:
    """Clase auxiliar para leer bits de un flujo de bytes."""
    
    def __init__(self, data: bytes):
        self.data = data
        self.pos = 0  # Posición en bits
    
    def read_bits(self, n: int) -> int:
        """Lee n bits y devuelve su valor entero."""
        byte_pos = self.pos // 8
        bit_offset = self.pos % 8
        
        result = 0
        bits_read = 0
        
        while bits_read < n:
            if byte_pos >= len(self.data):
                raise ValueError("Insufficient data in BitStream")
            
            available_bits = 8 - bit_offset
            bits_to_read = min(n - bits_read, available_bits)
            
            byte_val = self.data[byte_pos]
            # Extraer bits del byte actual
            shift = available_bits - bits_to_read
            mask = (1 << bits_to_read) - 1
            bits = (byte_val >> shift) & mask
            
            result = (result << bits_to_read) | bits
            bits_read += bits_to_read
            self.pos += bits_to_read
            
            if bit_offset + bits_to_read >= 8:
                byte_pos += 1
                bit_offset = 0
            else:
                bit_offset += bits_to_read
        
        return result
    
    def skip_bits(self, n: int):
        """Salta n bits."""
        self.pos += n
    
    def align_to_byte(self):
        """Alinea a la siguiente frontera de byte."""
        if self.pos % 8 != 0:
            self.pos += 8 - (self.pos % 8)


class AsterixDecoder:
    """Decodificador genérico de mensajes ASTERIX."""
    
    @staticmethod
    def parse_fspec(data: bytes) -> Tuple[Set[int], int]:
        """
        Parsea FSPEC (Field Specification) e identifica qué campos están presentes.
        Retorna un set de índices de campos presentes (0-based) y los bytes consumidos.
        """
        fields = set()
        byte_count = 0
        field_index_offset = 0
        
        while byte_count < len(data):
            byte_val = data[byte_count]
            
            # Los bits 8 al 2 (MSB al LSB+1) indican la presencia de los campos.
            for bit_pos in range(7):  # Corresponde a los 7 campos por octeto FSPEC
                # El bit 8 (MSB) corresponde al primer campo (índice 0), bit 7 al segundo (índice 1), etc.
                mask = 1 << (7 - bit_pos)
                if byte_val & mask:
                    fields.add(field_index_offset + bit_pos)
            
            byte_count += 1
            field_index_offset += 7  # El siguiente octeto FSPEC empieza 7 campos después
            
            # El bit 1 (LSB) es el bit de extensión (FX). Si es 0, es el último octeto.
            if not (byte_val & 0x01):
                break
        
        return fields, byte_count


class CAT048Decoder:
    """Decodificador para CAT 048 (Monoradar Mode S)."""
    
    @staticmethod
    def decode(data: bytes, start_pos: int = 0) -> Tuple[AsterixRecord, int]:
        """
        Decodifica un mensaje CAT 048.
        Retorna (AsterixRecord, bytes_consumidos).
        """
        stream = BitStream(data[start_pos:])
        
        # Leer Data Record Header
        category = stream.read_bits(8) # Should be 48
        length = stream.read_bits(16)
        
        # Leer FSPEC
        fspec_fields, fspec_bytes = AsterixDecoder.parse_fspec(data[start_pos + 3:])
        
        record = AsterixRecord(category=category, sac=0, sic=0)
        
        # Posicionar después de FSPEC
        stream.pos = 24 + fspec_bytes * 8
        
        # Decodificar campos basados en FSPEC
        # Campo 1: I048/010 Data Source Identifier
        if 0 in fspec_fields:
            record.sac = stream.read_bits(8)
            record.sic = stream.read_bits(8)
        
        # Campo 2: I048/140 Time of Day
        if 1 in fspec_fields:
            tod_raw = stream.read_bits(24)
            record.timestamp = (tod_raw / 128.0)  # LSB = 1/128 segundo
        
        # Campo 3: I048/020 Target Report Descriptor
        if 2 in fspec_fields:
            ext = 1
            while ext:
                octet = stream.read_bits(8)
                ext = octet & 0x01
        
        # Campo 4: I048/040 Measured Position in Polar Coordinates
        if 3 in fspec_fields:
            azimuth_raw = stream.read_bits(16)
            range_raw = stream.read_bits(16)
            record.azimuth = (azimuth_raw / 65536.0) * 360  # LSB = 360/2^16
            record.range_slant = (range_raw / 256.0)  # LSB = 1/256 NM
        
        # Campo 5: I048/070 Mode-3/A Code
        if 4 in fspec_fields:
            mode3a_raw = stream.read_bits(16)
            record.mode_3a = mode3a_raw & 0x0FFF  # 12 bits válidos
        
        # Campo 6: I048/090 Flight Level
        if 5 in fspec_fields:
            fl_raw = stream.read_bits(16)
            # LSB = 1/4 FL. Manejo de signo (Complemento a 2)
            def to_signed_16(val): return val if val < 0x8000 else val - 0x10000
            record.flight_level = to_signed_16(fl_raw) / 4.0 if fl_raw != 0xFFFF else None

        # Campo 7: I048/130 Radar Plot Characteristics
        if 6 in fspec_fields:
            ext = 1
            while ext:
                octet = stream.read_bits(8)
                ext = octet & 0x01

        # --- Octeto 2 del FSPEC --- (Items 8-14)

        # Campo 10: I048/042 Calculated Position in Cartesian Co-ordinates
        if 9 in fspec_fields:
            x_raw = stream.read_bits(16)
            y_raw = stream.read_bits(16)
            def to_signed_16(val): return val if val < 0x8000 else val - 0x10000
            # LSB = 1/128 NM
            record.extra_data['x_cartesian_nm'] = to_signed_16(x_raw) / 128.0
            record.extra_data['y_cartesian_nm'] = to_signed_16(y_raw) / 128.0

        # Campo 11: I048/250 Track Status
        if 10 in fspec_fields:
            ext = 1
            while ext:
                ext = stream.read_bits(8) & 0x01
        
        # Campo 8: I048/220 Aircraft Address (Mode S)
        if 7 in fspec_fields:
            record.target_address = stream.read_bits(24)
            
        # Campo 9: I048/240 Aircraft Identification (Callsign)
        if 8 in fspec_fields:
            raw_id = stream.read_bits(48)
            chars = " #ABCDEFGHIJKLMNOPQRSTUVWXYZ##### ###############0123456789######"
            callsign = ""
            for i in range(8):
                char_code = (raw_id >> (6 * (7 - i))) & 0x3F
                callsign += chars[char_code] if char_code < len(chars) else "?"
            record.target_id = callsign.strip()
            
        # Campo 13: I048/130 Plot Characteristics (Potencia/SSR)
        if 12 in fspec_fields:
            ext = 1
            characteristics = []
            while ext:
                octet = stream.read_bits(8)
                characteristics.append(octet)
                ext = octet & 0x01
            record.extra_data['plot_characteristics'] = characteristics

        # Campo 12: I048/161 Track Number
        if 11 in fspec_fields:
            record.track_number = stream.read_bits(16)

        # Campo 14: I048/080 Mode-C Code
        if 13 in fspec_fields:
            mc_raw = stream.read_bits(16)
            # V (Validity), G (Garble)
            is_valid = not (mc_raw & 0x2000)
            is_garbled = bool(mc_raw & 0x1000)
            record.extra_data['is_garbled'] = is_garbled
            
            if is_valid:
                # Reensamblar código Gray a binario
                c1 = (mc_raw >> 12) & 1
                a1 = (mc_raw >> 11) & 1
                c2 = (mc_raw >> 10) & 1
                a2 = (mc_raw >> 9) & 1
                c4 = (mc_raw >> 8) & 1
                a4 = (mc_raw >> 7) & 1
                b1 = (mc_raw >> 5) & 1
                d1 = (mc_raw >> 4) & 1
                b2 = (mc_raw >> 3) & 1
                d2 = (mc_raw >> 2) & 1
                b4 = (mc_raw >> 1) & 1
                d4 = mc_raw & 1
                record.extra_data['mode_c_valid'] = True
        
        bytes_consumed = length
        return record, bytes_consumed


class CAT034Decoder:
    """Decodificador para CAT 034 (Service Messages - Radar Information)."""
    
    @staticmethod
    def decode(data: bytes, start_pos: int = 0) -> Tuple[AsterixRecord, int]:
        """
        Decodifica un mensaje CAT 034.
        Extrae posición 3D del radar (I034/120).
        """
        stream = BitStream(data[start_pos:])
        
        category = stream.read_bits(8)
        length = stream.read_bits(16)
        
        fspec_fields, fspec_bytes = AsterixDecoder.parse_fspec(data[start_pos + 3:])
        
        record = AsterixRecord(category=category, sac=0, sic=0)
        
        stream.pos = 24 + fspec_bytes * 8
        
        # Campo 1: I034/010 Data Source Identifier
        if 0 in fspec_fields:
            record.sac = stream.read_bits(8)
            record.sic = stream.read_bits(8)
        
        # Campo 2: I034/020 Message Type
        if 1 in fspec_fields:
            msg_type = stream.read_bits(8)
            record.extra_data['message_type'] = msg_type
            
        # Campo 3: I034/030 Time of Day
        if 2 in fspec_fields:
            tod_raw = stream.read_bits(24)
            record.timestamp = tod_raw / 128.0
            
        # Campo 4: I034/041 Antenna Characteristics (LSB = 1/128 s para Periodo)
        if 3 in fspec_fields:
            ant_period_raw = stream.read_bits(16)
            if ant_period_raw > 0:
                ant_period = ant_period_raw / 128.0
                calculated_speed = 60.0 / ant_period
                
                # Heurística para radares que envían Velocidad en lugar de Periodo.
                # Un radar de vigilancia no gira a 0.2 RPM (periodo de 4 min).
                # Si la velocidad calculada es < 1 y el valor crudo es alto, probablemente sea RPM con un LSB diferente.
                if calculated_speed < 1.0 and ant_period_raw > 16384:
                    # Caso típico Indra: Valor crudo es RPM * 4000 o similar
                    record.extra_data['antenna_speed'] = ant_period_raw / 4000.0
                else:
                    record.extra_data['antenna_speed'] = calculated_speed

        if 4 in fspec_fields: # Campo 5: I034/050 System Config
            ext = 1
            while ext:
                octeto = stream.read_bits(8)
                ext = octeto & 0x01
        if 5 in fspec_fields: stream.skip_bits(8)  # Campo 6: I034/060 System Proc. Mode
        if 6 in fspec_fields: stream.skip_bits(64) # Campo 7: I034/070 Message Count
        
        # Segundo Octeto FSPEC
        if 7 in fspec_fields: stream.skip_bits(64) # I034/100 Generic Polar Window
        if 8 in fspec_fields: # I034/110 Data Filter
            stream.skip_bits(8)
            
        # Item 10: I034/120 3D Radar Position (WGS-84)
        if 9 in fspec_fields: # Campo 10
            lat_raw = stream.read_bits(32)
            lon_raw = stream.read_bits(32)
            height_raw = stream.read_bits(16)
            
            # LSB = 180 / 2^23
            def to_signed_32(val): return val if val < 0x80000000 else val - 0x100000000
            def to_signed_16(val): return val if val < 0x8000 else val - 0x10000
            
            lat = to_signed_32(lat_raw) * (180.0 / 8388608.0)
            lon = to_signed_32(lon_raw) * (180.0 / 8388608.0)
            height = to_signed_16(height_raw) * 25.0 # en pies
            
            record.latitude = lat
            record.longitude = lon
            record.altitude = height
            record.radar_position = (lat, lon, height)

        bytes_consumed = length
        return record, bytes_consumed


class CAT021Decoder:
    """Decodificador para CAT 021 v2.4 (ADS-B)."""
    
    @staticmethod
    def decode(data: bytes, start_pos: int = 0) -> Tuple[AsterixRecord, int]:
        """
        Decodifica un mensaje CAT 021 (ADS-B).
        """
        stream = BitStream(data[start_pos:])
        
        category = stream.read_bits(8)
        length = stream.read_bits(16)
        
        fspec_fields, fspec_bytes = AsterixDecoder.parse_fspec(data[start_pos + 3:])
        
        record = AsterixRecord(category=category, sac=0, sic=0)
        
        def to_signed(val, bits):
            """Convierte un valor a entero con signo (complemento a 2)."""
            if val & (1 << (bits - 1)):
                val -= (1 << bits)
            return val

        stream.pos = 24 + fspec_bytes * 8
        
        # Campo 1: I021/010 Data Source Identifier
        if 0 in fspec_fields:
            record.sac = stream.read_bits(8)
            record.sic = stream.read_bits(8)

        # Campo 2: I021/040 Target Report Descriptor
        if 1 in fspec_fields:
            ext = 1
            while ext: ext = stream.read_bits(8) & 0x01

        # Campo 3: I021/161 Track Number
        if 2 in fspec_fields:
            record.track_number = stream.read_bits(16)

        # Campo 4: I021/015 Service Identification
        if 3 in fspec_fields: stream.skip_bits(8)

        # Campo 5: I021/071 Time of Message Reception for Position
        if 4 in fspec_fields:
            record.timestamp = stream.read_bits(24) / 128.0

        # Campo 6: I021/130 Position in WGS-84 Co-ordinates
        if 5 in fspec_fields:
            # Ed 2.4: 6 octets (24 bits Lat, 24 bits Lon), LSB = 180/2^23
            lat_raw = stream.read_bits(24)
            lon_raw = stream.read_bits(24)
            lsb = 180.0 / (2**23)
            lat = to_signed(lat_raw, 24) * lsb
            lon = to_signed(lon_raw, 24) * lsb
            record.latitude = lat
            record.longitude = lon
        
        # Campo 7: I021/080 Target Address
        if 6 in fspec_fields:
            record.target_address = stream.read_bits(24)
        
        # Campo 8: I021/145 Flight Level
        if 7 in fspec_fields:
            fl_raw = stream.read_bits(16)
            record.flight_level = to_signed(fl_raw, 16) / 4.0

        # --- Octeto 2 FSPEC ---

        # Campo 9: I021/131 High-Resolution Position in WGS-84
        if 8 in fspec_fields:
            # Ed 2.4: 8 octets (32 bits Lat, 32 bits Lon), LSB = 180/2^30
            lat_hr_raw = stream.read_bits(32)
            lon_hr_raw = stream.read_bits(32)
            lsb_hr = 180.0 / (2**30)
            # Priorizar alta resolución si está presente
            record.latitude = to_signed(lat_hr_raw, 32) * lsb_hr
            record.longitude = to_signed(lon_hr_raw, 32) * lsb_hr

        # Campo 10: I021/140 Geometric Altitude
        if 9 in fspec_fields:
            alt_raw = stream.read_bits(16)
            record.altitude = to_signed(alt_raw, 16) * 6.25 # LSB = 6.25 ft

        # Campo 13: I021/070 Mode-3/A Code
        if 12 in fspec_fields:
            mode3a_raw = stream.read_bits(16)
            record.mode_3a = mode3a_raw & 0x0FFF

        # Campo 14: I021/160 Ground Vector
        if 13 in fspec_fields:
            gs_raw = stream.read_bits(16)
            ta_raw = stream.read_bits(16)
            # Ground Speed, LSB = 2^-14 NM/s
            record.extra_data['ground_speed_nms'] = to_signed(gs_raw, 16) * (2**-14)
            # Track Angle, LSB = 360/2^16
            record.extra_data['track_angle_deg'] = ta_raw * (360.0 / (2**16))

        # --- Octeto 3 FSPEC ---

        # Campo 16: I021/170 Target Identification (Callsign)
        if 15 in fspec_fields:
            raw_id = stream.read_bits(48)
            chars = " #ABCDEFGHIJKLMNOPQRSTUVWXYZ##### ###############0123456789######"
            callsign = ""
            for i in range(8):
                char_code = (raw_id >> (6 * (7 - i))) & 0x3F
                callsign += chars[char_code] if char_code < len(chars) else "?"
            record.target_id = callsign.strip()

        bytes_consumed = length
        return record, bytes_consumed


class CAT062Decoder:
    """Decodificador para CAT 062 (System Track Data)."""
    
    @staticmethod
    def decode(data: bytes, start_pos: int = 0) -> Tuple[AsterixRecord, int]:
        """
        Decodifica un mensaje CAT 062 (Tracks del sistema).
        """
        stream = BitStream(data[start_pos:])
        
        category = stream.read_bits(8)
        length = stream.read_bits(16)
        
        fspec_fields, fspec_bytes = AsterixDecoder.parse_fspec(data[start_pos + 3:])
        record = AsterixRecord(category=category, sac=0, sic=0)
        stream.pos = 24 + fspec_bytes * 8
        
        # Funciones auxiliares para conversión de signos
        def to_signed_32(val): return val if val < 0x80000000 else val - 0x100000000
        def to_signed_16(val): return val if val < 0x8000 else val - 0x10000
        
        # Campo 1: I062/010 Data Source Identifier
        if 0 in fspec_fields:
            record.sac = stream.read_bits(8)
            record.sic = stream.read_bits(8)
        
        # Campo 2: I062/015 Service Identification
        if 1 in fspec_fields: stream.skip_bits(8)
        
        # Campo 3: I062/070 Time of Track Information
        if 2 in fspec_fields:
            tod_raw = stream.read_bits(24)
            record.timestamp = tod_raw / 128.0
            
        # Campo 4: I062/105 Calculated Position (Cartesian)
        if 3 in fspec_fields:
            x_raw = to_signed_32(stream.read_bits(32))
            y_raw = to_signed_32(stream.read_bits(32))
            record.extra_data['x_m'] = x_raw * 0.5 # LSB = 0.5m
            record.extra_data['y_m'] = y_raw * 0.5
            
        # Campo 5: I062/100 Calculated Position (WGS-84)
        if 4 in fspec_fields:
            lat_raw = stream.read_bits(32)
            lon_raw = stream.read_bits(32)
            # Ed 1.18: LSB = 180 / 2^31
            lsb = 180.0 / (2**31)
            record.latitude = to_signed_32(lat_raw) * lsb
            record.longitude = to_signed_32(lon_raw) * lsb
            
        # Campo 6: I062/185 Calculated Velocity (Cartesian)
        if 5 in fspec_fields:
            # Ed 1.18: 4 octetos, LSB = 0.25 m/s
            vx_raw = to_signed_16(stream.read_bits(16))
            vy_raw = to_signed_16(stream.read_bits(16))
            record.extra_data['vx_mps'] = vx_raw * 0.25
            record.extra_data['vy_mps'] = vy_raw * 0.25
            
        # Campo 7: I062/210 Calculated Acceleration (Cartesian)
        if 6 in fspec_fields: stream.skip_bits(16)
            
        # --- Octeto 2 FSPEC ---
        
        # Campo 8: I062/040 Track Number
        if 7 in fspec_fields:
            record.track_number = stream.read_bits(16)
            
        # Campo 9: I062/060 Track Status
        if 8 in fspec_fields:
            ext = 1
            while ext:
                ext = stream.read_bits(8) & 0x01
        
        # Campo 17: I062/380 Aircraft Derived Data (Compound Field)
        if 16 in fspec_fields:
            # This is a compound field with its own FSPEC.
            # We need to get the data slice from the current stream position to parse the sub-FSPEC.
            sub_fspec_data = data[start_pos + (stream.pos // 8):]
            sub_fspec_fields, sub_fspec_bytes = AsterixDecoder.parse_fspec(sub_fspec_data)
            stream.skip_bits(sub_fspec_bytes * 8)

            # Subcampo 1: Target Address (Mode S)
            if 0 in sub_fspec_fields:
                record.target_address = stream.read_bits(24)

            # Subcampo 2: Target Identification (Callsign)
            if 1 in sub_fspec_fields:
                raw_id = stream.read_bits(48)
                chars = " #ABCDEFGHIJKLMNOPQRSTUVWXYZ##### ###############0123456789######"
                callsign = ""
                for i in range(8):
                    char_code = (raw_id >> (6 * (7 - i))) & 0x3F
                    callsign += chars[char_code] if char_code < len(chars) else "?"
                record.target_id = callsign.strip()

            # Subcampo 8: Mode-3/A Code
            if 7 in sub_fspec_fields:
                mode3a_raw = stream.read_bits(16)
                record.mode_3a = mode3a_raw & 0x0FFF

            # Subcampo 18: Flight Level
            if 17 in sub_fspec_fields:
                fl_raw = stream.read_bits(16)
                record.flight_level = to_signed_16(fl_raw) / 4.0

            # Para avanzar correctamente el stream, se omiten los subcampos no procesados.
            # Este enfoque basado en un diccionario es más mantenible que una cadena de 'ifs'.
            subfield_lengths = {
                2: 16, 3: 16, 4: 16, 5: 16, 6: 16,  # Heading, IAS, TAS, Sel Alt, FSSA
                8: 16, 9: 16, 10: 16, 11: 16, 12: 16, 13: 16,  # Vert Rates, Roll, Track Angles, GS
                14: 8, 15: 8,  # Target Status, MOPS Version
                18: 8, 19: 8,  # Turbulence, Emitter Cat
                20: 64, # Position
                21: 8, 22: 8  # Surface Caps, Msg Amp
            }
            
            # Subcampos que ya han sido leídos explícitamente
            handled_subfields = {0, 1, 7, 17}

            for subfield_index in sub_fspec_fields:
                if subfield_index not in handled_subfields:
                    if subfield_index in subfield_lengths:
                        stream.skip_bits(subfield_lengths[subfield_index])
                    # En un sistema con logging, aquí se podría advertir sobre un subcampo desconocido.

        bytes_consumed = length
        return record, bytes_consumed


class CAT001Decoder:
    """Decodificador para CAT 001 (Monoradar Standard)."""
    
    @staticmethod
    def decode(data: bytes, start_pos: int = 0) -> Tuple[AsterixRecord, int]:
        """
        Decodifica un mensaje CAT 001.
        """
        stream = BitStream(data[start_pos:])
        
        category = stream.read_bits(8)
        length = stream.read_bits(16)
        
        fspec_fields, fspec_bytes = AsterixDecoder.parse_fspec(data[start_pos + 3:])
        
        record = AsterixRecord(category=category, sac=0, sic=0)
        
        stream.pos = 24 + fspec_bytes * 8
        
        # Campo 1: I001/010 Data Source Identifier
        if 0 in fspec_fields:
            record.sac = stream.read_bits(8)
            record.sic = stream.read_bits(8)
            
        # Campo 2: I001/020 Target Report Descriptor
        typ_flag = 0  # Por defecto Rho/Theta
        if 1 in fspec_fields:
            ext = 1
            octets = []
            while ext:
                octet = stream.read_bits(8)
                octets.append(octet)
                ext = octet & 0x01
            
            # Extraer Bit TYP (Típicamente Bit 8 del primer octeto)
            # TYP=0 (Polar), TYP=1 (Cartesiano)
            typ_flag = (octets[0] >> 7) & 0x01
            record.extra_data['TYP'] = typ_flag
        
        # Campo 3: I001/040 Measured Position in Polar Coordinates
        if 2 in fspec_fields:
            if typ_flag == 0:
                azimuth_raw = stream.read_bits(16)
                range_raw = stream.read_bits(16)
                record.azimuth = (azimuth_raw / 65536.0) * 360
                record.range_slant = range_raw / 128.0
            else:
                # Skip bits si el TYP dice que no es polar pero FSPEC indicó campo 3
                stream.skip_bits(32)
                
        # (Pseudo implementación) Campo 8: I001/042 Cartesian
        if 7 in fspec_fields and typ_flag == 1:
            x_raw = stream.read_bits(16)
            y_raw = stream.read_bits(16)
            def to_signed_16(val): return val if val < 0x8000 else val - 0x10000
            record.extra_data['x_m'] = to_signed_16(x_raw) * (1852.0 / 128.0) # LSB = 1/128 NM en Metros
            record.extra_data['y_m'] = to_signed_16(y_raw) * (1852.0 / 128.0)
        
        # Campo 6: I001/141 Time of Day
        if 5 in fspec_fields:
            # I001/141 is 2 bytes, LSB = 1s (seconds since midnight)
            tod_raw = stream.read_bits(16)
            record.timestamp = float(tod_raw)

        # Campo 4: I001/070 Mode-3/A Code
        if 3 in fspec_fields:
            mode3a_raw = stream.read_bits(16)
            record.mode_3a = mode3a_raw & 0x0FFF

        bytes_consumed = length
        return record, bytes_consumed


class CAT002Decoder:
    """Decodificador para CAT 002 (Service Messages - Radar Configuration)."""
    
    @staticmethod
    def decode(data: bytes, start_pos: int = 0) -> Tuple[AsterixRecord, int]:
        """
        Decodifica un mensaje CAT 002.
        """
        stream = BitStream(data[start_pos:])
        
        category = stream.read_bits(8)
        length = stream.read_bits(16)
        
        fspec_fields, fspec_bytes = AsterixDecoder.parse_fspec(data[start_pos + 3:])
        
        record = AsterixRecord(category=category, sac=0, sic=0)
        
        stream.pos = 24 + fspec_bytes * 8
        
        # Campo 1: I002/010 Data Source Identifier
        if 0 in fspec_fields:
            record.sac = stream.read_bits(8)
            record.sic = stream.read_bits(8)
        
        # Campo 6: I002/150 Antenna Rotation Period
        if 5 in fspec_fields:
            # I002/150 is Antenna Rotation Period, LSB = 1/128 s
            ant_period_raw = stream.read_bits(16)
            if ant_period_raw > 0:
                ant_period_s = ant_period_raw / 128.0
                ant_speed_rpm = 60.0 / ant_period_s
                record.extra_data['antenna_speed'] = ant_speed_rpm

        bytes_consumed = length
        return record, bytes_consumed


def is_valid_asterix_block(data: bytes, pos: int, total_len: int) -> bool:
    """Verifica estrictamente si los bytes en 'pos' forman una cabecera ASTERIX válida."""
    if pos + 3 > total_len:
        return False
    category = data[pos]
    if category not in {1, 2, 8, 10, 19, 20, 21, 34, 48, 62, 63, 65, 244, 253}:
        return False
    length = (data[pos + 1] << 8) | data[pos + 2]
    if length < 5 or length > 30000 or pos + length > total_len:
        return False
        
    fspec_pos = pos + 3
    fspec_len = 0
    fspec_valid = False
    for i in range(20):
        if fspec_pos + i >= pos + length: break
        fspec_len += 1
        if (data[fspec_pos + i] & 0x01) == 0:
            fspec_valid = True
            break
    if not fspec_valid or 3 + fspec_len > length:
        return False
    if (data[fspec_pos] & 0x80) != 0 and 3 + fspec_len + 2 > length:
        return False
    return True


def is_likely_synced(data: bytes, pos: int, length: int, total_len: int) -> bool:
    """Lookahead: Comprueba si después de este bloque existe otro bloque válido."""
    next_pos = pos + length
    if next_pos >= total_len - 32:
        return True
    if is_valid_asterix_block(data, next_pos, total_len):
        return True
    for offset in [16, 20, 24, 32, 42, 54]:
        if next_pos + offset < total_len and is_valid_asterix_block(data, next_pos + offset, total_len):
            return True
    return False


def filter_asterix_stream_by_sensor(data: bytes, selected_sensors: set, progress_hook: Optional[callable] = None) -> bytes:
    filtered_data = bytearray()
    pos = 0
    total_len = len(data)
    records_processed = 0

    while pos < total_len:
        if not is_valid_asterix_block(data, pos, total_len):
            pos += 1
            continue

        try:
            length = (data[pos + 1] << 8) | data[pos + 2]
            
            records_processed += 1
            if progress_hook and records_processed % 1000 == 0:
                progress_hook(pos, total_len)

            category = data[pos]
            fspec_pos = pos + 3
            if (data[fspec_pos] & 0x80):
                fspec_len = 1
                current_fspec_pos = fspec_pos
                while (data[current_fspec_pos] & 0x01):
                    fspec_len += 1
                    current_fspec_pos += 1
                    if current_fspec_pos >= pos + length:
                        fspec_len -= 1 
                        break
                
                sac_sic_pos = fspec_pos + fspec_len
                if sac_sic_pos + 2 <= pos + length:
                    sac = data[sac_sic_pos]
                    sic = data[sac_sic_pos + 1]
                    if (sac, sic) in selected_sensors or (category, sac, sic) in selected_sensors:
                        filtered_data.extend(data[pos:pos+length])

            if is_likely_synced(data, pos, length, total_len):
                pos += length
            else:
                pos += 1
        except (IndexError, struct.error, ValueError):
            pos += 1

    if progress_hook:
        progress_hook(total_len, total_len)

    return bytes(filtered_data)


def find_sensors_in_stream(data: bytes, progress_hook: Optional[callable] = None, min_occurrences: int = 3) -> Dict:
    """
    Analiza el flujo para encontrar sensores, categorías y el rango de tiempo (TOD).

    Args:
        data: Flujo de bytes con datos ASTERIX.
        progress_hook: Función callback para reportar progreso.
        min_occurrences: Número mínimo de apariciones para considerar válido un sensor.

    Returns:
        Dict con 'sensors', 'categories', 'start_time' y 'end_time'.
    """
    from collections import defaultdict
    sensor_counts = defaultdict(int)
    categories_found = set()
    first_time = None
    last_time = None
    
    pos = 0
    total_len = len(data)
    supported_categories = {1, 2, 21, 34, 48, 62}
    records_processed = 0

    while pos < total_len:
        if not is_valid_asterix_block(data, pos, total_len):
            pos += 1
            continue

        try:
            category = data[pos]
            length = (data[pos + 1] << 8) | data[pos + 2]
            
            records_processed += 1
            if progress_hook and records_processed % 1000 == 0:
                progress_hook(pos, total_len)

            # FSPEC empieza después del header (CAT+LEN)
            fspec_pos = pos + 3
            categories_found.add(category)
            
            if fspec_pos < pos + length:
                fspec_byte = data[fspec_pos]
                
                fspec_len = 1
                current_fspec_pos = fspec_pos
                while (data[current_fspec_pos] & 0x01):
                    fspec_len += 1
                    current_fspec_pos += 1
                    if (current_fspec_pos) >= (pos + length):
                        fspec_len -= 1
                        break
                
                # Intentar extraer SAC/SIC y TOD (Time of Day)
                item_pos = fspec_pos + fspec_len
                
                # SAC/SIC suele ser el primer ítem (bit 7 del primer octeto FSPEC)
                if (fspec_byte & 0x80) and item_pos + 2 <= pos + length:
                    sac = data[item_pos]
                    sic = data[item_pos + 1]
                    sensor_counts[(sac, sic)] += 1
                    item_pos += 2
                
                # TOD suele ser el segundo ítem en CAT 48, 34, 62 (bit 6 del primer octeto)
                # En CAT 21 es el ítem 5 (bit 3). Simplificamos para el escaneo rápido.
                has_tod = False
                if category in [48, 34, 62] and (fspec_byte & 0x40): has_tod = True
                elif category == 21 and (fspec_byte & 0x08): has_tod = True
                
                if has_tod and item_pos + 3 <= pos + length:
                    tod_raw = (data[item_pos] << 16) | (data[item_pos+1] << 8) | data[item_pos+2]
                    tod_sec = tod_raw / 128.0
                    if first_time is None: first_time = tod_sec
                    last_time = tod_sec

            pos += length
        except (IndexError, struct.error, ValueError):
            pos += 1
    
    # Filtrar sensores según el umbral de ocurrencias solicitado
    sensors_found = {sensor: count for sensor, count in sensor_counts.items() if count >= min_occurrences}
    
    if progress_hook:
        progress_hook(total_len, total_len)

    return {
        "sensors": sensors_found,
        "categories": categories_found,
        "start_time": first_time,
        "end_time": last_time
    }


def decode_asterix_stream(data: bytes, progress_hook: Optional[callable] = None, gui_progress_callback: Optional[callable] = None) -> List[AsterixRecord]:
    """
    Decodifica un flujo de datos ASTERIX completo.
    Retorna lista de AsterixRecord decodificados.

    Args:
        data: Flujo de bytes con datos ASTERIX.
        progress_hook: Función callback para reportar progreso.
                       Llamada con (posición_actual, tamaño_total, prefix, suffix).
        gui_progress_callback: Función callback para reportar progreso a la GUI.
                               Llamada con (posición_actual, tamaño_total, prefix, suffix).
    """
    records = []
    pos = 0
    total_len = len(data)
    valid_categories = {1, 2, 21, 34, 48, 62}
    
    if gui_progress_callback:
        gui_progress_callback(0, total_len, prefix='Decodificando:', suffix='Completado')
        
    while pos < total_len:
        # Análisis previo: Validar estructura y coherencia del bloque antes de procesar
        if not is_valid_asterix_block(data, pos, total_len):
            pos += 1
            continue

        category = data[pos]
        length = (data[pos + 1] << 8) | data[pos + 2]

        decoder = None
        if category == 48: decoder = CAT048Decoder
        elif category == 34: decoder = CAT034Decoder
        elif category == 21: decoder = CAT021Decoder
        elif category == 1: decoder = CAT001Decoder
        elif category == 62: decoder = CAT062Decoder
        elif category == 2: decoder = CAT002Decoder
        
        if progress_hook and (len(records) % 1000 == 0):
            progress_hook(pos, total_len)
        if gui_progress_callback and (len(records) % 1000 == 0):
            gui_progress_callback(pos, total_len, prefix='Decodificando:', suffix='Completado')

        if decoder:
            try:
                record, consumed = decoder.decode(data, pos)
                
                # Validación estricta: Descartar paquetes con Rho (Rango) o Theta (Azimut) negativos
                if (record.range_slant is not None and record.range_slant < 0) or \
                   (record.azimuth is not None and record.azimuth < 0):
                    pos += length
                    continue
                    
                records.append(record)
                pos += length
            except Exception as e:
                # Si falla la decodificación interna, no confiamos en la longitud
                # y avanzamos bit a bit para buscar el siguiente paquete válido
                pos += 1
        else:
            pos += length

    # Llamada final para asegurar que la barra de progreso llegue al 100%
    if progress_hook:
        progress_hook(total_len, total_len)
    if gui_progress_callback:
        gui_progress_callback(total_len, total_len, prefix='Decodificando:', suffix='Completado')

    return records
