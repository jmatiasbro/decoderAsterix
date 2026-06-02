"""
geo_utils.py — Geodesia para ASTERIX Radar Decoder
===================================================
Proyección Estereográfica Local (estándar IGN) centrada en un radar.
Carga sensores desde default-site-params/*.json.
Conversión RHO/THETA (coordenadas polares de radar) a:
  - WGS84 (lat, lon) vía fórmula de Vincenty (pyproj.Geod)
  - Cartesianas locales (X, Y en metros) vía proyección estereográfica

Dependencias: pyproj, json, glob
"""

import os
import json
import glob
from typing import Dict, Tuple, Optional, Any

from pyproj import Proj, Geod


# Constantes
METERS_PER_NM = 1852.0          # 1 milla náutica = 1852 m
WGS84_GEOD = Geod(ellps='WGS84')   # Elipsoide para cálculos Vincenty


# ============================================================
# CARGA DE SENSORES (Radar Sites)
# ============================================================

def cargar_sensores(directorio: str = "default-site-params") -> Dict[Tuple[int, int], Dict[str, Any]]:
    """
    Escanea directorio de archivos JSON y extrae parámetros de cada sensor.

    Returns
    -------
    dict : {(sac, sic): {'lat': float, 'lon': float, 'elev': float, 'name': str}}
    """
    registro: Dict[Tuple[int, int], Dict[str, Any]] = {}
    if not os.path.isdir(directorio):
        return registro

    for fp in sorted(glob.glob(os.path.join(directorio, "*.json"))):
        try:
            with open(fp, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except Exception:
            continue

        sac = data.get('sac')
        sic = data.get('sic')
        if sac is None or sic is None:
            continue

        loc = data.get('location', {})
        lat = loc.get('latitude')
        lon = loc.get('longitude')
        if lat is None or lon is None:
            continue

        registro[(int(sac), int(sic))] = {
            'lat': float(lat),
            'lon': float(lon),
            'elev': float(loc.get('elevation', 0)),
            'name': str(data.get('name', f"Radar {sac}/{sic}"))
        }

    return registro


def obtener_sensor_por_id(
    sac: int,
    sic: int,
    sensores: Dict[Tuple[int, int], Dict[str, Any]]
) -> Optional[Dict[str, Any]]:
    """
    Obtiene datos de un sensor específico por SAC/SIC.
    Si no existe, retorna None.
    """
    return sensores.get((sac, sic))


def sensor_mas_cercano(
    lat: float,
    lon: float,
    sensores: Dict[Tuple[int, int], Dict[str, Any]]
) -> Optional[Tuple[Tuple[int, int], Dict[str, Any]]]:
    """
    Encuentra el sensor más cercano a una coordenada dada.
    Útil para auto-seleccionar el radar de referencia cuando no se conoce SAC/SIC.

    Returns
    -------
    (sac, sic), info  o  None si no hay sensores.
    """
    if not sensores:
        return None

    mejor_dist = float('inf')
    mejor_key = None
    mejor_info = None

    for (sac, sic), info in sensores.items():
        # Aproximación esférica rápida (no se necesita Vincenty aquí)
        dlat = info['lat'] - lat
        dlon = info['lon'] - lon
        dist_aprox = (dlat * 111320) ** 2 + (dlon * 111320 * abs(math.cos(math.radians(lat)))) ** 2
        if dist_aprox < mejor_dist:
            mejor_dist = dist_aprox
            mejor_key = (sac, sic)
            mejor_info = info

    return (mejor_key, mejor_info) if mejor_key else None


# ============================================================
# PROYECCIÓN ESTEREOGRÁFICA LOCAL
# ============================================================

import math


class StereographicLocal:
    """
    Proyección Estereográfica Local centrada en un radar (estándar IGN).

    Proyección conforme: +proj=stere +lat_0=<radar_lat> +lon_0=<radar_lon>
    +k=1 +datum=WGS84 +units=m +no_defs

    Conversiones:
        latlon_to_xy(lat, lon) -> (x_m, y_m)
        xy_to_latlon(x_m, y_m) -> (lat, lon)
        rho_theta_to_wgs84(rho_nm, theta_deg) -> (lat, lon)
        rho_theta_to_xy(rho_nm, theta_deg) -> (x_m, y_m)
    """

    def __init__(self, center_lat: float = None, center_lon: float = None):
        self.center_lat = center_lat
        self.center_lon = center_lon
        self._proj = None

        if center_lat is not None and center_lon is not None:
            self._build_proj()

    def _build_proj(self):
        """Construye internamente el objeto Proj de pyproj."""
        if self.center_lat is None or self.center_lon is None:
            raise ValueError("Se requiere center_lat y center_lon para construir la proyección.")
        proj_string = (
            f"+proj=stere +lat_0={self.center_lat} +lon_0={self.center_lon} "
            f"+k=1 +datum=WGS84 +units=m +no_defs"
        )
        self._proj = Proj(proj_string)

    def set_center(self, lat: float, lon: float):
        """Cambia el centro de la proyección (útil al seleccionar otro radar)."""
        self.center_lat = lat
        self.center_lon = lon
        self._build_proj()

    # --------------------------------------------------------
    # Conversiones directas WGS84 ↔ Cartesianas
    # --------------------------------------------------------

    def latlon_to_xy(self, lat: float, lon: float) -> Tuple[float, float]:
        """
        Convierte coordenadas geográficas WGS84 a cartesianas locales (X, Y en metros).
        """
        if self._proj is None or lat is None or lon is None:
            return 0.0, 0.0
        x, y = self._proj(lon, lat)
        return float(x), float(y)

    def xy_to_latlon(self, x: float, y: float) -> Tuple[float, float]:
        """
        Convierte coordenadas cartesianas locales de vuelta a WGS84.
        """
        if self._proj is None:
            return 0.0, 0.0
        lon, lat = self._proj(x, y, inverse=True)
        return float(lat), float(lon)

    # --------------------------------------------------------
    # Conversión Polar (RHO/THETA) → WGS84 vía Vincenty
    # --------------------------------------------------------

    def rho_theta_to_wgs84(
        self,
        rho_nm: float,
        theta_deg: float,
        sensor_lat: float = None,
        sensor_lon: float = None
    ) -> Tuple[Optional[float], Optional[float]]:
        """
        Convierte coordenadas polares de radar (RHO en NM, THETA en grados)
        a WGS84 (lat, lon) usando la fórmula directa de Vincenty (pyproj.Geod.fwd).

        Si no se especifica sensor_lat/sensor_lon, usa el centro actual de la
        proyección como origen del radar.

        Parameters
        ----------
        rho_nm : float
            Distancia en millas náuticas.
        theta_deg : float
            Azimuth en grados (0° = Norte, 90° = Este).
        sensor_lat, sensor_lon : float, optional
            Coordenadas del radar. Si se omiten, se usa center_lat/center_lon.

        Returns
        -------
        (lat, lon) : coordenadas WGS84 del punto, o (None, None) si falla.
        """
        if sensor_lat is None:
            sensor_lat = self.center_lat
        if sensor_lon is None:
            sensor_lon = self.center_lon

        if sensor_lat is None or sensor_lon is None:
            # En lugar de lanzar un error, se loguea y retorna None para robustez.
            # El worker que llama a esta función debe manejar el caso None.
            print("[geo_utils] Advertencia: No se puede convertir polar a WGS-84 sin coordenadas de sensor.")
            return None, None

        dist_m = float(rho_nm) * METERS_PER_NM
        azimuth = float(theta_deg)

        try:
            lon_dest, lat_dest, _ = WGS84_GEOD.fwd(sensor_lon, sensor_lat, azimuth, dist_m)
            return float(lat_dest), float(lon_dest)
        except Exception as e:
            print(f"[geo_utils] Error en cálculo de Vincenty fwd: {e}")
            return None, None

    def rho_theta_to_xy(
        self,
        rho_nm: float,
        theta_deg: float,
        sensor_lat: float = None,
        sensor_lon: float = None
    ) -> Tuple[Optional[float], Optional[float]]:
        """
        Convierte coordenadas polares directamente a cartesianas locales (X, Y en metros),
        evitando la doble conversión.

        Atajo: rho_theta_to_wgs84 → latlon_to_xy.
        """
        lat, lon = self.rho_theta_to_wgs84(rho_nm, theta_deg, sensor_lat, sensor_lon)
        if lat is None or lon is None:
            return None, None
        return self.latlon_to_xy(lat, lon)

    # --------------------------------------------------------
    # Utilidades
    # --------------------------------------------------------

    def distancia_vincenty(self, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """
        Distancia entre dos puntos WGS84 usando la fórmula de Vincenty (pyproj.Geod.inv).

        Returns
        -------
        float : distancia en metros.
        """
        _, _, dist_m = WGS84_GEOD.inv(lon1, lat1, lon2, lat2)
        return dist_m

    def azimuth_vincenty(self, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """
        Azimut inicial (forward azimuth) entre dos puntos WGS84.

        Returns
        -------
        float : azimut en grados (0° = Norte, 90° = Este).
        """
        az_fwd, _, _ = WGS84_GEOD.inv(lon1, lat1, lon2, lat2)
        return float(az_fwd)

    @property
    def activo(self) -> bool:
        """Indica si la proyección está configurada y lista para usar."""
        return self._proj is not None


# ============================================================
# EJEMPLO DE USO
# ============================================================
if __name__ == '__main__':
    # Demo: cargar sensores y probar proyección
    sensores = cargar_sensores("default-site-params")

    if not sensores:
        print("No se encontraron sensores. Verifique la ruta default-site-params/")
        sys.exit(1)

    # Tomar el primer sensor como ejemplo
    (sac, sic), info = list(sensores.items())[0]
    print(f"Sensor seleccionado: {info['name']} ({sac}/{sic})")
    print(f"  Lat: {info['lat']}, Lon: {info['lon']}")

    # Crear proyección centrada en ese radar
    proy = StereographicLocal(info['lat'], info['lon'])
    print(f"  Proyección activa: {proy.activo}")

    # Probar conversión de un punto polar (50 NM, 045°)
    rho, theta = 50.0, 45.0
    lat, lon = proy.rho_theta_to_wgs84(rho, theta)
    print(f"\nPolar ({rho} NM, {theta}°) → WGS84: ({lat:.6f}, {lon:.6f})")

    x, y = proy.latlon_to_xy(lat, lon)
    print(f"  → Cartesianas: ({x:.2f}, {y:.2f}) m")

    # Verificar inversa
    lat2, lon2 = proy.xy_to_latlon(x, y)
    print(f"  → Inversa: ({lat2:.6f}, {lon2:.6f})")
    print(f"  Error: {abs(lat - lat2):.2e}, {abs(lon - lon2):.2e}")