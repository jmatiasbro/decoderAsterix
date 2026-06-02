from pyproj import Proj


class RadarProjectionSystem:
    """Sistema de Proyección Cónica Conforme de Lambert (LCC) - Legacy."""
    def __init__(self, center_lat=-31.31, center_lon=-64.21):
        self.center_lat = None
        self.center_lon = None
        self.lcc_proj = None
        self.set_radar_center(center_lat, center_lon)

    def set_radar_center(self, lat: float, lon: float):
        """Establece el centro de la proyección y recrea el objeto de proyección."""
        if lat is None or lon is None:
            return
        self.center_lat = lat
        self.center_lon = lon
        # Proyección Cónica Conforme de Lambert (LCC)
        proj_string = (
            f"+proj=lcc +lat_1={lat} +lat_2={lat} "
            f"+lat_0={lat} +lon_0={lon} "
            f"+datum=WGS84 +units=m +no_defs"
        )
        self.lcc_proj = Proj(proj_string)

    def latlon_to_lcc(self, lat: float, lon: float) -> tuple:
        if self.lcc_proj is None or lat is None or lon is None:
            return None, None
        x, y = self.lcc_proj(lon, lat)
        return x, y

    def lcc_to_latlon(self, x: float, y: float) -> tuple:
        """Convierte coordenadas LCC (metros) de vuelta a WGS-84."""
        if self.lcc_proj is None:
            return None, None
        lon, lat = self.lcc_proj(x, y, inverse=True)
        return lon, lat


class StereographicProjection:
    """
    Proyección Estereográfica centrada en el radar activo.
    
    Utiliza la proyección +proj=stere con centro en la ubicación del radar
    para convertir coordenadas geográficas (lat/lon) a cartesianas (X, Y)
    en metros, garantizando que el mapa DXF y los ploteos coincidan exactamente.
    """
    def __init__(self, center_lat: float = None, center_lon: float = None):
        self.center_lat = center_lat
        self.center_lon = center_lon
        self.proj = None
        if center_lat is not None and center_lon is not None:
            self.set_center(center_lat, center_lon)

    def set_center(self, lat: float, lon: float):
        """Establece el centro de la proyección estereográfica."""
        if lat is None or lon is None:
            return
        self.center_lat = lat
        self.center_lon = lon
        proj_string = (
            f"+proj=stere +lat_0={lat} +lon_0={lon} "
            f"+k=1 +datum=WGS84 +units=m +no_defs"
        )
        self.proj = Proj(proj_string)

    def latlon_to_xy(self, lat: float, lon: float) -> tuple:
        """Convierte lat/lon WGS-84 a coordenadas cartesianas (X, Y) en metros."""
        if self.proj is None or lat is None or lon is None:
            return 0.0, 0.0
        x, y = self.proj(lon, lat)
        return x, y

    def xy_to_latlon(self, x: float, y: float) -> tuple:
        """Convierte coordenadas cartesianas (X, Y) de vuelta a lat/lon WGS-84."""
        if self.proj is None:
            return 0.0, 0.0
        lon, lat = self.proj(x, y, inverse=True)
        return lat, lon