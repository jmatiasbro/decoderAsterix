import os
import json
from typing import Dict, List, Tuple
from PyQt6.QtGui import QPainterPath
from player.video_map_manager import VideoMapManager, VideoMapLayer, is_valid_coord

# Neon Terminal colors for beautiful log output
NEON_GREEN = "\033[92m"
NEON_CYAN = "\033[96m"
NEON_MAGENTA = "\033[95m"
RESET = "\033[0m"

class MapManager(VideoMapManager):
    """
    Subclass of VideoMapManager that adds support for:
    - GeoJSON serialization/deserialization of tactical and structural maps.
    - Saving maps to global (mapas_generales/) or per-profile (profiles/mapas_[username]/) directories.
    - Linking saved map paths dynamically to the current profile's 'mapas_visibles' list.
    - Loading base cartography, general maps, and per-profile maps.
    """
    def __init__(self):
        super().__init__()
        # Determine the project base directory
        self.base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.cartografia_dir = os.path.join(self.base_dir, "cartografia_base")
        self.mapas_generales_dir = os.path.join(self.base_dir, "mapas_generales")
        self.profiles_dir = os.path.join(self.base_dir, "profiles")
        
        # Ensure target directories exist
        os.makedirs(self.mapas_generales_dir, exist_ok=True)
        os.makedirs(self.profiles_dir, exist_ok=True)
        
        print(f"{NEON_CYAN}[MapManager] Inicializado. Directorio Base: {self.base_dir}{RESET}")

    def load_profile_maps(self, profile: dict, profile_manager=None):
        """
        Loads base cartography, general maps under mapas_generales/, and per-profile
        map files under profiles/mapas_[nombre_usuario]/, setting their visibility
        according to the profile's 'mapas_visibles' list.
        """
        self.layers.clear()
        
        # 1. Load base cartography
        print(f"{NEON_CYAN}[MapManager] Cargando cartografía base...{RESET}")
        self.cargar_cartografia_base()
        for layer in self.layers.values():
            layer.filepath = os.path.join(self.cartografia_dir, layer.name)
            
        # 2. Load general maps
        print(f"{NEON_CYAN}[MapManager] Cargando mapas generales...{RESET}")
        if os.path.exists(self.mapas_generales_dir):
            for filename in os.listdir(self.mapas_generales_dir):
                if filename.lower().endswith(".geojson"):
                    filepath = os.path.join(self.mapas_generales_dir, filename)
                    self.load_geojson(filepath, name=filename, tipo="ESTRUCTURAL")
                    if filename in self.layers:
                        self.layers[filename].filepath = filepath

        # 3. Load per-profile maps
        username = profile.get("name", "Default")
        user_map_dir = os.path.join(self.profiles_dir, f"mapas_{username}")
        print(f"{NEON_CYAN}[MapManager] Cargando mapas del perfil '{username}' desde {user_map_dir}...{RESET}")
        if os.path.exists(user_map_dir):
            for filename in os.listdir(user_map_dir):
                if filename.lower().endswith(".geojson"):
                    filepath = os.path.join(user_map_dir, filename)
                    self.load_geojson(filepath, name=filename, tipo="TACTICO")
                    if filename in self.layers:
                        self.layers[filename].filepath = filepath

        # 4. Apply visibility based on 'mapas_visibles' from the profile
        mapas_visibles = profile.get("mapas_visibles", [])
        if mapas_visibles:
            print(f"{NEON_MAGENTA}[MapManager] Aplicando visibilidad de capas: {mapas_visibles}{RESET}")
            # Normalize list of visible maps for comparison
            normalized_visibles = []
            for path in mapas_visibles:
                normalized_visibles.append(os.path.normpath(path).lower())
                normalized_visibles.append(os.path.basename(path).lower())
                
            for name, layer in self.layers.items():
                layer_path = getattr(layer, 'filepath', '')
                layer_path_norm = os.path.normpath(layer_path).lower() if layer_path else ''
                layer_name_lower = name.lower()
                
                # If layer filepath or name is found in the visible list, set visible to True
                is_visible = False
                for nv in normalized_visibles:
                    if nv == layer_name_lower or (layer_path_norm and nv in layer_path_norm) or (layer_path_norm and layer_path_norm.endswith(nv)):
                        is_visible = True
                        break
                layer.visible = is_visible
        else:
            # If no visibility preference exists, default to visible
            for layer in self.layers.values():
                layer.visible = True

    def save_map(self, name: str, segments: list, profile_name: str, is_general: bool = False, profile_manager=None, color: str = "#00E5FF") -> str:
        """
        Serializes segments to GeoJSON, writes them to the appropriate directory,
        updates the layers dictionary, and links the saved path to the profile's 'mapas_visibles' list.
        """
        # Ensure a clean .geojson extension
        base_filename = name if name.lower().endswith(".geojson") else f"{name}.geojson"
        
        if is_general:
            target_dir = self.mapas_generales_dir
            tipo = "ESTRUCTURAL"
        else:
            target_dir = os.path.join(self.profiles_dir, f"mapas_{profile_name}")
            tipo = "TACTICO"
            
        os.makedirs(target_dir, exist_ok=True)
        filepath = os.path.join(target_dir, base_filename)
        
        # Perform serialization
        geojson_data = self.segments_to_geojson(segments)
        geojson_data["color"] = color  # Persistir el color elegido por el usuario
        
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(geojson_data, f, indent=4, ensure_ascii=False)
            print(f"{NEON_GREEN}[MapManager] Mapa guardado exitosamente en: {filepath}{RESET}")
        except Exception as e:
            print(f"[MapManager] Error guardando mapa en {filepath}: {e}")
            raise e

        # Add/update the layer in memory
        self.add_layer(base_filename, segments, tipo)
        if base_filename in self.layers:
            self.layers[base_filename].filepath = filepath
            self.layers[base_filename].visible = True
            self.layers[base_filename].color = color
            
        # Dynamic linking to the profile's 'mapas_visibles'
        # Get path relative to the base directory for portability
        rel_path = os.path.relpath(filepath, self.base_dir).replace('\\', '/')
        
        if profile_manager is not None:
            profile = profile_manager.profile
            visibles = profile.get("mapas_visibles", [])
            if rel_path not in visibles:
                visibles.append(rel_path)
                profile_manager.update_profile({"mapas_visibles": visibles})
                print(f"{NEON_GREEN}[MapManager] Vinculado '{rel_path}' a mapas_visibles del perfil.{RESET}")
        else:
            # Fallback to direct config update if profile_manager is not present
            config_path = os.path.join(self.base_dir, "config", "profile.json")
            if os.path.exists(config_path):
                try:
                    with open(config_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    visibles = data.get("mapas_visibles", [])
                    if rel_path not in visibles:
                        visibles.append(rel_path)
                        data["mapas_visibles"] = visibles
                        with open(config_path, 'w', encoding='utf-8') as f:
                            json.dump(data, f, indent=4, ensure_ascii=False)
                        print(f"{NEON_GREEN}[MapManager] Vinculado '{rel_path}' directamente en {config_path}.{RESET}")
                except Exception as e:
                    print(f"[MapManager] Fallback de vinculación falló: {e}")
                    
        return filepath

    def segments_to_geojson(self, segments: list) -> dict:
        """
        Converts the list of raw segment tuples/lists to standard GeoJSON FeatureCollection.
        Supports LineString and Point (with text or symbol types) matching VideoMapLayer conventions.
        """
        features = []
        current_linestring = []
        current_layer = "LINEAS_DE_MAPA"
        
        for seg in segments:
            if not seg or len(seg) < 2:
                continue
            
            t = seg[0]
            layer = seg[1]
            
            if t in ('M', 'L') and len(seg) >= 4:
                lat, lon = seg[2], seg[3]
                if not is_valid_coord(lon, lat):
                    continue
                
                if t == 'M':
                    # If we had a line under construction, flush it
                    if len(current_linestring) > 1:
                        features.append({
                            "type": "Feature",
                            "geometry": {
                                "type": "LineString",
                                "coordinates": current_linestring
                            },
                            "properties": {
                                "layer": current_layer
                            }
                        })
                    current_linestring = [[lon, lat]]  # GeoJSON is [longitude, latitude]
                    current_layer = layer
                elif t == 'L':
                    # Only append if we started with moveTo
                    if current_linestring:
                        current_linestring.append([lon, lat])
                    else:
                        current_linestring = [[lon, lat]]
                        current_layer = layer
                        
            elif t == 'C':
                # Close the path
                if len(current_linestring) > 0:
                    current_linestring.append(current_linestring[0])  # Close coordinates loop
                    features.append({
                        "type": "Feature",
                        "geometry": {
                            "type": "LineString",
                            "coordinates": current_linestring
                        },
                        "properties": {
                            "layer": current_layer
                        }
                    })
                    current_linestring = []
                    
            elif t in ('T', 'S') and len(seg) >= 5:
                lat, lon = seg[2], seg[3]
                text = seg[4]
                if not is_valid_coord(lon, lat):
                    continue
                
                ptype = "symbol" if t == 'S' else "text"
                features.append({
                    "type": "Feature",
                    "geometry": {
                        "type": "Point",
                        "coordinates": [lon, lat]
                    },
                    "properties": {
                        "name": text,
                        "type": ptype,
                        "layer": layer
                    }
                })
                
        # Flush any remaining line
        if len(current_linestring) > 1:
            features.append({
                "type": "Feature",
                "geometry": {
                    "type": "LineString",
                    "coordinates": current_linestring
                },
                "properties": {
                    "layer": current_layer
                }
            })
            
        return {
            "type": "FeatureCollection",
            "features": features
        }
