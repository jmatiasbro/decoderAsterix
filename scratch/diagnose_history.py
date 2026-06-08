import sys
import os
import time

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from PyQt6.QtWidgets import QApplication
from player.radar_widget import RadarWidget, RadarPlot, SimulationTime

def test_history():
    print("=== Diagnosing History Deque ===")
    app = QApplication(sys.argv)
    widget = RadarWidget(sensores={})
    widget.reset_origin_for_new_file(-31.31, -64.21, 1, 1)
    widget.history_limit = 500
    widget.history_visible = True
    widget._is_playing = True
    
    # Enable PCAP mode
    SimulationTime.instance().set_time(1000.0)
    
    plot_data = {
        'id': 'TEST_1',
        'sac_sic': '1/1',
        'category': 48,
        'time': 1000.0,
        'lat_render': -31.31,
        'lon_render': -64.21,
        'x': 0.0,
        'y': 0.0,
        'raw_azimuth': 0.0,
        'raw_range': 0.0,
        'mode3a': 1200,
        'sac_sic': '1/1'
    }
    
    # 1. Ingest first plot
    print("Ingesting plot at T=1000.0...")
    widget.agregar_plot_individual(plot_data, trigger_update=False)
    
    # Promote to self.tracks
    widget._promote_all_pending()
    
    print(f"Tracks in widget: {list(widget.tracks.keys())}")
    print(f"History keys: {list(widget.history.keys())}")
    print(f"History points for 2260_1/1: {len(widget.history['2260_1/1'])}")
    
    # 2. Ingest second plot at T=1004.0 (4 seconds later)
    print("\nIngesting plot at T=1004.0...")
    SimulationTime.instance().set_time(1004.0)
    plot_data['time'] = 1004.0
    plot_data['x'] = 1000.0
    plot_data['y'] = 1000.0
    widget.agregar_plot_individual(plot_data, trigger_update=False)
    
    print(f"History points for 2260_1/1: {len(widget.history['2260_1/1'])}")
    for i, hp in enumerate(widget.history['2260_1/1']):
        print(f"  Point {i}: timestamp={hp.timestamp}, x={hp.x}, y={hp.y}")
        
    # Check is_alive
    plot = widget.tracks['2260_1/1']
    print(f"\nPlot age: {plot.age}")
    print(f"Plot is_alive(): {plot.is_alive()}")
    
    # Check max_age and alpha
    scan_time = 4.0
    max_age = 3.2 * scan_time
    alpha = plot.get_alpha(max_age)
    print(f"get_alpha({max_age}): {alpha}")

    # 3. Ingest out of order plot (negative delta: T=1003.0, less than last_seen=1004.0)
    print("\nIngesting out-of-order plot at T=1003.0...")
    SimulationTime.instance().set_time(1003.0)
    plot_data['time'] = 1003.0
    widget.agregar_plot_individual(plot_data, trigger_update=False)
    print(f"History points for 2260_1/1: {len(widget.history['2260_1/1'])}")
    for i, hp in enumerate(widget.history['2260_1/1']):
        print(f"  Point {i}: timestamp={hp.timestamp}, x={hp.x}, y={hp.y}")

    # 4. Simulate backward seek to T=1002.0 (should prune points with T > 1002.0)
    print("\nSimulating seek back to T=1002.0...")
    SimulationTime.instance().set_time(1002.0)
    plot_data['time'] = 1002.0
    widget.agregar_plot_individual(plot_data, trigger_update=False)
    print(f"History points for 2260_1/1: {len(widget.history['2260_1/1'])}")
    for i, hp in enumerate(widget.history['2260_1/1']):
        print(f"  Point {i}: timestamp={hp.timestamp}, x={hp.x}, y={hp.y}")

if __name__ == '__main__':
    test_history()
