"""Modelo MSAW: zonas de Altitud Mínima de Sector (MSA) por TMA.

Sin Qt: testeable en aislamiento. Los radiales de sector son MAGNÉTICOS (radial
VOR); el rumbo se calcula verdadero desde lat/lon y se corrige con la declinación
magnética de la zona antes de comparar.

MSA en pies MSL. Parámetros del algoritmo desde msaw_parameters (atm_db).
"""
from dataclasses import dataclass, field
import math

from player.areas.model import haversine_nm, point_in_poly

NM_PER_DEG = 60.0
FT_PER_NM = 6076.12


def enu_nm(lat0, lon0, lat, lon):
    """Desplazamiento local (este, norte) en NM desde (lat0,lon0)."""
    dy = (lat - lat0) * NM_PER_DEG
    dx = (lon - lon0) * NM_PER_DEG * math.cos(math.radians(lat0))
    return dx, dy


def cross_along_nm(lat, lon, lat1, lon1, lat2, lon2):
    """(cross, along) en NM del punto respecto del segmento (1)->(2).

    cross = distancia perpendicular (>=0); along = proyección sobre el eje
    medida desde el extremo (1) (puede ser <0 o > largo del segmento).
    """
    px, py = enu_nm(lat1, lon1, lat, lon)
    sx, sy = enu_nm(lat1, lon1, lat2, lon2)
    seg = math.hypot(sx, sy)
    if seg < 1e-9:
        return math.hypot(px, py), 0.0
    ux, uy = sx / seg, sy / seg
    along = px * ux + py * uy
    cross = abs(px * (-uy) + py * ux)
    return cross, along


def bearing_true(lat0, lon0, lat, lon) -> float:
    """Rumbo verdadero inicial (°, 0=N horario) del centro (lat0,lon0) al punto."""
    p0, p = math.radians(lat0), math.radians(lat)
    dl = math.radians(lon - lon0)
    y = math.sin(dl) * math.cos(p)
    x = math.cos(p0) * math.sin(p) - math.sin(p0) * math.cos(p) * math.cos(dl)
    return math.degrees(math.atan2(y, x)) % 360.0


def in_arc(brg, desde, hasta) -> bool:
    """True si brg cae en el arco HORARIO desde→hasta (maneja cruce de 0°)."""
    span = (hasta - desde) % 360.0
    if span == 0.0:               # arco completo (omnidireccional)
        return True
    return ((brg - desde) % 360.0) <= span


@dataclass
class MsaSector:
    desde: float                  # radial magnético inicial (°)
    hasta: float                  # radial magnético final (°), horario
    msa_ft: int                   # altitud mínima de sector (ft MSL)


@dataclass
class MsaZone:
    icao: str
    center: tuple                 # (lat, lon) del VOR/ARP
    radius_nm: float
    elev_ft: int = 0
    trans_alt_ft: int = 0
    mag_decl_w: float = 0.0       # declinación magnética OESTE en grados (Córdoba 6.0)
    sectors: list = field(default_factory=list)

    def contiene(self, lat, lon) -> bool:
        if not self.center:
            return False
        return haversine_nm(lat, lon, self.center[0], self.center[1]) <= self.radius_nm

    def msa_en(self, lat, lon):
        """MSA (ft MSL) aplicable en el punto, o None si está fuera del radio."""
        if not self.contiene(lat, lon):
            return None
        if len(self.sectors) == 1:                 # omnidireccional
            return self.sectors[0].msa_ft
        brg_true = bearing_true(self.center[0], self.center[1], lat, lon)
        brg_mag = (brg_true + self.mag_decl_w) % 360.0   # mag = true - decl_E = true + decl_W
        for s in self.sectors:
            if in_arc(brg_mag, s.desde, s.hasta):
                return s.msa_ft
        return None


@dataclass
class MsawParams:
    """Parámetros del algoritmo (msaw_parameters)."""
    time_to_prediction: int = 120     # s de look-ahead
    rocd: int = 1500                  # ft/min: razón de descenso considerada
    cfl_thold: int = 5                # FL de tolerancia sobre el nivel autorizado


@dataclass
class MsaPolygon:
    """Zona MSA poligonal (altitud mínima por polígono geográfico)."""
    identifier: str
    msa_ft: int
    coords: list                  # [(lat,lon)...]

    def contiene(self, lat, lon) -> bool:
        return point_in_poly(lat, lon, self.coords)

    def msa_en(self, lat, lon):
        return self.msa_ft if self.contiene(lat, lon) else None


@dataclass
class ApmCorridor:
    """Corredor de aproximación paramétrico (trapezoidal) por pista."""
    airport: str
    runway: str
    near: tuple                   # (lat,lon) umbral
    far: tuple                    # (lat,lon) punto lejano
    half_wide_nm: float
    min_dist: float
    max_dist: float
    lower_slope: float            # grados
    upper_slope: float            # grados
    glide_slope: float
    thr_elev_ft: int

    def _cross_along(self, lat, lon):
        return cross_along_nm(lat, lon, self.near[0], self.near[1],
                              self.far[0], self.far[1])

    def en_corredor(self, lat, lon) -> bool:
        cross, along = self._cross_along(lat, lon)
        return (cross <= self.half_wide_nm
                and self.min_dist <= along <= self.max_dist)

    def en_envelope(self, lat, lon, alt_ft) -> bool:
        _cross, along = self._cross_along(lat, lon)
        if along <= 0:
            return False
        ft = along * FT_PER_NM
        alt_lo = self.thr_elev_ft + ft * math.tan(math.radians(self.lower_slope))
        alt_hi = self.thr_elev_ft + ft * math.tan(math.radians(self.upper_slope))
        return alt_lo <= alt_ft <= alt_hi


@dataclass
class ProfileCorridor:
    """Corredor de aproximación por waypoints (altitud mínima interpolada)."""
    profile: str
    kind: str                     # 'A' | 'D'
    points: list                  # [(lat,lon,min_ft,dlat_nm,az)...] por seq

    def _nearest_segment(self, lat, lon):
        """(idx, cross, along, min_interp, dlat) del tramo más cercano."""
        best = None
        for i in range(len(self.points) - 1):
            la1, lo1, m1, dl1, _ = self.points[i]
            la2, lo2, m2, _dl2, _ = self.points[i + 1]
            cross, along = cross_along_nm(lat, lon, la1, lo1, la2, lo2)
            seg = haversine_nm(la1, lo1, la2, lo2)
            t = max(0.0, min(1.0, along / seg)) if seg > 1e-9 else 0.0
            min_interp = m1 + (m2 - m1) * t
            cand = (i, cross, along, min_interp, dl1)
            if best is None or cross < best[1]:
                best = cand
        return best

    def en_corredor(self, lat, lon) -> bool:
        b = self._nearest_segment(lat, lon)
        if b is None:
            return False
        _i, cross, _along, _m, dlat = b
        return cross <= dlat

    def en_envelope(self, lat, lon, alt_ft, tol_ft=300) -> bool:
        b = self._nearest_segment(lat, lon)
        if b is None:
            return False
        _i, _cross, _along, min_interp, _dlat = b
        # suprime si la aeronave sigue el perfil de mínimos (no muy por debajo)
        return alt_ft >= (min_interp - tol_ft)


@dataclass
class SuppressionSet:
    """Conjunto de corredores que inhiben la alerta MSAW en aproximación."""
    apm: list = field(default_factory=list)        # [ApmCorridor]
    profiles: list = field(default_factory=list)   # [ProfileCorridor]
    params: dict = field(default_factory=dict)

    def suprime(self, lat, lon, alt_ft) -> bool:
        for c in self.apm:
            if c.en_corredor(lat, lon) and c.en_envelope(lat, lon, alt_ft):
                return True
        tol = self.params.get("tol_altitude_ft", 300)
        for p in self.profiles:
            if p.en_corredor(lat, lon) and p.en_envelope(lat, lon, alt_ft, tol):
                return True
        return False
