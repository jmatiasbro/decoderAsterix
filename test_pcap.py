import glob
import sys
import traceback
import tempfile
import shutil
from utils.geo import cargar_sensores
from decoder.data_engine import DataEngine

pcaps = glob.glob("*.pcap") + glob.glob("*.pcapng")
if not pcaps:
    print("No PCAP files found.")
    sys.exit(0)

# Load sensors
sensores = cargar_sensores("default-site-params")
print(f"Loaded {len(sensores)} sensors from default-site-params")

cache_dir = tempfile.mkdtemp(prefix="debug_asterix_cache_")
try:
    for pcap in pcaps:
        print(f"\n--- Testing DataEngine with {pcap} ---")
        engine = DataEngine(sensores=sensores, cache_dir=cache_dir)
        try:
            plots, duration, sensors = engine.scan_pcap(pcap)
            print(f"Success! Found {len(plots)} plots, duration {duration:.1f}s, sensors {sensors}")
            if plots:
                print(f"  First 3 plots:")
                for p in plots[:3]:
                    print(f"    ID={p.id}, SAC_SIC={p.sac_sic}, CAT={p.category}, TIME={p.time}, LAT={p.lat:.5f}, LON={p.lon:.5f}")
        except Exception as e:
            print(f"Error during scan_pcap for {pcap}:")
            traceback.print_exc()
finally:
    shutil.rmtree(cache_dir, ignore_errors=True)
