import sys
import os
import json

sys.path.append('c:/documentos/decode_asterix')
from decoder.data_engine import DataEngine
from analysis.pass_analyzer import PASSAnalyticsEngine
from utils.geo import GeoTools

def run_analysis():
    print("Ingesting PCAP file...")
    engine = DataEngine()
    
    # Inject Monteros sensor coordinates so the decoder can project polar plots to WGS-84
    engine.sensores[(226, 213)] = {
        'lat': -27.274167,
        'lon': -65.498333,
        'elev': 360.0,
        'name': "Monteros SSR",
        'category': "CAT048",
        'type': "SSR"
    }
    
    # Decode MTR pcap
    plots, duration, active_sensors = engine.scan_pcap('c:/documentos/decode_asterix/MTR_2026_04_16_16-28-16.pcap')
    print(f"Total plots decoded: {len(plots)}")
    
    # Convert AsterixPlot instances to dictionaries (matching the main GUI format)
    plots_data = [p.to_dict() for p in plots]
    
    # We need sensor_info mapping
    sensor_sac = 226
    sensor_sic = 213
    
    # Let's get the site params coordinates for 226/213 (Monteros)
    # Monteros is at lat=-27.274167, lon=-65.498333, elev=360.0
    sensores = {
        (226, 213): {
            'lat': -27.274167,
            'lon': -65.498333,
            'elev': 360.0,
            'name': "Monteros SSR",
            'category': "CAT048",
            'type': "SSR"
        }
    }
    
    # Run PASS engine
    print("Running PASS Analytics Engine...")
    pass_engine = PASSAnalyticsEngine(sensores=sensores)
    # Since Monteros is CAT 48, RPM is typically 7.9 (period = 7.6)
    results = pass_engine.analyze_data(plots_data, {(226, 213): 7.9})
    
    print("\n=========================================")
    print("PASS ANALYSIS RESULTS FOR MONTEROS SSR")
    print("=========================================")
    for key, data in results.items():
        print(f"Sensor: {data['name']} [{key[0]}/{key[1]}]")
        print(f"Total Plots: {data['total_plots']}")
        print(f"RPM: {data['rpm']:.1f}")
        print(f"Global Pd: {data['pd_global']:.2f}%")
        print(f"Mode A Pd: {data['pd_mode_a']:.2f}%")
        print(f"Mode C Pd: {data['pd_mode_c']:.2f}%")
        print(f"Range Bias: {data['range_bias_m']:.2f} m")
        print(f"Azimuth Bias: {data['azimuth_bias_deg']:.4f}°")
        print(f"Range Jitter: {data['range_jitter_m']:.2f} m")
        print(f"Azimuth Jitter: {data['azimuth_jitter_deg']:.4f}°")
        print(f"Split Plots: {data['split_plots_pct']:.2f}%")
        print(f"False Plots: {data['false_plots_pct']:.2f}%")
        
if __name__ == "__main__":
    run_analysis()
