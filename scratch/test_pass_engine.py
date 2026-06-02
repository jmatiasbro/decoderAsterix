"""
test_pass_engine.py — Script de validación automatizada para PASSAnalyticsEngine.
Simula una trayectoria de referencia (con ADS-B) y un radar con sesgo controlado
para verificar matemáticamente la exactitud de las fórmulas analíticas.
"""

import sys
import os
import math
import unittest

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from analysis.pass_analyzer import PASSAnalyticsEngine
from utils.geo import GeoTools, METERS_PER_NM

class TestPASSAnalyticsEngine(unittest.TestCase):

    def test_bias_and_jitter_calculation(self):
        # 1. Definir sensor radar (Ezeiza simulado)
        sensor_sac = 226
        sensor_sic = 230
        sensor_lat = -34.822222
        sensor_lon = -58.535833
        
        sensores = {
            (sensor_sac, sensor_sic): {
                'lat': sensor_lat,
                'lon': sensor_lon,
                'elev': 67.0,
                'name': "Ezeiza PSR/SSR",
                'category': "CAT048",
                'type': "PSR/SSR"
            }
        }
        
        # 2. Generar trayectoria de referencia ideal (ADS-B)
        # Una aeronave volando en línea recta de oeste a este pasando cerca del radar
        target_key = "ARG1234"
        plots = []
        
        # Parámetros del sesgo y jitter sintéticos a introducir
        TRUE_RANGE_BIAS_M = 120.0      # +120 metros
        TRUE_AZIMUTH_BIAS_DEG = 0.125  # +0.125 grados
        TRUE_RANGE_JITTER_M = 0.0     # 0 metros (Prueba de exactitud geométrica pura)
        TRUE_AZIMUTH_JITTER_DEG = 0.0 # 0 grados
        
        # Generar muestras cada segundo
        for i in range(120):
            t = float(i)
            # Mover la latitud constante, la longitud avanza de -59.5 a -57.5
            lat = -34.500000
            lon = -59.500000 + i * 0.016666
            
            # Agregar ploteo ADS-B de referencia (sin ningún sesgo)
            plots.append({
                'id': f"226_108_{t}_adsb",
                'sac_sic': "226/108", # Un sensor ADS-B dummy
                'category': 21,
                'time': t,
                'lat': lat,
                'lon': lon,
                'mode3a': "0000",
                'mode_s': "E42A8C",
                'callsign': "ARG1234",
                'flight_level': 240,
                'altitude_ft': 24000,
                'is_track': True
            })
            
            # Generar ploteo de radar (cada 4 segundos - período de rotación)
            if i % 4 == 0:
                # 1. Obtener la distancia y el azimut real desde el radar
                dist_m, az = GeoTools.calculate_distance_and_azimuth(sensor_lat, sensor_lon, lat, lon)
                range_nm = GeoTools.meters_to_nm(dist_m)
                
                # 2. Introducir sesgo sintético puro sin ruido
                sim_range_nm = range_nm + GeoTools.meters_to_nm(TRUE_RANGE_BIAS_M)
                sim_az = (az + TRUE_AZIMUTH_BIAS_DEG) % 360
                
                # 3. Derivar la coordenada (lat/lon) sesgada que registraría el radar
                sim_lat, sim_lon = GeoTools.polar_to_wgs84(sensor_lat, sensor_lon, sim_az, sim_range_nm)
                
                plots.append({
                    'id': f"226_230_{t}_radar",
                    'sac_sic': "226/230",
                    'category': 48,
                    'time': t,
                    'lat': sim_lat,
                    'lon': sim_lon,
                    'mode3a': "0000",
                    'mode_s': "E42A8C",
                    'callsign': "ARG1234",
                    'flight_level': 240,
                    'altitude_ft': 24000,
                    'is_track': False,
                    'raw_range': sim_range_nm,
                    'raw_azimuth': sim_az
                })

        # 3. Ejecutar PASSAnalyticsEngine
        engine = PASSAnalyticsEngine(sensores=sensores)
        results = engine.analyze_data(plots, {(226, 230): 15.0}) # RPM = 15
        
        # Verificar resultados
        self.assertIn((226, 230), results)
        res = results[(226, 230)]
        
        calc_range_bias = res['range_bias_m']
        calc_azimuth_bias = res['azimuth_bias_deg']
        calc_range_jitter = res['range_jitter_m']
        calc_azimuth_jitter = res['azimuth_jitter_deg']
        calc_pd_mode_a = res['pd_mode_a']
        calc_pd_mode_c = res['pd_mode_c']
        
        print("\n" + "="*60)
        print("RESULTADOS DE VALIDACIÓN DEL MOTOR ANALÍTICO PASS (JITTER = 0)")
        print("="*60)
        print(f"Muestras Analizadas: {res['samples_count']}")
        print(f"Sesgo Distancia (m): Esperado={TRUE_RANGE_BIAS_M:+.1f} | Calculado={calc_range_bias:+.1f}")
        print(f"Sesgo Acimut (°):    Esperado={TRUE_AZIMUTH_BIAS_DEG:+.3f} | Calculado={calc_azimuth_bias:+.3f}")
        print(f"Jitter Distancia (m): Esperado={TRUE_RANGE_JITTER_M:.1f} | Calculado={calc_range_jitter:.1f}")
        print(f"Jitter Acimut (°):    Esperado={TRUE_AZIMUTH_JITTER_DEG:.3f} | Calculado={calc_azimuth_jitter:.3f}")
        print(f"Pd Modo A (%):       Esperado=100.0 | Calculado={calc_pd_mode_a:.1f}")
        print(f"Pd Modo C (%):       Esperado=100.0 | Calculado={calc_pd_mode_c:.1f}")
        print("="*60)
        
        # Comprobar tolerancias de error extremadamene estrictas en la reconstrucción geométrica
        self.assertAlmostEqual(calc_range_bias, TRUE_RANGE_BIAS_M, delta=0.5)
        self.assertAlmostEqual(calc_azimuth_bias, TRUE_AZIMUTH_BIAS_DEG, delta=0.005)
        self.assertEqual(calc_pd_mode_a, 100.0)
        self.assertEqual(calc_pd_mode_c, 100.0)
        
        # Verificar curvas de Pd por nivel de vuelo (Altitud en miles de pies)
        self.assertIn('pd_vs_fl', res)
        self.assertGreater(len(res['pd_vs_fl']), 0)
        pd_fl_bins = dict(res['pd_vs_fl'])
        self.assertIn(20, pd_fl_bins)
        self.assertEqual(pd_fl_bins[20], 100.0)
        
        # Verificar curvas de Pd por tiempo de día
        self.assertIn('pd_vs_time', res)
        self.assertGreater(len(res['pd_vs_time']), 0)
        
        # Verificar exportación de datos de ploteos individuales
        self.assertIn('plots_data', res)
        self.assertGreater(len(res['plots_data']), 0)
        p0 = res['plots_data'][0]
        self.assertIn('range_nm', p0)
        self.assertIn('azimuth', p0)
        self.assertIn('flight_level', p0)
        self.assertIn('time', p0)
        self.assertIn('mode3a', p0)
        
        # Verificar matrices de cobertura 2D SASS-C (Polar y Vertical)
        self.assertIn('polar_pd_grid', res)
        self.assertGreater(len(res['polar_pd_grid']), 0)
        self.assertIn('vertical_pd_grid', res)
        self.assertGreater(len(res['vertical_pd_grid']), 0)
        
        # Comprobar llaves del polar_pd_grid y vertical_pd_grid
        p_cell = res['polar_pd_grid'][0]
        self.assertIn('r_nm', p_cell)
        self.assertIn('az_deg', p_cell)
        self.assertIn('pd', p_cell)
        
        v_cell = res['vertical_pd_grid'][0]
        self.assertIn('r_nm', v_cell)
        self.assertIn('alt_kft', v_cell)
        self.assertIn('pd', v_cell)

if __name__ == '__main__':
    unittest.main()
