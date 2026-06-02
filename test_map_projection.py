import sys
import math
import matplotlib.pyplot as plt
import ezdxf

# Add local path to import modules
sys.path.append('c:/documentos/decode_asterix')
from geo_tools import CoordinateTransformer
from config import get_sensor_position

def run_test():
    # Use Cordoba Radar
    sensor_lat = -31.31
    sensor_lon = -64.21
    
    METERS_PER_NM = 1852.0
    
    transformer = CoordinateTransformer()
    
    # 1. Test coordinate conversion scale
    # If point is 100 NM East
    x_nm, y_nm = 100.0, 0.0
    x_m, y_m = x_nm * METERS_PER_NM, y_nm * METERS_PER_NM
    lat_wgs, lon_wgs = transformer.cartesian_to_wgs84(sensor_lat, sensor_lon, x_m, y_m)
    print(f"Test Point (100NM East): X={x_m}m, Y={y_m}m -> Lat={lat_wgs}, Lon={lon_wgs}")
    
    # Check back
    x_lcc_m, y_lcc_m = transformer.wgs84_to_lcc_cartesian(sensor_lat, sensor_lon, lat_wgs, lon_wgs)
    print(f"Back to LCC: X={x_lcc_m}m, Y={y_lcc_m}m")
    
    # 2. Load DXF Map
    dxf_path = 'c:/documentos/decode_asterix/mapa/mapa.dxf'
    doc = ezdxf.readfile(dxf_path)
    msp = doc.modelspace()
    
    wgs_lines = []
    
    for entity in msp:
        if entity.dxftype() == 'LINE':
            start = entity.dxf.start
            end = entity.dxf.end
            
            x1_m = start.x * METERS_PER_NM
            y1_m = start.y * METERS_PER_NM
            x2_m = end.x * METERS_PER_NM
            y2_m = end.y * METERS_PER_NM
            
            lon1, lat1 = transformer.cartesian_to_wgs84(sensor_lat, sensor_lon, x1_m, y1_m)
            lon2, lat2 = transformer.cartesian_to_wgs84(sensor_lat, sensor_lon, x2_m, y2_m)
            
            wgs_lines.append(((lon1, lat1), (lon2, lat2)))
    
    # Range Rings WGS
    rings = []
    for r_nm in range(50, 300, 50):
        r_deg_lat = r_nm / 60.0
        r_deg_lon = (r_nm / 60.0) / math.cos(math.radians(sensor_lat))
        rings.append((r_nm, r_deg_lon, r_deg_lat))
    
    # Graphical Plot
    plt.figure(figsize=(10, 10))
    
    for (lon1, lat1), (lon2, lat2) in wgs_lines:
        plt.plot([lon1, lon2], [lat1, lat2], color='blue', alpha=0.5)
        
    # Plot Rings as ellipses (approximate)
    theta = [i * math.pi / 180 for i in range(360)]
    for r_nm, rx, ry in rings:
        x = [sensor_lon + rx * math.cos(t) for t in theta]
        y = [sensor_lat + ry * math.sin(t) for t in theta]
        plt.plot(x, y, color='red', linestyle='--')
        plt.text(sensor_lon, sensor_lat + ry, f'{r_nm}NM', color='red')
        
    plt.scatter([sensor_lon], [sensor_lat], color='green', marker='x', s=100, label='Sensor')
    
    plt.title('Proyección WGS84 - Mapa DXF vs Anillos de Rango')
    plt.xlabel('Longitud')
    plt.ylabel('Latitud')
    plt.grid(True)
    plt.legend()
    plt.axis('equal')
    
    plt.savefig('c:/documentos/decode_asterix/test_map_projection.png')
    print("Grafica generada en c:/documentos/decode_asterix/test_map_projection.png")

if __name__ == "__main__":
    run_test()
