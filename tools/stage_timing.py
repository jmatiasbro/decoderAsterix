"""Desglosa el costo del cold: (1) leer pcap + dpkt + extraer payload UDP,
(2) decode ASTERIX puro (router), (3) escritura de caché pickle."""
import os
import sys
import time
import pickle
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main():
    pcap = sys.argv[1] if len(sys.argv) > 1 else "baires.pcap"
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if not os.path.isabs(pcap):
        pcap = os.path.join(base, pcap)

    import dpkt
    # --- Etapa 1: lectura pcap + dpkt + extracción de payload UDP ---
    payloads = []
    t0 = time.perf_counter()
    with open(pcap, 'rb') as f:
        reader = dpkt.pcap.Reader(f)
        is_sll = (getattr(reader, 'datalink', lambda: 1)() == 113)
        for ts, buf in reader:
            try:
                pkt = dpkt.sll.SLL(buf) if is_sll else dpkt.ethernet.Ethernet(buf)
                if not isinstance(pkt.data, dpkt.ip.IP):
                    continue
                ip = pkt.data
                if not isinstance(ip.data, dpkt.udp.UDP):
                    continue
                payloads.append(bytes(ip.data.data))
            except Exception:
                continue
    t_read = time.perf_counter() - t0
    print(f"1) leer pcap + dpkt + payload UDP : {t_read:7.2f} s   ({len(payloads)} datagramas UDP)")

    # --- Etapa 1b: lo mismo pero extrayendo payload por OFFSETS (sin dpkt objs) ---
    t0 = time.perf_counter()
    n_off = 0
    with open(pcap, 'rb') as f:
        reader = dpkt.pcap.Reader(f)
        is_sll = (getattr(reader, 'datalink', lambda: 1)() == 113)
        for ts, buf in reader:
            # Ethernet(14) | IP(ihl*4) | UDP(8) ; SLL=16 en vez de 14
            l2 = 16 if is_sll else 14
            if len(buf) < l2 + 20 + 8:
                continue
            if buf[l2 - 2:l2] != b'\x08\x00' and not is_sll:
                continue
            ihl = (buf[l2] & 0x0F) * 4
            if buf[l2 + 9] != 17:  # proto UDP
                continue
            start = l2 + ihl + 8
            if start <= len(buf):
                _ = buf[start:]
                n_off += 1
    t_off = time.perf_counter() - t0
    print(f"1b) payload UDP por OFFSETS (sin dpkt objs): {t_off:7.2f} s   ({n_off} datagramas)")

    # --- Etapa 2: decode ASTERIX puro sobre los payloads ya extraídos ---
    from decoder.asterix_router import AsterixRouter
    router = AsterixRouter()
    t0 = time.perf_counter()
    total = 0
    for p in payloads:
        recs = router.procesar_paquete_udp(p, silent=True)
        total += len(recs)
    t_decode = time.perf_counter() - t0
    print(f"2) decode ASTERIX (router puro)  : {t_decode:7.2f} s   ({total} registros)")

    # --- Etapa 3: pickle de una lista de N dicts (proxy de write_cache) ---
    sample = [{'category': 48, 'sac_sic': '1/1', 'x': 1.0, 'y': 2.0}] * max(1, total)
    t0 = time.perf_counter()
    tmp = os.path.join(tempfile.gettempdir(), "stage_pickle.pkl")
    with open(tmp, 'wb') as f:
        pickle.dump(sample, f)
    t_pkl = time.perf_counter() - t0
    sz = os.path.getsize(tmp)
    os.remove(tmp)
    print(f"3) pickle.dump {total} objetos      : {t_pkl:7.2f} s   ({sz/1e6:.1f} MB)")


if __name__ == "__main__":
    main()
