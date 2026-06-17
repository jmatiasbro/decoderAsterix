"""Motor MSAW: evalúa violación inmediata y predicción de descenso por debajo
de la Altitud Mínima de Sector (MSA) dentro de las TMA.

Sin dependencias de Qt: testeable en aislamiento. Reusa los helpers de lectura
de tracks de apw.py (tolerante a objetos o dicts).
"""
from dataclasses import dataclass

from player.areas.apw import predecir_posicion, _get_val
from player.msaw.model import MsawParams


@dataclass
class AlertaMSAW:
    track_id: str
    icao: str
    tipo: str          # 'VIOLATION' | 'PREDICTED'
    msa_ft: int
    alt_ft: int
    eta_s: float


def _alive(track) -> bool:
    if hasattr(track, 'is_alive'):
        return track.is_alive() if callable(track.is_alive) else bool(track.is_alive)
    if isinstance(track, dict):
        return track.get('is_alive', True)
    return True


def msa_lookup(zones, lat, lon):
    """MSA aplicable en el punto. Polígonos primero, luego círculos.

    `zones` es una lista que puede mezclar MsaPolygon (tienen `.identifier`) y
    MsaZone (tienen `.icao`). Devuelve (msa_ft, ident) o (None, None).
    """
    polys = [z for z in zones if hasattr(z, "identifier")]
    circles = [z for z in zones if not hasattr(z, "identifier")]
    for z in polys:
        msa = z.msa_en(lat, lon)
        if msa is not None:
            return msa, z.identifier
    for z in circles:
        msa = z.msa_en(lat, lon)
        if msa is not None:
            return msa, z.icao
    return None, None


def evaluar_msaw(tracks, zones, params: MsawParams = None, exentos=None,
                 suppression=None):
    """Devuelve [AlertaMSAW].

    - Altitud del track: FL*100 (ft MSL, aprox; pressure≈QNH cerca de TA).
    - En TMA (zona.msa_en): VIOLATION si alt < MSA del sector.
    - PREDICTED: con razón de descenso (vertical_rate, ft/min < 0), si la
      trayectoria a `time_to_prediction` cruza por debajo de la MSA del sector
      donde estará (proyección horizontal con vx/vy).
    - Inhibición: categorías de vuelo en `exentos`.
    """
    params = params or MsawParams()
    exentos = {str(c).strip().upper() for c in (exentos or [])}
    look = int(params.time_to_prediction)
    alertas = []

    tracks_list = tracks.values() if hasattr(tracks, "values") else tracks
    for track in tracks_list:
        if not _alive(track):
            continue
        if getattr(track, 'degradada', False) or getattr(track, 'is_reflection', False):
            continue

        track_id = _get_val(track, ['id', 'track_id', 'plot_id'])
        if not track_id:
            continue

        cat = _get_val(track, ['flight_category', 'category'])
        if cat is not None and str(cat).strip().upper() in exentos:
            continue

        fl = _get_val(track, ['flight_level', 'fl'])
        lat = _get_val(track, ['latitude', 'lat', 'lat_render'])
        lon = _get_val(track, ['longitude', 'lon', 'lon_render'])
        if fl is None or lat is None or lon is None:
            continue
        try:
            fl = float(fl); lat = float(lat); lon = float(lon)
        except (ValueError, TypeError):
            continue
        alt_ft = fl * 100.0

        vx = _get_val(track, ['vx'])
        vy = _get_val(track, ['vy'])
        vrate = _get_val(track, ['vertical_rate', 'vrate', 'rocd', 'roc'])
        try:
            vx = float(vx) if vx is not None else None
            vy = float(vy) if vy is not None else None
            vrate = float(vrate) if vrate is not None else None
        except (ValueError, TypeError):
            vx = vy = vrate = None

        msa, ident = msa_lookup(zones, lat, lon)
        if msa is None:                            # fuera de toda zona
            continue

        # Supresión en aproximación (corredor + envelope vertical)
        if suppression is not None and suppression.suprime(lat, lon, alt_ft):
            continue

        # 1. Violación inmediata
        if alt_ft < msa:
            alertas.append(AlertaMSAW(track_id, ident, 'VIOLATION',
                                      int(msa), int(alt_ft), 0.0))
            continue

        # 2. Predicción de descenso (sólo si desciende)
        if vrate is not None and vrate < 0:
            for t in range(1, look + 1):
                alt_t = alt_ft + vrate * (t / 60.0)
                if vx is not None and vy is not None:
                    lat_t, lon_t = predecir_posicion(lat, lon, vx, vy, t)
                else:
                    lat_t, lon_t = lat, lon
                if suppression is not None and suppression.suprime(lat_t, lon_t, alt_t):
                    continue
                msa_t, ident_t = msa_lookup(zones, lat_t, lon_t)
                if msa_t is None:
                    msa_t, ident_t = msa, ident
                if alt_t < msa_t:
                    alertas.append(AlertaMSAW(track_id, ident_t, 'PREDICTED',
                                              int(msa_t), int(alt_ft), float(t)))
                    break

    return alertas
