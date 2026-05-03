"""
EJEMPLOS DE USO - ASTERIX Analyzer

Este archivo contiene ejemplos prácticos de cómo usar la herramienta
de análisis ASTERIX en diferentes escenarios.
"""

# ============================================================================
# EJEMPLO 1: Análisis Básico desde Línea de Comandos
# ============================================================================

# Comando simple para procesar un archivo PCAP:
# 
# $ python main.py mi_archivo.pcap
#
# Esto genera automáticamente:
# - output/asterix_data.kml (para Google Earth)
# - output/asterix_data.geojson (para QGIS)
# - output/asterix_data.csv (tabla de análisis)
# - output/analysis_report.txt (estadísticas)


# ============================================================================
# EJEMPLO 2: Análisis con Posición Manual del Radar
# ============================================================================

# Si el archivo PCAP no contiene mensaje CAT 034 con posición del radar,
# puedes especificar manualmente:
#
# $ python main.py datos.ast \
#       --sensor 1 1 40.416775 -3.703790 \
#       --elevation 2000 \
#       --output resultados/
#
# Parámetros:
#   SAC = 1              (System Area Code)
#   SIC = 1              (System Identification Code)
#   LAT = 40.416775      (Latitud en grados decimales)
#   LON = -3.703790      (Longitud en grados decimales)
#   elevation = 2000     (Elevación del radar en pies)


# ============================================================================
# EJEMPLO 3: Uso Programático en Python
# ============================================================================

"""
from main import AsterixAnalyzer

# Crear instancia del analizador
analyzer = AsterixAnalyzer()

# Cargar archivo PCAP
asterix_data = analyzer.load_pcap('datos.pcap')

# Decodificar
analyzer.decode_data(asterix_data)

# Configurar sensor manualmente (si no está en CAT 034)
analyzer.set_sensor_position(
    sac=1, 
    sic=1, 
    lat=40.416775, 
    lon=-3.703790, 
    elev=2000
)

# Exportar resultados
analyzer.export(output_dir='resultados/')

# Acceder a datos decodificados
for record in analyzer.records:
    print(f"Target CAT {record['category']}: Lat {record['latitude']}, Lon {record['longitude']}")
"""


# ============================================================================
# EJEMPLO 4: Acceso Directo a Decodificadores
# ============================================================================

"""
from decoders import decode_asterix_stream, CAT048Decoder

# Cargar datos crudos
with open('datos.ast', 'rb') as f:
    data = f.read()

# Decodificar completamente
records = decode_asterix_stream(data)

# O decodificar un registro específico
single_record, bytes_consumed = CAT048Decoder.decode(data, start_pos=0)
print(f"Azimut: {single_record.azimuth}°")
print(f"Rango: {single_record.range_slant} NM")
print(f"Mode-3/A: {single_record.mode_3a}")
"""


# ============================================================================
# EJEMPLO 5: Conversiones Geoespaciales
# ============================================================================

"""
from geo_tools import GeoTools, SensorRegistry, TargetProcessor

# Crear registro de sensores
registry = SensorRegistry()
registry.register_sensor(sac=1, sic=1, lat=40.4167, lon=-3.7038, elevation=2000)

# Crear procesador
processor = TargetProcessor(registry)

# Convertir coordenadas polares a WGS-84
from decoders import AsterixRecord

record = AsterixRecord(
    category=48,
    sac=1,
    sic=1,
    azimuth=45.0,        # 45 grados (Noreste)
    range_slant=10.0,    # 10 NM oblicuo
    flight_level=250     # FL250 (25000 pies)
)

# Procesar (convierte a WGS-84)
result = processor.process_record(record)
print(f"Lat: {result['latitude']}")
print(f"Lon: {result['longitude']}")
print(f"Ground Range: {result['ground_range']} NM")
"""


# ============================================================================
# EJEMPLO 6: Exportar Múltiples Formatos
# ============================================================================

"""
from main import AsterixAnalyzer
from exporters import KMLExporter, GeoJSONExporter, CSVExporter, ReportGenerator

analyzer = AsterixAnalyzer()
asterix_data = analyzer.load_pcap('datos.pcap')
analyzer.decode_data(asterix_data)

# Filtrar registros válidos
valid_records = [r for r in analyzer.records 
                if r['latitude'] is not None and r['longitude'] is not None]

# Exportar cada formato
KMLExporter.export(valid_records, 'salida/mapa.kml')
GeoJSONExporter.export(valid_records, 'salida/mapa.geojson')
CSVExporter.export(analyzer.records, 'salida/datos.csv')

# Generar reporte
report = ReportGenerator.generate_summary(analyzer.records, analyzer.sensor_registry)
ReportGenerator.save_report(report, 'salida/reporte.txt')
"""


# ============================================================================
# EJEMPLO 7: Procesamiento en Lote
# ============================================================================

"""
import os
from main import AsterixAnalyzer

# Procesar múltiples archivos PCAP
pcap_files = [f for f in os.listdir('datos/') if f.endswith('.pcap')]

for pcap_file in pcap_files:
    print(f"Procesando {pcap_file}...")
    
    analyzer = AsterixAnalyzer()
    asterix_data = analyzer.load_pcap(f'datos/{pcap_file}')
    analyzer.decode_data(asterix_data)
    
    # Usar sensores conocidos (de config.py)
    analyzer.set_sensor_position(1, 1, 40.4167, -3.7038, 2000)
    
    # Exportar a carpeta específica
    output_dir = f'resultados/{pcap_file[:-5]}/'
    analyzer.export(output_dir)
"""


# ============================================================================
# EJEMPLO 8: Análisis de Cobertura de Radar
# ============================================================================

"""
from main import AsterixAnalyzer
import statistics

analyzer = AsterixAnalyzer()
asterix_data = analyzer.load_pcap('datos.pcap')
analyzer.decode_data(asterix_data)

# Analizar distribución de targets por azimut
azimuths = [r['raw_azimuth'] for r in analyzer.records if r['raw_azimuth'] is not None]
ranges = [r['raw_range'] for r in analyzer.records if r['raw_range'] is not None]

print(f"Azimut promedio: {statistics.mean(azimuths):.1f}°")
print(f"Rango promedio: {statistics.mean(ranges):.2f} NM")
print(f"Rango máximo: {max(ranges):.2f} NM")
print(f"Desviación estándar azimut: {statistics.stdev(azimuths):.1f}°")
"""


# ============================================================================
# EJEMPLO 9: Configuración Avanzada
# ============================================================================

"""
from config import KNOWN_SENSORS, add_sensor, DECODER_CONFIG, GEO_CONFIG

# Añadir un nuevo sensor conocido
add_sensor(
    sac=3,
    sic=1,
    name='Nuevo Radar',
    latitude=41.2871,
    longitude=-3.7673,
    elevation=1500,
    description='Radar en zona de pruebas'
)

# Ver sensores conocidos
for (sac, sic), info in KNOWN_SENSORS.items():
    print(f"{info['name']}: ({info['latitude']}, {info['longitude']})")

# Configurar opciones de decodificación
DECODER_CONFIG['skip_unknown_categories'] = True
GEO_CONFIG['use_vincenty'] = True  # Usar fórmula más precisa
"""


# ============================================================================
# EJEMPLO 10: Depuración y Diagnóstico
# ============================================================================

"""
from main import AsterixAnalyzer
from exporters import ReportGenerator

analyzer = AsterixAnalyzer()

# Cargar y decodificar
asterix_data = analyzer.load_pcap('datos.pcap')
analyzer.decode_data(asterix_data)

# Generar reporte detallado
report = ReportGenerator.generate_summary(analyzer.records, analyzer.sensor_registry)
print(report)

# Ver sensores registrados
print("Sensores detectados:")
for (sac, sic), info in analyzer.sensor_registry.get_all_sensors().items():
    print(f"  SAC:{sac} SIC:{sic} - {info['records_count']} registros")
    if info['latitude'] is not None:
        print(f"    Posición: ({info['latitude']:.6f}, {info['longitude']:.6f})")

# Verificar registros problemáticos
no_position = [r for r in analyzer.records if r['latitude'] is None]
print(f"\\nRegistros sin posición: {len(no_position)}")
"""


# ============================================================================
# EJEMPLO 11: Conversión de Coordenadas (DMS ↔ Grados Decimales)
# ============================================================================

"""
La herramienta soporta múltiples formatos de coordenadas:
- Grados Decimales (DD): 40.474635
- Grados, Minutos, Segundos (DMS): 40° 28' 28.686" N

Conversiones disponibles:

from config import (
    dms_to_decimal, decimal_to_dms, dms_to_string,
    parse_dms_string, input_coordinate_interactive
)

# CONVERSIÓN 1: DMS → Decimal
print("=== Conversión DMS → Decimal ===")
lat_decimal = dms_to_decimal(40, 28, 28.686, 'N')
print(f"40° 28' 28.686\" N = {lat_decimal}°")

lon_decimal = dms_to_decimal(3, 35, 19.896, 'W')
print(f"3° 35' 19.896\" W = {lon_decimal}°")

# CONVERSIÓN 2: Decimal → DMS
print("\\n=== Conversión Decimal → DMS ===")
dms_dict = decimal_to_dms(40.474635)
print(f"40.474635° = {dms_dict}")
# Resultado: {'degrees': 40, 'minutes': 28, 'seconds': 28.686, 'direction': 'N'}

# CONVERSIÓN 3: Decimal → String legible
print("\\n=== Formato Legible ===")
print(f"40.474635° = {dms_to_string(40.474635)}")
print(f"-3.588860° = {dms_to_string(-3.588860)}")

# CONVERSIÓN 4: Parsear strings DMS
print("\\n=== Parsear Strings DMS ===")
formats = [
    "40 28 28.686 N",
    "40:28:28.686N",
    "40° 28' 28.686\" N",
    "40d 28m 28.686s N"
]
for fmt in formats:
    result = parse_dms_string(fmt)
    print(f"{fmt:25} → {result:.6f}°")

# CONVERSIÓN 5: Ingreso Interactivo
print("\\n=== Ingreso Interactivo (Descomenta para usar) ===")
# lat = input_coordinate_interactive("Latitud")
# lon = input_coordinate_interactive("Longitud")
# print(f"Coordenadas: ({lat}, {lon})")

# CONVERSIÓN 6: Agregar sensor con DMS
print("\\n=== Agregar Sensor con Coordenadas DMS ===")
from config import add_sensor

# Convertir DMS a decimal
madrid_lat = dms_to_decimal(40, 28, 28.686, 'N')   # 40.474635
madrid_lon = dms_to_decimal(3, 35, 19.896, 'W')   # -3.588860

add_sensor(
    sac=1,
    sic=3,
    name='Madrid Radar (DMS)',
    latitude=madrid_lat,
    longitude=madrid_lon,
    elevation=2000,
    description='Configurado usando DMS'
)
print(f"✓ Sensor añadido: {dms_to_string(madrid_lat)}, {dms_to_string(madrid_lon)}")
"""


if __name__ == "__main__":
    print("""
    ============================================================
    EJEMPLOS DE USO - ASTERIX Analyzer
    ============================================================
    
    Este archivo contiene 11 ejemplos de uso de la herramienta.
    Ver comentarios en el código para detalles de cada ejemplo.
    
    NUEVOS: Ejemplos 11 - Conversión de coordenadas DMS/Decimal
    
    Para ejecutar los ejemplos, descomenta el código correspondiente
    y ejecuta este archivo como script Python.
    
    O consulta el README.md para ejemplos 
línea de comandos.
    ============================================================
    """)
