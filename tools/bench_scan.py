"""Benchmark de carga de PCAP (scan_pcap): mide decode (cold) vs cache (warm),
pico de memoria y el costo extra de la suite (to_dict masivo).

Uso: python tools/bench_scan.py [archivo.pcap]   (def: baires.pcap)
"""
import os
import sys
import time
import tempfile
import tracemalloc

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    import psutil
    _PROC = psutil.Process()
    def rss_mb():
        return _PROC.memory_info().rss / 1e6
except Exception:
    def rss_mb():
        return float('nan')


def mb(x):
    return f"{x/1e6:8.1f} MB"


def fmt(t):
    return f"{t:7.2f} s"


def main():
    pcap = sys.argv[1] if len(sys.argv) > 1 else "baires.pcap"
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if not os.path.isabs(pcap):
        pcap = os.path.join(base, pcap)
    if not os.path.exists(pcap):
        print(f"No existe: {pcap}")
        return

    size = os.path.getsize(pcap)
    print(f"Archivo : {pcap}")
    print(f"Tamaño  : {mb(size)}")
    print("-" * 56)

    from decoder.data_engine import DataEngine
    cache_dir = tempfile.mkdtemp(prefix="benchscan_")

    # ---------- COLD: decodificación completa + escritura de caché ----------
    rss0 = rss_mb()
    tracemalloc.start()
    eng = DataEngine(cache_dir=cache_dir)
    t0 = time.perf_counter()
    plots, dur, sensores = eng.scan_pcap(pcap)
    t_cold = time.perf_counter() - t0
    _, py_peak_cold = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    rss_cold = rss_mb()

    n = len(plots)
    cache_files = [f for f in os.listdir(cache_dir) if f.endswith(".cache.pkl")]
    cache_size = sum(os.path.getsize(os.path.join(cache_dir, f)) for f in cache_files)

    print(f"COLD (decode)        : {fmt(t_cold)}   plots={n}  sensores={len(sensores)}")
    print(f"  duración capturada : {dur:.1f} s")
    if n:
        print(f"  velocidad          : {n/t_cold:,.0f} plots/s")
    print(f"  pico Python (tracemalloc): {mb(py_peak_cold)}")
    print(f"  RSS proceso  {mb(rss0*1e6)} -> {mb(rss_cold*1e6)}  (Δ {rss_cold-rss0:6.1f} MB)")
    print(f"  caché pickle escrito : {mb(cache_size)}  ({n} plots)")
    print("-" * 56)

    # ---------- Costo extra de la suite: to_dict() masivo ----------
    tracemalloc.start()
    t0 = time.perf_counter()
    dicts = [p.to_dict() for p in plots]
    t_dict = time.perf_counter() - t0
    _, py_peak_dict = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    print(f"SUITE to_dict()      : {fmt(t_dict)}   ({len(dicts)} dicts)")
    print(f"  pico Python adicional: {mb(py_peak_dict)}")
    print("-" * 56)
    del dicts, plots, eng

    # ---------- WARM: carga desde caché pickle ----------
    rssw0 = rss_mb()
    tracemalloc.start()
    eng2 = DataEngine(cache_dir=cache_dir)
    t0 = time.perf_counter()
    plots2, _, _ = eng2.scan_pcap(pcap)
    t_warm = time.perf_counter() - t0
    _, py_peak_warm = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    rss_warm = rss_mb()
    print(f"WARM (cache pickle)  : {fmt(t_warm)}   plots={len(plots2)}")
    print(f"  pico Python (tracemalloc): {mb(py_peak_warm)}")
    print(f"  RSS proceso  {mb(rssw0*1e6)} -> {mb(rss_warm*1e6)}  (Δ {rss_warm-rssw0:6.1f} MB)")
    if t_warm > 0:
        print(f"  speedup vs cold    : {t_cold/t_warm:.1f}×")
    print("-" * 56)

    # limpiar
    try:
        for f in os.listdir(cache_dir):
            os.remove(os.path.join(cache_dir, f))
        os.rmdir(cache_dir)
    except Exception:
        pass


if __name__ == "__main__":
    main()
