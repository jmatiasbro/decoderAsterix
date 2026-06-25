"""Profiling del decode (cold) de scan_pcap con cProfile.
Uso: python tools/prof_scan.py [archivo.pcap]   (def: baires.pcap)
"""
import os
import sys
import cProfile
import pstats
import io
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main():
    pcap = sys.argv[1] if len(sys.argv) > 1 else "baires.pcap"
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if not os.path.isabs(pcap):
        pcap = os.path.join(base, pcap)
    from decoder.data_engine import DataEngine
    cache_dir = tempfile.mkdtemp(prefix="profscan_")
    eng = DataEngine(cache_dir=cache_dir)

    pr = cProfile.Profile()
    pr.enable()
    plots, dur, sensores = eng.scan_pcap(pcap)
    pr.disable()

    print(f"plots={len(plots)} sensores={len(sensores)} dur={dur:.0f}s")
    for orden in ("tottime", "cumulative"):
        s = io.StringIO()
        ps = pstats.Stats(pr, stream=s).strip_dirs().sort_stats(orden)
        ps.print_stats(22)
        print("\n" + "=" * 70)
        print(f"TOP por {orden}")
        print("=" * 70)
        print(s.getvalue())

    try:
        for f in os.listdir(cache_dir):
            os.remove(os.path.join(cache_dir, f))
        os.rmdir(cache_dir)
    except Exception:
        pass


if __name__ == "__main__":
    main()
