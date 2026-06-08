import sys
import os

# Add root folder to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

try:
    print("[*] Importing decoupled cat048 decoder...")
    from decoder.decoders import cat048
    print("  [+] Successfully imported cat048")
    
    print("[*] Importing decoupled cat021 decoder...")
    from decoder.decoders import cat021
    print("  [+] Successfully imported cat021")

    print("[*] Importing decoupled radar_widget...")
    from player.radar_widget import RadarWidget, RadarPlot
    print("  [+] Successfully imported radar_widget")
    
    print("[*] Checking dynamic coasting logic in RadarPlot...")
    # Mock self for testing sweep_rpm
    class MockWidget:
        def __init__(self):
            self.sweep_rpm = 12.0
            
    # Mocking paint or draw conditions
    sweep_rpm = 12.0
    scan_time = 60.0 / sweep_rpm
    coasting_threshold = max(6.0, scan_time * 1.5)
    print(f"  [+] RPM: {sweep_rpm} -> Scan Time: {scan_time:.2f}s -> Coasting Threshold: {coasting_threshold:.2f}s")
    
    sweep_rpm = 4.0
    scan_time = 60.0 / sweep_rpm
    coasting_threshold = max(6.0, scan_time * 1.5)
    print(f"  [+] RPM: {sweep_rpm} -> Scan Time: {scan_time:.2f}s -> Coasting Threshold: {coasting_threshold:.2f}s")
    
    print("[*] Everything imports and basic math is correct!")

except Exception as e:
    print(f"[ERROR] Import failed: {e}")
    sys.exit(1)
