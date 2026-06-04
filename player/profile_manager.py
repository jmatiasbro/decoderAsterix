import os
import json

class ProfileManager:
    """
    Administrador de perfiles de usuario y configuración del sector.
    Implementa CRUD completo de perfiles en el directorio profiles/
    utilizando un esquema de datos estructurado y estricto.
    """
    DEFAULT_STRICT_PROFILE = {
        "nombre_usuario": "Matias_TWR",
        "aeropuerto_trabajo": "SACO",
        "coordenadas_centro": {"lat": -31.31, "lon": -64.21},
        "nivel_incumbencia": 95,
        "frecuencias_sector": ["118.300", "121.750", "119.850"],
        "mapas_visibles": ["ar_apt.geojson"],
        "stca_habilitado": False
    }

    def __init__(self, profile_path=None):
        self.base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.profile_path = profile_path or os.path.join(self.base_dir, "config", "profile.json")
        self.profiles_dir = os.path.join(self.base_dir, "profiles")
        
        # Asegurar directorios de perfiles y configuración
        os.makedirs(os.path.dirname(self.profile_path), exist_ok=True)
        os.makedirs(self.profiles_dir, exist_ok=True)
        
        self.profile = {}
        self.load_profile()

    @staticmethod
    def to_strict_schema(data: dict) -> dict:
        """Convierte un diccionario de perfil de cualquier formato al esquema estricto."""
        nombre_usuario = data.get("nombre_usuario") or data.get("name") or "Default"
        aeropuerto_trabajo = data.get("aeropuerto_trabajo") or data.get("aeropuerto") or "SACO"
        
        coords = data.get("coordenadas_centro")
        if isinstance(coords, dict) and "lat" in coords and "lon" in coords:
            coordenadas_centro = {"lat": float(coords["lat"]), "lon": float(coords["lon"])}
        else:
            lat = data.get("center_lat", -31.31)
            lon = data.get("center_lon", -64.21)
            coordenadas_centro = {"lat": float(lat), "lon": float(lon)}
            
        nivel_incumbencia = data.get("nivel_incumbencia")
        if nivel_incumbencia is None:
            nivel_incumbencia = data.get("techo_incumbencia", 95)
        nivel_incumbencia = int(nivel_incumbencia)
        
        frecuencias = data.get("frecuencias_sector")
        if not isinstance(frecuencias, list) or len(frecuencias) < 3:
            twr = data.get("frecuencia_twr") or (frecuencias[0] if isinstance(frecuencias, list) and len(frecuencias) > 0 else "118.300")
            gnd = data.get("frecuencia_gnd") or (frecuencias[1] if isinstance(frecuencias, list) and len(frecuencias) > 1 else "121.750")
            app = data.get("frecuencia_app") or (frecuencias[2] if isinstance(frecuencias, list) and len(frecuencias) > 2 else "119.850")
            frecuencias_sector = [str(twr), str(gnd), str(app)]
        else:
            frecuencias_sector = [str(f) for f in frecuencias[:3]]
            
        mapas_visibles = data.get("mapas_visibles", [])
        if not isinstance(mapas_visibles, list):
            mapas_visibles = []
            
        stca_habilitado = data.get("stca_habilitado")
        if stca_habilitado is None:
            stca_habilitado = data.get("stca_enabled", True)
        stca_habilitado = bool(stca_habilitado)
        
        return {
            "nombre_usuario": nombre_usuario,
            "aeropuerto_trabajo": aeropuerto_trabajo,
            "coordenadas_centro": coordenadas_centro,
            "nivel_incumbencia": nivel_incumbencia,
            "frecuencias_sector": frecuencias_sector,
            "mapas_visibles": mapas_visibles,
            "stca_habilitado": stca_habilitado
        }

    @staticmethod
    def to_compat_dict(strict_data: dict) -> dict:
        """Añade claves compatibles en inglés/antiguas para el resto de los componentes."""
        res = strict_data.copy()
        
        res["name"] = strict_data.get("nombre_usuario", "Default")
        res["aeropuerto"] = strict_data.get("aeropuerto_trabajo", "SACO")
        
        coords = strict_data.get("coordenadas_centro", {})
        res["center_lat"] = coords.get("lat", -31.31)
        res["center_lon"] = coords.get("lon", -64.21)
        
        freqs = strict_data.get("frecuencias_sector", ["118.300", "121.750", "119.850"])
        res["frecuencia_twr"] = freqs[0] if len(freqs) > 0 else "118.300"
        res["frecuencia_gnd"] = freqs[1] if len(freqs) > 1 else "121.750"
        res["frecuencia_app"] = freqs[2] if len(freqs) > 2 else "119.850"
        
        res["stca_enabled"] = strict_data.get("stca_habilitado", True)
        res["declinacion_magnetica"] = -7.0
        
        return res

    def load_profile(self):
        """Carga el perfil activo desde config/profile.json o genera el perfil por defecto."""
        if os.path.exists(self.profile_path):
            try:
                with open(self.profile_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                strict = self.to_strict_schema(data)
                self.profile = self.to_compat_dict(strict)
            except Exception as e:
                print(f"[ProfileManager] Error cargando perfil activo: {e}. Usando por defecto.")
                self.profile = self.to_compat_dict(self.DEFAULT_STRICT_PROFILE)
                self.save_profile()
        else:
            self.profile = self.to_compat_dict(self.DEFAULT_STRICT_PROFILE)
            self.save_profile()

    def save_profile(self):
        """Persiste el perfil activo actual en config/profile.json en formato estricto."""
        try:
            strict = self.to_strict_schema(self.profile)
            with open(self.profile_path, 'w', encoding='utf-8') as f:
                json.dump(strict, f, indent=4, ensure_ascii=False)
        except Exception as e:
            print(f"[ProfileManager] Error guardando perfil activo: {e}")

    # ================================================================
    # MÉTODOS CRUD (Fase 1)
    # ================================================================

    def guardar_perfil(self, nombre: str, datos_dict: dict):
        """Guarda un perfil en profiles/[nombre].json."""
        if not nombre:
            raise ValueError("El nombre del perfil no puede estar vacío.")
        
        filename = nombre if nombre.lower().endswith(".json") else f"{nombre}.json"
        filepath = os.path.join(self.profiles_dir, filename)
        
        strict = self.to_strict_schema(datos_dict)
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(strict, f, indent=4, ensure_ascii=False)
        print(f"[ProfileManager] Perfil guardado: {filepath}")

    def leer_perfil(self, nombre: str) -> dict:
        """Lee profiles/[nombre].json y lo retorna como compat_dict."""
        filename = nombre if nombre.lower().endswith(".json") else f"{nombre}.json"
        filepath = os.path.join(self.profiles_dir, filename)
        
        if not os.path.exists(filepath):
            raise FileNotFoundError(f"El perfil {nombre} no existe.")
            
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
            
        strict = self.to_strict_schema(data)
        return self.to_compat_dict(strict)

    def eliminar_perfil(self, nombre: str):
        """Elimina físicamente el archivo del perfil de profiles/."""
        filename = nombre if nombre.lower().endswith(".json") else f"{nombre}.json"
        filepath = os.path.join(self.profiles_dir, filename)
        
        if os.path.exists(filepath):
            os.remove(filepath)
            print(f"[ProfileManager] Perfil eliminado: {filepath}")
        else:
            print(f"[ProfileManager] No se pudo eliminar: {filepath} no existe.")

    def listar_perfiles(self) -> list:
        """Retorna una lista con los nombres de todos los perfiles disponibles (sin la extensión .json)."""
        if not os.path.exists(self.profiles_dir):
            return []
        
        names = []
        for filename in os.listdir(self.profiles_dir):
            if filename.lower().endswith(".json"):
                names.append(filename[:-5])
        return sorted(names)

    # ================================================================
    # MÉTODOS COMPATIBILIDAD GETTERS
    # ================================================================

    def get_declinacion_magnetica(self) -> float:
        return -7.0

    def get_nivel_incumbencia(self) -> int:
        return int(self.profile.get("nivel_incumbencia", 95))

    def get_center_lat(self) -> float:
        return float(self.profile.get("center_lat", -31.31))

    def get_center_lon(self) -> float:
        return float(self.profile.get("center_lon", -64.21))

    def get_aeropuerto(self) -> str:
        return str(self.profile.get("aeropuerto", "SACO"))

    def update_profile(self, new_data: dict):
        """Actualiza el perfil activo con los nuevos datos y lo guarda."""
        self.profile.update(new_data)
        self.save_profile()
