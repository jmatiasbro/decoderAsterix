"""
pass_analyzer.py — Motor Analítico PASS para Evaluación de Desempeño Radar
===========================================================================
Cálculo de Probabilidad de Detección (Pd), Errores Sistemáticos (Sesgos)
y Precisión (Jitter) basado en el estándar Eurocontrol SASS-C.
"""

import math
import collections
import bisect
from typing import List, Dict, Tuple, Optional, Any, Set
from utils.geo import GeoTools, METERS_PER_NM

class PASSAnalyticsEngine:
    """
    Motor de análisis de prestaciones de radares (PASS).
    Calcula de manera desacoplada todas las métricas de calidad de ploteos y tracks.
    """

    def __init__(self, sensores: Dict[Tuple[int, int], Dict[str, Any]] = None):
        """
        Inicializa el motor analítico.
        
        Args:
            sensores: Registro de sensores {(sac, sic): {'lat': lat, 'lon': lon, 'name': name, ...}}
        """
        self.sensores = sensores or {}
        # RPM predefinidos de sitio o fallbacks estándar
        # Ezeiza (226, 230) gira a 15.8 RPM (~3.8s período)
        # Otros radares PSR/SSR en Argentina suelen girar a 7.9 RPM (~7.6s período)
        self.fallback_period = 4.0 # Período por defecto si no se detecta nada

    def cargar_datos_desde_duckdb(self, db_path: str = "pass_analytics.duckdb", query_filter: str = "") -> List[Dict[str, Any]]:
        """
        [Preparación SASS-C / DuckDB - Fase 3]
        Carga datos directamente desde pass_analytics.duckdb para cálculos masivos en memoria de SASS-C.
        
        TODO: En la siguiente fase de desarrollo, los métodos de cálculo de SASS-C (Bias, Jitter, Pd)
        ejecutarán consultas SQL analíticas contra la persistencia de DuckDB en lugar de requerir
        listas gigantescas de diccionarios en la memoria RAM del proceso Qt.
        
        "Antigravity: Ejecuta la inyección del Pipeline Dual respetando la separación de capas actual. La capa de decodificación (data_engine.py) actuará como el orquestador principal, interceptando los objetos puros de asterix_router y enviando una copia no bloqueante al nuevo duckdb_repo.py. Esto es el cimiento para que pass_analyzer.py pueda procesar gigabytes de datos radar usando SQL analítico en el futuro cercano."
        """
        import duckdb
        plots = []
        try:
            conn = duckdb.connect(db_path)
            sql = "SELECT timestamp, category, sac_sic, track_id, lat, lon, flight_level, raw_azimuth, raw_range FROM asterix_plots"
            if query_filter:
                sql += f" WHERE {query_filter}"
            sql += " ORDER BY timestamp ASC"
            
            rows = conn.execute(sql).fetchall()
            for r in rows:
                fl_val = None if r[6] == '---' else float(r[6])
                plots.append({
                    'time': r[0],
                    'category': r[1],
                    'sac_sic': r[2],
                    'mode_s': r[3],
                    'lat': r[4],
                    'lon': r[5],
                    'flight_level': fl_val,
                    'raw_azimuth': r[7],
                    'raw_range': r[8]
                })
            conn.close()
        except Exception as e:
            print(f"[PASS Engine Warning] Error preparativo al leer DuckDB: {e}")
        return plots

    def analyze_data(self, plots: List[Dict[str, Any]], sensor_rpms: Dict[Tuple[int, int], float] = None) -> Dict[str, Any]:
        """
        Ejecuta el análisis completo del conjunto de ploteos.
        
        Args:
            plots: Lista de diccionarios de ploteos decodificados (provenientes de AsterixPlot.to_dict())
            sensor_rpms: RPMs detectados en tiempo real (de CAT 34) {(sac, sic): rpm}
            
        Returns:
            Dict con los resultados resumidos por sensor y gráficos espaciales.
        """
        # Normalizar claves de tiempo para admitir tanto 'time' como 'timestamp'
        normalized_plots = []
        for p in plots:
            np = p.copy()
            if 'time' not in np and 'timestamp' in np:
                np['time'] = np['timestamp']
            elif 'timestamp' not in np and 'time' in np:
                np['timestamp'] = np['time']
            normalized_plots.append(np)
        plots = normalized_plots

        sensor_rpms = sensor_rpms or {}
        from utils.geo import _calculate_distance_and_azimuth_jit
        
        # Recolectar ploteos ADS-B (Categoría 21) globales con coordenadas válidas para usarlos como verdad de terreno
        adsb_plots = [p for p in plots if p.get('category') == 21 and p.get('lat') != 0.0 and p.get('lon') != 0.0]
        
        def get_fl(pt):
            fl = pt.get('flight_level')
            if fl is not None:
                if isinstance(fl, str):
                    if fl == '---' or fl.strip() == '':
                        return None
                    try:
                        return float(fl)
                    except ValueError:
                        return None
                return float(fl)
            alt = pt.get('altitude_ft')
            if alt is not None:
                try:
                    return float(alt) / 100.0
                except (ValueError, TypeError):
                    return None
            return None
        
        # 1. Agrupar ploteos por SAC/SIC y por aeronave (Target ID)
        # Usamos como clave de aeronave: Mode S (24-bit address), Callsign, o Squawk
        plots_by_sensor = collections.defaultdict(list)
        plots_by_target = collections.defaultdict(list)
        adsb_plots_by_target = collections.defaultdict(list)
        
        for p in plots:
            sac_sic_str = p.get('sac_sic')
            if not sac_sic_str or '/' not in sac_sic_str:
                continue
            
            try:
                sac_parts = sac_sic_str.split('/')
                sac_sic = (int(sac_parts[0]), int(sac_parts[1]))
            except ValueError:
                continue
                
            plots_by_sensor[sac_sic].append(p)
            
            # Construir clave única de aeronave
            target_key = p.get('mode_s') or p.get('callsign') or p.get('mode3a')
            if not target_key:
                continue
            
            plots_by_target[target_key].append(p)
            
            # Si es CAT 21 (ADS-B), guardarlo por separado para usarlo como ground truth
            if p.get('category') == 21:
                adsb_plots_by_target[target_key].append(p)

        # 2. Reconstruir Trayectorias de Referencia (Reference Tracks)
        reference_tracks = {}
        for target_key, target_plots in plots_by_target.items():
            # Si tiene ploteos ADS-B, esos son la referencia ideal (Ground Truth satelital)
            ref_source = adsb_plots_by_target.get(target_key, [])
            if len(ref_source) >= 3:
                # Ordenar cronológicamente
                sorted_ref = sorted(ref_source, key=lambda x: x.get('time') or 0.0)
                reference_tracks[target_key] = {
                    'type': 'ADSB',
                    'points': sorted_ref
                }
            elif len(target_plots) >= 5:
                # Si no tiene ADS-B pero tiene suficientes ploteos radar, 
                # construimos una trayectoria de referencia por interpolación/consenso multi-sensor
                sorted_ref = sorted(target_plots, key=lambda x: x.get('time') or 0.0)
                reference_tracks[target_key] = {
                    'type': 'Consenso',
                    'points': sorted_ref
                }

        # Código Mode A de consenso por aeronave (constante durante el vuelo): la
        # moda de los códigos no vacíos vistos por toda la red. Es la "verdad"
        # para la tasa Correct de Mode A (ICAO Doc 8071 §3.2.16).
        consensus_mode_a = {}
        for target_key, target_plots in plots_by_target.items():
            codes = [p.get('mode3a') for p in target_plots
                     if p.get('mode3a') not in (None, "", "----")]
            if codes:
                consensus_mode_a[target_key] = collections.Counter(codes).most_common(1)[0][0]

        # 3. Analizar cada sensor por separado
        results = {}
        
        for sac_sic, s_plots in plots_by_sensor.items():
            sensor_name = "Desconocido"
            sensor_lat = None
            sensor_lon = None
            sensor_type = "PSR/SSR"
            sensor_cat = "CAT048"
            
            # Buscar info en el registro de default-site-params
            if sac_sic in self.sensores:
                s_info = self.sensores[sac_sic]
                sensor_name = s_info.get('name', sensor_name)
                sensor_lat = s_info.get('lat')
                sensor_lon = s_info.get('lon')
                sensor_type = s_info.get('type', sensor_type)
                sensor_cat = s_info.get('category', sensor_cat)

            # Si no hay coordenadas de este sensor, no podemos estimar sesgos geodésicos
            if sensor_lat is None or sensor_lon is None:
                # Tomar la mediana de los ploteos si es necesario, o omitir
                continue

            # Dividir ploteos de este sensor por aeronave
            sensor_plots_by_target = collections.defaultdict(list)
            for p in s_plots:
                t_key = p.get('mode_s') or p.get('callsign') or p.get('mode3a')
                if t_key:
                    sensor_plots_by_target[t_key].append(p)

            # Estimación automática del período de rotación
            estimated_period = None
            diffs = []
            for t_key, t_s_plots in sensor_plots_by_target.items():
                if len(t_s_plots) >= 2:
                    sorted_t = sorted([pt.get('time') or 0.0 for pt in t_s_plots])
                    for t1, t2 in zip(sorted_t, sorted_t[1:]):
                        dt = t2 - t1
                        if 1.5 < dt < 15.0:
                            diffs.append(dt)
            if diffs:
                rounded_diffs = [round(d, 1) for d in diffs]
                mode_dt = collections.Counter(rounded_diffs).most_common(1)[0][0]
                close_diffs = [d for d in diffs if abs(d - mode_dt) <= 0.3]
                if close_diffs:
                    estimated_period = sum(close_diffs) / len(close_diffs)

            # Período de rotación de antena (RPM)
            rpm = sensor_rpms.get(sac_sic, 0.0)
            if rpm <= 0.0:
                if estimated_period is not None and estimated_period > 0.1:
                    period = estimated_period
                    rpm = 60.0 / period
                else:
                    # Intentar leer desde default-site-params
                    rpm = s_info.get('rpm', 0.0) or 0.0
                    if rpm > 0.0:
                        period = 60.0 / rpm
                    else:
                        # Fallbacks de sitio comunes en Argentina
                        if sensor_cat == "CAT021":
                            period = 1.0 # ADS-B transmite rápido
                        elif sac_sic == (226, 230): # Ezeiza
                            period = 3.8
                            rpm = 15.8
                        else:
                            period = 7.6
                            rpm = 7.9
            else:
                period = 60.0 / rpm

            # Inicializar acumuladores estadísticas
            residuals_range = []    # en metros
            residuals_azimuth = []  # en grados
            spatial_residuals = []  # lista de dicts para plots polares
            
            # Para calcular Pd espacial
            range_bins_expected = collections.defaultdict(int)
            range_bins_actual = collections.defaultdict(int)
            az_bins_expected = collections.defaultdict(int)
            az_bins_actual = collections.defaultdict(int)
            
            # Para calcular Pd por nivel de vuelo
            fl_bins_expected = collections.defaultdict(int)
            fl_bins_actual = collections.defaultdict(int)
            
            # Para calcular Pd por tiempo de día (ToD)
            time_bins_expected = collections.defaultdict(int)
            time_bins_actual = collections.defaultdict(int)
            
            # Para calcular Cobertura Polar y Vertical SASS-C 2D
            polar_bins_expected = collections.defaultdict(int)
            polar_bins_actual = collections.defaultdict(int)
            vertical_bins_expected = collections.defaultdict(int)
            vertical_bins_actual = collections.defaultdict(int)

            # (sensor_plots_by_target ya agrupados al estimar el período de rotación)

            # 4. Cálculo de Sesgos y Jitter (Residuos contra Trayectorias de Referencia)
            total_plots = len(s_plots)
            split_plots_count = 0
            gap_sizes = []  # longitud (en vueltas perdidas) de cada hueco, todos los targets

            for t_key, t_s_plots in sensor_plots_by_target.items():
                ref_track = reference_tracks.get(t_key)
                if not ref_track:
                    continue
                
                ref_points = ref_track['points']
                ref_times = [pt.get('time') or 0.0 for pt in ref_points]
                t_start = ref_times[0]
                t_end = ref_times[-1]
                
                # --- FILTRO DEDUP (Desactivar impacto de BLPs en Jitter, Bias y Pd) ---
                # Ordenar ploteos por tiempo
                sorted_plots = sorted(t_s_plots, key=lambda x: x.get('time') or 0.0)
                deduped_plots = []
                current_group = []
                
                def select_best_plot(plot_list):
                    # 1. Preferir ploteo con Modo C (flight_level o altitude_ft)
                    with_mode_c = [pt for pt in plot_list if pt.get('flight_level') is not None or pt.get('altitude_ft') is not None]
                    candidates = with_mode_c if with_mode_c else plot_list
                    
                    # 2. Preferir ploteo con mayor replies count (srr) si está decodificado
                    with_srr = [pt for pt in candidates if pt.get('srr') is not None]
                    if with_srr:
                        return max(with_srr, key=lambda x: x.get('srr', 0))
                    return candidates[0]
                
                for p in sorted_plots:
                    t_plot = p.get('time') or 0.0
                    if not current_group:
                        current_group.append(p)
                    else:
                        t_last = current_group[-1].get('time') or 0.0
                        # Umbral de rotación: mínimo de 1.5s o el 50% del período
                        threshold = max(1.5, 0.5 * period)
                        if t_plot - t_last < threshold:
                            current_group.append(p)
                        else:
                            best = select_best_plot(current_group)
                            deduped_plots.append(best)
                            if len(current_group) > 1:
                                split_plots_count += len(current_group) - 1
                            current_group = [p]
                if current_group:
                    best = select_best_plot(current_group)
                    deduped_plots.append(best)
                    if len(current_group) > 1:
                        split_plots_count += len(current_group) - 1
                
                # Para evitar duplicados en la misma rotación en los bins de Pd
                plots_by_scan = collections.defaultdict(list)
                
                for p in deduped_plots:
                    t_plot = p.get('time') or 0.0
                    scan_idx = int(t_plot / period)
                    plots_by_scan[scan_idx].append(p)
                    
                    # Evaluar contra trayectoria de referencia si cae dentro de sus límites
                    if t_start <= t_plot <= t_end and len(ref_points) >= 2:
                        # Encontrar puntos de referencia antes y después del ploteo para interpolar con búsqueda binaria O(log M)
                        idx_next = bisect.bisect_right(ref_times, t_plot)
                        
                        if 0 < idx_next < len(ref_times):
                            p_prev = ref_points[idx_next - 1]
                            p_next = ref_points[idx_next]
                            t_prev = ref_times[idx_next - 1]
                            t_next = ref_times[idx_next]
                            
                            # Interpolación lineal simple de latitud y longitud
                            dt = t_next - t_prev
                            if dt > 0.0:
                                frac = (t_plot - t_prev) / dt
                                true_lat = p_prev['lat'] + frac * (p_next['lat'] - p_prev['lat'])
                                true_lon = p_prev['lon'] + frac * (p_next['lon'] - p_prev['lon'])
                            else:
                                true_lat, true_lon = p_prev['lat'], p_prev['lon']
                                frac = 0.0
                                
                            # Obtener nivel de vuelo de referencia interpolado
                            fl_prev = get_fl(p_prev)
                            fl_next = get_fl(p_next)
                            if fl_prev is not None and fl_next is not None:
                                if dt > 0.0:
                                    true_fl = fl_prev + frac * (fl_next - fl_prev)
                                else:
                                    true_fl = fl_prev
                            elif fl_prev is not None:
                                true_fl = fl_prev
                            else:
                                true_fl = fl_next
                                
                            # Convertir posición real a rango/acimut verdadero respecto a este sensor
                            true_dist_m, true_az = GeoTools.calculate_distance_and_azimuth(
                                sensor_lat, sensor_lon, true_lat, true_lon
                            )
                            true_range_nm = GeoTools.meters_to_nm(true_dist_m)
                            
                            # Medición observada (rango/acimut del ploteo)
                            meas_range_nm = p.get('raw_range')
                            meas_az = p.get('raw_azimuth')
                            
                            if meas_range_nm is None or meas_az is None:
                                meas_dist_m, meas_az = GeoTools.calculate_distance_and_azimuth(
                                    sensor_lat, sensor_lon, p['lat'], p['lon']
                                )
                                meas_range_nm = GeoTools.meters_to_nm(meas_dist_m)

                            # Residuos
                            dr_nm = meas_range_nm - true_range_nm
                            dr_m = dr_nm * METERS_PER_NM
                            
                            daz = meas_az - true_az
                            # Normalizar diferencia de acimut en [-180, 180]
                            daz = (daz + 180) % 360 - 180
                            
                            residuals_range.append(dr_m)
                            residuals_azimuth.append(daz)
                            
                            spatial_residuals.append({
                                'range_nm': true_range_nm,
                                'azimuth': true_az,
                                'dr_m': dr_m,
                                'daz_deg': daz
                            })
                            
                            # Cargar bins espaciales para análisis de Pd
                            r_bin = int(true_range_nm / 10) * 10
                            az_bin = int(true_az / 10) * 10
                            range_bins_actual[r_bin] += 1
                            az_bins_actual[az_bin] += 1
                            
                            if true_fl is not None:
                                fl_bin = int(max(0.0, true_fl) / 50) * 5
                                fl_bins_actual[fl_bin] += 1
                                
                            # Cargar bins de tiempo
                            t_bin = int(t_plot / 30) * 30
                            time_bins_actual[t_bin] += 1
                            
                            # Cargar bins polares 2D SASS-C
                            r_bin_2d = int(max(0.0, true_range_nm) / 20) * 20
                            az_bin_2d = int(true_az / 10) * 10
                            if r_bin_2d < 240:
                                polar_bins_actual[(r_bin_2d, az_bin_2d)] += 1
                                
                            # Cargar bins verticales 2D SASS-C
                            if true_fl is not None:
                                alt_kft = max(0.0, true_fl / 10.0)
                                alt_bin_2d = int(alt_kft / 5) * 5
                                if r_bin_2d < 240 and alt_bin_2d < 50:
                                    vertical_bins_actual[(r_bin_2d, alt_bin_2d)] += 1

                # 5. Calcular Pd por aeronave en esta estación
                # Usamos deduped_plots para que las brechas temporales sean reales y no estén enmascaradas por ráfagas de BLPs
                times_in_sensor = sorted([p.get('time') or 0.0 for p in deduped_plots])
                if len(times_in_sensor) >= 2:
                    t_span = times_in_sensor[-1] - times_in_sensor[0]
                    # Control defensivo ante periodos de rotación erróneos o nulos
                    safe_period = period if period > 0.05 else 4.0
                    expected_scans = t_span / safe_period
                    
                    # Acumular expected para Pd espacial con tope de seguridad de 2000 barridos por aeronave
                    scans_to_run = int(expected_scans)
                    if scans_to_run > 2000:
                        scans_to_run = 2000
                    elif scans_to_run < 0:
                        scans_to_run = 0
                        
                    for i in range(scans_to_run):
                        t_est = times_in_sensor[0] + i * safe_period
                        # Interpolar posición de referencia estimada usando búsqueda binaria O(log M)
                        idx_n = bisect.bisect_right(ref_times, t_est)
                        
                        if 0 < idx_n < len(ref_times):
                            p_pr = ref_points[idx_n - 1]
                            p_nx = ref_points[idx_n]
                            t_pr = ref_times[idx_n - 1]
                            t_nx = ref_times[idx_n]
                            dt_r = t_nx - t_pr
                            if dt_r > 0.0:
                                fr = (t_est - t_pr) / dt_r
                                est_lat = p_pr['lat'] + fr * (p_nx['lat'] - p_pr['lat'])
                                est_lon = p_pr['lon'] + fr * (p_nx['lon'] - p_pr['lon'])
                            else:
                                est_lat, est_lon = p_pr['lat'], p_pr['lon']
                                fr = 0.0
                                
                            d_m, az_est = GeoTools.calculate_distance_and_azimuth(sensor_lat, sensor_lon, est_lat, est_lon)
                            r_nm = GeoTools.meters_to_nm(d_m)
                                
                            # Obtener nivel de vuelo de referencia estimado
                            fl_pr = get_fl(p_pr)
                            fl_nx = get_fl(p_nx)
                            if fl_pr is not None and fl_nx is not None:
                                if dt_r > 0.0:
                                    est_fl = fl_pr + fr * (fl_nx - fl_pr)
                                else:
                                    est_fl = fl_pr
                            elif fl_pr is not None:
                                est_fl = fl_pr
                            else:
                                est_fl = fl_nx
                                
                            if est_fl is not None:
                                fl_bin = int(max(0.0, est_fl) / 50) * 5
                                fl_bins_expected[fl_bin] += 1
                                
                            # Cargar bins de tiempo estimados
                            t_bin_est = int(t_est / 30) * 30
                            time_bins_expected[t_bin_est] += 1
                            
                            # Cargar bins polares 2D SASS-C estimados
                            r_bin_est_2d = int(max(0.0, r_nm) / 20) * 20
                            az_bin_est_2d = int(az_est / 10) * 10
                            if r_bin_est_2d < 240:
                                polar_bins_expected[(r_bin_est_2d, az_bin_est_2d)] += 1
                                
                            # Cargar bins verticales 2D SASS-C estimados
                            if est_fl is not None:
                                alt_kft_est = max(0.0, est_fl / 10.0)
                                alt_bin_est_2d = int(alt_kft_est / 5) * 5
                                if r_bin_est_2d < 240 and alt_bin_est_2d < 50:
                                    vertical_bins_expected[(r_bin_est_2d, alt_bin_est_2d)] += 1
                                
                            r_bin = int(r_nm / 10) * 10
                            az_bin = int(az_est / 10) * 10
                            range_bins_expected[r_bin] += 1
                            az_bins_expected[az_bin] += 1

                # 5b. Huecos de detección (ICAO §3.2.14): rachas de vueltas
                # ausentes entre la primera y la última detección de este target.
                present_scans = sorted(plots_by_scan.keys())
                for a, b in zip(present_scans, present_scans[1:]):
                    miss = b - a - 1
                    if miss > 0:
                        gap_sizes.append(miss)

            # 6. Estadísticas Finales del Sensor
            n_samples = len(residuals_range)
            
            # Calcular Sesgos (Averages)
            range_bias = sum(residuals_range) / n_samples if n_samples > 0 else 0.0
            azimuth_bias = sum(residuals_azimuth) / n_samples if n_samples > 0 else 0.0
            
            # Calcular Jitter (Standard Deviations)
            if n_samples > 1:
                range_jitter = math.sqrt(sum((x - range_bias)**2 for x in residuals_range) / (n_samples - 1))
                azimuth_jitter = math.sqrt(sum((x - azimuth_bias)**2 for x in residuals_azimuth) / (n_samples - 1))
            else:
                range_jitter = 0.0
                azimuth_jitter = 0.0

            # Calcular Pd global
            total_expected_updates = sum(range_bins_expected.values())
            total_actual_updates = sum(range_bins_actual.values())
            
            global_pd = (total_actual_updates / total_expected_updates * 100.0) if total_expected_updates > 0 else 100.0
            global_pd = min(100.0, global_pd)

            # Métricas de huecos (ICAO §3.2.14)
            n_gaps = len(gap_sizes)
            total_misses = sum(gap_sizes)
            big_gaps = [g for g in gap_sizes if g > 2]
            gap_mean_size = (total_misses / n_gaps) if n_gaps > 0 else 0.0
            gap_pct_gt2 = (len(big_gaps) / n_gaps * 100.0) if n_gaps > 0 else 0.0
            gap_pct_misses_big = (sum(big_gaps) / total_misses * 100.0) if total_misses > 0 else 0.0
            
            # Si no hay trazas de referencia para calcular Pd geodésico, usamos fallback básico de gaps
            if total_expected_updates == 0 and total_plots > 5:
                # Estimación por gaps temporales simple
                actual = len(s_plots)
                t_sorted = sorted([p.get('time') or 0.0 for p in s_plots])
                duration = t_sorted[-1] - t_sorted[0]
                expected = (duration / period) if period > 0 else 1
                global_pd = min(100.0, (actual / expected) * 100.0) if expected > 0 else 95.0

            # Split plots %
            split_pct = (split_plots_count / total_plots * 100.0) if total_plots > 0 else 0.0
            
            # Ploteos Falsos / No asociados
            # Definidos como aeronaves con traza ultra corta (longitud de ploteo < 2)
            false_plots_count = 0
            for t_key, t_s_plots in sensor_plots_by_target.items():
                if len(t_s_plots) < 2:
                    false_plots_count += len(t_s_plots)
            false_pct = (false_plots_count / total_plots * 100.0) if total_plots > 0 else 0.0

            # Detección de código Mode A/C: tasas Valid y Correct (ICAO §3.2.16).
            #   Valid   = el reporte trae código (validado).
            #   Correct = el código coincide con la verdad: consenso de red para
            #             Mode A, FL de la traza de referencia para Mode C.
            # Denominador: reportes recibidos por el sensor (total_plots).
            MODE_C_TOL_FL = 2.0  # ±200 ft: cuantización Mode C + baro vs geométrico
            mode_a_valid = mode_a_correct = 0
            mode_c_valid = mode_c_correct = 0
            for t_key, t_s_plots in sensor_plots_by_target.items():
                ref_a = consensus_mode_a.get(t_key)
                ref_track = reference_tracks.get(t_key)
                ref_pts = ref_track['points'] if ref_track else None
                ref_times = [pt.get('time') or 0.0 for pt in ref_pts] if ref_pts else None
                for p in t_s_plots:
                    m3a = p.get('mode3a')
                    if m3a not in (None, "", "----"):
                        mode_a_valid += 1
                        if ref_a is not None and m3a == ref_a:
                            mode_a_correct += 1
                    fl = get_fl(p)
                    if fl is not None:
                        mode_c_valid += 1
                        if ref_pts and ref_times:
                            tp = p.get('time') or 0.0
                            idx = bisect.bisect_left(ref_times, tp)
                            if idx == 0:
                                nearest = ref_pts[0]
                            elif idx == len(ref_times):
                                nearest = ref_pts[-1]
                            else:
                                t_prev = ref_times[idx - 1]
                                t_next = ref_times[idx]
                                if abs(t_prev - tp) < abs(t_next - tp):
                                    nearest = ref_pts[idx - 1]
                                else:
                                    nearest = ref_pts[idx]
                            ref_fl = get_fl(nearest)
                            if (ref_fl is not None
                                    and abs((nearest.get('time') or 0.0) - tp) <= period
                                    and abs(fl - ref_fl) <= MODE_C_TOL_FL):
                                mode_c_correct += 1

            pd_mode_a = (mode_a_valid / total_plots * 100.0) if total_plots > 0 else 0.0
            pd_mode_c = (mode_c_valid / total_plots * 100.0) if total_plots > 0 else 0.0
            mode_a_correct_pct = (mode_a_correct / total_plots * 100.0) if total_plots > 0 else 0.0
            mode_c_correct_pct = (mode_c_correct / total_plots * 100.0) if total_plots > 0 else 0.0

            # Generar datos espaciales para curvas Pd vs Distancia y Acimut
            pd_vs_range = []
            for r_bin in sorted(range_bins_expected.keys()):
                exp = range_bins_expected[r_bin]
                act = range_bins_actual[r_bin]
                pd_bin = (act / exp * 100.0) if exp > 0 else 100.0
                pd_vs_range.append((r_bin, min(100.0, pd_bin)))

            pd_vs_azimuth = []
            for az_bin in sorted(az_bins_expected.keys()):
                exp = az_bins_expected[az_bin]
                act = az_bins_actual.get(az_bin, 0)
                pd_bin = (act / exp * 100.0) if exp > 0 else 100.0
                pd_vs_azimuth.append((az_bin, min(100.0, pd_bin)))
                
            pd_vs_fl = []
            for fl_bin in sorted(fl_bins_expected.keys()):
                exp = fl_bins_expected[fl_bin]
                act = fl_bins_actual[fl_bin]
                pd_bin = (act / exp * 100.0) if exp > 0 else 100.0
                pd_vs_fl.append((fl_bin, min(100.0, pd_bin)))
                
            # Generar curva de Pd vs Tiempo de Día
            pd_vs_time = []
            for t_bin in sorted(time_bins_expected.keys()):
                exp = time_bins_expected[t_bin]
                act = time_bins_actual[t_bin]
                pd_bin = (act / exp * 100.0) if exp > 0 else 100.0
                pd_vs_time.append((t_bin, min(100.0, pd_bin)))
                
            # Generar matriz Pd Polar 2D SASS-C
            polar_pd_grid = []
            for (r_bin, az_bin), exp in polar_bins_expected.items():
                act = polar_bins_actual.get((r_bin, az_bin), 0)
                pd_val = (act / exp * 100.0) if exp > 0 else 100.0
                polar_pd_grid.append({
                    'r_nm': r_bin,
                    'az_deg': az_bin,
                    'pd': min(100.0, pd_val)
                })
                
            # Generar matriz Pd Vertical 2D SASS-C
            vertical_pd_grid = []
            for (r_bin, alt_bin), exp in vertical_bins_expected.items():
                act = vertical_bins_actual.get((r_bin, alt_bin), 0)
                pd_val = (act / exp * 100.0) if exp > 0 else 100.0
                vertical_pd_grid.append({
                    'r_nm': r_bin,
                    'alt_kft': alt_bin,
                    'pd': min(100.0, pd_val)
                })
                
            # Generar datos limpios y rápidos de todos los ploteos individuales para los gráficos dinámicos
            plots_data = []
            delays = []  # Transmission Delays
            plots_con_squawk = []  # Para Reflection Rate
            for p_idx, p in enumerate(s_plots):
                m3a_str = p.get('mode3a')
                m3a_num = None
                if m3a_str and m3a_str.isdigit():
                    try:
                        m3a_num = int(m3a_str)
                    except ValueError:
                        pass
                
                r_nm = p.get('raw_range')
                az_deg = p.get('raw_azimuth')
                if r_nm is None or az_deg is None:
                    dist_m, az_est = GeoTools.calculate_distance_and_azimuth(sensor_lat, sensor_lon, p['lat'], p['lon'])
                    if r_nm is None:
                        r_nm = GeoTools.meters_to_nm(dist_m)
                    if az_deg is None:
                        az_deg = az_est
                r_nm = max(0.0, r_nm)
                    
                fl_val = get_fl(p)
                alt_kft = max(0.0, fl_val / 10.0) if fl_val is not None else None
                
                plots_data.append({
                    'range_nm': r_nm,
                    'azimuth': az_deg,
                    'flight_level': alt_kft,
                    'time': p.get('time') or 0.0,
                    'mode3a': m3a_num
                })
                
                # --- Transmission Delay por ploteo ---
                pcap_t = p.get('pcap_time')
                tod_s = p.get('time')
                if pcap_t is not None and tod_s is not None and tod_s > 0:
                    pcap_tod = pcap_t % 86400.0
                    delay = pcap_tod - tod_s
                    if delay < -43200:
                        delay += 86400
                    elif delay > 43200:
                        delay -= 86400
                    if abs(delay) < 30.0:
                        delays.append(delay)
                
                # --- Datos para Reflection Rate ---
                if m3a_str and m3a_str not in ("----", "0000", "7777", "7700", "7600", "7500"):
                    if az_deg is not None and r_nm is not None:
                        plots_con_squawk.append((p_idx, p.get('time') or 0.0, m3a_str, az_deg, r_nm))

            # ======================================================
            # PARÁMETROS AVANZADOS
            # ======================================================
            
            # --- RANGE GAIN (Ganancia de Rango) ---
            range_gain_slope = 0.0
            range_gain_intercept = 0.0
            range_gain_r_squared = 0.0
            
            if len(spatial_residuals) >= 10:
                rg_R_true = [sr['range_nm'] for sr in spatial_residuals]
                rg_deltas = [sr['dr_m'] for sr in spatial_residuals]
                
                rg_n = len(rg_R_true)
                rg_sum_x = sum(rg_R_true)
                rg_sum_y = sum(rg_deltas)
                rg_sum_xy = sum(x * y for x, y in zip(rg_R_true, rg_deltas))
                rg_sum_x2 = sum(x * x for x in rg_R_true)
                
                rg_denom = rg_n * rg_sum_x2 - rg_sum_x ** 2
                if abs(rg_denom) > 1e-12:
                    range_gain_slope = (rg_n * rg_sum_xy - rg_sum_x * rg_sum_y) / rg_denom
                    range_gain_intercept = (rg_sum_y - range_gain_slope * rg_sum_x) / rg_n
                    
                    rg_mean_y = rg_sum_y / rg_n
                    rg_ss_tot = sum((y - rg_mean_y) ** 2 for y in rg_deltas)
                    rg_ss_res = sum((y - (range_gain_slope * x + range_gain_intercept)) ** 2
                                    for x, y in zip(rg_R_true, rg_deltas))
                    range_gain_r_squared = 1.0 - (rg_ss_res / rg_ss_tot) if rg_ss_tot > 0 else 0.0

            # --- TRANSMISSION DELAYS (Demoras de Transmisión) ---
            if delays:
                delay_mean = sum(delays) / len(delays)
                delay_std = math.sqrt(sum((d - delay_mean) ** 2 for d in delays) / max(1, len(delays) - 1)) if len(delays) > 1 else 0.0
                delay_min = min(delays)
                delay_max = max(delays)
                delays_sorted = sorted(delays)
                delay_median = delays_sorted[len(delays_sorted) // 2]
                idx_p95 = min(int(len(delays_sorted) * 0.95), len(delays_sorted) - 1)
                delay_p95 = delays_sorted[idx_p95]
            else:
                delay_mean = delay_std = delay_min = delay_max = delay_median = delay_p95 = 0.0

            # --- CLASIFICACIÓN DE FALSOS BLANCOS SSR (ICAO §3.2.20-23) ---
            # Pares con mismo squawk casi simultáneos: si la separación angular
            # supera ~2x el ancho de haz, es un blanco espurio. Se distingue:
            #   side-lobe  = mismo rango, acimut equivocado (§3.2.20)
            #   reflexión  = camino indirecto más largo => mayor rango (§3.2.21)
            # (split = misma posición, <2x ancho de haz, ya contado por dedup §3.2.22)
            SSR_BEAMWIDTH_DEG = 2.4
            FALSE_AZ_SEP_DEG = 2.0 * SSR_BEAMWIDTH_DEG
            SIDELOBE_RANGE_TOL_NM = 0.5
            FALSE_TIME_WINDOW_S = 2.0
            reflejados_set = set()
            sidelobe_set = set()
            if sensor_cat in ("CAT048", "CAT001"):
                plots_con_squawk.sort(key=lambda x: x[1])
                for i in range(len(plots_con_squawk)):
                    id_i, t_i, sq_i, az_i, r_i = plots_con_squawk[i]
                    for j in range(i + 1, len(plots_con_squawk)):
                        id_j, t_j, sq_j, az_j, r_j = plots_con_squawk[j]
                        if t_j - t_i > FALSE_TIME_WINDOW_S:
                            break
                        if sq_i != sq_j:
                            continue
                        daz_ref = abs(az_i - az_j)
                        if daz_ref > 180:
                            daz_ref = 360 - daz_ref
                        if daz_ref <= FALSE_AZ_SEP_DEG:
                            continue
                        if abs(r_i - r_j) <= SIDELOBE_RANGE_TOL_NM:
                            sidelobe_set.add(id_j)            # mismo rango, acimut espurio
                        elif r_i > r_j:
                            reflejados_set.add(id_i)          # el de mayor rango es el reflejo
                        else:
                            reflejados_set.add(id_j)

            reflejados_set -= sidelobe_set  # evitar doble conteo (prioriza side-lobe)
            reflejados_count = len(reflejados_set)
            sidelobe_count = len(sidelobe_set)
            reflection_rate = (reflejados_count / total_plots * 100.0) if total_plots > 0 else 0.0
            sidelobe_rate = (sidelobe_count / total_plots * 100.0) if total_plots > 0 else 0.0

            # --- COMPARATIVA DE CO-DETECCIÓN RADAR VS ADS-B ---
            pd_vs_adsb = None
            pd_vs_adsb_expected = 0
            pd_vs_adsb_actual = 0
            
            if sensor_cat != "CAT021" and adsb_plots and sensor_lat is not None and sensor_lon is not None:
                limit_m = 200.0 * 1852.0  # Rango operativo de 200 NM
                
                # Agrupar tiempos del radar por Squawk para búsquedas binarias rápidas
                radar_times_by_squawk = collections.defaultdict(list)
                for p in s_plots:
                    sq = p.get('mode3a')
                    if sq and sq not in ("0000", "2000", "7000", "----", "----"):
                        radar_times_by_squawk[sq].append(p.get('time') or 0.0)
                        
                for sq in radar_times_by_squawk:
                    radar_times_by_squawk[sq].sort()
                    
                for p_adsb in adsb_plots:
                    sq = p_adsb.get('mode3a')
                    if not sq or sq in ("0000", "2000", "7000", "----", "----"):
                        continue
                        
                    # Validar si el ploteo ADS-B cae dentro del área de cobertura del radar terrestre (<= 200 NM)
                    dist_to_radar_m, _ = _calculate_distance_and_azimuth_jit(
                        sensor_lat, sensor_lon, p_adsb['lat'], p_adsb['lon']
                    )
                    if dist_to_radar_m > limit_m:
                        continue
                        
                    # Validar si está por encima del horizonte físico de curvatura terrestre
                    fl_val = get_fl(p_adsb)
                    if fl_val is None:
                        continue
                        
                    r_nm = dist_to_radar_m / 1852.0
                    fl_min = 0.00662 * (r_nm ** 2)
                    if fl_val < fl_min:
                        continue
                        
                    pd_vs_adsb_expected += 1
                    
                    # Buscar co-detección en +/- 8 segundos
                    candidate_times = radar_times_by_squawk.get(sq, [])
                    matched = False
                    if candidate_times:
                        t_ref = p_adsb['time']
                        idx = bisect.bisect_left(candidate_times, t_ref - 8.0)
                        if idx < len(candidate_times) and candidate_times[idx] <= t_ref + 8.0:
                            matched = True
                            
                    if matched:
                        pd_vs_adsb_actual += 1
                        
                if pd_vs_adsb_expected > 0:
                    pd_vs_adsb = (pd_vs_adsb_actual / pd_vs_adsb_expected) * 100.0

            results[sac_sic] = {
                'name': sensor_name,
                'category': sensor_cat,
                'type': sensor_type,
                'total_plots': total_plots,
                'pd_vs_adsb': pd_vs_adsb,
                'pd_vs_adsb_expected': pd_vs_adsb_expected,
                'pd_vs_adsb_actual': pd_vs_adsb_actual,
                'rpm': rpm,
                'pd_global': global_pd,
                'pd_mode_a': pd_mode_a,
                'pd_mode_c': pd_mode_c,
                'mode_a_correct_pct': mode_a_correct_pct,
                'mode_c_correct_pct': mode_c_correct_pct,
                'gap_mean_size': gap_mean_size,
                'gap_pct_gt2': gap_pct_gt2,
                'gap_pct_misses_big': gap_pct_misses_big,
                'range_bias_m': range_bias,
                'azimuth_bias_deg': azimuth_bias,
                'range_jitter_m': range_jitter,
                'azimuth_jitter_deg': azimuth_jitter,
                'split_plots_pct': split_pct,
                'false_plots_pct': false_pct,
                'pd_vs_range': pd_vs_range,
                'pd_vs_azimuth': pd_vs_azimuth,
                'pd_vs_fl': pd_vs_fl,
                'pd_vs_time': pd_vs_time,
                'plots_data': plots_data,
                'polar_pd_grid': polar_pd_grid,
                'vertical_pd_grid': vertical_pd_grid,
                'spatial_residuals': spatial_residuals,
                'samples_count': n_samples,
                # --- Parámetros Avanzados ---
                'range_gain_slope': range_gain_slope,
                'range_gain_intercept': range_gain_intercept,
                'range_gain_r2': range_gain_r_squared,
                'delay_mean': delay_mean,
                'delay_std': delay_std,
                'delay_min': delay_min,
                'delay_max': delay_max,
                'delay_median': delay_median,
                'delay_p95': delay_p95,
                'delays_data': delays,
                'reflection_count': reflejados_count,
                'reflection_rate': reflection_rate,
                'sidelobe_rate': sidelobe_rate,
            }

        # Calcular la Probabilidad de Detección Cruzada en Áreas de Solapamiento (Overlap Pd)
        try:
            overlap_pds = self.calculate_overlap_pd(plots)
            pairwise = overlap_pds.pop('pairwise', {})
            for sac_sic, pd_val in overlap_pds.items():
                if sac_sic in results:
                    results[sac_sic]['pd_overlap'] = pd_val
            # Guardar el análisis por pares a nivel global en el diccionario de resultados
            results['overlap_pairwise'] = pairwise
        except Exception as e_ov:
            print(f"[PASS Engine] Error al calcular Overlap Pd: {e_ov}")

        return results

    def calculate_overlap_pd(self, plots: List[Dict[str, Any]], range_limit_nm: float = 200.0) -> Dict[Tuple[int, int], float]:
        """
        Calcula la probabilidad de detección cruzada (Overlap Pd) entre sensores radares
        dentro de su área de cobertura solapada (límite operativo de 200 NM).
        Utiliza los códigos SSR (Squawk) coincidentes en ventanas temporales estrechas
        para determinar la presencia real del blanco sin requerir ground truth absoluto.
        """
        # Normalizar claves de tiempo para admitir tanto 'time' como 'timestamp'
        normalized_plots = []
        for p in plots:
            np = p.copy()
            if 'time' not in np and 'timestamp' in np:
                np['time'] = np['timestamp']
            elif 'timestamp' not in np and 'time' in np:
                np['timestamp'] = np['time']
            normalized_plots.append(np)
        plots = normalized_plots

        from utils.geo import cargar_sensores, GeoTools, _calculate_distance_and_azimuth_jit
        import collections
        import bisect
        
        def get_fl_local(pt):
            fl = pt.get('flight_level')
            if fl is not None:
                if isinstance(fl, str):
                    if fl == '---' or fl.strip() == '':
                        return None
                    try:
                        return float(fl)
                    except ValueError:
                        return None
                return float(fl)
            alt = pt.get('altitude_ft')
            if alt is not None:
                try:
                    return float(alt) / 100.0
                except (ValueError, TypeError):
                    return None
            return None
            
        # 1. Agrupar ploteos por SAC/SIC y filtrar por rango operativo de 200 NM
        plots_by_sensor = collections.defaultdict(list)
        sensor_coords = {}
        
        # Obtener coordenadas de los sensores cargados
        for key, info in self.sensores.items():
            sensor_coords[key] = (info['lat'], info['lon'])
            
        limit_m = range_limit_nm * 1852.0
        
        for p in plots:
            # Excluir ADS-B (Categoría 21) de la comparación de solapamiento de radares
            if p.get('category') == 21:
                continue
                
            sac_sic_str = p.get('sac_sic')
            if not sac_sic_str or '/' not in sac_sic_str:
                continue
            try:
                parts = sac_sic_str.split('/')
                sac_sic = (int(parts[0]), int(parts[1]))
            except ValueError:
                continue
                
            # Validar Squawk
            sq = p.get('mode3a')
            if not sq or sq in ("0000", "2000", "7000", "----", "----"):
                continue
                
            # Validar si el sensor tiene coordenadas para medir distancias
            if sac_sic not in sensor_coords:
                continue
                
            s_lat, s_lon = sensor_coords[sac_sic]
            
            # Pre-filtro rápido por caja contenedora antes del cálculo geodésico
            if abs(p['lat'] - s_lat) > 3.6 or abs(p['lon'] - s_lon) > 6.5:
                continue
                
            # Calcular distancia del plot al origen del radar
            dist_m, _ = _calculate_distance_and_azimuth_jit(s_lat, s_lon, p['lat'], p['lon'])
            if dist_m <= limit_m:
                p_copy = p.copy()
                p_copy['dist_origin_m'] = dist_m
                plots_by_sensor[sac_sic].append(p_copy)
                
        # 2. Calcular probabilidades solapadas cruzadas
        overlap_pd_results = {}
        pairwise_results = {}
        sensores_activos = list(plots_by_sensor.keys())
        
        for s_target in sensores_activos:
            s_target_plots = plots_by_sensor[s_target]
            s_target_lat, s_target_lon = sensor_coords[s_target]
            
            total_expected_matches = 0
            actual_matches = 0
            
            # Agrupar plots del target por Squawk para búsquedas rápidas
            plots_by_squawk = collections.defaultdict(list)
            times_by_squawk = collections.defaultdict(list)
            for p in s_target_plots:
                plots_by_squawk[p['mode3a']].append(p)
                times_by_squawk[p['mode3a']].append(p['time'])
                
            # Comparar contra todos los demás radares que puedan tener solapamiento
            for s_ref in sensores_activos:
                if s_ref == s_target:
                    continue
                    
                s_ref_plots = plots_by_sensor[s_ref]
                s_ref_lat, s_ref_lon = sensor_coords[s_ref]
                
                pairwise_expected = 0
                pairwise_actual = 0
                
                # Bins de rango: 10 bins de 20 NM c/u (hasta 200 NM)
                range_expected = [0] * 10
                range_actual = [0] * 10
                
                # Bins de altitud: 10 bins de 50 FL c/u (hasta FL500)
                alt_expected = [0] * 10
                alt_actual = [0] * 10
                
                # Para cada ploteo del radar de referencia
                for p_ref in s_ref_plots:
                    sq = p_ref['mode3a']
                    t_ref = p_ref['time']
                    
                    # Pre-filtro rápido por caja contenedora antes del cálculo geodésico
                    if abs(p_ref['lat'] - s_target_lat) > 3.6 or abs(p_ref['lon'] - s_target_lon) > 6.5:
                        continue
                        
                    # El plot de referencia debe caer dentro del área de cobertura del radar target (<= 200 NM)
                    dist_to_target_m, _ = _calculate_distance_and_azimuth_jit(
                        s_target_lat, s_target_lon, p_ref['lat'], p_ref['lon']
                    )
                    if dist_to_target_m > limit_m:
                        continue
                        
                    dist_to_target_nm = dist_to_target_m / 1852.0
                    r_bin_idx = int(dist_to_target_nm / 20.0)
                    
                    fl_val = get_fl_local(p_ref)
                    alt_bin_idx = int(fl_val / 50.0) if fl_val is not None else None
                    
                    # Si cae en la zona solapada, esperamos que el radar target también lo detecte
                    pairwise_expected += 1
                    if 0 <= r_bin_idx < 10:
                        range_expected[r_bin_idx] += 1
                    if alt_bin_idx is not None and 0 <= alt_bin_idx < 10:
                        alt_expected[alt_bin_idx] += 1
                    
                    # Buscar si el radar target vio el mismo Squawk en una ventana temporal de +/- 8 segundos en tiempo O(log K)
                    candidate_times = times_by_squawk.get(sq, [])
                    matched = False
                    if candidate_times:
                        idx = bisect.bisect_left(candidate_times, t_ref - 8.0)
                        if idx < len(candidate_times) and candidate_times[idx] <= t_ref + 8.0:
                            matched = True
                            
                    if matched:
                        pairwise_actual += 1
                        if 0 <= r_bin_idx < 10:
                            range_actual[r_bin_idx] += 1
                        if alt_bin_idx is not None and 0 <= alt_bin_idx < 10:
                            alt_actual[alt_bin_idx] += 1
                
                # Guardar detalles del par si tiene suficientes puntos en el espacio solapado
                if pairwise_expected >= 5:
                    pd_pair = (pairwise_actual / pairwise_expected) * 100.0
                    pairwise_results[(s_target, s_ref)] = {
                        'expected': pairwise_expected,
                        'actual': pairwise_actual,
                        'pd': min(100.0, pd_pair),
                        'range_expected': range_expected,
                        'range_actual': range_actual,
                        'alt_expected': alt_expected,
                        'alt_actual': alt_actual
                    }
                    
                total_expected_matches += pairwise_expected
                actual_matches += pairwise_actual
                        
            # Calcular Pd por solapamiento global para el sensor
            if total_expected_matches > 0:
                pd_val = (actual_matches / total_expected_matches) * 100.0
                overlap_pd_results[s_target] = min(100.0, pd_val)
            else:
                overlap_pd_results[s_target] = None
                
        # Guardar par a nivel de retorno
        overlap_pd_results['pairwise'] = pairwise_results
        return overlap_pd_results
