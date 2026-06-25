"""Mide cuánto del cold se va en WGS84_GEOD.fwd (proyección polar->WGS84 por registro)
envolviéndolo, y el total de scan_pcap. Sin tocar el motor."""
import os
import sys
import time
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main():
    pcap = sys.argv[1] if len(sys.argv) > 1 else "baires.pcap"
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if not os.path.isabs(pcap):
        pcap = os.path.join(base, pcap)

    import utils.geo as geo
    stats = {"n": 0, "t": 0.0}
    orig_fwd = geo.WGS84_GEOD.fwd

    def timed_fwd(*a, **k):
        t0 = time.perf_counter()
        r = orig_fwd(*a, **k)
        stats["t"] += time.perf_counter() - t0
        stats["n"] += 1
        return r
    geo.WGS84_GEOD.fwd = timed_fwd

    # data_engine importó WGS84_GEOD por nombre; re-apuntar su referencia.
    import decoder.data_engine as de
    de.WGS84_GEOD.fwd = timed_fwd

    from decoder.data_engine import DataEngine
    eng = DataEngine(cache_dir=tempfile.mkdtemp(prefix="timegeod_"))
    t0 = time.perf_counter()
    plots, _, _ = eng.scan_pcap(pcap)
    t_total = time.perf_counter() - t0

    print(f"scan_pcap total      : {t_total:7.2f} s   plots={len(plots)}")
    print(f"WGS84_GEOD.fwd       : {stats['t']:7.2f} s   llamadas={stats['n']:,}  "
          f"({100*stats['t']/t_total:.0f}% del total)")
    if stats['n']:
        print(f"  por llamada        : {1e6*stats['t']/stats['n']:.1f} µs")


if __name__ == "__main__":
    main()
