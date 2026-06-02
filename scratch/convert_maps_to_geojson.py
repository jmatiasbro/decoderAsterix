import os
import re
import json
from typing import Dict, Tuple, List, Optional, Any

def parse_coordinate(coord_str: str) -> Optional[Tuple[float, float]]:
    match = re.match(r'^(\d{2})(\d{2})(\d{2}(?:\.\d+)?)([NS])(\d{3})(\d{2})(\d{2}(?:\.\d+)?)([EW])$', coord_str.strip())
    if not match:
        return None
    
    lat_deg, lat_min, lat_sec, lat_hem, lon_deg, lon_min, lon_sec, lon_hem = match.groups()
    
    lat = float(lat_deg) + float(lat_min) / 60.0 + float(lat_sec) / 3600.0
    if lat_hem == 'S':
        lat = -lat
        
    lon = float(lon_deg) + float(lon_min) / 60.0 + float(lon_sec) / 3600.0
    if lon_hem == 'W':
        lon = -lon
        
    return lat, lon

def parse_coordinate_robust(coord_line: str) -> Optional[Tuple[float, float]]:
    tokens = coord_line.strip().split()
    if not tokens:
        return None
    return parse_coordinate(tokens[0])

def map_to_geojson(filepath: str) -> Dict[str, Any]:
    print(f"Parsing: {filepath}")
    features = []
    
    with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
        lines = f.readlines()
        
    idx = 0
    while idx < len(lines):
        line = lines[idx].strip()
        if not line or line.startswith('/*') or line.startswith('//') or line.startswith('*'):
            idx += 1
            continue
            
        line_lower = line.lower()
        
        # Polyline, Polilinea, AirwayPolyline
        if 'polyline' in line_lower or 'polilinea' in line_lower:
            parts = line.split()
            if len(parts) >= 2:
                try:
                    count = int(parts[1])
                except ValueError:
                    count = 0
                    
                airway_name = ""
                match_bracket = re.search(r'\[([^\]]+)\]', line)
                if match_bracket:
                    airway_name = match_bracket.group(1).strip()
                    
                coords_parsed = []
                idx += 1
                parsed_count = 0
                while parsed_count < count and idx < len(lines):
                    coord_line = lines[idx].strip()
                    if not coord_line or coord_line.startswith('/*') or coord_line.startswith('//'):
                        idx += 1
                        continue
                    res = parse_coordinate_robust(coord_line)
                    if res:
                        lat, lon = res
                        coords_parsed.append([lon, lat])  # GeoJSON is [lon, lat]
                        parsed_count += 1
                    idx += 1
                
                if coords_parsed:
                    features.append({
                        "type": "Feature",
                        "geometry": {
                            "type": "LineString",
                            "coordinates": coords_parsed
                        },
                        "properties": {
                            "layer": "AEROVIAS" if airway_name else "LINEAS_DE_MAPA",
                            "name": airway_name,
                            "type": "polyline"
                        }
                    })
            continue
            
        # Text
        elif line_lower.startswith('text\t') or line_lower.startswith('text '):
            parts = line.split(maxsplit=2)
            if len(parts) >= 3:
                coord_str = parts[1].strip()
                label_str = parts[2].strip().replace('"', '')
                res = parse_coordinate_robust(coord_str)
                if res:
                    lat, lon = res
                    features.append({
                        "type": "Feature",
                        "geometry": {
                            "type": "Point",
                            "coordinates": [lon, lat]
                        },
                        "properties": {
                            "layer": "NOMBRES_WAYPOINTS",
                            "name": label_str,
                            "type": "text"
                        }
                    })
            idx += 1
            continue
            
        # FixPointSymbol
        elif line_lower.startswith('fixpointsymbol'):
            parts = line.split(maxsplit=3)
            if len(parts) >= 4:
                coord_str = parts[1].strip()
                label_str = parts[3].strip().replace('[', '').replace(']', '').strip()
                res = parse_coordinate_robust(coord_str)
                if res:
                    lat, lon = res
                    features.append({
                        "type": "Feature",
                        "geometry": {
                            "type": "Point",
                            "coordinates": [lon, lat]
                        },
                        "properties": {
                            "layer": "SIMBOLOS_WAYPOINTS",
                            "name": label_str,
                            "type": "symbol"
                        }
                    })
            idx += 1
            continue
            
        idx += 1
        
    return {
        "type": "FeatureCollection",
        "features": features
    }

def main():
    base_dir = r"c:\documentos\decode_asterix\files\INFERIOR"
    
    files_to_convert = [
        "RNAV_INF.map",
        "NO_RNAV_INF.map",
        "fix_nombres_RNAV_INF.map",
        "fix_nombres_NO_RNAV_INF.map"
    ]
    
    merged_features = []
    
    for filename in files_to_convert:
        map_path = os.path.join(base_dir, filename)
        if os.path.exists(map_path):
            geojson_data = map_to_geojson(map_path)
            out_filename = filename.replace(".map", ".geojson")
            out_path = os.path.join(base_dir, out_filename)
            
            with open(out_path, 'w', encoding='utf-8') as f:
                json.dump(geojson_data, f, indent=2)
            print(f"Successfully wrote GeoJSON to: {out_path} with {len(geojson_data['features'])} features.")
            
            merged_features.extend(geojson_data['features'])
            
    # Also create the merged INFERIOR.geojson containing everything
    merged_data = {
        "type": "FeatureCollection",
        "features": merged_features
    }
    merged_path = os.path.join(base_dir, "INFERIOR.geojson")
    with open(merged_path, 'w', encoding='utf-8') as f:
        json.dump(merged_data, f, indent=2)
    print(f"Successfully wrote MERGED GeoJSON to: {merged_path} with {len(merged_features)} total features.")

if __name__ == "__main__":
    main()
