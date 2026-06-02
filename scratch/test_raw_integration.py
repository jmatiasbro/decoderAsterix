import sys
import os

# Add project root to python path
project_root = r"c:\documentos\decode_asterix"
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from decoder.data_engine import DataEngine

def test_raw_integration():
    print("=== STARTING RAW INTEGRATION TEST ===")
    
    # 1. Instantiate DataEngine
    # Using a clean/temporary directory for cache to force full decoding in this test
    import tempfile
    temp_cache_dir = tempfile.mkdtemp()
    print(f"Using temp cache dir: {temp_cache_dir}")
    
    # We can load standard sensors to allow correct coordinates calculation
    from utils.geo import cargar_sensores
    sensores = {}
    try:
        sensores = cargar_sensores()
        print(f"Loaded {len(sensores)} sensors successfully.")
    except Exception as e:
        print(f"Could not load sensors: {e}. Using empty sensor registry.")
        
    engine = DataEngine(sensores=sensores, cache_dir=temp_cache_dir)
    
    # 2. Test user's wrapped file (the .Z file)
    wrapped_file = os.path.join(project_root, "20251111112025111112")
    print(f"\nScanning wrapped .Z file: {wrapped_file}")
    
    plots, duration, sensors = engine.scan_pcap(wrapped_file)
    print(f"Scan complete. Plots: {len(plots)}, Duration: {duration:.2f} seconds, Sensors: {sensors}")
    
    # Check assertions
    assert len(plots) > 0, "No plots decoded from wrapped file!"
    assert duration > 0, "Duration should be positive for wrapped file!"
    assert len(sensors) > 0, "No sensors were detected in wrapped file!"
    
    # Check that plots have correct attributes
    first_plot = plots[0]
    print(f"Sample Plot: ID={first_plot.id}, SAC/SIC={first_plot.sac_sic}, CAT={first_plot.category}, Time={first_plot.time}, Lat={first_plot.lat:.5f}, Lon={first_plot.lon:.5f}")
    
    # 3. Test pure raw file
    pure_raw_file = os.path.join(project_root, "asterix_decoder-0.7.4", "asterix", "sample_data", "cat048.raw")
    print(f"\nScanning pure raw file: {pure_raw_file}")
    
    pure_plots, pure_duration, pure_sensors = engine.scan_pcap(pure_raw_file)
    print(f"Scan complete. Plots: {len(pure_plots)}, Duration: {pure_duration:.2f} seconds, Sensors: {pure_sensors}")
    
    # Check assertions
    assert len(pure_plots) == 1, f"Expected 1 plot from pure raw file, got {len(pure_plots)}!"
    
    # 4. Clean up DuckDB to avoid locking database
    engine.close()
    
    print("\n=== ALL INTEGRATION TESTS PASSED SUCCESSFULLY! ===")

if __name__ == "__main__":
    try:
        test_raw_integration()
    except AssertionError as e:
        print(f"\n❌ ASSERTION ERROR: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ UNEXPECTED ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
