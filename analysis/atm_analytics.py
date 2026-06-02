import collections
from typing import List, Dict, Tuple, Any

class ATMAnalyticsEngine:
    """Motor Analítico para cálculo de Probabilidad de Detección (Pd) y degradación de cobertura."""
    
    def __init__(self, rotation_period: float = 4.0):
        self.rotation_period = rotation_period
        self.degradations = []

    def calculate_pd_series(self, records: List[Dict[str, Any]]) -> Tuple[List[int], Dict[int, List[float]], Dict[str, Any]]:
        # Agrupar registros por categoría e ID
        tracks_by_cat = collections.defaultdict(lambda: collections.defaultdict(list))
        stats = {'mode_a_missing': 0, 'mode_c_missing': 0}
        
        for r in records:
            cat = r.get('category', 0)
            tid = r.get('track_number') or r.get('callsign') or r.get('mode_3a')
            if not tid:
                continue
            
            if r.get('mode_3a') is None:
                stats['mode_a_missing'] += 1
            if r.get('flight_level') is None:
                stats['mode_c_missing'] += 1
                
            tracks_by_cat[cat][tid].append(r)
        
        pd_dict = {}
        pd_intervals = list(range(1, 11))
        
        for cat, tracks in tracks_by_cat.items():
            pd_values = []
            for interval in pd_intervals:
                expected_updates = 0
                actual_updates = 0
                for tid, track_records in tracks.items():
                    if len(track_records) < 2:
                        continue
                    track_records.sort(key=lambda x: x.get('timestamp') or 0)
                    start_time = track_records[0].get('timestamp') or 0
                    end_time = track_records[-1].get('timestamp') or 0
                    
                    duration = end_time - start_time
                    expected = duration / self.rotation_period
                    expected_updates += expected
                    actual_updates += len(track_records)
                    
                    if interval == 1:
                        for i in range(1, len(track_records)):
                            t_curr = track_records[i].get('timestamp') or 0
                            t_prev = track_records[i-1].get('timestamp') or 0
                            dt = t_curr - t_prev
                            if dt > self.rotation_period * 2.5: # 2.5 missed scans
                                r_val = track_records[i].get('raw_range') or 0
                                az_val = track_records[i].get('raw_azimuth') or 0
                                self.degradations.append({
                                    'time': t_curr, 'type': 'Gap Detectado', 'id': tid, 
                                    'details': f"R:{r_val:.1f} NM, Az:{az_val:.1f}°"})

                pd = (actual_updates / expected_updates * 100.0) if expected_updates > 0 else 100.0
                pd_values.append(min(100.0, pd))
            pd_dict[cat] = pd_values
        return pd_intervals, pd_dict, stats