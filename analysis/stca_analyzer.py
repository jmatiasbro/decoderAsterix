import math

class STCA_Engine:
    def __init__(self):
        self.min_horizontal_nm = 10.0
        self.min_vertical_ft = 900
        self.fl_min = 245
        self.fl_max = 450

    @staticmethod
    def haversine_nm(lat1, lon1, lat2, lon2):
        R = 3440.065 # Radio terrestre en NM
        dlat, dlon = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
        a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
        return R * (2 * math.atan2(math.sqrt(a), math.sqrt(1 - a)))

    def evaluar_conflictos(self, tracks_dict):
        """
        Evalúa conflictos de separación de forma cinemática.
        Retorna una lista de tuplas: (track1_id, track2_id, estado, tiempo)
        - estado: 'VIOLATION' (violación actual) o 'PREDICTION' (vulneración futura en t_cpa)
        - tiempo: 0 para VIOLATION, o t_cpa (segundos redondeados) para PREDICTION.
        """
        conflictos = []
        track_ids = list(tracks_dict.keys())
        
        for i in range(len(track_ids)):
            t1_id = track_ids[i]
            t1 = tracks_dict[t1_id]
            
            # Excluir blancos estáticos (ej: transpondedores de calibración, reflectores MTR a 0 nudos)
            speed1 = t1.get('speed_kt')
            if speed1 is not None and speed1 < 40.0:
                continue
                
            fl1_str = str(t1.get('flight_level', ''))
            if not fl1_str.isdigit() or not (self.fl_min <= int(fl1_str) <= self.fl_max): continue

            for j in range(i + 1, len(track_ids)):
                t2_id = track_ids[j]
                t2 = tracks_dict[t2_id]
                
                speed2 = t2.get('speed_kt')
                if speed2 is not None and speed2 < 40.0:
                    continue
                    
                fl2_str = str(t2.get('flight_level', ''))
                if not fl2_str.isdigit() or not (self.fl_min <= int(fl2_str) <= self.fl_max): continue

                # Suprimir conflicto si comparten squawk o Mode S → misma aeronave
                m3a1 = t1.get('mode3a', '')
                m3a2 = t2.get('mode3a', '')
                if m3a1 and m3a2 and m3a1 not in ('----', '0000') and m3a1 == m3a2:
                    continue
                ms1 = t1.get('mode_s', '')
                ms2 = t2.get('mode_s', '')
                if ms1 and ms2 and ms1 == ms2:
                    continue

                diff_vertical_ft = abs(int(fl1_str) - int(fl2_str)) * 100
                if diff_vertical_ft >= self.min_vertical_ft: continue

                lat1, lon1 = t1.get('lat_render'), t1.get('lon_render')
                lat2, lon2 = t2.get('lat_render'), t2.get('lon_render')
                
                if None in (lat1, lon1, lat2, lon2): continue

                # 1. EVALUACIÓN ACTUAL (Fase de Violación)
                dist_actual = self.haversine_nm(lat1, lon1, lat2, lon2)
                if dist_actual < self.min_horizontal_nm:
                    conflictos.append((t1_id, t2_id, 'VIOLATION', 0, dist_actual, diff_vertical_ft))
                    continue

                # 2. EVALUACIÓN PREDICTIVA (Fase de Predicción)
                # Obtener posiciones cartesianas en metros y vectores de velocidad
                x1, y1 = t1.get('x'), t1.get('y')
                x2, y2 = t2.get('x'), t2.get('y')
                vx1, vy1 = t1.get('vx'), t1.get('vy')
                vx2, vy2 = t2.get('vx'), t2.get('vy')

                if None in (x1, y1, x2, y2, vx1, vy1, vx2, vy2):
                    continue

                # Posición y velocidad relativas
                dx = x1 - x2
                dy = y1 - y2
                dvx = vx1 - vx2
                dvy = vy1 - vy2

                # Velocidad relativa al cuadrado
                v_sq = dvx**2 + dvy**2

                if v_sq < 1e-4:
                    continue  # Sin movimiento relativo significativo o paralelos

                # Tiempo hasta el CPA (en segundos)
                t_cpa = -(dx * dvx + dy * dvy) / v_sq

                # Si el CPA ocurrirá en el futuro (dentro de los próximos 120 segundos)
                if 0 < t_cpa <= 120.0:
                    # Proyectar posiciones futuras al t_cpa
                    x1_cpa = x1 + vx1 * t_cpa
                    y1_cpa = y1 + vy1 * t_cpa
                    x2_cpa = x2 + vx2 * t_cpa
                    y2_cpa = y2 + vy2 * t_cpa

                    # Distancia en el CPA
                    dist_cpa_m = math.sqrt((x1_cpa - x2_cpa)**2 + (y1_cpa - y2_cpa)**2)
                    dist_cpa_nm = dist_cpa_m / 1852.0

                    # Si en el CPA la distancia rompe el mínimo horizontal
                    if dist_cpa_nm < self.min_horizontal_nm:
                        conflictos.append((t1_id, t2_id, 'PREDICTION', int(round(t_cpa)), dist_cpa_nm, diff_vertical_ft))

        return conflictos
