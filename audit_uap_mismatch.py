#!/usr/bin/env python3
"""
Auditoría CRÍTICA: Mapeo FRN incorrecto en _decode_cat062

El código actual asigna FRN en orden arbitrario, pero el XML define
un orden específico que NO coincide.

Causa raíz de 'Offset Drift detectado en FRN 16/14':
  - I062/185 (Velocity) NO es FRN 14 como asume el código
  - I062/185 es FRN 7 (fspec[6])
  - Al procesar campos FRN 1-13 con longitudes equivocadas,
    el offset se desvía y la velocidad se lee de datos incorrectos

Comparación XML UAP vs Código Actual:
"""

# UAP real del XML asterix_cat062_1_18.xml
def get_xml_uap():
    return [
        (1,  'I062/010 SAC/SIC', '2'),
        (2,  'Spare', '-'),
        (3,  'I062/015 Service ID', '1'),
        (4,  'I062/070 ToT', '3'),
        (5,  'I062/105 WGS-84 Pos', '8'),
        (6,  'I062/100 Cartesian Pos', '6'),
        (7,  'I062/185 Velocity', '4'),
        # FX
        (8,  'I062/210 Acceleration', '2'),
        (9,  'I062/060 Mode 3/A', '2'),
        (10, 'I062/245 Target ID', '7'),
        (11, 'I062/380 Aircraft Derived Data', '1+'),
        (12, 'I062/040 Track Number', '2'),
        (13, 'I062/080 Track Status', '1+'),
        (14, 'I062/290 Track Update Ages', '1+'),
        # FX
        (15, 'I062/200 Mode of Movement', '1'),
        (16, 'I062/295 Track Data Ages', '1+'),
        (17, 'I062/136 Measured FL', '2'),
        (18, 'I062/130 Geo Altitude', '2'),
        (19, 'I062/135 Baro Altitude', '2'),
        (20, 'I062/220 Climb/Descent', '2'),
        (21, 'I062/390 Flight Plan Data', '1+'),
        # FX
        (22, 'I062/270 Target Size', '1+'),
        (23, 'I062/300 Vehicle Fleet ID', '1'),
        (24, 'I062/110 Mode 5 Data', '1+'),
        (25, 'I062/120 Mode 2 Code', '2'),
        (26, 'I062/510 Comp Track No', '3+'),
        # FX
        (27, 'I062/500 Est Accuracies', '1+'),
        (28, 'I062/340 Measured Info', '1+'),
        # FX
        (29, 'Spare', '-'),
        (30, 'Spare', '-'),
        (31, 'Spare', '-'),
        (32, 'Spare', '-'),
        (33, 'Spare', '-'),
        (34, 'RE (Reserved Expansion)', '1+'),
        (35, 'SP (Special Purpose)', '1+'),
    ]

def get_code_frn_mapping():
    """Lo que el código actual ASIGNA a cada FRN."""
    return {
        1:  'I062/010 SAC/SIC (2B) [CORRECTO]',
        2:  'I062/015 Service ID (1B) [DEBERÍA SER Spare FRN2]',
        3:  'I062/040 Track Number (2B) [DEBERÍA SER ServiceID FRN3]',
        4:  'I062/060 Mode 3/A (2B) [DEBERÍA SER ToT FRN4]',
        5:  'I062/070 ToT (3B) [DEBERÍA SER WGS84 FRN5]',
        6:  'I062/080 Track Status (var) [DEBERÍA SER Cartesian FRN6]',
        7:  'I062/100 Cartesian Pos (6B) [DEBERÍA SER Velocity FRN7]',
        8:  'I062/105 WGS-84 Pos (8B) [DEBERÍA SER Acceleration FRN8]',
        9:  'I062/110 Mode 5 (var) [DEBERÍA SER Mode3A FRN9]',
        10: 'I062/120 Mode 2 (2B) [DEBERÍA SER TargetID FRN10]',
        11: 'I062/130 Geo Alt (2B) [DEBERÍA SER I380 FRN11]',
        12: 'I062/135 Baro Alt (2B) [DEBERÍA SER TrackNo FRN12]',
        13: 'I062/136 Meas FL (2B) [DEBERÍA SER TrackStatus FRN13]',
        14: 'I062/185 Velocity (4B) [DEBERÍA SER I290 FRN14]',
        15: 'I062/200 ModeMov (1B) [CORRECTO]',
        16: 'I062/210 Accel (2B) [DEBERÍA SER I295 FRN16]',
        17: 'I062/220 ROCD (2B) [DEBERÍA SER MeasFL FRN17]',
        18: 'I062/245 Target ID (7B) [DEBERÍA SER GeoAlt FRN18]',
        19: 'I062/270 Target Size (var) [DEBERÍA SER BaroAlt FRN19]',
        20: 'I062/290 Track Ages (var) [DEBERÍA SER ROCD FRN20]',
        21: 'I062/300 Mode3A (2B) [DEBERÍA SER I390 FRN21]',
        22: 'I062/380 Aircraft Data (1+) [DEBERÍA SER TargetSize FRN22]',
        23: 'I062/390 Flight Plan (1+) [DEBERÍA SER FleetID FRN23]',
        24: '- (spare) [DEBERÍA SER Mode5 FRN24]',
        25: '- (spare) [DEBERÍA SER Mode2 FRN25]',
        26: '- (spare) [DEBERÍA SER CompTrack FRN26]',
        27: '- (spare) [DEBERÍA SER Accuracies FRN27]',
        28: '- (spare) [DEBERÍA SER I340 FRN28]',
        29: '- (spare) [CORRECTO (spare)]',
        30: '- (spare) [CORRECTO (spare)]',
        31: '- (spare) [CORRECTO (spare)]',
        32: '- (spare) [CORRECTO (spare)]',
        33: '- (spare) [CORRECTO (spare)]',
        34: 'RE [CORRECTO]',
        35: 'SP [CORRECTO]',
    }

if __name__ == '__main__':
    print("=" * 80)
    print("AUDITORÍA CRÍTICA: DESALINEACIÓN FRN EN _decode_cat062")
    print("=" * 80)
    print()
    print(f"{'FRN':>5} {'XML UAP':<30} {'CÓDIGO ACTUAL':<30}")
    print("-" * 70)
    
    xml_uap = get_xml_uap()
    code_map = get_code_frn_mapping()
    
    for frn, xml_name, xml_len in xml_uap:
        code_item = code_map.get(frn, 'NO DEFINIDO')
        match = '✅' if (xml_name.split()[0] in code_item) else '❌'
        print(f"{frn:>5} {xml_name:<30} {code_item:<30} {match}")
    
    print()
    print("=" * 80)
    print("IMPACTO: Cuando los datos reales usan el UAP del XML,")
    print("el código interpreta campos con longitudes equivocadas.")
    print("El offset se desvía progresivamente hasta causar:")
    print('  "\"Offset Drift detectado en FRN X. Buffer too small...\""')
    print()
    print("SOLUCIÓN: Reescribir _decode_cat062 con el mapeo FRN correcto.")
    print("=" * 80)
