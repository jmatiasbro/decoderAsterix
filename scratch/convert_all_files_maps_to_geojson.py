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

def parse_map_recursive(filepath: str, parsed_files: set) -> List[Dict[str, Any]]:
    filepath = os.path.abspath(filepath)
    if filepath in parsed_files:
        return []
    parsed_files.add(filepath)
    
    if not os.path.exists(filepath):
        print(f"Warning: File not found: {filepath}")
        return []
        
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
        
        # Check if it's a reference to another map file
        if '.map' in line_lower and not 'polyline' in line_lower and not 'polilinea' in line_lower:
            parts = line.split()
            map_ref = parts[0]
            filename = os.path.basename(map_ref)
            parent_dir = os.path.dirname(filepath)
            
            # Resolve possible candidate locations
            candidate1 = os.path.join(parent_dir, filename)
            base_project = r"c:\documentos\decode_asterix"
            candidate2 = os.path.join(base_project, "files", "INFERIOR", filename)
            candidate3 = os.path.join(base_project, "files", filename)
            candidate4 = os.path.join(parent_dir, "INFERIOR", filename)
            
            resolved_path = None
            for cand in [candidate1, candidate2, candidate3, candidate4]:
                if os.path.exists(cand):
                    resolved_path = cand
                    break
                    
            if resolved_path:
                sub_features = parse_map_recursive(resolved_path, parsed_files)
                features.extend(sub_features)
            idx += 1
            continue
            
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
        
    return features

def main():
    files_dir = r"c:\documentos\decode_asterix\files"
    print(f"Scanning files directory recursively: {files_dir}")
    
    count_converted = 0
    
    for root, dirs, files in os.walk(files_dir):
        for file in files:
            if file.lower().endswith(".map"):
                map_path = os.path.join(root, file)
                geojson_path = map_path.replace(".map", ".geojson")
                
                # Perform recursive parse to handle submap list files cleanly
                parsed_files = set()
                features = parse_map_recursive(map_path, parsed_files)
                
                if features:
                    geojson_data = {
                        "type": "FeatureCollection",
                        "features": features
                    }
                    
                    with open(geojson_path, 'w', encoding='utf-8') as f:
                        json.dump(geojson_data, f, indent=2)
                    
                    print(f"Converted: {file} -> {os.path.basename(geojson_path)} ({len(features)} features)")
                    count_converted += 1
                else:
                    print(f"Skipped/Empty: {file}")
                    
    print(f"\n--- TRANSFORMATION COMPLETE ---")
    print(f"Successfully transformed {count_converted} airspace charts to premium GeoJSON format!")

if __name__ == "__main__":
    main()
