import sys
import os
import unittest

# Add root folder to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from player.radar_widget import RadarPlot, RadarWidget
from PyQt6.QtWidgets import QApplication

class TestLabelFilters(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Create a dummy QApplication if not already created
        cls.app = QApplication.instance()
        if cls.app is None:
            cls.app = QApplication(sys.argv)
            
    def test_rho_theta_label_line(self):
        # Instantiate a RadarPlot with raw_range and raw_azimuth
        plot = RadarPlot(
            x=100.0, y=200.0,
            sac_sic="1/1",
            category=48,
            timestamp=1000.0,
            mode3a="1200",
            callsign="ARG1234",
            flight_level=300.0,
            is_track=True,
            mode_s="3A2B1C",
            track_angle=90.0,
            ground_speed=300.0,
            raw_range=124.54,
            raw_azimuth=235.62
        )
        
        widget = RadarWidget()
        
        # Test 1: Config has rho_theta = False
        widget.label_filter_config["rho_theta"] = False
        lines = widget._build_plot_label_lines(plot)
        has_rho_theta = any("NM" in line and "A:" in line for line in lines)
        self.assertFalse(has_rho_theta, "Should NOT show RHO/THETA when disabled in config")
        
        # Test 2: Config has rho_theta = True
        widget.label_filter_config["rho_theta"] = True
        lines = widget._build_plot_label_lines(plot)
        has_rho_theta = any("NM" in line and "A:" in line for line in lines)
        self.assertTrue(has_rho_theta, "Should show RHO/THETA when enabled in config")
        
        # Verify the format matches exactly
        expected_line = "R:124.5NM A:235.6°"
        self.assertIn(expected_line, lines, f"Line format should be '{expected_line}'")
        
        print("[+] RHO/THETA label filter option and text formatting verified successfully!")
        print(f"    - Enabled: {widget.label_filter_config['rho_theta']}")
        print(f"    - Rendered Label Lines: {lines}")

if __name__ == '__main__':
    unittest.main()
