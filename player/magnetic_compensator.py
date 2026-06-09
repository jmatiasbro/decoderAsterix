"""
magnetic_compensator.py — Compensador magnético dinámico (World Magnetic Model).

Calcula la declinación magnética exacta para una coordenada WGS84 usando pygeomag
(WMM2025). Reemplaza el offset estático del perfil por un valor dependiente de la
posición geográfica. Incluye caché por celda para que consultas repetidas (p. ej.
durante el repintado del RBL) no recalculen el modelo.

Degradación segura: si pygeomag no está instalada o falla el cálculo, devuelve el
valor de fallback (la declinación estática del perfil), de modo que el sistema sigue
funcionando.
"""
import datetime

try:
    from pygeomag import GeoMag
    _PYGEOMAG_OK = True
except Exception:  # ImportError u otros problemas de carga
    GeoMag = None
    _PYGEOMAG_OK = False


def _anio_decimal(fecha: datetime.date = None) -> float:
    """Convierte una fecha a año decimal (requerido por el WMM)."""
    fecha = fecha or datetime.date.today()
    inicio = datetime.date(fecha.year, 1, 1).toordinal()
    fin = datetime.date(fecha.year + 1, 1, 1).toordinal()
    return fecha.year + (fecha.toordinal() - inicio) / (fin - inicio)


class MagneticCompensator:
    """Declinación magnética (WMM) por coordenada WGS84, con caché por celda (~1 km)."""

    def __init__(self, fallback_deg: float = 0.0):
        self.fallback_deg = float(fallback_deg)
        self._cache = {}
        self._geomag = GeoMag() if _PYGEOMAG_OK else None
        self.disponible = _PYGEOMAG_OK

    def obtener_declinacion(self, latitud, longitud, altitud_ft: float = 0.0) -> float:
        """Declinación en grados decimales (oeste negativo). Fallback si no hay modelo."""
        if latitud is None or longitud is None or self._geomag is None:
            return self.fallback_deg

        clave = (round(latitud, 2), round(longitud, 2))  # celda ~1 km
        cached = self._cache.get(clave)
        if cached is not None:
            return cached

        try:
            alt_km = (altitud_ft or 0.0) * 0.0003048
            res = self._geomag.calculate(
                glat=float(latitud), glon=float(longitud),
                alt=alt_km, time=_anio_decimal()
            )
            dec = float(res.d)
        except Exception:
            dec = self.fallback_deg

        self._cache[clave] = dec
        return dec
