#!/usr/bin/env python3
"""
Unit tests for the Profile Manager system, UI Dialog, View configuration, and Hot Swapping.
"""

import unittest
import os
import shutil
import sys
from PyQt6.QtWidgets import QApplication
from player.profile_manager import ProfileManager
from player.radar_widget import RadarWidget
from player.main_window import MainWindow

# Initialize PyQt application in headless mode or standard mode
app = QApplication.instance() or QApplication(sys.argv)

class TestProfileSystem(unittest.TestCase):
    def setUp(self):
        # Create a temporary profiles directory within the workspace
        self.base_dir = os.path.dirname(os.path.abspath(__file__))
        self.temp_dir = os.path.join(self.base_dir, "profiles_test_temp")
        os.makedirs(self.temp_dir, exist_ok=True)
        # Create profile_manager with a temp config file as well
        self.temp_config_path = os.path.join(self.temp_dir, "config_profile.json")
        self.manager = ProfileManager(profile_path=self.temp_config_path)
        self.manager.profiles_dir = self.temp_dir

    def tearDown(self):
        # Clean up the temporary profiles directory
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def test_create_and_read_profile(self):
        """Test FASE 1: Core CRUD and profile storage."""
        profile_data = {
            "nombre_usuario": "Matias_TWR",
            "aeropuerto_trabajo": "SACO",
            "coordenadas_centro": {"lat": -31.31, "lon": -64.21},
            "nivel_incumbencia": 95,
            "frecuencias_sector": ["118.5", "121.9", "122.5"],
            "mapas_visibles": ["mapas_Matias_TWR/twr_corridor.geojson"],
            "stca_habilitado": False
        }
        self.manager.guardar_perfil("Matias_TWR", profile_data)
        
        # Verify profile JSON is created
        expected_file = os.path.join(self.temp_dir, "Matias_TWR.json")
        self.assertTrue(os.path.exists(expected_file))
        
        # Verify read attributes
        read_data = self.manager.leer_perfil("Matias_TWR")
        self.assertEqual(read_data["nombre_usuario"], "Matias_TWR")
        self.assertEqual(read_data["aeropuerto_trabajo"], "SACO")
        self.assertEqual(read_data["stca_habilitado"], False)
        self.assertEqual(read_data["coordenadas_centro"]["lat"], -31.31)

    def test_schema_validation_missing_key(self):
        """Test validation schema for missing/invalid required keys."""
        # A profile with a string for coordinates instead of a float/dict
        invalid_data = {
            "nombre_usuario": "Invalid_Profile",
            "aeropuerto_trabajo": "SACO",
            "coordenadas_centro": {"lat": "not_a_float", "lon": -64.21},
            "nivel_incumbencia": 95,
            "frecuencias_sector": ["118.5", "121.9", "122.5"],
            "mapas_visibles": [],
            "stca_habilitado": True
        }
        with self.assertRaises(ValueError):
            self.manager.guardar_perfil("Invalid_Profile", invalid_data)

    def test_schema_validation_type_mismatch(self):
        """Test validation schema for type mismatches."""
        invalid_data = {
            "nombre_usuario": "Invalid_Profile",
            "aeropuerto_trabajo": "SACO",
            "coordenadas_centro": {"lat": -31.31, "lon": -64.21},
            "nivel_incumbencia": "not_an_int",
            "frecuencias_sector": ["118.5", "121.9", "122.5"],
            "mapas_visibles": [],
            "stca_habilitado": True
        }
        with self.assertRaises(ValueError):
            self.manager.guardar_perfil("Invalid_Profile", invalid_data)

    def test_delete_profile(self):
        """Test profile deletion."""
        profile_data = {
            "nombre_usuario": "Delete_Me",
            "aeropuerto_trabajo": "SACO",
            "coordenadas_centro": {"lat": -31.31, "lon": -64.21},
            "nivel_incumbencia": 95,
            "frecuencias_sector": ["118.5", "121.9", "122.5"],
            "mapas_visibles": [],
            "stca_habilitado": True
        }
        self.manager.guardar_perfil("Delete_Me", profile_data)
        expected_file = os.path.join(self.temp_dir, "Delete_Me.json")
        self.assertTrue(os.path.exists(expected_file))
        
        self.manager.eliminar_perfil("Delete_Me")
        self.assertFalse(os.path.exists(expected_file))

    def test_radar_widget_stca_inhibition_and_view_setup(self):
        """Test FASE 3: RadarWidget center positioning and STCA inhibition."""
        radar = RadarWidget()
        radar.resize(800, 600)
        
        # Test view adjustment
        radar.configurar_vista_perfil(-31.31, -64.21)
        self.assertAlmostEqual(radar.proy.center_lat, -31.31)
        self.assertAlmostEqual(radar.proy.center_lon, -64.21)
        self.assertGreater(radar.zoom_factor, 0)
        
        # Test STCA alerts inhibition logic
        radar.stca_habilitado = False
        radar.tracks_en_alerta = {"test_track_1", "test_track_2"}
        radar.evaluar_stca()
        
        self.assertEqual(len(radar.tracks_en_alerta), 0)
        self.assertEqual(len(radar.conflictos_activos), 0)

    def test_main_window_hot_load(self):
        """Test FASE 4: MainWindow hot profile load integration."""
        window = MainWindow()
        window.profile_manager = self.manager
        
        profile_data = {
            "nombre_usuario": "Hot_Swap_User",
            "aeropuerto_trabajo": "SACO",
            "coordenadas_centro": {"lat": -31.31, "lon": -64.21},
            "nivel_incumbencia": 120,
            "frecuencias_sector": ["118.5", "121.9", "122.5"],
            "mapas_visibles": [],
            "stca_habilitado": False
        }
        self.manager.guardar_perfil("Hot_Swap_User", profile_data)
        
        # Hot load the profile in real time
        window.hot_load_profile("Hot_Swap_User")
        
        self.assertEqual(window.techo_incumbencia, 120)
        self.assertEqual(window.radar.techo_incumbencia, 120)
        self.assertEqual(window.radar.stca_habilitado, False)
        self.assertAlmostEqual(window.radar.proy.center_lat, -31.31)
        self.assertAlmostEqual(window.radar.proy.center_lon, -64.21)

if __name__ == "__main__":
    unittest.main()
