import sys
import os
import re
from typing import Optional

# Add project root to python path
project_root = r"c:\documentos\decode_asterix"
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from player.main_window import parse_coordinate

def parse_coordinate_robust(coord_line: str) -> Optional[tuple]:
    # Extract only the first token (which contains the coordinate)
    tokens = coord_line.strip().split()
    if not tokens:
        return None
    coord_str = tokens[0]
    return parse_coordinate(coord_str)

def parse_map_file_robust(path, segments, update_ext):
    if not os.path.exists(path):
        print(f"File not found: {path}")
        return
        
    print(f"Parsing: {path}")
    with open(path, 'r', encoding='utf-8', errors='ignore') as f:
        lines = f.readlines()
        
    idx = 0
    while idx < len(lines):
        line = lines[idx].strip()
        if not line or line.startswith('/*') or line.startswith('//'):
            idx += 1
            continue
            
        line_lower = line.lower()
        
        # Check if it is a list map referencing other .map files
        if '.map' in line_lower and not line_lower.startswith('polyline') and not line_lower.startswith('polilinea'):
            # Extract the map path
            parts = line.split()
            map_ref = parts[0] # e.g. SACF/AEROVIAS/INFERIOR/RNAV_INF.map
            filename = os.path.basename(map_ref)
            # Try to find the file in the same directory, or project files/INFERIOR/
            parent_dir = os.path.dirname(path)
            candidate1 = os.path.join(parent_dir, filename)
            candidate2 = os.path.join(project_root, "files", "INFERIOR", filename)
            candidate3 = os.path.join(project_root, "files", filename)
            
            submap_path = None
            for cand in [candidate1, candidate2, candidate3]:
                if os.path.exists(cand):
                    submap_path = cand
                    break
                    
            if submap_path:
                parse_map_file_robust(submap_path, segments, update_ext)
            else:
                print(f"Could not resolve submap: {map_ref}")
            idx += 1
            continue
            
        if line_lower.startswith('polilinea') or line_lower.startswith('polyline'):
            parts = line.split()
            if len(parts) >= 2:
                try:
                    count = int(parts[1])
                except ValueError:
                    count = 0
                
                # Try to extract airway name if present inside brackets [L405  ]
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
                        coords_parsed.append((lat, lon))
                        update_ext(lat, lon)
                        parsed_count += 1
                    idx += 1
                
                if coords_parsed:
                    # If an airway name was found, use the AEROVIAS layer
                    layer = "AEROVIAS" if airway_name else "LINEAS_DE_MAPA"
                    lat0, lon0 = coords_parsed[0]
                    segments.append(('M', layer, lat0, lon0))
                    for lat, lon in coords_parsed[1:]:
                        segments.append(('L', layer, lat, lon))
                continue
                
        elif line_lower.startswith('text\t') or line_lower.startswith('text '):
            # Text	370536.00S0642027.00W	"AKPUR"
            parts = line.split(maxsplit=2)
            if len(parts) >= 3:
                coord_str = parts[1].strip()
                label_str = parts[2].strip().replace('"', '')
                res = parse_coordinate_robust(coord_str)
                if res:
                    lat, lon = res
                    segments.append(('T', "NOMBRES_WAYPOINTS", lat, lon, label_str))
                    update_ext(lat, lon)
            idx += 1
            continue
            
        elif line_lower.startswith('fixpointsymbol'):
            # FixPointSymbol	370536.00S0642027.00W	265	[AKPUR ]
            parts = line.split(maxsplit=3)
            if len(parts) >= 4:
                coord_str = parts[1].strip()
                label_str = parts[3].strip().replace('[', '').replace(']', '').strip()
                res = parse_coordinate_robust(coord_str)
                if res:
                    lat, lon = res
                    segments.append(('S', "SIMBOLOS_WAYPOINTS", lat, lon, label_str))
                    update_ext(lat, lon)
            idx += 1
            continue
            
        idx += 1

def test_parse():
    segments = []
    min_x = min_y = float('inf')
    max_x = max_y = float('-inf')
    
    def update_ext(x, y):
        nonlocal min_x, max_x, min_y, max_y
        min_x = min(min_x, x)
        max_x = max(max_x, x)
        min_y = min(min_y, y)
        max_y = max(max_y, y)
        
    start_map = os.path.join(project_root, "files", "INFERIOR", "INFERIOR.map")
    parse_map_file_robust(start_map, segments, update_ext)
    
    print(f"\nParse complete.")
    print(f"Total parsed segments: {len(segments)}")
    print(f"Limits: Lat ({min_x:.4f} to {max_x:.4f}), Lon ({min_y:.4f} to {max_y:.4f})")
    
    # Analyze segment types
    types = {}
    for seg in segments:
        t = seg[0]
        types[t] = types.get(t, 0) + 1
    print("Segment types count:")
    for t, cnt in types.items():
        print(f"  Type '{t}': {cnt}")

test_parse()
