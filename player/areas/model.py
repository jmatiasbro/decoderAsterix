"""Modelo de áreas (restringidas/prohibidas/peligrosas) y geometría para APW.

Sin dependencias de Qt: testeable en aislamiento. Las coordenadas son lat/lon
decimales. Niveles en FL (centenas de pies); 999 = sin tope (UNL).
"""
from dataclasses import dataclass, field
from datetime import datetime, time
import math

_EARTH_NM = 3440.065       # radio terrestre medio en millas náuticas
UNLIMITED_FL = 999         # centinela de la DB para 'sin tope'

KIND_LABEL = {"R": "Restringida", "P": "Prohibida", "D": "Peligrosa", "C": "Personalizada"}


def haversine_nm(lat1, lon1, lat2, lon2) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * _EARTH_NM * math.asin(min(1.0, math.sqrt(a)))


def point_in_poly(lat, lon, verts) -> bool:
    """Ray casting sobre verts=[(lat,lon)]. < 3 vértices -> False."""
    n = len(verts)
    if n < 3:
        return False
    inside = False
    j = n - 1
    for i in range(n):
        yi, xi = verts[i]
        yj, xj = verts[j]
        if (yi > lat) != (yj > lat):
            xint = (xj - xi) * (lat - yi) / (yj - yi) + xi
            if lon < xint:
                inside = not inside
        j = i
    return inside


@dataclass
class Vigencia:
    """Cuándo está activa un área.

    - DB: permanente=True (las de la base se tratan como permanentes).
    - Usuario temporal: permanente=False + dias/franja, y `habilitada` como
      interruptor manual de activación que el controlador puede apagar.
    """
    permanente: bool = True
    habilitada: bool = True                       # switch manual (temporales)
    dias: set = field(default_factory=set)        # 0=lun .. 6=dom
    desde: time = None
    hasta: time = None

    def activa(self, ahora: datetime) -> bool:
        if not self.habilitada:
            return False
        if self.permanente:
            return True
        if self.dias and ahora.weekday() not in self.dias:
            return False
        if self.desde and self.hasta:
            t = ahora.time()
            if self.desde <= self.hasta:
                if not (self.desde <= t <= self.hasta):
                    return False
            elif not (t >= self.desde or t <= self.hasta):   # cruza medianoche
                return False
        return True


@dataclass
class Area:
    name: str
    kind: str                                     # 'R' | 'P' | 'D' | 'C'
    shape: str                                    # 'poly' | 'circle'
    lower_fl: int = 0
    upper_fl: int = UNLIMITED_FL
    vertices: list = field(default_factory=list)  # [(lat,lon)] para 'poly'
    center: tuple = None                          # (lat,lon) para 'circle'
    radius_nm: float = None
    vigencia: Vigencia = field(default_factory=Vigencia)
    origen: str = "db"                            # 'db' | 'usuario'
    prediction_time: int = 120

    def contiene(self, lat, lon) -> bool:
        if self.shape == "circle" and self.center and self.radius_nm:
            return haversine_nm(lat, lon, self.center[0], self.center[1]) <= self.radius_nm
        return point_in_poly(lat, lon, self.vertices)

    def banda(self, fl, margen=0) -> bool:
        if fl is None:
            return False
        return (self.lower_fl - margen) <= fl <= (self.upper_fl + margen)

    def bbox(self):
        """(min_lat, min_lon, max_lat, max_lon) para prefiltro APW. None si vacía."""
        if self.shape == "circle" and self.center and self.radius_nm:
            clat, clon = self.center
            dlat = self.radius_nm / 60.0
            dlon = self.radius_nm / (60.0 * max(0.01, math.cos(math.radians(clat))))
            return (clat - dlat, clon - dlon, clat + dlat, clon + dlon)
        if not self.vertices:
            return None
        lats = [v[0] for v in self.vertices]
        lons = [v[1] for v in self.vertices]
        return (min(lats), min(lons), max(lats), max(lons))

    def polilinea(self, n=64):
        """Contorno cerrado [(lat,lon)] para render (círculo -> n segmentos)."""
        if self.shape == "circle" and self.center and self.radius_nm:
            clat, clon = self.center
            dlat = self.radius_nm / 60.0
            dlon = self.radius_nm / (60.0 * max(0.01, math.cos(math.radians(clat))))
            return [(clat + dlat * math.cos(2 * math.pi * i / n),
                     clon + dlon * math.sin(2 * math.pi * i / n)) for i in range(n + 1)]
        if not self.vertices:
            return []
        return list(self.vertices) + [self.vertices[0]]
