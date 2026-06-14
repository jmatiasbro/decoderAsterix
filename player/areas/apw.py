"""Motor APW (Area Proximity Warning) para evaluar penetraciones inmediatas y predicciones futuras.

Sin dependencias de Qt: testeable en aislamiento.
"""
import math
from dataclasses import dataclass
from datetime import datetime

@dataclass
class AlertaAPW:
    track_id: str
    area_name: str
    kind: str
    tipo: str  # 'VIOLATION' | 'PREDICTED'
    eta_s: float


def predecir_posicion(lat: float, lon: float, vx: float, vy: float, dt: float) -> tuple[float, float]:
    """Proyecta la posición usando velocidades vx y vy (en m/s).

    Mapea vx (este/oeste) y vy (norte/sur) a incrementos de latitud y longitud.
    """
    if vx is None or vy is None:
        return lat, lon
    dlat = (vy * dt) / 111120.0
    lat_rad = math.radians(lat)
    cos_lat = math.cos(lat_rad)
    if abs(cos_lat) < 1e-3:
        dlon = 0.0
    else:
        dlon = (vx * dt) / (111120.0 * cos_lat)
    return lat + dlat, lon + dlon


def _get_val(obj, attr_names):
    for name in attr_names:
        if hasattr(obj, name):
            val = getattr(obj, name)
            if val is not None:
                return val
        elif isinstance(obj, dict):
            val = obj.get(name)
            if val is not None:
                return val
    return None


def evaluar_apw(tracks, areas, ahora: datetime, lead_s: float = 120.0) -> list[AlertaAPW]:
    """Evalúa la proximidad o penetración de pistas en las áreas vigentes.

    - Pistas: tracks vivos con FL confiable.
    - Áreas: vigencia activa.
    - Bounding Box prefilter: se evalúa la caja contenedora de la predicción y del área.
    - Banda vertical: el FL actual de la pista debe intersectar la banda del área.
    - VIOLATION: el punto actual está dentro del área.
    - PREDICTED: el punto actual está fuera, pero la trayectoria a lead_s entra al área.
    """
    alertas = []
    
    # Soporta diccionarios (como self.tracks) o iterables de trazas
    if hasattr(tracks, "values"):
        tracks_list = tracks.values()
    else:
        tracks_list = tracks

    for track in tracks_list:
        # Verificar estado vivo de la traza
        is_alive = True
        if hasattr(track, 'is_alive'):
            if callable(track.is_alive):
                is_alive = track.is_alive()
            else:
                is_alive = bool(track.is_alive)
        elif isinstance(track, dict):
            is_alive = track.get('is_alive', True)
        
        if not is_alive:
            continue

        # Excluir trazas degradadas o reflejos fantasmas
        if getattr(track, 'degradada', False) or getattr(track, 'is_reflection', False):
            continue

        # Identificador de traza
        track_id = _get_val(track, ['id', 'track_id', 'plot_id'])
        if not track_id:
            continue

        # Nivel de vuelo confiable (FL)
        fl = _get_val(track, ['flight_level', 'fl'])
        if fl is None:
            continue
        try:
            fl = float(fl)
        except (ValueError, TypeError):
            continue

        # Coordenadas actuales
        lat = _get_val(track, ['latitude', 'lat', 'lat_render'])
        lon = _get_val(track, ['longitude', 'lon', 'lon_render'])
        if lat is None or lon is None:
            continue
        try:
            lat = float(lat)
            lon = float(lon)
        except (ValueError, TypeError):
            continue

        # Vectores de velocidad vx y vy (en m/s)
        vx = _get_val(track, ['vx'])
        vy = _get_val(track, ['vy'])
        try:
            if vx is not None:
                vx = float(vx)
            if vy is not None:
                vy = float(vy)
        except (ValueError, TypeError):
            vx = vy = None

        for area in areas:
            # Filtrar vigencia activa
            if not area.vigencia.activa(ahora):
                continue

            # 1. Filtro de banda vertical (con margen=0)
            if not area.banda(fl, margen=0):
                continue

            # Tiempo de predicción del área o por defecto
            limit_s = area.prediction_time if (hasattr(area, 'prediction_time') and area.prediction_time is not None) else lead_s

            # 2. Prefiltro rápido de Bounding Box
            bbox = area.bbox()
            if bbox is not None:
                min_alat, min_alon, max_alat, max_alon = bbox
                lat_pred, lon_pred = predecir_posicion(lat, lon, vx, vy, limit_s)
                
                min_tlat = min(lat, lat_pred)
                max_tlat = max(lat, lat_pred)
                min_tlon = min(lon, lon_pred)
                max_tlon = max(lon, lon_pred)
                
                if not (max_tlat >= min_alat and min_tlat <= max_alat and
                        max_tlon >= min_alon and min_tlon <= max_alon):
                    continue

            # 3. Test de violación inmediata
            if area.contiene(lat, lon):
                alertas.append(AlertaAPW(
                    track_id=track_id,
                    area_name=area.name,
                    kind=area.kind,
                    tipo='VIOLATION',
                    eta_s=0.0
                ))
                continue

            # 4. Test de predicción paso a paso
            if vx is not None and vy is not None:
                entered = False
                for t in range(1, int(limit_s) + 1):
                    lat_t, lon_t = predecir_posicion(lat, lon, vx, vy, t)
                    if area.contiene(lat_t, lon_t):
                        alertas.append(AlertaAPW(
                            track_id=track_id,
                            area_name=area.name,
                            kind=area.kind,
                            tipo='PREDICTED',
                            eta_s=float(t)
                        ))
                        entered = True
                        break
                if entered:
                    continue

    return alertas
