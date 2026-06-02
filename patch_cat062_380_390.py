#!/usr/bin/env python3
"""
FASE 3: PARCHE DE SEGURIDAD PARA I062/380 Y I062/390

Corrige el Offset Drift causado por:
  1. I062/380: sub_lengths incompleto y subcampos dinámicos (Variable/Repetitive)
  2. I062/390: solo lee el indicador pero NO el contenido de los subcampos
"""

REPLACEMENT_380 = '''
            # FRN 22 (fspec[21]): I062/380 Aircraft Derived Data (Compound)
            current_frn = 22
            if len(fspec) > 21 and fspec[21]:
                if offset >= len(payload): raise IndexError("Buffer too small for I062/380 FSPEC")
                sub_fspec, offset = read_fspec(payload, offset)
                '''

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
                7: 0,   # TIS - handled as Repetitive above
                8: 2,   # COM - Communications (2B)
                9: 2,   # SAB - Status ADS-B (2B)
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
            offset += skip_len'''

# I062/390: Complete rewrite to skip subfield content
REPLACEMENT_390 = '''
            # FRN 23 (fspec[22]): I062/390 Flight Plan Related Data (Compound)
            current_frn = 23
            if len(fspec) > 22 and fspec[22]:
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
                                if length == -1:  # Repetitive
                                    if offset + 1 > len(payload):
                                        raise IndexError(f"Buffer too small for I062/390 TOD rep")
                                    rep = payload[offset]
                                    offset += 1
                                    if offset + rep * 4 > len(payload):
                                        raise IndexError(f"Buffer too small for I062/390 TOD ({rep}x4B)")
                                    offset += rep * 4
                                else:
                                    if offset + length > len(payload):
                                        raise IndexError(f"Buffer too small for I062/390 subfield bit {bit_idx} ({length}B)")
                                    offset += length
                            else:
                                # Bit beyond known subfields - skip 1 byte
                                if offset + 1 > len(payload): break
                                offset += 1
                        bit_idx += 1
                    # FX bit is bit 0 - we already stopped at the last byte with FX=0'''

if __name__ == '__main__':
    print("PARCHE GENERADO. Usar replace_in_file en native_asterix.py")
    print("\nBloque I062/380 a reemplazar (desde 'FRN 22' hasta antes de 'FRN 23'):")
    print("-" * 50)
    print(REPLACEMENT_380)
    print("\nBloque I062/390 a reemplazar (desde 'FRN 23' hasta antes de 'FRN 24'):")
    print("-" * 50)
    print(REPLACEMENT_390)
