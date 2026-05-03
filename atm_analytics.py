import math
import time
from collections import defaultdict
from typing import List, Dict

class ATMAnalyticsEngine:
    def __init__(self, rotation_period=4.0):
        """
        Engine para análisis de performance radar.
        rotation_period: Tiempo en segundos por vuelta (ej. 15 RPM = 4s).
        """
        self.rotation_period = rotation_period
        self.degradations = []
        self.stats = {"mode_a_missing": 0, "mode_c_missing": 0}

    def calculate_pd_series(self, records):
        """
        Calcula la Pd (o tasa de actualización) por cada intervalo de tiempo.
        Si rotation_period es 0, usa un intervalo fijo de 4s para datos no rotacionales (ADS-B).
        Retorna (eje_x_intervalos, resultados_dict).
        """
        if not records:
            return [], {}
        
        # Filtrar registros con timestamp
        valid_records = [r for r in records if r.get('timestamp') is not None]
        if not valid_records:
            return [], {}

        # Reiniciar estadísticas y degradaciones
        self.stats = {"mode_a_missing": 0, "mode_c_missing": 0}
        self.degradations = []

        # Adaptación para ADS-B: si no hay periodo de rotación, usar un bucket de tiempo fijo.
        analysis_interval = self.rotation_period if self.rotation_period > 0 else 4.0

        min_t = min(r['timestamp'] for r in valid_records)
        max_t = max(r['timestamp'] for r in valid_records)
        
        # Identificar vida útil de cada traza para saber cuándo esperar detección
        # cat_hits almacena los índices de rotación donde el blanco fue visto por categoría
        tracks = defaultdict(lambda: {
            'first': float('inf'), 
            'last': float('-inf'), 
            'cat_hits': defaultdict(set)
        })
        
        # Mapa para detectar réplicas en la misma rotación: (rot_idx, squawk) -> [records]
        rotation_squawk_map = defaultdict(list)
        
        for r in valid_records:
            # Identificador único: Mode S Address o Squawk
            tid = r.get('mode_s') or r.get('mode_3a')
            if tid is None: continue
            
            cat = r.get('category')
            t = r['timestamp']
            rel_t = t - min_t
            rot_idx = int(rel_t / analysis_interval)
            
            tracks[tid]['first'] = min(tracks[tid]['first'], t)
            tracks[tid]['last'] = max(tracks[tid]['last'], t)
            tracks[tid]['cat_hits'][cat].add(rot_idx)
            
            # Si tiene datos de Squawk y posición polar, agrupar para detectar lóbulos laterales
            if r.get('mode_3a') and r.get('raw_range') and r.get('raw_azimuth'):
                rotation_squawk_map[(rot_idx, r['mode_3a'])].append(r)
            
            # Contadores de integridad para el reporte
            if r.get('category') == 48:
                if r.get('mode_3a') is None: self.stats["mode_a_missing"] += 1
                if r.get('flight_level') is None: self.stats["mode_c_missing"] += 1

        # Ejecutar detección de Reflexiones por Lóbulo Lateral
        self._detect_side_lobes(rotation_squawk_map)
        self.detect_garbling_events(valid_records)

        total_intervals = int((max_t - min_t) / analysis_interval) + 1
        
        # Identificar qué categorías están realmente presentes (48 o 62)
        # Como nunca coexisten, esto filtra la categoría ausente del análisis
        present_cats = sorted(list({r.get('category') for r in valid_records if r.get('category') in [48, 62]}))
        results = {cat: [] for cat in present_cats}
        
        for i in range(total_intervals):
            rot_start = min_t + (i * analysis_interval)
            rot_end = rot_start + analysis_interval
            
            for cat in present_cats:
                expected_tracks = 0
                actual_hits = 0
                
                for tid, data in tracks.items():
                    # ¿Estaba el blanco activo durante esta rotación?
                    # Se espera detección si el blanco está en vida útil global
                    if data['first'] < rot_end and data['last'] > rot_start:
                        expected_tracks += 1
                        if i in data['cat_hits'][cat]:
                            actual_hits += 1
                
                pd = (actual_hits / expected_tracks) * 100 if expected_tracks > 0 else 0
                results[cat].append(pd)
            
        return list(range(total_intervals)), results, self.stats

    def _detect_side_lobes(self, rotation_squawk_map):
        """
        Compara réplicas de Squawks en diferentes acimuts para detectar 
        reflexiones de lóbulo lateral (Side Lobe Reflections).
        """
        for (rot_idx, squawk), plots in rotation_squawk_map.items():
            if len(plots) > 1:
                # Comparar pares de plots dentro de la misma rotación para el mismo Squawk
                for i in range(len(plots)):
                    for j in range(i + 1, len(plots)):
                        p1, p2 = plots[i], plots[j]
                        
                        # Criterio: Rango casi idéntico (< 0.25 NM) y Acimut diferente (> 3.0 grados)
                        range_diff = abs(p1['raw_range'] - p2['raw_range'])
                        az_diff = abs(p1['raw_azimuth'] - p2['raw_azimuth'])
                        if az_diff > 180: az_diff = 360 - az_diff

                        if range_diff < 0.25 and az_diff > 3.0:
                            self.degradations.append({
                                "type": "Lóbulo Lateral (Reflexión)",
                                "time": p1['timestamp'],
                                "id": f"SQ:{squawk:04o}",
                                "details": f"Az1:{p1['raw_azimuth']:.1f}° Az2:{p2['raw_azimuth']:.1f}° R:{p1['raw_range']:.2f}NM"
                            })

    def detect_garbling_events(self, plots: List[Dict]):
        """
        Identifica eventos de Garbling (superposición de respuestas)
        basado en el flag I048/080 o proximidad extrema.
        """
        # Criterio 1: Flag de Garble explícito
        for p in plots:
            if p.get('is_garbled'):
                self.degradations.append({
                    "type": "Garbling (Flag)",
                    "time": p['timestamp'],
                    "id": f"SQ:{p.get('mode_3a', 'N/A'):04o}",
                    "details": f"Az:{p.get('raw_azimuth', 0):.1f}° R:{p.get('raw_range', 0):.2f}NM"
                })

        # Criterio 2: Proximidad (dos plots diferentes muy juntos)
        for i in range(len(plots)):
            for j in range(i + 1, len(plots)):
                p1, p2 = plots[i], plots[j]
                if p1.get('mode_3a') != p2.get('mode_3a') and p1.get('raw_range') is not None and p2.get('raw_range') is not None:
                    dist_range = abs(p1['raw_range'] - p2['raw_range'])
                    dist_az = abs(p1['raw_azimuth'] - p2['raw_azimuth'])
                    if dist_az > 180: dist_az = 360 - dist_az
                    
                    # Criterio típico: < 1.0 NM y < 1.5°
                    if dist_range < 1.0 and dist_az < 1.5:
                        self.degradations.append({
                            "type": "Garbling (Proximidad)",
                            "time": p1['timestamp'],
                            "id": f"SQ:{p1.get('mode_3a', 'N/A'):04o} vs SQ:{p2.get('mode_3a', 'N/A'):04o}",
                            "details": f"Az:{p1['raw_azimuth']:.1f}° R:{p1['raw_range']:.2f}NM"
                        })

class PlaybackEngine:
    """Motor de simulación para reproducción síncrona de datos ASTERIX."""
    def __init__(self, records, antenna_rpm=15.0):
        # Ordenar registros por timestamp para la línea de tiempo
        self.raw_records = sorted(
            [r for r in records if r.get('timestamp') is not None],
            key=lambda x: x['timestamp']
        )
        self.antenna_rpm = antenna_rpm
        self.playback_speed = 1.0
        self.is_playing = False
        self.current_sim_time = self.raw_records[0]['timestamp'] if self.raw_records else 0
        self.last_update_wall_clock = 0
        self.pointer = 0

    def reset(self):
        self.pointer = 0
        self.current_sim_time = self.raw_records[0]['timestamp'] if self.raw_records else 0
        self.is_playing = False

    def get_state(self) -> Dict:
        """Retorna el estado actual de la simulación para ser guardado."""
        return {
            "current_sim_time": self.current_sim_time,
            "pointer": self.pointer,
            "playback_speed": self.playback_speed,
            "antenna_rpm": self.antenna_rpm
        }

    def set_state(self, state: Dict):
        """Restaura el estado de la simulación desde un diccionario."""
        self.current_sim_time = state.get("current_sim_time", 0)
        self.playback_speed = state.get("playback_speed", 1.0)
        self.antenna_rpm = state.get("antenna_rpm", 15.0)
        # Forzar la búsqueda del puntero correcto basado en el tiempo restaurado
        self.seek(self.current_sim_time)

    def seek(self, timestamp: float):
        """Mueve la simulación a un punto de tiempo específico."""
        self.current_sim_time = timestamp
        
        new_pointer = 0
        for i, record in enumerate(self.raw_records):
            if record['timestamp'] >= self.current_sim_time:
                new_pointer = i
                break
        else: # Si el tiempo es mayor que el último registro
            new_pointer = len(self.raw_records)
            
        self.pointer = new_pointer
        self.last_update_wall_clock = 0

    def step(self):
        """Avanza la simulación y retorna los paquetes que deben 'dispararse'."""
        if not self.is_playing or self.pointer >= len(self.raw_records):
            return []

        now = time.time()
        if self.last_update_wall_clock == 0:
            self.last_update_wall_clock = now
            delta_wall = 0
        else:
            # Calcular cuánto tiempo ha pasado en el mundo real y aplicar multiplicador
            delta_wall = now - self.last_update_wall_clock

        self.last_update_wall_clock = now
        
        self.current_sim_time += delta_wall * self.playback_speed
        
        # Extraer paquetes cuya hora sea menor o igual a la actual de simulación
        to_dispatch = []
        while self.pointer < len(self.raw_records) and self.raw_records[self.pointer]['timestamp'] <= self.current_sim_time:
            to_dispatch.append(self.raw_records[self.pointer])
            self.pointer += 1
            
        return to_dispatch