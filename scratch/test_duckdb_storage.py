import sys
import os
import time

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from storage.duckdb_repo import DuckDBRepository

def run_test():
    print("=== Testing DuckDB analytical persistence layer (Phase 1) ===")
    
    db_path = "test_pass_analytics.duckdb"
    
    # Remove old database file if exists to ensure a clean test
    if os.path.exists(db_path):
        try:
            os.remove(db_path)
            print(f"Cleared old test database: {db_path}")
        except Exception as e:
            print(f"Could not remove old db file: {e}")

    # Instantiate the repository
    repo = DuckDBRepository(db_path=db_path)
    print("Database connection initialized. Schema created.")

    # 1. Insert some synthetic plots of different types to test robust extraction
    plot_1 = {
        'time': 12345.67,
        'category': 48,
        'sac_sic': '226/230',
        'mode_s': 'E42A8C',
        'lat': -34.822222,
        'lon': -58.535833,
        'flight_level': 240,
        'raw_azimuth': 45.12,
        'raw_range': 100.5
    }
    
    # Format 2 (raw output / timestamp instead of time)
    plot_2 = {
        'timestamp': 12349.89,
        'category': 21,
        'sac_sic': '226/108',
        'target_address': 'A0B1C2',
        'lat_render': -34.500000,
        'lon_render': -59.500000,
        'flight_level': None,
        'raw_azimuth': None,
        'raw_range': None
    }

    print("Inserting 2 synthetic plots...")
    repo.guardar_plot(plot_1)
    repo.guardar_plot(plot_2)

    # Let's insert many more plots to trigger a batch appender flush (>200 plots)
    print("Bulk inserting 250 more plots...")
    for i in range(250):
        repo.guardar_plot({
            'time': 12400.0 + i,
            'category': 48,
            'sac_sic': '226/213',
            'mode3a': '1200',
            'lat': -27.27 - (i * 0.001),
            'lon': -65.49 + (i * 0.001),
            'flight_level': 100 + i,
            'raw_azimuth': 90.0,
            'raw_range': 20.0
        })

    # Wait for the background thread to completely process and insert all plots from the queue
    print("Waiting for queue to drain completely...")
    repo.cola_insercion.join()

    # 2. Query DuckDB to verify the data was correctly inserted
    print("Querying table 'asterix_plots'...")
    rows = repo.query("SELECT COUNT(*) FROM asterix_plots")
    count = rows[0][0] if rows else 0
    print(f"Total plots stored in DuckDB: {count}, rows={rows}")

    # Query details
    print("\nFirst 3 plots stored:")
    details = repo.query("SELECT timestamp, category, sac_sic, track_id, lat, lon, flight_level FROM asterix_plots LIMIT 3")
    for r in details:
        print(f"  - TOD={r[0]:.2f}s | Cat={r[1]} | SAC_SIC={r[2]} | ID={r[3]} | Lat={r[4]:.4f} | Lon={r[5]:.4f} | FL={r[6]}")

    # Close repo cleanly
    repo.close()
    print("\nDatabase closed successfully.")

    # Validation asserts
    assert count == 252, f"Expected 252 plots, got {count}"
    assert details[0][3] == 'E42A8C', f"Expected ID E42A8C, got {details[0][3]}"
    assert details[1][3] == 'A0B1C2', f"Expected ID A0B1C2, got {details[1][3]}"
    assert details[1][6] == '---', f"Expected FL '---' for None, got {details[1][6]}"
    print("=== ALL PERSISTENCE TESTS PASSED FLawlessly! ===")

if __name__ == "__main__":
    run_test()
