import time
from typing import Dict, Optional, Deque
from collections import deque

class ManagedTrack:
    """Holds the state and plot history for a single track."""
    def __init__(self, first_record: Dict, max_plots: int = 2000):
        self.plots: Deque[Dict] = deque(maxlen=max_plots)
        self.category = first_record.get('category')
        self.sac = first_record.get('sac', 0)
        self.sic = first_record.get('sic', 0)
        self.mode_3a = first_record.get('mode_3a')
        
        # Guardar TODAS las variantes de posición
        self.range_slant = first_record.get('range_slant', first_record.get('raw_range'))
        self.azimuth = first_record.get('azimuth', first_record.get('raw_azimuth'))
        self.latitude = first_record.get('latitude')
        self.longitude = first_record.get('longitude')
        self.x = first_record.get('x', first_record.get('x_lcc_m'))
        self.y = first_record.get('y', first_record.get('y_lcc_m'))

        # State for promotion/demotion
        self.consecutive_hits = 1
        self.is_local_track = False
        self.last_update_time = first_record.get('timestamp', time.time())

        # CAT 62 or 21 (ADS-B) are born as tracks
        if self.category in (62, 21):
            self.is_local_track = True
        
        first_record['is_local_track'] = self.is_local_track
        self.plots.append(first_record)

    def update_from_record(self, data: Dict):
        self.category = data.get('category', self.category)
        
        # Actualización ultra-agresiva preservando el último valor conocido
        self.range_slant = data.get('range_slant', data.get('raw_range', getattr(self, 'range_slant', None)))
        self.azimuth = data.get('azimuth', data.get('raw_azimuth', getattr(self, 'azimuth', None)))
        self.latitude = data.get('latitude') if data.get('latitude') is not None else getattr(self, 'latitude', None)
        self.longitude = data.get('longitude') if data.get('longitude') is not None else getattr(self, 'longitude', None)
        self.x = data.get('x', data.get('x_lcc_m', getattr(self, 'x', None)))
        self.y = data.get('y', data.get('y_lcc_m', getattr(self, 'y', None)))

class TrackManager:
    """
    Gestor de Estado de Traza (Memoria Circular).
    Mantiene los últimos N minutos de historia para evitar desbordamiento de RAM.
    """
    def __init__(self, history_minutes: int = 10, timeout_seconds: int = 60):
        self.tracks: Dict[str, ManagedTrack] = {}
        self.last_update: Dict[str, float] = {}
        self.history_limit_seconds = history_minutes * 60
        self.timeout = timeout_seconds
        self.max_plots_per_track = 2000
        
        # Define the maximum range in meters for filtering (250 NM)
        self.MAX_RANGE_METERS = 250.0 * 1852.0

    def update_track(self, track_id: str, data: Dict) -> None:
        current_time = data.get('timestamp', time.time())

        if track_id not in self.tracks:
            self.tracks[track_id] = ManagedTrack(data, self.max_plots_per_track)
        else:
            track = self.tracks[track_id]
            track.update_from_record(data)
            time_diff = current_time - track.last_update_time
            
            # Handle timestamp wrap around midnight
            if time_diff < -40000:
                time_diff += 86400

            # Only apply promotion/demotion logic to CAT 48 (and CAT 01)
            if track.category in (48, 1):
                # REGLA 2: Degradación por pérdidas
                if time_diff > 10.0:
                    track.consecutive_hits = 1
                    track.is_local_track = False
                else:
                    track.consecutive_hits += 1
                
                # REGLA 1: Promoción a Pista Local
                if track.consecutive_hits >= 3:
                    track.is_local_track = True
            
            # Update track state
            track.last_update_time = current_time
            data['is_local_track'] = track.is_local_track

            # Si es CAT 62 real del archivo, fusionar datos
            if track.category == 62 and track.plots:
                last = track.plots[-1]
                if data.get('callsign') is None:
                    data['callsign'] = last.get('callsign')
                if data.get('mode_3a') is None:
                    data['mode_3a'] = last.get('mode_3a')

            # Add new plot
            track.plots.append(data)

        now = time.time()
        data['wall_clock'] = now # For history trimming
        self.last_update[track_id] = now

        # History trimming
        track_plots = self.tracks[track_id].plots
        while track_plots and (now - track_plots[0].get('wall_clock', now) > self.history_limit_seconds):
            track_plots.popleft()

    def get_record(self, track_id: str, timestamp: float) -> Optional[Dict]:
        """
        Retrieves a specific record from a track by its timestamp.
        Assumes timestamps are unique enough for identification within a track.
        """
        if track_id in self.tracks:
            for record in reversed(self.tracks[track_id].plots):
                if record.get('timestamp') == timestamp:
                    return record
        return None

    def purge_stale_tracks(self) -> int:
        """Rutina de Garbage Collection para blancos inactivos."""
        now = time.time()
        stale_ids = [tid for tid, last_t in self.last_update.items() if (now - last_t) > self.timeout]
        for tid in stale_ids:
            del self.tracks[tid]
            del self.last_update[tid]
        return len(stale_ids)

    def clear_all(self) -> None:
        self.tracks.clear()
        self.last_update.clear()
