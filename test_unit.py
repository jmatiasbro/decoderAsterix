#!/usr/bin/env python3
"""
Suite de Pruebas Unitarias para ASTERIX Analyzer.

Ejecución:
    python -m unittest test_unit.py -v
"""

import unittest
import math
import os
from main import AsterixAnalyzer
from decoders import BitStream, AsterixRecord
from geo_tools import GeoTools, SensorRegistry, TargetProcessor
from config import dms_to_decimal, decimal_to_dms, parse_dms_string
from mode_analyzer import ModeAnalyzer
from flight_loss_analyzer import FlightLossAnalyzer

class TestBitStream(unittest.TestCase):
    """Pruebas unitarias para la lectura bit a bit."""
    
    def test_read_bits_aligned(self):
        # 0b11001010 (202), 0b01010101 (85)
        stream = BitStream(bytes([0xCA, 0x55]))
        self.assertEqual(stream.read_bits(4), 12)  # 1100 = 12
        self.assertEqual(stream.read_bits(4), 10)  # 1010 = 10
        self.assertEqual(stream.read_bits(8), 85)  # 01010101 = 85
        
    def test_read_bits_cross_byte(self):
        # 0b11111111, 0b00000000
        stream = BitStream(bytes([0xFF, 0x00]))
        self.assertEqual(stream.read_bits(4), 15)  # Lee 4 bits: 1111
        self.assertEqual(stream.read_bits(8), 240) # Lee 4 del primero y 4 del segundo: 11110000
        
    def test_skip_bits(self):
        stream = BitStream(bytes([0xFF, 0x00]))
        stream.skip_bits(4)
        self.assertEqual(stream.read_bits(4), 15)


class TestGeoTools(unittest.TestCase):
    """Pruebas unitarias para conversiones geoespaciales y matemáticas."""
    
    def test_unit_conversions(self):
        self.assertEqual(GeoTools.nm_to_meters(1.0), 1852.0)
        self.assertEqual(GeoTools.meters_to_nm(1852.0), 1.0)
        self.assertAlmostEqual(GeoTools.feet_to_meters(100), 30.48, places=2)
        self.assertAlmostEqual(GeoTools.meters_to_feet(30.48), 100.0, places=2)
        
    def test_slant_to_ground_range(self):
        # Triángulo rectángulo clásico 3-4-5
        # Slant Range = 5 NM (~30380 pies)
        # Altura = 3 NM (~18228 pies) -> FL = 182.28
        # Resultado esperado Ground Range = 4 NM
        slant_ft = 5 * 6076.118
        height_ft = 3 * 6076.118
        fl = int(height_ft / 100)
        
        ground_nm = GeoTools.slant_to_ground_range(5.0, fl, radar_height_ft=0)
        self.assertAlmostEqual(ground_nm, 4.0, places=2)
        
    def test_polar_to_wgs84_zero_distance(self):
        lat, lon = GeoTools.polar_to_wgs84(40.0, -3.0, azimuth_deg=90, ground_range_nm=0)
        self.assertEqual(lat, 40.0)
        self.assertEqual(lon, -3.0)


class TestConfigDMS(unittest.TestCase):
    """Pruebas unitarias para las funciones de grados/minutos/segundos."""
    
    def test_dms_to_decimal(self):
        # 40 grados, 30 minutos, 0 segundos N -> 40.5
        dec = dms_to_decimal(40, 30, 0, 'N')
        self.assertAlmostEqual(dec, 40.5, places=5)
        
        # Hemisferio Sur y Oeste (deben ser negativos)
        dec_s = dms_to_decimal(40, 30, 0, 'S')
        self.assertAlmostEqual(dec_s, -40.5, places=5)
        dec_w = dms_to_decimal(3, 45, 0, 'W')
        self.assertAlmostEqual(dec_w, -3.75, places=5)
        
    def test_parse_dms_string(self):
        dec1 = parse_dms_string("40 30 0.0 N")
        self.assertAlmostEqual(dec1, 40.5, places=5)
        
        dec2 = parse_dms_string("40° 30' 0.0\" W")
        self.assertAlmostEqual(dec2, -40.5, places=5)


class TestModeAnalyzer(unittest.TestCase):
    """Pruebas unitarias para la evaluación del ModeAnalyzer."""
    
    def test_analyze_record_high_confidence(self):
        analyzer = ModeAnalyzer()
        rec = {"mode_3a": 0o1234, "flight_level": 250, "category": 48}
        det = analyzer.analyze_record(rec)
        
        self.assertTrue(det.mode_a_detected)
        self.assertTrue(det.mode_c_detected)
        self.assertEqual(det.confidence_level, "high")
        self.assertAlmostEqual(det.combined_probability, 0.95 * 0.90)


class TestFlightLossAnalyzer(unittest.TestCase):
    """Pruebas unitarias para el analizador de pérdidas y vuelos."""
    
    def test_analyze_records_basic(self):
        analyzer = FlightLossAnalyzer(antenna_rpm=12.0)
        records = [{"mode_3a": 0o1234, "flight_level": 100}] * 5  # 5 detecciones usando un Squawk válido
        
        result = analyzer.analyze_records(records)
        self.assertIn("1234", result)
        self.assertEqual(result["1234"].flight_count, 5)

class TestAsterixAnalyzerMemory(unittest.TestCase):
    """Pruebas para la gestión de memoria del analizador."""
    
    def test_reset_clears_all_data(self):
        """Verifica que el método reset limpie correctamente los datos cargados."""
        analyzer = AsterixAnalyzer()
        
        # 1. Simular carga previa de datos
        analyzer.records = [{"category": 48}]
        analyzer.decoded_records = [{"category": 48, "sac": 1, "sic": 1}]
        analyzer.selected_sensors = {(1, 1)}
        analyzer.asterix_data = b'datos dummy asterix'
        analyzer.current_file_path = "ruta/al/archivo.pcap"
        analyzer.filtered_asterix_data = b'datos filtrados'
        
        # 2. Ejecutar el reset (lo que hace la Opción 1 del menú)
        analyzer.reset()
        
        # 3. Verificar que las estructuras críticas estén vacías o en None
        self.assertEqual(analyzer.records, [], "Los records deberían estar vacíos")
        self.assertEqual(analyzer.decoded_records, [], "Los decoded_records deberían estar vacíos")
        self.assertIsNone(analyzer.selected_sensors, "La selección de sensores debería ser None")
        self.assertEqual(analyzer.asterix_data, b'', "La data binaria debería estar vacía")
        self.assertIsNone(analyzer.current_file_path, "La ruta del archivo debería ser None")
        self.assertIsNone(analyzer.filtered_asterix_data, "La data filtrada debería ser None")


class TestMathStability(unittest.TestCase):
    """Pruebas para asegurar que no ocurran 'math domain errors' con datos corruptos."""

    def test_polar_to_wgs84_robustness(self):
        # Caso 1: Distancia extremadamente larga (podría causar sin_lat2 > 1)
        radar_lat, radar_lon = 45.0, 0.0
        azimuth = 45.0
        extreme_range = 20000.0  # 20,000 NM (casi la vuelta al mundo)
        
        try:
            lat, lon = GeoTools.polar_to_wgs84(radar_lat, radar_lon, azimuth, extreme_range)
            self.assertIsInstance(lat, float)
        except ValueError as e:
            self.fail(f"polar_to_wgs84 lanzó math domain error con rango extremo: {e}")

    def test_slant_to_ground_impossible_geometry(self):
        # Caso: Altura del target es mayor que la distancia oblicua (físicamente imposible)
        slant_nm = 2.0
        flight_level = 400  # 40,000 pies (~6.5 NM)
        
        try:
            ground_nm = GeoTools.slant_to_ground_range(slant_nm, flight_level)
            # Con la nueva lógica, si es imposible, devuelve 0.0
            self.assertEqual(ground_nm, 0.0)
        except ValueError as e:
            self.fail(f"slant_to_ground_range lanzó math domain error con geometría imposible: {e}")

    def test_slant_to_ground_negative_diff(self):
        # Caso: Objetivo por debajo del radar (Radar en montaña a 10000ft, avión a 5000ft)
        radar_height = 10000
        slant_nm = 2.0 # ~12152 pies
        flight_level = 50 # 5000 pies
        # height_diff = 5000 - 10000 = -5000
        
        try:
            ground_nm = GeoTools.slant_to_ground_range(slant_nm, flight_level, radar_height_ft=radar_height)
            self.assertLess(ground_nm, slant_nm)
        except ValueError as e:
            self.fail(f"slant_to_ground_range lanzó math domain error con height_diff negativo: {e}")

    def test_vincenty_extreme_coordinates(self):
        # Caso: Polos o antimeridiano
        try:
            lat, lon = GeoTools.vincenty_forward(89.9, 179.9, 0, 1000)
            self.assertIsInstance(lat, float)
        except ValueError as e:
            self.fail(f"vincenty_forward falló en coordenadas límite: {e}")

class TestIntegrationPCAP(unittest.TestCase):
    """Prueba de integración con el archivo PCAP de ejemplo."""
    
    def test_process_sample_pcap(self):
        pcap_file = "UIS.pcap"
        if not os.path.exists(pcap_file):
            self.skipTest(f"Archivo {pcap_file} no encontrado en el directorio.")
            
        analyzer = AsterixAnalyzer()
        
        asterix_data = analyzer.load_pcap(pcap_file)
        self.assertTrue(len(asterix_data) > 0, "No se extrajeron datos ASTERIX del PCAP.")
        
        analyzer.asterix_data = asterix_data
        analyzer.decode_data()
        self.assertTrue(len(analyzer.records) > 0, "No se decodificaron registros del PCAP.")
        self.assertIn('category', analyzer.records[0], "Falta la clave 'category' en el registro.")

class TestPPIPresentation(unittest.TestCase):
    """Pruebas para validar la lógica de presentación del PPI."""
    
    def test_ppi_rendering_logic(self):
        """Verifica que los datos se agrupan y filtran correctamente para la visualización PPI."""
        active_plots = [
            {'data': {'category': 48, 'raw_azimuth': 45.0, 'raw_range': 100.0, 'mode_3a': 0o1234, 'callsign': 'IBE123'}, 'life': 1.0},
            {'data': {'category': 62, 'raw_azimuth': 90.0, 'raw_range': 150.0, 'mode_3a': 0o5670}, 'life': 0.5},
            {'data': {'category': 21, 'raw_azimuth': -10.0, 'raw_range': 50.0}, 'life': 1.0}, # Inválido
            {'data': {'category': 48, 'raw_azimuth': None, 'raw_range': 100.0}, 'life': 1.0} # Inválido
        ]
        
        ppi_category_vars = {
            48: type('MockVar', (), {'get': lambda: True})(),
            62: type('MockVar', (), {'get': lambda: True})(),
            21: type('MockVar', (), {'get': lambda: False})()
        }
        
        filtered_plots = [p for p in active_plots if p['data']['category'] in ppi_category_vars and ppi_category_vars[p['data']['category']].get()]
        self.assertEqual(len(filtered_plots), 3)
        
        renderable_plots = [
            p for p in filtered_plots
            if p['data'].get('raw_azimuth') is not None and p['data'].get('raw_range') is not None
            and p['data'].get('raw_range') >= 0 and p['data'].get('raw_azimuth') >= 0
        ]
        self.assertEqual(len(renderable_plots), 2)
        
    def test_ppi_label_extraction(self):
        """Verifica que la lógica de extracción extraiga Callsign y Squawk apropiadamente."""
        plot_callsign = {'data': {'callsign': 'RYR404', 'mode_3a': 0o1234}, 'life': 1.0}
        plot_squawk_only = {'data': {'callsign': None, 'mode_3a': 0o7777}, 'life': 1.0}
        
        def extract_label(p, label_mode):
            text_str = ""
            if label_mode == "Callsign":
                text_str = str(p['data'].get('callsign', '')).strip()
                if not text_str or text_str == 'None':
                    sq = p['data'].get('mode_3a')
                    if sq is not None:
                        text_str = f"{sq:04o}"
            elif label_mode == "Squawk":
                sq = p['data'].get('mode_3a')
                if sq is not None:
                    text_str = f"{sq:04o}"
            return text_str
            
        self.assertEqual(extract_label(plot_callsign, "Callsign"), "RYR404")
        self.assertEqual(extract_label(plot_squawk_only, "Callsign"), "7777")
        self.assertEqual(extract_label(plot_callsign, "Squawk"), "1234")

if __name__ == '__main__':
    unittest.main()