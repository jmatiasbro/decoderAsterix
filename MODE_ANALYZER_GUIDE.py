#!/usr/bin/env python3
"""
MODE A/C DETECTION ANALYZER - DOCUMENTATION

Este módulo analiza información de Modo A (3/A Code), Modo C (Flight Level),
código Squawk, y calcula probabilidades de detección desde paquetes ASTERIX.

CARACTERÍSTICAS PRINCIPALES
==========================

1. DETECCIÓN DE MODO A
   - Extrae código Mode 3/A (Squawk) del paquete ASTERIX
   - Valida disponibilidad del dato
   - Calcula probabilidad de detección: 95% si presente

2. DETECCIÓN DE MODO C
   - Extrae Flight Level (FL) del paquete ASTERIX
   - Modo C se considera "presente" si hay Modo A + FL
   - Calcula probabilidad de detección: 90% si presente

3. CÓDIGO SQUAWK
   - Representa el código Mode 3/A
   - Se muestra en formato octal (estándar aviación) y decimal
   - Ejemplo: 7654 (octal) = 4012 (decimal)

4. PROBABILIDAD COMBINADA
   - Calcula P(A AND C) = P(A) * P(C|A)
   - Solo si ambos modos están presentes
   - Ejemplo: 95% * 90% = 85.5%

5. NIVEL DE CONFIANZA
   - HIGH: Modo A + Modo C + Flight Level
   - MEDIUM: Solo Modo A o Modo A + FL sin Modo C
   - LOW: Sin datos de modo

USO DESDE MENÚ PRINCIPAL
========================

1. Cargar archivo (opción 1)
2. Decodificar datos (opción 4)
3. Acceder a análisis Modo A/C (opción 9)
4. Seleccionar visualización:
   - Ver todos los registros
   - Ver solo estadísticas
   - Exportar a JSON/CSV
   - Ver registro específico

EJEMPLO DE SALIDA
=================

======================================================================
RECORD #1 - MODE A/C ANALYSIS
======================================================================

Mode A (3/A Code):
  Detected: YES
  Squawk Code: 7654 (octal) / 4012 (decimal)
  Probability: 95.00%

Mode C (Flight Level):
  Detected: YES
  Flight Level: FL25000
  Probability: 90.00%

Combined Detection (Mode A + Mode C):
  P(A AND C): 85.50%

Confidence Level: HIGH
======================================================================

ESTADÍSTICAS GENERALES
======================

Total Records Analyzed: 3
  - Mode A Only: 1
  - Mode C Only: 0
  - Mode A AND C: 2
  - No Mode Data: 0

Average Probabilities:
  - Mode A: 95.00%
  - Mode C: 90.00%
  - Combined (A AND C): 85.50%

Squawk Codes Found: 2
  Códigos únicos encontrados en todos los registros

Flight Levels Found: 2
  Niveles de vuelo únicos encontrados

EXPORTACIÓN DE DATOS
===================

1. JSON (mode_analysis.json)
   - Estructura completa de datos
   - Estadísticas y detalles de cada registro
   - Fácil integración con otras herramientas

2. CSV (mode_analysis.csv)
   - Formato tabular
   - Compatible con Excel, QGIS, etc.
   - Columnas: Record#, Mode_A_Detected, Mode_C_Detected, etc.

EJEMPLO DE USO PROGRAMÁTICO
============================

from mode_analyzer import ModeAnalyzer

# Crear analizador
analyzer = ModeAnalyzer()

# Analizar registros decodificados
records = [...]  # Desde decode_asterix_stream()
results = analyzer.analyze_batch(records)

# Mostrar estadísticas
analyzer.display_statistics()

# Exportar
analyzer.export_to_json("mi_analisis.json")
analyzer.export_to_csv("mi_analisis.csv")

ESTRUCTURA DE DATOS
===================

Cada registro analizado contiene:

{
  "mode_a_detected": true/false,        # Modo A está presente?
  "mode_c_detected": true/false,        # Modo C está presente?
  "squawk_code": 4012,                  # Código Mode 3/A (decimal)
  "flight_level": 25000,                # Flight Level en pies/100
  "mode_3a": 4012,                      # Valor Mode 3/A crudomode_a_probability": 0.95,           # Probabilidad Modo A
  "mode_c_probability": 0.90,           # Probabilidad Modo C
  "combined_probability": 0.855,        # Probabilidad combinada
  "confidence_level": "HIGH"            # Nivel de confianza
}

NOTAS TÉCNICAS
==============

1. Squawk en formato octal:
   - Estándar en aviación
   - Rango: 0000 a 7777 (octal)
   - Equivalente: 0 a 4095 (decimal)

2. Flight Level:
   - En pies/100
   - Ejemplo: FL25000 = 25,000 pies
   - Rango típico: FL100 a FL430

3. Probabilidades:
   - Basadas en disponibilidad de datos
   - Valores fijos: 95% (Modo A), 90% (Modo C)
   - Pueden ajustarse según necesidad

4. Campos ASTERIX utilizados:
   - I048/070: Mode-3/A Code (Squawk)
   - I048/090: Flight Level

RESOLUCIÓN DE PROBLEMAS
======================

¿No extrae datos de Modo A/C?
  → Verificar que los registros ASTERIX contengan estos campos
  → Usar opción "Ver registro específico" para debuggear

¿CSV no se importa correctamente?
  → Verificar encoding: UTF-8
  → Usar delimitador: coma (,)

¿Probabilidades no suman 100%?
  → Es normal: no es suma, es multiplicación condicional
  → P(A AND C) ≠ P(A) + P(C)
"""

if __name__ == "__main__":
    print(__doc__)
