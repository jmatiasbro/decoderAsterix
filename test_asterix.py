#!/usr/bin/env python3
"""
Suite de Pruebas Unitarias - Red de Seguridad (FASE 1)
Analizador ASTERIX

Asegura la estabilidad de los decodificadores, el motor geodésico
y la correlación de trazas antes de iniciar la refactorización.
"""

import unittest
from unittest.mock import patch

from decoders import decode_asterix_stream, AsterixRecord
from geo_tools import GeoTools
from track_manager import TrackManager

class TestAsterixDecoders(unittest.TestCase):
    """Pruebas de ingesta binaria para las categorías principales."""

    @patch('decoders.asterix.parse')
    def test_decode_asterix_stream_adapter(self, mock_parse):
        # Simula la respuesta de la librería asterix para un paquete CAT048
        mock_msg = {'category': 48, 'I048/010': {'SAC': 10, 'SIC': 20}}
        mock_parse.return_value = [mock_msg]
        
        data = b'\x30\x00\x06\x80\x0A\x14'
        records = decode_asterix_stream(data)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].category, 48)
        self.assertEqual(records[0].sac, 10)
        self.assertEqual(records[0].sic, 20)


class TestGeodesicEngine(unittest.TestCase):
    """Pruebas del motor de proyección matemática WGS-84."""

    def setUp(self):
        self.radar_lat = 40.0
        self.radar_lon = -3.0

    def test_polar_to_wgs84_north(self):
        # Objetivo a 10 Millas Náuticas al Norte Exacto (Azimut 0)
        lat, lon = GeoTools.polar_to_wgs84(
            self.radar_lat, self.radar_lon, azimuth_deg=0.0, ground_range_nm=10.0
        )
        self.assertGreater(lat, self.radar_lat, "La latitud debe aumentar hacia el norte.")
        self.assertAlmostEqual(lon, self.radar_lon, delta=0.05, msg="La longitud no debe variar significativamente.")

    def test_cartesian_to_wgs84_north(self):
        # Objetivo a 18520 metros (10 NM) al Norte Exacto (Eje Y)
        lat, lon = GeoTools.cartesian_to_wgs84(
            self.radar_lat, self.radar_lon, x_m=0.0, y_m=18520.0
        )
        self.assertGreater(lat, self.radar_lat, "La latitud debe aumentar con Y positivo.")
        self.assertAlmostEqual(lon, self.radar_lon, delta=0.05)


class TestTrackManagerCorrelation(unittest.TestCase):
    """Pruebas de la lógica de estado y limpieza de memoria en vivo."""

    def setUp(self):
        self.tm = TrackManager(history_minutes=10, timeout_seconds=60)

    @patch('time.time')
    def test_track_insertion_and_update(self, mock_time):
        mock_time.return_value = 1000.0
        self.tm.update_track("SQ1234", {"mode_3a": 0o1234, "lat": 40.0})
        self.assertIn("SQ1234", self.tm.tracks)
        self.assertEqual(len(self.tm.tracks["SQ1234"]), 1)
        
        mock_time.return_value = 1005.0
        self.tm.update_track("SQ1234", {"mode_3a": 0o1234, "lat": 40.1})
        self.assertEqual(len(self.tm.tracks["SQ1234"]), 2)
        self.assertEqual(self.tm.last_update["SQ1234"], 1005.0)

    @patch('time.time')
    def test_track_purge_stale(self, mock_time):
        mock_time.return_value = 1000.0
        self.tm.update_track("STALE_TRK", {"mode_3a": 0o0000})
        
        mock_time.return_value = 1061.0 # Supera el timeout de 60s
        self.tm.update_track("FRESH_TRK", {"mode_3a": 0o1111})
        
        purged = self.tm.purge_stale_tracks()
        self.assertEqual(purged, 1, "Debería purgar exactamente 1 traza expirada.")
        self.assertNotIn("STALE_TRK", self.tm.tracks)
        self.assertIn("FRESH_TRK", self.tm.tracks)

if __name__ == '__main__':
    unittest.main()
