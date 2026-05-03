"""
DOCUMENTACIÓN TÉCNICA - ASTERIX Analyzer

Especificación detallada de la implementación, algoritmos y fórmulas matemáticas.
"""

# ============================================================================
# 1. ESTRUCTURA DE DATOS ASTERIX
# ============================================================================

"""
ASTERIX utiliza una estructura binaria estándar:

┌─────────────────────────────────────────────────────────┐
│ Data Record Header (CAT 21 v2.4 supports up to 7 FSPEC bytes)│
├─────┬────────┬──────────────────────────────────────────┤
│ CAT │ LEN    │ FSPEC      | Data Fields                 │
│ 1B  │ 2B     │ 1-7B (CAT21) | Variable                  │
└─────┴────────┴──────────────────────────────────────────┘

- CAT (Category): Identificador del tipo de mensaje (1B)
- LEN (Length): Tamaño total del record incluyendo header (2B, big-endian)
- FSPEC (Field Specification): Bitmap que indica qué campos opcionales están presentes
- Data Fields: Los campos variables según FSPEC

FSPEC es una secuencia de bytes donde:
- Bits 0-6 indican presencia de campos
- Bit 7 = 1: Hay más bytes FSPEC (continuación)
- Bit 7 = 0: Última byte de FSPEC

Ejemplo FSPEC 0xF8:
  Binario: 11111000
  - Bit 7 = 1: Hay más bytes FSPEC
  - Bits 0-6 = 1111000: Campos 0-6 presentes
"""


# ============================================================================
# 2. DECODIFICACIÓN BIT A BIT (BitStream)
# ============================================================================

"""
La clase BitStream implementa lectura de bits arbitrarios desde un flujo de bytes.

Algoritmo read_bits(n):
  1. Calcular posición de byte: byte_pos = pos // 8
  2. Calcular offset en bit: bit_offset = pos % 8
  3. Leer n bits empezando desde la posición actual
  4. Manejar bordes de bytes
  5. Actualizar posición: pos += n

Ejemplo: Leer 4 bits de 0b11001010 01010101
  - Posición inicial: bit 0
  - Leer bits 7-4: 0b1100 = 12 (decimal)
  - Nueva posición: bit 4

Ventajas:
- Permite decodificar campos ASTERIX de tamaño no múltiple de 8 bits
- Manejo automático de boundaries
- Compatible con FSPEC de tamaño variable
"""


# ============================================================================
# 3. FACTORES DE ESCALA (LSB - Least Significant Bit)
# ============================================================================

"""
ASTERIX define factores de escala para convertir valores enteros a unidades reales:

POSICIÓN (Latitud/Longitud WGS-84):
  Estándar (I021/130): LSB = 180° / 2^23 (~2.1457e-05°)
  Alta Resolución (I021/131): LSB = 180° / 2^30 (~1.6764e-07°)
  
  Conversión Estándar: lat_grados = lat_raw * (180 / 2^23)
  Conversión Alta Res: lat_grados = lat_raw * (180 / 2^30)
  
  Ejemplo CAT 021/130 con valor raw 67108864:
  lat_grados = 67108864 * (180 / 8388608) ≈ 1.44°

VELOCIDAD Y RUMBOS (CAT 021 v2.4):
  Ground Speed (I021/160): LSB = 2^-14 NM/s (≈ 0.22 knots)
  Track Angle (I021/160): LSB = 360° / 2^16 (≈ 0.0055°)
  Vertical Rate (I021/155/157): LSB = 6.25 feet/minute
  
TIEMPOS (CAT 021 v2.4):
  Estándar (I021/073/140): LSB = 1/128 s
  Alta Precisión (I021/071/075): LSB = 2^-30 s

AZIMUT:
  LSB = 360° / 2^16
  Conversión: azimuth_grados = azimuth_raw * (360 / 2^16)
  
  Ejemplo CAT 048/040 con valor raw 32768:
  azimuth_grados = 32768 * (360 / 65536) = 180°

RANGO OBLICUO (Slant Range):
  LSB = 1/256 NM (millas náuticas)
  Conversión: range_nm = range_raw * (1 / 256)
  
  Ejemplo CAT 048/040 con valor raw 10240:
  range_nm = 10240 / 256 = 40 NM

NIVEL DE VUELO (Flight Level):
  LSB = 1/4 FL (o 25 pies)
  Conversión: flight_level = flight_level_raw * (1 / 4)
  
  Ejemplo CAT 048/090 con valor raw 1000:
  flight_level = 1000 / 4 = 250 FL = 25,000 pies
"""


# ============================================================================
# 4. CONVERSIÓN SLANT RANGE A GROUND RANGE
# ============================================================================

"""
El Slant Range es la distancia oblicua desde el radar al target.
El Ground Range es la distancia horizontal sobre el terreno.

Ambos se relacionan por el Flight Level (altitud del target):

Geometría:
    Target (alt = FL * 100 pies)
        *
       /|
      / | height
     /  |
    /   |
   /____|_____ Ground
  Radar
      ground_range

Fórmula (Pitágoras):
  ground_range² + height² = slant_range²
  ground_range = √(slant_range² - height²)

Pseudocódigo:
  slant_range_ft = slant_range_nm * 6076.118  # Convertir NM a pies
  target_height_ft = flight_level * 100
  height_diff = target_height_ft - radar_elevation
  
  if slant_range_ft > height_diff:
    ground_range_ft = √(slant_range_ft² - height_diff²)
  else:
    ground_range_ft = slant_range_ft
  
  ground_range_nm = ground_range_ft / 6076.118

Ejemplo:
  Slant Range: 30 NM = 182284.54 pies
  Flight Level: 250 (= 25000 pies)
  Radar height: 0 pies
  Height diff: 25000 pies
  
  Ground range = √(182284.54² - 25000²) 
               = √(33227345149 - 625000000)
               = √32602345149
               ≈ 180,562 pies
               ≈ 29.7 NM
"""


# ============================================================================
# 5. CONVERSIÓN POLARES A WGS-84 (Great Circle)
# ============================================================================

"""
Convierte coordenadas polares (Azimut, Distancia) a WGS-84 (Lat, Lon).

Inputs:
  - Posición del radar: (lat1, lon1) en grados
  - Azimut: dirección en grados (0°=Norte, 90°=Este, 180°=Sur, 270°=Oeste)
  - Distancia horizontal: en millas náuticas

Algoritmo (Great Circle Distance):

1. Convertir a radianes:
   lat1_rad = rad(lat1)
   lon1_rad = rad(lon1)
   az_rad = rad(azimuth)
   d_angular = (distancia_m) / R_tierra

2. Calcular latitud de destino (Latitud2):
   sin(lat2) = sin(lat1)*cos(d) + cos(lat1)*sin(d)*cos(az)

3. Calcular longitud de destino (Longitud2):
   tan(Δlon) = sin(az)*sin(d)*cos(lat1) / (cos(d) - sin(lat1)*sin(lat2))

4. Convertir a grados:
   lat2 = rad_inversa(lat2_rad)
   lon2 = rad_inversa(lon2_rad)

Parámetros WGS-84:
  R_tierra (Radio ecuatorial) = 6,378,137 metros
  1 NM = 1,852 metros

Ejemplo:
  Radar en: 40.4167°N, 3.7038°W
  Azimut: 45° (Noreste)
  Distancia: 10 NM = 18,520 metros
  
  d_angular = 18520 / 6378137 ≈ 0.002903 radianes
  
  sin(lat2) = sin(40.4167°)*cos(0.002903) + cos(40.4167°)*sin(0.002903)*cos(45°)
            ≈ 0.6477
  lat2 ≈ 40.419° (aumentó)
  
  Similar para lon2, resultado aproximadamente:
  Target en: 40.419°N, 3.696°W
"""


# ============================================================================
# 6. FÓRMULA DE VINCENTY (Mayor Precisión)
# ============================================================================

"""
La fórmula de Vincenty es más precisa para distancias largas.

Se utilizan en geo_tools.py con vincenty_forward():

Parámetros WGS-84:
  a = 6,378,137.0 metros (radio ecuatorial)
  b = 6,356,752.314245 metros (radio polar)
  e² = 0.00669437999014132 (excentricidad²)

Ventajas sobre Great Circle:
- Tiene en cuenta el achatamiento de la Tierra
- Mayor precisión para distancias > 100 km
- Más computacionalmente intensivo

Para nuestro caso (vigilancia de tráfico aéreo):
- Distancias típicas: 10-100 NM
- Great Circle es suficientemente preciso
- Vincenty activable en config.py (use_vincenty = True)
"""


# ============================================================================
# 7. CATEGORÍAS ASTERIX Y CAMPOS IMPLEMENTADOS
# ============================================================================

"""
┌────────┬──────────────────────┬─────────────────────────────┐
│ CAT    │ Nombre               │ Campos Implementados        │
├────────┼──────────────────────┼─────────────────────────────┤
│ 048    │ Monoradar Mode S     │ I048/010, 040, 042, 070, 080, 090, 200, 250│
│ 001    │ Monoradar Estándar   │ I001/010, 020, 040, 070, 141│
│ 021    │ ADS-B (v2.4)         │ I021/010, 040, 070, 080, 130, 131, 140, 145, 160, 161, 170│
│ 034    │ Service Messages     │ I034/010, 120 (Pos. Radar)  │
│ 062    │ System Track Data    │ I062/010, 040, 100, 105, 380│
│ 002    │ Configuración Radar  │ I002/010, 150 (Vel. Antena) │
└────────┴──────────────────────┴─────────────────────────────┘

CAT 048 (Monoradar Mode S):
  I048/010: Data Source ID (SAC/SIC) - 2 bytes
  I048/040: Measured Position Polar (Azimuth, Range) - 4 bytes
  I048/042: Calculated Position Cartesian (X, Y) - 4 bytes (LSB 1/128 NM)
  I048/070: Mode-3/A Code - 2 bytes
  I048/080: Mode-C Code - 2 bytes
  I048/090: Flight Level - 2 bytes
  I048/140: Time of Day - 3 bytes
  I048/200: Calculated Track Velocity Polar - 4 bytes
  I048/250: Track Status - Variable

CAT 021 (ADS-B v2.4):
  I021/010: Data Source ID - 2 bytes
  I021/130: Position WGS-84 (Lat, Lon) - 6 bytes (LSB 180/2^23)
  I021/131: High-Res Position WGS-84 - 8 bytes (LSB 180/2^30)
  I021/080: Mode S Code - 3 bytes
  I021/170: Target Identification (Callsign) - 6 bytes
  I021/070: Mode-3/A Code (Squawk) - 2 bytes
  I021/145: Flight Level - 2 bytes
  I021/140: Geometric Altitude - 2 bytes (LSB 6.25 ft)
  I021/160: Ground Vector (GS, TA) - 4 bytes

CAT 034 (Service Messages - Pos. Radar):
  I034/010: Data Source ID - 2 bytes
  I034/030: Time of Day - LSB 1/128s
  I034/120: 3D Radar Position (Lat, Lon, Height) - 10 bytes
  
  CRÍTICO: Este es el único mensaje que contiene la posición del radar.
  Según v1.26, Lat/Lon usan LSB 180/2^23 y Height LSB 25ft.
"""

CAT 062 (System Track Data):
  I062/010: Data Source ID - 2 bytes
  I062/040: Track Number - 2 bytes
  I062/100: Calculated Track Position (WGS-84) - 8 bytes (LSB 180/2^31, Ed. 1.18)
  I062/105: Calculated Track Position (Cartesian) - 8 bytes (LSB 0.5m)
  I062/380: Aircraft Derived Data - Campo compuesto variable que incluye:
    - Target Address (Mode S)
    - Target Identification (Callsign)
    - Mode-3/A Code
    - Flight Level


# ============================================================================
# 8. ESTRUCTURA DE DATOS INTERNA
# ============================================================================

NOTAS DE IMPLEMENTACIÓN (CAT 021 v2.4):
- **Conversión de Signo**: Campos como Vertical Rate (I021/155) o Latitud (I021/130) deben tratarse como enteros con signo (Complemento a 2).
- **Prioridad de Posición**: Si I021/131 (High Res) está presente, debe tener prioridad sobre I021/130.
- **Formatos de Tiempo**: Diferenciar entre Time of Applicability (I021/140) y Time of Message Reception (I021/071/073/075).

```python
def to_signed(val, bits):
    if val & (1 << (bits - 1)):
        val -= (1 << bits)
    return val
```

"""
AsterixRecord: Almacena un mensaje decodificado

  Atributos obligatorios:
    - category: int (1-254)
    - sac: System Area Code (0-255)
    - sic: System Identification Code (0-255)
  
  Atributos opcionales:
    - timestamp: float (segundos desde medianoche)
    - latitude: float (grados decimales)
    - longitude: float (grados decimales)
    - altitude: float (pies)
    - mode_3a: int (4 dígitos octales)
    - azimuth: float (grados)
    - range_slant: float (millas náuticas)
    - flight_level: int (en 1/4 FL)
    - radar_position: tuple (lat, lon, elevation)
    - extra_data: dict (campos adicionales por categoría)

SensorRegistry: Mantiene registro de sensores únicos

  Por cada combinación (SAC, SIC):
    - sac: int
    - sic: int
    - latitude: float (None si desconocida)
    - longitude: float (None si desconocida)
    - elevation: float (en pies)
    - records_count: int (número de registros de este sensor)

TargetProcessor: Procesa targets individuales

  Convierte cada AsterixRecord a dict procesado:
    - Mantiene todos los datos originales
    - Añade conversiones a WGS-84
    - Calcula slant→ground range
    - Añade referencias a radar
"""


# ============================================================================
# 9. FLUJO DE PROCESAMIENTO
# ============================================================================

"""
Secuencia de ejecución en main.py:

1. CARGA DE ARCHIVO
   load_pcap() o load_ast()
   → Extrae datos ASTERIX crudos en bytes

2. DECODIFICACIÓN (decode_asterix_stream)
   → Parsea estructura CAT/LEN/FSPEC
   → Decodifica campos según categoría
   → Retorna lista de `AsterixRecord`

3. REGISTRO DE SENSORES
   Para cada record:
     → Registra SAC/SIC en SensorRegistry
     → Si tiene posición (CAT 034), la almacena
   
4. PROCESAMIENTO DE TARGETS (TargetProcessor)
   Para cada record:
     → Si es target con coordenadas polares (CAT 048/001)
     → Si sensor tiene posición conocida
     → Calcula slant→ground range
     → Convierte polares→WGS-84
     → Guarda resultado en formato procesado

5. EXPORTACIÓN
   Filtra registros con coordenadas válidas
   → KML: Organiza por sensor, añade etiquetas
   → GeoJSON: Feature collection con propiedades
   → CSV: Tabla para análisis
   → Reporte: Estadísticas de cobertura
"""


# ============================================================================
# 10. EJEMPLO DE DECODIFICACIÓN BYTE A BYTE
# ============================================================================

"""
Suponer archivo.ast con datos CAT 048:

Hexadecimal:    30 00 1B F8 01 01 92 F4 20 00 02 AB A7 ...
Decimal:        48  0  27 248 1  1  ...
Binario:        00110000 00000000 00011011

Paso 1: Leer header
  CAT = 0x30 = 48 (CAT 048)
  LEN = 0x001B = 27 bytes

Paso 2: Parsear FSPEC
  FSPEC byte = 0xF8 = 11111000 (binario)
  Bit 7=1: Hay continuación
  Bits 0-6: 1111000 = Campos 0-6 presentes
  
Paso 3: Leer campos presentes
  Campo 0 (I048/010): SAC=0x01, SIC=0x01
  Campo 1 (I048/140): TOD=... (24 bits)
  Campo 2 (I048/020): Descriptor=...
  ...y así sucesivamente

Paso 4: Convertir valores con LSB
  Range raw = 0xXXXX → range_nm = raw / 256
  Azimuth raw = 0xXXXX → azimuth_deg = raw * (360/65536)
  Mode3A raw = 0xXXXX → mode3a = raw & 0x0FFF
"""


if __name__ == "__main__":
    print("""
    ╔═══════════════════════════════════════════════════════════════╗
    ║          DOCUMENTACIÓN TÉCNICA - ASTERIX Analyzer              ║
    ╚═══════════════════════════════════════════════════════════════╝
    
    Este módulo contiene documentación técnica completa.
    Consulta los comentarios para:
    
    1. Estructura binaria de ASTERIX
    2. Algoritmo de lectura bit a bit
    3. Factores de escala (LSB)
    4. Conversiones geoespaciales
    5. Fórmulas matemáticas
    6. Especificación de categorías
    7. Flujo de procesamiento
    8. Ejemplos de decodificación
    
    Para información de uso, consulta README.md
    """)
