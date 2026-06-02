#!/usr/bin/env python3
"""
FASE 3: AUDITORÍA DE CAMPOS I062/380 Y I062/390

Identifica los problemas de Offset Drift y propone la solución.
"""

def audit_issues():
    """Audita el código actual de _decode_cat062 para campos 380 y 390."""
    
    print("=" * 70)
    print("FASE 3: AUDITORÍA DE CAMPOS I062/380 Y I062/390")
    print("=" * 70)
    
    # =============================================================
    # ISSUE 1: I062/380 - sub_lengths incompleto y subcampos dinámicos
    # =============================================================
    print("\n[ISSUE 1] I062/380 Aircraft Derived Data (FRN 22, fspec[21])")
    print("-" * 50)
    
    print("\n  CÓDIGO ACTUAL:")
    print("""    sub_lengths = {
        0: 3, 1: 6, 2: 2, 3: 2, 4: 2, 5: 2, 6: 2, 7: 2, 8: 2, 9: 2,
        10: 2, 11: 2, 12: 2, 13: 2, 14: 1, 15: 1, 16: 1, 17: 2, 18: 1, 19: 1, 20: 8, 21: 1, 22: 1
    }
    for i in range(len(sub_fspec)):
        if sub_fspec[i]:
            skip_len = sub_lengths.get(i, 1)
            offset += skip_len""")
    
    print("\n  PROBLEMAS IDENTIFICADOS:")
    problems_380 = [
        ("Subfield #7 (TIS, index 6)", "Es VARIABLE (con FX bits), no fixed 2B",
         "Según XML: <Variable><Fixed length='1'>... FX ...</Fixed></Variable>"),
        ("Subfield #8 (TID, index 7)", "Es REPETITIVE (15B c/u), no fixed 2B",
         "Según XML: <Repetitive><Fixed length='15'>...</Fixed></Repetitive>"),
        ("Subfield #24 (MB, index 24)", "Es REPETITIVE (BDS, 8B c/u), no fixed 1B",
         "Según XML: <Repetitive><BDS/></Repetitive>"),
        ("Faltan subfields 23-27", "Solo cubre hasta index 22, faltan PUN, MB, IAS, MNO, BPS",
         "Subfields #23(PUN=1B), #24(MB=rep), #25(IAS=2B), #26(MNO=2B), #27(BPS=2B)"),
    ]
    for name, issue, detail in problems_380:
        print(f"  ❌ {name}")
        print(f"     Problema: {issue}")
        print(f"     {detail}")
    
    # =============================================================
    # ISSUE 2: I062/390 - NO salta los subcampos después del indicador
    # =============================================================
    print("\n[ISSUE 2] I062/390 Flight Plan Related Data (FRN 23, fspec[22])")
    print("-" * 50)
    
    print("\n  CÓDIGO ACTUAL:")
    print("""    if len(fspec) > 22 and fspec[22]:
        sub_byte = payload[offset]
        offset += 1
        while (sub_byte & 0x01) and offset < len(payload):
            sub_byte = payload[offset]
            offset += 1
        # OFFSET DRIFT: ¡no se salta el contenido de los subcampos!""")
    
    print("\n  PROBLEMAS IDENTIFICADOS:")
    print("""  ❌ Solo lee los bytes del indicador (primary subfield de 3 bytes con FX)
     pero NO avanza el offset por el contenido de los subcampos.
     
     Ejemplo: Si el indicador marca CSN+WTC+DEP presentes, hay que saltar
     7+1+4 = 12 bytes de datos reales después del indicador.
     
     El XML define 18 subcampos con longitudes:
       1.  TAG (2B)   2. CSN (7B)   3. IFI (4B)   4. FCT (1B)
       5.  TAC (4B)   6. WTC (1B)   7. DEP (4B)   8. DST (4B)
       9.  RDS (3B)  10. CFL (2B)  11. CTL (2B)
      12. TOD (Repetitive, 4B c/u)
      13. AS  (6B)   14. STS (1B)  15. STD (7B)  16. STA (7B)
      17. PEM (2B)   18. PEC (7B)""")
    
    # =============================================================
    # IMPACTO
    # =============================================================
    print("\n[IMPACTO DEL OFFSET DRIFT]")
    print("-" * 50)
    print("""  Ambos errores provocan que offset quede DESALINEADO al llegar a:
    - I062/185 Calculated Track Velocity (FRN 14, fspec[13])
    - Cualquier campo posterior a FRN 22 o FRN 23
  
  Si I062/380 o I062/390 están presentes con datos reales, el offset
  avanza menos de lo necesario, y los campos posteriores se leen con
  datos incorrectos (bytes equivocados), causando:
    - Velocidades inválidas (valores fuera de rango)
    - Posiciones erróneas
    - "⚠️ Offset Drift detectado en FRN X" en el log""")
    
    print("\n" + "=" * 70)
    print("SOLUCIÓN PROPUESTA")
    print("=" * 70)
    print("""
  1. I062/380: Reemplazar sub_lengths fijo por dispatch dinámico:
     - Subcampos Fixed: saltar N bytes según tabla completa
     - Subcampo TIS (idx 6): Variable con FX loop
     - Subcampo TID (idx 7): Repetitive, leer byte de repetición + N*15
     - Subcampo MB  (idx 24): Repetitive, leer byte de repetición + N*8
     - Extender tabla hasta subfield #27
  
  2. I062/390: Después del indicador primario:
     - Mapear bits del indicador a longitudes de subcampo
     - Saltar datos de cada subcampo presente
     - Subcampo TOD (idx 11): Repetitive, leer byte de repetición + N*4
  """)

if __name__ == '__main__':
    audit_issues()
