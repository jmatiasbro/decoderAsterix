import os
import json
from typing import Dict, List, Tuple
from PyQt6.QtGui import QPainterPath

def is_valid_coord(x, y):
    if x is None or y is None: return False
    if x != x or y != y: return False
    if abs(x) == float('inf') or abs(y) == float('inf'): return False
    return True

class VideoMapLayer:
    def __init__(self, name: str, tipo: str):
        self.name = name
        self.tipo = tipo # 'ESTRUCTURAL' o 'TACTICO'
        self.visible = True
        self.color = "#00E5FF"  # Color por defecto (Cian)
        self.raw_segments = []
        
        # Paths agrupados por layer logic (para retrocompatibilidad de colores)
        self.path_borders = QPainterPath()
        self.path_airways = QPainterPath()
        self.path_runways = QPainterPath()
        self.path_other = QPainterPath()
        
        self.map_labels = []
        self.map_symbols = []
        
        self.min_x = self.min_y = float('inf')
        self.max_x = self.max_y = float('-inf')

    def reproject(self, proy):
        self.path_borders = QPainterPath()
        self.path_airways = QPainterPath()
        self.path_runways = QPainterPath()
        self.path_other = QPainterPath()
        self.map_labels = []
        self.map_symbols = []
        
        self.min_x = self.min_y = float('inf')
        self.max_x = self.max_y = float('-inf')

        if not proy or not proy.activo:
            return

        for seg in self.raw_segments:
            if len(seg) < 2: continue
            t = seg[0]
            layer = seg[1]
            
            if t == 'T' and len(seg) >= 5:
                lat, lon, text = seg[2], seg[3], seg[4]
                try:
                    px, py = proy.latlon_to_xy(lat, lon)
                    if is_valid_coord(px, py):
                        self.min_x = min(self.min_x, px)
                        self.max_x = max(self.max_x, px)
                        self.min_y = min(self.min_y, py)
                        self.max_y = max(self.max_y, py)
                        self.map_labels.append((px, py, text))
                except Exception: pass
                continue
                
            if t == 'S' and len(seg) >= 5:
                lat, lon, text = seg[2], seg[3], seg[4]
                try:
                    px, py = proy.latlon_to_xy(lat, lon)
                    if is_valid_coord(px, py):
                        self.min_x = min(self.min_x, px)
                        self.max_x = max(self.max_x, px)
                        self.min_y = min(self.min_y, py)
                        self.max_y = max(self.max_y, py)
                        self.map_symbols.append((px, py, text))
                except Exception: pass
                continue

            layer_upper = str(layer).upper()
            if "LINEAS_DE_MAPA" in layer_upper or "MAPA" in layer_upper or "LIMITES" in layer_upper or "FRONTERA" in layer_upper:
                path = self.path_borders
            elif "AEROVIAS" in layer_upper or "AIRWAYS" in layer_upper or "RUTAS" in layer_upper:
                path = self.path_airways
            elif "PISTAS" in layer_upper or "RUNWAYS" in layer_upper:
                path = self.path_runways
            else:
                path = self.path_other

            if t == 'C':
                path.closeSubpath()
            elif len(seg) >= 4:
                lat, lon = seg[2], seg[3]
                try:
                    px, py = proy.latlon_to_xy(lat, lon)
                    if is_valid_coord(px, py):
                        self.min_x = min(self.min_x, px)
                        self.max_x = max(self.max_x, px)
                        self.min_y = min(self.min_y, py)
                        self.max_y = max(self.max_y, py)
                        if t == 'M':
                            path.moveTo(px, py)
                        elif t == 'L':
                            path.lineTo(px, py)
                except Exception: pass

class VideoMapManager:
    def __init__(self):
        self.layers: Dict[str, VideoMapLayer] = {}
        
    def cargar_cartografia_base(self):
        """Lee los archivos .geojson en cartografia_base/ como ESTRUCTURAL."""
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        carto_dir = os.path.join(base_dir, "cartografia_base")
        if not os.path.exists(carto_dir):
            return

        for filename in os.listdir(carto_dir):
            if filename.lower().endswith(".geojson"):
                path = os.path.join(carto_dir, filename)
                self.load_geojson(path, name=filename, tipo="ESTRUCTURAL")

    def load_geojson(self, filepath: str, name: str, tipo: str):
        try:
            with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                data = json.load(f)
            
            segments = []
            features = data.get("features", [])
            # Leer color guardado en el FeatureCollection (si existe)
            saved_color = data.get("color", None)

            for feat in features:
                geom = feat.get("geometry", {})
                props = feat.get("properties", {})
                gtype = geom.get("type")
                layer = props.get("layer", "LINEAS_DE_MAPA")
                feat_name = props.get("name", "")
                
                if gtype == "LineString":
                    coords = geom.get("coordinates", [])
                    if coords:
                        lon0, lat0 = coords[0]
                        segments.append(('M', layer, lat0, lon0))
                        for lon, lat in coords[1:]:
                            segments.append(('L', layer, lat, lon))
                            
                elif gtype == "Point":
                    coords = geom.get("coordinates", [])
                    if len(coords) >= 2:
                        lon, lat = coords[0], coords[1]
                        ptype = props.get("type", "text")
                        if ptype == "symbol":
                            segments.append(('S', "SIMBOLOS_WAYPOINTS", lat, lon, feat_name))
                        else:
                            segments.append(('T', "NOMBRES_WAYPOINTS", lat, lon, feat_name))
            
            if segments:
                self.add_layer(name, segments, tipo)
                if saved_color and name in self.layers:
                    self.layers[name].color = saved_color
        except Exception as e:
            print(f"Error cargando cartografía {filepath}: {e}")

    def add_layer(self, name: str, segments: list, tipo: str = "TACTICO"):
        layer = VideoMapLayer(name, tipo)
        layer.raw_segments = segments
        self.layers[name] = layer
        
    def reproject_all(self, proy):
        for layer in self.layers.values():
            layer.reproject(proy)

    def get_visible_layers(self, tipo: str = None) -> List[VideoMapLayer]:
        visibles = []
        for layer in self.layers.values():
            if layer.visible and (tipo is None or layer.tipo == tipo):
                visibles.append(layer)
        return visibles

    def get_bounds(self) -> Tuple[float, float, float, float]:
        min_x = min_y = float('inf')
        max_x = max_y = float('-inf')
        for layer in self.layers.values():
            if layer.visible and layer.min_x != float('inf'):
                min_x = min(min_x, layer.min_x)
                min_y = min(min_y, layer.min_y)
                max_x = max(max_x, layer.max_x)
                max_y = max(max_y, layer.max_y)
                
        if min_x == float('inf'):
            return 0.0, 0.0, 1.0, 1.0
        return min_x, min_y, max_x, max_y
