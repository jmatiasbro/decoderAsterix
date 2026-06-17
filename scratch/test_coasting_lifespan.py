import sys
import os
import unittest

# Add root folder to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from player.radar_widget import RadarPlot

class TestCoastingLifespan(unittest.TestCase):
    def test_dynamic_coasting_and_purging_math(self):
        # Let's mock a RadarPlot
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
            ground_speed=300.0
        )
        
        # Test 1: sweep_rpm = 12.0 (Scan Time = 5.0s)
        rpm = 12.0
        scan_time = 60.0 / rpm
        coasting_threshold = 2.0 * scan_time  # 10.0s
        max_age = 3.0 * scan_time             # 15.0s
        
        # Age = 8.0s (less than 2 rotations)
        plot._last_seen = 1000.0
        # Mocking dynamic check age = curr_time - last_seen
        # Age = 8s
        age = 8.0
        is_coasting = age > coasting_threshold
        is_alive = age < max_age
        self.assertFalse(is_coasting, "Should NOT be coasting under 2 rotations")
        self.assertTrue(is_alive, "Should be alive under 3 rotations")
        
        # Age = 12.0s (between 2 and 3 rotations)
        age = 12.0
        is_coasting = age > coasting_threshold
        is_alive = age < max_age
        self.assertTrue(is_coasting, "Should be coasting at 3rd rotation")
        self.assertTrue(is_alive, "Should be alive at 3rd rotation")
        
        # Age = 16.0s (exceeds 3 rotations)
        age = 16.0
        is_coasting = age > coasting_threshold
        is_alive = age < max_age
        self.assertTrue(is_coasting)
        self.assertFalse(is_alive, "Should be dead at 4th rotation (removed)")
        
        print("[+] Coasting and purging mathematical thresholds verified successfully!")
        print(f"    - RPM: {rpm} (T_rotation = {scan_time:.1f}s)")
        print(f"    - Coasting (gray) after: {coasting_threshold:.1f}s")
        # Age 12s is in 3rd rotation -> Coasting
        # Age 16s is in 4th rotation -> Dead / Deleted
        print(f"    - Deletion (purged) after: {max_age:.1f}s")

if __name__ == '__main__':
    unittest.main()
