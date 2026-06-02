import sys
import os
import time

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from decoder.data_engine import DataEngine

def run_integration_test():
    print("=== Testing DataEngine & DuckDB Dual Pipeline Integration ===")
    
    # 1. Clear any old caches or databases to enforce clean live scan
    db_path = "pass_analytics.duckdb"
    if os.path.exists(db_path):
        try:
            os.remove(db_path)
            print("Cleared default pass_analytics.duckdb database.")
        except Exception as e:
            print(f"Could not remove database file: {e}")

    # 2. Instantiate DataEngine
    engine = DataEngine()
    
    # Inject Monteros coordinate mapping
    engine.sensores[(226, 213)] = {
        'lat': -27.274167,
        'lon': -65.498333,
        'elev': 360.0,
        'name': "Monteros SSR",
        'category': "CAT048",
        'type': "SSR"
    }

    # Verify DuckDBRepository was successfully instantiated
    assert hasattr(engine, 'repo_db') and engine.repo_db is not None, "DataEngine lacks repo_db!"
    print("DuckDBRepository injected successfully inside DataEngine.")

    # 3. Decode live PCAP
    pcap_path = 'c:/documentos/decode_asterix/MTR_2026_04_16_16-28-16.pcap'
    print(f"Decoding ASTERIX stream from PCAP: {pcap_path} ...")
    start_time = time.time()
    plots, duration, active_sensors = engine.scan_pcap(pcap_path)
    end_time = time.time()
    
    print(f"Ingested PCAP in {end_time - start_time:.2f} seconds.")
    print(f"Memory plots parsed: {len(plots)}")
    print(f"Active sensors detected: {active_sensors}")

    # Wait for the background queue to drain completely
    print("Waiting for analytical pipeline queue to drain completely...")
    engine.repo_db.cola_insercion.join()
    print("Queue drained successfully.")

    # 4. Query DuckDB to verify all plots were asynchronously committed
    print("Querying DuckDB table 'asterix_plots' for verification...")
    count_rows = engine.repo_db.query("SELECT COUNT(*) FROM asterix_plots")
    duckdb_count = count_rows[0][0] if count_rows else 0
    print(f"Total plots stored in DuckDB: {duckdb_count}")

    # 5. Clean close
    engine.close()
    print("DataEngine and DuckDB repository closed cleanly.")

    # Assertions
    # Monteros PCAP has exactly 81,431 CAT 48 plots
    assert len(plots) == 81431, f"Expected 81431 plots in memory, got {len(plots)}"
    assert duckdb_count == 81431, f"Expected 81431 plots in DuckDB, got {duckdb_count}"
    assert (226, 213) in active_sensors, "Monteros SSR sensor not detected!"
    
    print("=== DUAL PIPELINE INTEGRATION TEST PASSED FLAWLESSLY! ===")

if __name__ == "__main__":
    run_integration_test()
