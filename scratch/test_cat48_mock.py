import unittest
import struct
import sys
import os

# Add root folder to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from decoder.decoders import cat048

class TestCat048Decoding(unittest.TestCase):
    def test_decode_calculated_position_and_velocity(self):
        # Let's craft a mock ASTERIX CAT 048 message
        # Format:
        # Category: 48 (1 byte, 0x30)
        # Length: 2 bytes (big endian)
        # FSPEC: 2 bytes
        #   Let's check which FRNs are present.
        #   We want:
        #   FRN 1: Data Source Identifier (2 bytes) - present (Bit 1, 0x80)
        #   FRN 11: Track Number (2 bytes) - present (Bit 11 in second byte, 0x20)
        #   FRN 12: Calculated Position (4 bytes) - present (Bit 12, 0x10)
        #   FRN 13: Calculated Track Velocity (4 bytes) - present (Bit 13, 0x08)
        #   FSPEC Byte 1: 0x80 (FRN 1) | 0x01 (Extension bit for Byte 2) -> 0x81
        #   FSPEC Byte 2: 0x10 (FRN 11) | 0x08 (FRN 12) | 0x04 (FRN 13) -> 0x1C (Extension bit is 0)
        #
        # Fields:
        # - FRN 1 (Data Source Identifier): SAC=12, SIC=34 (2 bytes: 0x0C, 0x22)
        # - FRN 11 (Track Number): 1234 (2 bytes: 0x04, 0xD2)
        # - FRN 12 (Calculated Position in Cartesian Coordinates):
        #   X = 10 NM -> raw = 10 * 128 / 1.0 = 1280 (2 bytes signed: 0x05, 0x00)
        #   Y = -20 NM -> raw = -20 * 128 / 1.0 = -2560 (2 bytes signed: 0xF6, 0x00)
        # - FRN 13 (Calculated Track Velocity in Polar Coordinates):
        #   Ground Speed (cgs_raw): raw scale is 0.2197265625 knots.
        #     Let's set speed to 360 knots. cgs_raw = 360 / 0.2197265625 = 1638.39 -> 1638 (2 bytes: 0x06, 0x66)
        #   Track Angle (chdg_raw): raw scale is 360.0 / 65536.0 degrees.
        #     Let's set heading to 90 degrees. chdg_raw = 90 * 65536.0 / 360.0 = 16384 (2 bytes: 0x40, 0x00)
        
        fspec = b'\x81\x1C'
        frn1_data = struct.pack('>BB', 12, 34)
        frn11_data = struct.pack('>H', 1234)
        frn12_data = struct.pack('>hh', 1280, -2560)
        frn13_data = struct.pack('>HH', 1638, 16384)
        
        # Build packet payload (excluding category and length, as cat048.decode expects offset pointing to FSPEC)
        # The decode function: decode(payload: bytes, offset: int, block_length: int, category: int)
        payload = fspec + frn1_data + frn11_data + frn12_data + frn13_data
        
        plots = cat048.decode(payload, 0, len(payload) + 3, 48)
        
        self.assertEqual(len(plots), 1)
        plot = plots[0]
        
        self.assertEqual(plot['sac'], 12)
        self.assertEqual(plot['sic'], 34)
        self.assertEqual(plot['track_number'], 1234)
        
        # Positions:
        # X: 1280 * 1852.0 / 128.0 = 18520.0 meters (= 10 NM)
        # Y: -2560 * 1852.0 / 128.0 = -37040.0 meters (= -20 NM)
        self.assertAlmostEqual(plot['x'], 18520.0)
        self.assertAlmostEqual(plot['y'], -37040.0)
        
        # Velocity in extra_data:
        # ground_speed_nms = (1638 * 0.2197265625) / 3600.0 = 359.912 / 3600.0
        # track_angle = 16384 * 360.0 / 65536.0 = 90.0
        self.assertIn('extra_data', plot)
        extra = plot['extra_data']
        self.assertIn('ground_speed_nms', extra)
        self.assertIn('track_angle', extra)
        
        # GS in knots = ground_speed_nms * 3600.0 = 359.912
        gs_kts = extra['ground_speed_nms'] * 3600.0
        self.assertAlmostEqual(gs_kts, 359.912, places=3)
        self.assertAlmostEqual(extra['track_angle'], 90.0)
        
        print("[+] Mock CAT 048 packet successfully decoded!")
        print(f"    - Track: {plot['track_number']}")
        print(f"    - Position: X={plot['x']:.1f} m, Y={plot['y']:.1f} m")
        print(f"    - Speed: {gs_kts:.2f} knots")
        print(f"    - Track Angle: {extra['track_angle']:.2f}°")

if __name__ == '__main__':
    unittest.main()
