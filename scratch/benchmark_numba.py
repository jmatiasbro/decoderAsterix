import time
import math
import numpy as np
try:
    from numba import njit
    HAS_NUMBA = True
except ImportError:
    HAS_NUMBA = False
    # Mock njit decorator if numba is not installed
    def njit(*args, **kwargs):
        def decorator(func):
            return func
        return decorator

# =====================================================================
# 1. FORMULAS MATEMÁTICAS (DISTANCIA GEODÉSICA HAVERSINE)
# =====================================================================

def haversine_python(lat1, lon1, lat2, lon2):
    """Cálculo Haversine en Python puro."""
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    
    a = (math.sin(dphi / 2)**2 + 
         math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2)**2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return 6371000.0 * c  # Retorna metros

if HAS_NUMBA:
    @njit(fastmath=True)
    def haversine_numba(lat1, lon1, lat2, lon2):
        """Cálculo Haversine optimizado en Numba (JIT compilado a código C)."""
        phi1 = math.radians(lat1)
        phi2 = math.radians(lat2)
        dphi = math.radians(lat2 - lat1)
        dlambda = math.radians(lon2 - lon1)
        
        a = (math.sin(dphi / 2)**2 + 
             math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2)**2)
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        return 6371000.0 * c
else:
    haversine_numba = haversine_python

# =====================================================================
# 2. ALGORITMOS DE BÚSQUEDA Y FILTRADO POR COBERTURA (200 NM = 370400 m)
# =====================================================================

# A. Python Tradicional: Bucle sobre lista de diccionarios
def filter_python_dicts(plots, center_lat, center_lon, limit_m):
    count = 0
    for p in plots:
        dist = haversine_python(center_lat, center_lon, p['lat'], p['lon'])
        if dist <= limit_m:
            count += 1
    return count

# B. NumPy Vectorizado: Operaciones sobre arreglos matriciales en bloque
def filter_numpy_vectorized(lats, lons, center_lat, center_lon, limit_m):
    phi1 = np.radians(center_lat)
    phi2 = np.radians(lats)
    dphi = np.radians(lats - center_lat)
    dlambda = np.radians(lons - center_lon)
    
    a = np.sin(dphi / 2.0)**2 + np.cos(phi1) * np.cos(phi2) * np.sin(dlambda / 2.0)**2
    c = 2.0 * np.arctan2(np.sqrt(a), np.sqrt(1.0 - a))
    distances = 6371000.0 * c
    
    # Filtra y cuenta de forma vectorial (en C interno de NumPy)
    return np.sum(distances <= limit_m)

# C. Numba JIT: Bucle sobre arreglos 1D paralelos (con compilación LLVM)
if HAS_NUMBA:
    @njit(fastmath=True)
    def filter_numba_arrays(lats, lons, center_lat, center_lon, limit_m):
        count = 0
        n = len(lats)
        for i in range(n):
            dist = haversine_numba(center_lat, center_lon, lats[i], lons[i])
            if dist <= limit_m:
                count += 1
        return count
else:
    filter_numba_arrays = lambda lats, lons, clat, clon, lim: 0

# D. Numba JIT: Bucle sobre Structured Array (Representación de Structs en memoria contigua)
# Definimos el tipo del estructurado compatible con NumPy y Numba
plot_dtype = np.dtype([
    ('lat', np.float64),
    ('lon', np.float64),
    ('time', np.float64),
    ('mode3a', np.int32),
    ('sac', np.int16),
    ('sic', np.int16)
])

if HAS_NUMBA:
    @njit(fastmath=True)
    def filter_numba_structured(plots_struct, center_lat, center_lon, limit_m):
        count = 0
        n = len(plots_struct)
        for i in range(n):
            # Acceso contiguo en memoria a los campos de la estructura
            p = plots_struct[i]
            dist = haversine_numba(center_lat, center_lon, p['lat'], p['lon'])
            if dist <= limit_m:
                count += 1
        return count
else:
    filter_numba_structured = lambda plots_s, clat, clon, lim: 0

# =====================================================================
# 3. CONFIGURACIÓN DEL BENCHMARK
# =====================================================================

def run_benchmark():
    NUM_PLOTS = 200000  # 200,000 ploteos de radar simulados
    print("=" * 70)
    print(f"  BENCHMARK: OPTIMIZACIÓN DE MOTOR DE ANÁLISIS CON NUMBA JIT")
    print(f"  Simulando {NUM_PLOTS:,} ploteos de radar (Lat, Lon, Time, Squawk, SAC/SIC)")
    print("=" * 70)
    
    # Centro geográfico del radar (Córdoba, Argentina aprox)
    center_lat = -31.4
    center_lon = -64.2
    limit_m = 200.0 * 1852.0  # Cobertura de 200 Millas Náuticas a metros
    
    # Generar datos aleatorios de prueba
    np.random.seed(42)
    lats = np.random.uniform(-35.0, -28.0, NUM_PLOTS)
    lons = np.random.uniform(-68.0, -60.0, NUM_PLOTS)
    times = np.random.uniform(0.0, 86400.0, NUM_PLOTS)
    squawks = np.random.randint(1000, 7777, NUM_PLOTS)
    sacs = np.random.randint(1, 10, NUM_PLOTS)
    sics = np.random.randint(1, 10, NUM_PLOTS)
    
    # -------------------------------------------------------------
    # Estructura 1: Lista de Diccionarios Python (Formato actual)
    # -------------------------------------------------------------
    print("[...] Preparando Lista de Diccionarios en Python...")
    plots_python = []
    for i in range(NUM_PLOTS):
        plots_python.append({
            'lat': lats[i],
            'lon': lons[i],
            'time': times[i],
            'mode3a': squawks[i],
            'sac_sic': (sacs[i], sics[i])
        })
        
    # -------------------------------------------------------------
    # Estructura 2: Structured Array NumPy (Representación Numba Struct)
    # -------------------------------------------------------------
    print("[...] Preparando Structured Array (NumPy Structured C-like)...")
    plots_struct = np.empty(NUM_PLOTS, dtype=plot_dtype)
    plots_struct['lat'] = lats
    plots_struct['lon'] = lons
    plots_struct['time'] = times
    plots_struct['mode3a'] = squawks
    plots_struct['sac'] = sacs
    plots_struct['sic'] = sics

    print("\n--- INICIANDO PRUEBAS DE RENDIMIENTO ---")
    
    # -------------------------------------------------------------
    # Prueba A: Python Puro (Diccionarios)
    # -------------------------------------------------------------
    print("[...] Ejecutando Python Puro (Bucle + Diccionarios)...")
    t0 = time.perf_counter()
    res_py = filter_python_dicts(plots_python, center_lat, center_lon, limit_m)
    t_py = time.perf_counter() - t0
    print(f"  -> Resultado: {res_py:,} ploteos en zona. Tiempo: {t_py:.5f} seg.")
    
    # -------------------------------------------------------------
    # Prueba B: NumPy Vectorizado
    # -------------------------------------------------------------
    print("[...] Ejecutando NumPy Vectorizado (Operación en bloque)...")
    t0 = time.perf_counter()
    res_np = filter_numpy_vectorized(lats, lons, center_lat, center_lon, limit_m)
    t_np = time.perf_counter() - t0
    print(f"  -> Resultado: {res_np:,} ploteos en zona. Tiempo: {t_np:.5f} seg.")
    
    # Si Numba no está disponible, informamos y salimos
    if not HAS_NUMBA:
        print("\n[!] Numba no está instalado. No es posible ejecutar los tests JIT.")
        print("Instálalo corriendo: pip install numba")
        return
        
    # -------------------------------------------------------------
    # Compilación Calentamiento (Numba requiere compilar en la primera llamada)
    # -------------------------------------------------------------
    print("[...] Compilando funciones Numba LLVM JIT (Warm-up)...")
    filter_numba_arrays(lats[:10], lons[:10], center_lat, center_lon, limit_m)
    filter_numba_structured(plots_struct[:10], center_lat, center_lon, limit_m)
    
    # -------------------------------------------------------------
    # Prueba C: Numba JIT + Arreglos 1D Paralelos
    # -------------------------------------------------------------
    print("[...] Ejecutando Numba JIT (Bucle + Arreglos 1D)...")
    t0 = time.perf_counter()
    res_nb_arr = filter_numba_arrays(lats, lons, center_lat, center_lon, limit_m)
    t_nb_arr = time.perf_counter() - t0
    print(f"  -> Resultado: {res_nb_arr:,} ploteos en zona. Tiempo: {t_nb_arr:.5f} seg.")
    
    # -------------------------------------------------------------
    # Prueba D: Numba JIT + Structured Array (Estructuras de C)
    # -------------------------------------------------------------
    print("[...] Ejecutando Numba JIT (Bucle + Structured Array)...")
    t0 = time.perf_counter()
    res_nb_str = filter_numba_structured(plots_struct, center_lat, center_lon, limit_m)
    t_nb_str = time.perf_counter() - t0
    print(f"  -> Resultado: {res_nb_str:,} ploteos en zona. Tiempo: {t_nb_str:.5f} seg.")
    
    # =====================================================================
    # RESULTADOS FINALES Y COMPARATIVA
    # =====================================================================
    print("\n" + "=" * 70)
    print("                      RESUMEN DE COMPATIBILIDAD Y RENDIMIENTO")
    print("=" * 70)
    print(f"{'Estrategia de Optimización':<35} | {'Tiempo (seg)':<12} | {'Aceleración':<10}")
    print("-" * 70)
    print(f"{'A. Python + Diccionarios (Actual)':<35} | {t_py:.5f}s      | Base (1x)")
    print(f"{'B. NumPy Vectorizado (Sin loops)':<35} | {t_np:.5f}s      | {t_py/t_np:.1f}x más rápido")
    print(f"{'C. Numba JIT + Arreglos 1D':<35} | {t_nb_arr:.5f}s      | {t_py/t_nb_arr:.1f}x más rápido")
    print(f"{'D. Numba JIT + Structured Array':<35} | {t_nb_str:.5f}s      | {t_py/t_nb_str:.1f}x más rápido")
    print("=" * 70)
    print("  Conclusiones de Viabilidad:")
    print("  1. Numba JIT sobre arreglos plano o Structured Arrays alcanza velocidad de C++ nativo.")
    print("  2. Structured Array permite mantener campos con nombre (p['lat']) muy parecidos a los dicts.")
    print("  3. ¡La combinación de Numba y NumPy elimina cualquier cuello de botella geodésico!")
    print("=" * 70)

if __name__ == "__main__":
    run_benchmark()
