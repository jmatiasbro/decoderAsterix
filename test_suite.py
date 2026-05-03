#!/usr/bin/env python3
"""
Script de Pruebas Rápidas

Valida que todos los módulos estén correctamente instalados
y que la herramienta funciona correctamente.
"""

import sys
import os


def test_imports():
    """Prueba que todos los módulos se importan correctamente."""
    print("[*] Verificando importaciones de módulos...")
    
    try:
        import dpkt
        print("  [✓] dpkt OK")
    except ImportError as e:
        print(f"  [✗] dpkt NO instalado: {e}")
        return False
    
    try:
        from decoders import (
            BitStream, AsterixDecoder, CAT048Decoder, CAT034Decoder,
            CAT021Decoder, CAT001Decoder, CAT002Decoder, decode_asterix_stream
        )
        print("  [✓] decoders.py OK")
    except Exception as e:
        print(f"  [✗] decoders.py Error: {e}")
        return False
    
    try:
        from geo_tools import GeoTools, SensorRegistry, TargetProcessor
        print("  [✓] geo_tools.py OK")
    except Exception as e:
        print(f"  [✗] geo_tools.py Error: {e}")
        return False
    
    try:
        from exporters import (
            KMLExporter, GeoJSONExporter, CSVExporter, ReportGenerator
        )
        print("  [✓] exporters.py OK")
    except Exception as e:
        print(f"  [✗] exporters.py Error: {e}")
        return False
    
    try:
        from config import KNOWN_SENSORS, get_sensor_position
        print("  [✓] config.py OK")
    except Exception as e:
        print(f"  [✗] config.py Error: {e}")
        return False
    
    return True


def test_bitstream():
    """Prueba la clase BitStream."""
    print("\n[*] Probando BitStream...")
    
    try:
        from decoders import BitStream
        
        # Crear datos de prueba: 0b11001010 01010101
        data = bytes([0b11001010, 0b01010101])
        stream = BitStream(data)
        
        # Leer 4 bits: debe ser 0b1100 = 12
        val = stream.read_bits(4)
        assert val == 12, f"Expected 12, got {val}"
        print(f"  [✓] read_bits(4) = {val}")
        
        # Leer 4 bits: debe ser 0b1010 = 10
        val = stream.read_bits(4)
        assert val == 10, f"Expected 10, got {val}"
        print(f"  [✓] read_bits(4) = {val}")
        
        # Leer 8 bits: debe ser 0b01010101 = 85
        val = stream.read_bits(8)
        assert val == 85, f"Expected 85, got {val}"
        print(f"  [✓] read_bits(8) = {val}")
        
        return True
    except Exception as e:
        print(f"  [✗] Error: {e}")
        return False


def test_geo_conversion():
    """Prueba conversiones geoespaciales."""
    print("\n[*] Probando conversiones geoespaciales...")
    
    try:
        from geo_tools import GeoTools
        import math
        
        # Test 1: Convertir polares a WGS-84 (offset simple)
        radar_lat, radar_lon = 40.0, -3.0
        azimuth = 0  # Norte
        range_nm = 10  # 10 NM
        
        lat, lon = GeoTools.polar_to_wgs84(radar_lat, radar_lon, azimuth, range_nm)
        
        # Norte desde (40, -3) debe aumentar latitud
        assert lat > radar_lat, f"Latitud no aumentó: {lat} <= {radar_lat}"
        assert abs(lon - radar_lon) < 0.1, f"Longitud varió demasiado: {lon} vs {radar_lon}"
        print(f"  [✓] Conversión polar→WGS84: ({radar_lat}, {radar_lon}) + 10NM@0° = ({lat:.4f}, {lon:.4f})")
        
        # Test 2: Slant Range a Ground Range
        slant_range = 20.0  # NM
        flight_level = 250  # FL250
        ground_range = GeoTools.slant_to_ground_range(slant_range, flight_level, 0)
        
        assert ground_range < slant_range, "Ground range debe ser menor que slant range"
        print(f"  [✓] Slant Range: {slant_range} NM → Ground Range: {ground_range:.2f} NM (FL250)")
        
        # Test 3: Conversión metros/NM
        assert GeoTools.nm_to_meters(1.0) == 1852.0, "Conversión NM→m incorrecta"
        assert abs(GeoTools.meters_to_nm(1852.0) - 1.0) < 0.0001, "Conversión m→NM incorrecta"
        print("  [✓] Conversiones de unidades OK")
        
        return True
    except Exception as e:
        print(f"  [✗] Error: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_sensor_registry():
    """Prueba el registro de sensores."""
    print("\n[*] Probando SensorRegistry...")
    
    try:
        from geo_tools import SensorRegistry
        
        registry = SensorRegistry()
        
        # Registrar sensor
        registry.register_sensor(1, 1, 40.4167, -3.7038, 2000)
        
        # Recuperar sensor
        sensor = registry.get_sensor(1, 1)
        assert sensor is not None, "Sensor no encontrado"
        assert sensor['latitude'] == 40.4167, "Latitud incorrecta"
        print(f"  [✓] Sensor registrado: {sensor['sac']}/{sensor['sic']}")
        
        # Verificar posición
        has_pos = registry.has_position(1, 1)
        assert has_pos, "Sensor sin posición"
        print("  [✓] Verificación de posición OK")
        
        # Registrar segundo sensor
        registry.register_sensor(2, 1)
        sensors = registry.get_all_sensors()
        assert len(sensors) == 2, "Número de sensores incorrecto"
        print(f"  [✓] Total sensores registrados: {len(sensors)}")
        
        return True
    except Exception as e:
        print(f"  [✗] Error: {e}")
        return False


def test_data_structures():
    """Prueba las estructuras de datos."""
    print("\n[*] Probando estructuras de datos...")
    
    try:
        from decoders import AsterixRecord
        
        # Crear registro
        record = AsterixRecord(
            category=48,
            sac=1,
            sic=1,
            latitude=40.5,
            longitude=-3.5,
            altitude=10000,
            mode_3a=1234,
            azimuth=45.0,
            range_slant=15.0,
            flight_level=330
        )
        
        assert record.category == 48
        assert record.sac == 1
        assert record.latitude == 40.5
        print(f"  [✓] AsterixRecord creado: CAT {record.category}, SAC {record.sac}, SIC {record.sic}")
        
        return True
    except Exception as e:
        print(f"  [✗] Error: {e}")
        return False


def test_exporters():
    """Prueba los exportadores."""
    print("\n[*] Probando exportadores...")
    
    try:
        from exporters import KMLExporter, GeoJSONExporter, CSVExporter
        
        # Crear datos de prueba
        test_records = [
            {
                'category': 48,
                'sac': 1,
                'sic': 1,
                'timestamp': 12345.0,
                'latitude': 40.5,
                'longitude': -3.5,
                'altitude': 10000,
                'flight_level': 330,
                'mode_3a': 1234,
                'raw_range': 15.0,
                'raw_azimuth': 45.0,
            }
        ]
        
        # Crear directorio temporal
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            # Test KML
            kml_file = os.path.join(tmpdir, 'test.kml')
            KMLExporter.export(test_records, kml_file)
            assert os.path.exists(kml_file), "KML no creado"
            print("  [✓] KMLExporter OK")
            
            # Test GeoJSON
            geojson_file = os.path.join(tmpdir, 'test.geojson')
            GeoJSONExporter.export(test_records, geojson_file)
            assert os.path.exists(geojson_file), "GeoJSON no creado"
            print("  [✓] GeoJSONExporter OK")
            
            # Test CSV
            csv_file = os.path.join(tmpdir, 'test.csv')
            CSVExporter.export(test_records, csv_file)
            assert os.path.exists(csv_file), "CSV no creado"
            print("  [✓] CSVExporter OK")
        
        return True
    except Exception as e:
        print(f"  [✗] Error: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    print("=" * 70)
    print("ASTERIX Analyzer - Suite de Pruebas")
    print("=" * 70)
    
    all_passed = True
    
    # Ejecutar todas las pruebas
    tests = [
        test_imports,
        test_bitstream,
        test_data_structures,
        test_sensor_registry,
        test_geo_conversion,
        test_exporters,
    ]
    
    for test in tests:
        if not test():
            all_passed = False
    
    print("\n" + "=" * 70)
    if all_passed:
        print("[✓] TODAS LAS PRUEBAS PASARON")
        print("=" * 70)
        print("\nLa herramienta está lista para usar. Ejemplos:")
        print("  python main.py archivo.pcap")
        print("  python main.py archivo.ast --sensor 1 1 40.4167 -3.7038")
        print("  python main.py --interactive")
        return 0
    else:
        print("[✗] ALGUNAS PRUEBAS FALLARON")
        print("=" * 70)
        print("\nVerifica que todas las dependencias estén instaladas:")
        print("  pip install -r requirements.txt")
        return 1


if __name__ == "__main__":
    sys.exit(main())
