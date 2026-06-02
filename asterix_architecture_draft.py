from typing import Dict, Any, Callable, List, Tuple, Optional
import json

# ==============================================================================
# FASE 1: REGISTRO UAP (Data-Driven) OPTIMIZADO
# ==============================================================================

# Funciones de decodificación atómicas compartidas
def decode_I021_010_sac_sic(data: bytes, offset: int) -> Tuple[Dict[str, Any], int]:
    # Ejemplo de decodificación de SAC/SIC (2 bytes)
    return {"sac": data[offset], "sic": data[offset+1]}, offset + 2

def decode_I021_130_modern(data: bytes, offset: int) -> Tuple[Dict[str, Any], int]:
    # Ejemplo de posición en WGS-84 (6 bytes)
    return {"lat": 0.0, "lon": 0.0}, offset + 6

def decode_I021_130_legacy(data: bytes, offset: int) -> Tuple[Dict[str, Any], int]:
    # Posición en formato antiguo (Legacy)
    return {"lat_legacy": 0.0, "lon_legacy": 0.0}, offset + 6

def decode_I021_071_time(data: bytes, offset: int) -> Tuple[Dict[str, Any], int]:
    # 3 bytes para timestamp
    return {"time": 0.0}, offset + 3

# Diccionarios UAP para CAT 021 (Independientes por rupturas críticas)
UAP_CAT021_V026 = {
    1: {"id": "I021/010", "len": 2, "func": decode_I021_010_sac_sic},
    2: {"id": "I021/071", "len": 3, "func": decode_I021_071_time},
    3: {"id": "I021/130", "len": 6, "func": decode_I021_130_legacy},
    # ... otros campos legacy
}

UAP_CAT021_V21 = {
    1: {"id": "I021/010", "len": 2, "func": decode_I021_010_sac_sic},
    2: {"id": "I021/071", "len": 3, "func": decode_I021_071_time},
    3: {"id": "I021/130", "len": 6, "func": decode_I021_130_modern}, # Diferente Data Item / Formato a la v0.26
    # ... otros campos transición
}

UAP_CAT021_V24 = {
    1: {"id": "I021/010", "len": 2, "func": decode_I021_010_sac_sic},
    2: {"id": "I021/071", "len": 3, "func": decode_I021_071_time},
    3: {"id": "I021/130", "len": 6, "func": decode_I021_130_modern}, # Comparte función decodificadora con v2.1
    # ... otros campos modernos
}

# CAT 062: Herencia de Diccionarios
UAP_CAT062_V117 = {
    1: {"id": "I062/010", "len": 2, "func": decode_I021_010_sac_sic},
    2: {"id": "I062/070", "len": 3, "func": None}, # Ejemplo
    # ... 
}

# v1.21 hereda de v1.17 y añade nuevos campos
UAP_CAT062_V121 = UAP_CAT062_V117.copy()
UAP_CAT062_V121.update({
    22: {"id": "I062/390", "len": -1, "func": None}, # Campo de extensión nuevo, -1 denota longitud variable/Repetitive
})

# CAT 048 y CAT 034 (Herencia similar)
UAP_CAT048_V115 = { 1: {"id": "I048/010", "len": 2, "func": decode_I021_010_sac_sic} }
UAP_CAT048_V131 = UAP_CAT048_V115.copy()
# UAP_CAT048_V131.update({...})

UAP_CAT034_V115 = { 1: {"id": "I034/010", "len": 2, "func": decode_I021_010_sac_sic} }
UAP_CAT034_V131 = UAP_CAT034_V115.copy()

# CAT 001 y 002
UAP_CAT001_V10 = { 1: {"id": "I001/010", "len": 2, "func": decode_I021_010_sac_sic} }
UAP_CAT002_V10 = { 1: {"id": "I002/010", "len": 2, "func": decode_I021_010_sac_sic} }

# Registro maestro de UAPs por versión
UAP_REGISTRY = {
    21: {"2.4": UAP_CAT021_V24, "2.1": UAP_CAT021_V21, "0.26": UAP_CAT021_V026},
    62: {"1.21": UAP_CAT062_V121, "1.17": UAP_CAT062_V117},
    48: {"1.31": UAP_CAT048_V131, "1.15": UAP_CAT048_V115},
    34: {"1.31": UAP_CAT034_V131, "1.15": UAP_CAT034_V115},
    1:  {"1.0": UAP_CAT001_V10},
    2:  {"1.0": UAP_CAT002_V10}
}


# ==============================================================================
# FASE 2: GESTOR DE VERSIONES HEURÍSTICO
# ==============================================================================
class AsterixVersionManager:
    def __init__(self, config_path: str = "default-site-params.json"):
        self.config_path = config_path
        self.sensor_versions_cache: Dict[Tuple[int, int, int], str] = {} # (cat, sac, sic) -> version
        self._load_config()

    def _load_config(self):
        # En la realidad se cargaría el JSON.
        # Simulación del mapeo estático de SAC/SIC:
        self.site_params = {
            # Formato: "sac_sic": { cat: "version" }
            "1_1": {21: "2.4", 62: "1.21"}
        }

    def _get_fspec_active_items(self, data: bytes, offset: int) -> Tuple[List[int], int]:
        """Decodifica el FSPEC y retorna los índices FRN activos y el nuevo offset."""
        frns = []
        frn_index = 1
        current_offset = offset
        while current_offset < len(data):
            byte = data[current_offset]
            for bit in range(7, -1, -1):
                if bit == 0:
                    continue # FX bit
                if (byte & (1 << bit)):
                    frns.append(frn_index)
                frn_index += 1
            current_offset += 1
            if not (byte & 1): # FX bit es 0, fin del FSPEC
                break
        return frns, current_offset

    def _calculate_record_size(self, uap: Dict[int, Any], frns: List[int], data: bytes, offset: int) -> int:
        """
        Simula el salto por los Data Items para calcular el tamaño total del registro.
        (Requiere lógicas para campos de longitud variable/repetitiva)
        """
        current_offset = offset
        for frn in frns:
            item_def = uap.get(frn)
            if not item_def:
                return -1 # Falla si el FRN no existe en este UAP (incompatible)
            
            length = item_def["len"]
            if length > 0:
                current_offset += length
            elif length == -1: 
                # Lógica heurística para campos variables y repetitivos.
                # Como simulación, fallamos aquí explícitamente para el ejemplo
                pass
        return current_offset

    def get_version(self, cat: int, sac: int, sic: int, record_data: bytes, record_length: int) -> str:
        cache_key = (cat, sac, sic)
        
        # 1. Búsqueda en Caché
        if cache_key in self.sensor_versions_cache:
            return self.sensor_versions_cache[cache_key]

        # 2. Detección por Origen (Lookup en Configuración)
        site_key = f"{sac}_{sic}"
        if site_key in self.site_params and cat in self.site_params[site_key]:
            version = self.site_params[site_key][cat]
            self.sensor_versions_cache[cache_key] = version
            return version

        # 3. Heurística de Tamaño (Fallback)
        if cat in UAP_REGISTRY:
            versions = UAP_REGISTRY[cat]
            # Iterar desde la más reciente a la más antigua
            for version_name, uap in versions.items():
                frns, fspec_end_offset = self._get_fspec_active_items(record_data, 0)
                
                calculated_size = self._calculate_record_size(uap, frns, record_data, fspec_end_offset)
                
                if calculated_size == record_length:
                    self.sensor_versions_cache[cache_key] = version_name
                    return version_name
        
        return "UNKNOWN"


# ==============================================================================
# FASE 3: PATRÓN FACTORY DE DECODIFICACIÓN
# ==============================================================================
class AsterixDecoderFactory:
    def __init__(self):
        self.version_manager = AsterixVersionManager()

    def decode_record(self, data: bytes) -> Dict[str, Any]:
        """
        Punto de entrada principal. Se asume que 'data' es un paquete con el CAT y Longitud.
        """
        if len(data) < 3:
            return {}

        cat = data[0]
        length = (data[1] << 8) | data[2]
        
        # Extraer FSPEC inicial temporalmente para buscar SAC/SIC
        # En el diseño final real de ASTERIX, I021/010 (SAC/SIC) se extraería en este paso
        # Aquí lo simulamos con (0, 0) para el fallback
        sac, sic = 0, 0 
        
        # Gestor determina la versión correcta
        version = self.version_manager.get_version(cat, sac, sic, data[3:length], length - 3)
        
        if version == "UNKNOWN" or cat not in UAP_REGISTRY or version not in UAP_REGISTRY[cat]:
            raise ValueError(f"No se pudo determinar el UAP para CAT {cat} SAC {sac} SIC {sic}")

        uap = UAP_REGISTRY[cat][version]
        
        decoded_result = {
            "category": cat,
            "version": version,
            "sac": sac,
            "sic": sic
        }

        # Extracción final de campos iterando sobre el FSPEC validado
        frns, offset = self.version_manager._get_fspec_active_items(data, 3)
        
        for frn in frns:
            item_def = uap.get(frn)
            if item_def and item_def["func"]:
                try:
                    parsed_data, new_offset = item_def["func"](data, offset)
                    decoded_result.update(parsed_data)
                    offset = new_offset
                except Exception as e:
                    # Manejo de error y avance forzado (simulado)
                    offset += item_def["len"]
            elif item_def:
                 offset += item_def["len"]
                 
        return decoded_result

if __name__ == "__main__":
    print("Arquitectura de Motor ASTERIX (Data-Driven / Heurístico) generada exitosamente.")