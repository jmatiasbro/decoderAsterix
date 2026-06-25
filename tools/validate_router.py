"""Captura/compara una firma del output de scan_pcap para validar que una
optimización del router no cambia ningún valor decodificado.

  python tools/validate_router.py baseline   -> escribe tools/_sig.txt
  python tools/validate_router.py check       -> compara contra tools/_sig.txt
"""
import os
import sys
import hashlib
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SIG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_sig.txt")


def firma(pcap):
    from decoder.data_engine import DataEngine
    eng = DataEngine(cache_dir=tempfile.mkdtemp(prefix="valrouter_"))
    plots, _, _ = eng.scan_pcap(pcap)
    h = hashlib.sha256()
    n = 0
    for p in plots:
        def r(x):
            try:
                return f"{float(x):.6f}"
            except Exception:
                return "·"
        campos = "|".join([
            str(p.category), str(p.sac_sic),
            r(getattr(p, 'lat', None)), r(getattr(p, 'lon', None)),
            r(getattr(p, 'rho_render', None)), r(getattr(p, 'theta_render', None)),
        ])
        h.update(campos.encode())
        h.update(b"\n")
        n += 1
    return n, h.hexdigest()


def main():
    modo = sys.argv[1] if len(sys.argv) > 1 else "check"
    pcap = sys.argv[2] if len(sys.argv) > 2 else "baires.pcap"
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if not os.path.isabs(pcap):
        pcap = os.path.join(base, pcap)

    n, dig = firma(pcap)
    linea = f"{n} {dig}"
    if modo == "baseline":
        with open(SIG, "w") as f:
            f.write(linea)
        print(f"BASELINE  plots={n}  sha256={dig}")
    else:
        prev = open(SIG).read().strip() if os.path.exists(SIG) else ""
        print(f"AHORA     plots={n}  sha256={dig}")
        print(f"BASELINE  {prev}")
        print("IDÉNTICO ✔" if prev == linea else "DIFERENTE �’")


if __name__ == "__main__":
    main()
