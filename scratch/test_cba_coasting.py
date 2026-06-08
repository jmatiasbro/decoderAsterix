import sys
import os
import unittest
import dpkt

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from decoder.asterix_router import AsterixRouter
from player.radar_widget import RadarPlot, SimulationTime

class TestCbaCoastingLifespan(unittest.TestCase):
    def setUp(self):
        # Reset simulation time before each test
        SimulationTime.instance().reset()

    def test_cba_dataset_rpm_and_coasting_logic(self):
        filepath = 'c:/documentos/decode_asterix/cba_010626.pcap'
        self.assertTrue(os.path.exists(filepath), f"File {filepath} not found")
        
        router = AsterixRouter()
        detected_rpm = None
        sample_record = None
        
        # Read the pcap file to find rotation speed and a sample CAT048 target
        with open(filepath, 'rb') as f:
            pcap = dpkt.pcap.Reader(f)
            for ts, buf in pcap:
                try:
                    eth = dpkt.ethernet.Ethernet(buf)
                    if not isinstance(eth.data, dpkt.ip.IP): continue
                    ip = eth.data
                    if not isinstance(ip.data, dpkt.udp.UDP): continue
                    udp = ip.data
                    data = udp.data
                    if len(data) < 3: continue
                    
                    records = router.procesar_paquete_udp(data)
                    if records:
                        for rec in records:
                            cat = rec.get('category')
                            extra = rec.get('extra_data', {})
                            
                            # Detect antenna RPM from CAT034
                            if cat == 34 and 'antenna_rpm' in extra and detected_rpm is None:
                                detected_rpm = extra['antenna_rpm']
                                
                            # Extract a sample CAT048 target plot
                            if cat == 48 and sample_record is None and rec.get('mode_3a') is not None:
                                sample_record = rec
                                
                    if detected_rpm is not None and sample_record is not None:
                        break
                except Exception:
                    pass
                    
        # Verify that we could find the RPM and a sample plot in the dataset
        self.assertIsNotNone(detected_rpm, "Could not detect antenna RPM from CAT034 in PCAP")
        self.assertIsNotNone(sample_record, "Could not find a sample CAT048 target plot in PCAP")
        
        print(f"\n[TEST CBA] Detected Antenna Speed: {detected_rpm:.2f} RPM")
        
        # Calculate scan period: scan_time = 60.0 / RPM
        scan_time = 60.0 / detected_rpm
        print(f"[TEST CBA] Calculated Scan Period (1 sweep): {scan_time:.3f} seconds")
        print(f"[TEST CBA] 2 Sweeps (Coasting Threshold): {2.0 * scan_time:.3f} seconds")
        print(f"[TEST CBA] 3 Sweeps (Deletion Threshold): {3.0 * scan_time:.3f} seconds")
        
        # Instantiate a RadarPlot using the sample record
        # Note: RadarPlot constructor signature matches the one in radar_widget.py
        plot = RadarPlot(
            x=sample_record.get('x', 0.0),
            y=sample_record.get('y', 0.0),
            sac_sic=f"{sample_record.get('sac')}/{sample_record.get('sic')}",
            category=sample_record.get('category'),
            timestamp=sample_record.get('timestamp', 0.0),
            mode3a=str(sample_record.get('mode_3a')),
            callsign=sample_record.get('callsign', ''),
            flight_level=sample_record.get('flight_level'),
            is_track=True,
            mode_s=sample_record.get('mode_s', ''),
            track_angle=sample_record.get('track_angle'),
            ground_speed=sample_record.get('ground_speed')
        )
        
        # We manually control SimulationTime to simulate exact plot ages
        base_time = 1000.0
        SimulationTime.instance().set_time(base_time)
        plot._last_seen = base_time  # Plot just updated
        
        # Case 1: age is less than 2 sweeps (e.g. 1.5 sweeps)
        age_active = 1.5 * scan_time
        SimulationTime.instance().set_time(base_time + age_active)
        self.assertAlmostEqual(plot.age, age_active, places=4)
        
        coasting_threshold = 2.2 * scan_time
        is_coasting_active = plot.age > coasting_threshold
        max_age = 3.2 * scan_time
        is_alive_active = plot.is_alive(max_age)
        
        print(f"[TEST CBA] At age = {plot.age:.3f}s (1.5 sweeps): coasting={is_coasting_active}, alive={is_alive_active}")
        self.assertFalse(is_coasting_active, "Plot should NOT be in coasting state under 2.2 sweeps")
        self.assertTrue(is_alive_active, "Plot should be alive under 3.2 sweeps")
        
        # Case 2: age is between 2 and 3 sweeps (e.g. 2.5 sweeps)
        age_coasting = 2.5 * scan_time
        SimulationTime.instance().set_time(base_time + age_coasting)
        self.assertAlmostEqual(plot.age, age_coasting, places=4)
        
        is_coasting_coast = plot.age > coasting_threshold
        is_alive_coast = plot.is_alive(max_age)
        
        print(f"[TEST CBA] At age = {plot.age:.3f}s (2.5 sweeps): coasting={is_coasting_coast}, alive={is_alive_coast}")
        self.assertTrue(is_coasting_coast, "Plot should be in coasting state (gray) on the 3rd sweep")
        self.assertTrue(is_alive_coast, "Plot should still be alive on the 3rd sweep")
        
        # Case 3: age is 3 sweeps or more (e.g. 3.3 sweeps)
        age_deleted = 3.3 * scan_time
        SimulationTime.instance().set_time(base_time + age_deleted)
        self.assertAlmostEqual(plot.age, age_deleted, places=4)
        
        is_alive_deleted = plot.is_alive(max_age)
        
        print(f"[TEST CBA] At age = {plot.age:.3f}s (3.3 sweeps): alive={is_alive_deleted}")
        self.assertFalse(is_alive_deleted, "Plot should be marked for deletion (not alive) after 3.2 sweeps")

if __name__ == '__main__':
    unittest.main()
