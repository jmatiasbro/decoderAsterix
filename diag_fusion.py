"""
Diagnóstico de fusión multisensor (NO modifica el motor).
Decodifica un PCAP con el mismo DataEngine del proyecto, proyecta lat/lon a un
plano local en metros y replica la precedencia de correlación de radar_widget
(A: Mode S, B: Squawk+gate, E: proximidad) en MODO INTEGRADO, para detectar
aviones que terminan como track_id duplicados y mostrar por qué no fusionan.
"""
import sys, math
from collections import defaultdict
from decoder.data_engine import DataEngine
from utils.geo import cargar_sensores

PCAP = sys.argv[1] if len(sys.argv) > 1 else "baires.pcap"
NM = 1852.0

sensores = cargar_sensores("default-site-params")
print(f"sensores con posicion cargados: {len(sensores)}")
eng = DataEngine(sensores=sensores)
plots, dur, sensores = eng.scan_pcap(PCAP)
print(f"PCAP={PCAP}  plots={len(plots)}  dur={dur:.1f}s  sensores={sorted(sensores)}")

# Centro para proyección local (primer plot con lat/lon)
clat = clon = None
for p in plots:
    if p.lat is not None and p.lon is not None:
        clat, clon = p.lat, p.lon
        break
if clat is None:
    print("Sin lat/lon en el PCAP; no se puede proyectar."); sys.exit(0)

MPD_LAT = 111320.0
def xy(lat, lon):
    if lat is None or lon is None:
        return None, None
    x = (lon - clon) * MPD_LAT * math.cos(math.radians(clat))
    y = (lat - clat) * MPD_LAT
    return x, y

def norm_s(v):
    return (v or "").strip().upper()

def norm_sq(v):
    if v is None: return ""
    if isinstance(v, int): return f"{v:04o}"
    return str(v).strip()

# Estadística: ¿qué identificadores trae cada plot CAT 48? -------------------
c48 = both = only_ms = only_sq = neither = 0
for p in plots:
    if p.category != 48:
        continue
    c48 += 1
    has_ms = bool(norm_s(p.mode_s)) and norm_s(p.mode_s) != "----" and not norm_s(p.mode_s).startswith("0AD5B")
    sq = norm_sq(p.mode3a)
    has_sq = bool(sq) and sq not in ("----", "0000")
    if has_ms and has_sq: both += 1
    elif has_ms: only_ms += 1
    elif has_sq: only_sq += 1
    else: neither += 1
print(f"\nCAT48 total={c48}")
print(f"  con ModeS Y squawk : {both} ({100*both/max(1,c48):.1f}%)")
print(f"  solo ModeS (sq=----): {only_ms} ({100*only_ms/max(1,c48):.1f}%)  <- bloque B no puede")
print(f"  solo squawk (sin MS): {only_sq} ({100*only_sq/max(1,c48):.1f}%)  <- bloque A no puede")
print(f"  sin ninguno (primar.): {neither} ({100*neither/max(1,c48):.1f}%)  <- solo bloque E")

# Replica simplificada de la correlación en MODO INTEGRADO -------------------
tracks = {}  # tid -> dict(x,y,mode_s,sq,fl,sac_sic,cat)
reasons = defaultdict(int)
dup_examples = []

def correlate(d):
    x, y = xy(d.lat, d.lon)
    if x is None:
        return None, "sin_xy"
    ms = norm_s(d.mode_s)
    is_mock = ms.startswith("0AD5B") or norm_s(d.callsign).startswith("ADSB")
    sq = norm_sq(d.mode3a)
    fl = d.flight_level
    sid = d.sac_sic

    # A. Mode S
    if ms and ms != "----" and not is_mock:
        for tid, t in tracks.items():
            if t["mode_s"] == ms:
                return tid, "A_modeS"
    # B. Squawk + gate
    if sq and sq not in ("----", "0000"):
        generic = sq in ("1200", "2000", "7000", "0000")
        maxd = (10.0 if generic else 30.0) * NM
        for tid, t in tracks.items():
            if t["sq"] == sq:
                tms = t["mode_s"]
                if (not ms) or (not tms) or tms == ms:
                    if math.hypot(t["x"]-x, t["y"]-y) < maxd:
                        return tid, "B_squawk"
    # E. Proximidad cartesiana + vertical
    alt_c = fl*100.0 if fl is not None else None
    has_alt = alt_c is not None
    maxd = (3.0 if has_alt else 1.0) * NM
    best, bestd = None, float("inf")
    for tid, t in tracks.items():
        alt_t = t["fl"]*100.0 if t["fl"] is not None else None
        if has_alt and alt_t is not None and abs(alt_c-alt_t) >= 1500.0:
            continue
        dd = math.hypot(t["x"]-x, t["y"]-y)
        if dd < maxd and dd < bestd:
            bestd, best = dd, tid
    if best:
        return best, "E_prox"
    return None, "NEW"

# Para agrupar "mismo avión real" usamos Mode S si existe, si no squawk+vecindad
def truth_key(d):
    ms = norm_s(d.mode_s)
    if ms and ms != "----" and not (ms.startswith("0AD5B")):
        return ("MS", ms)
    sq = norm_sq(d.mode3a)
    if sq and sq not in ("----", "0000"):
        return ("SQ", sq)
    return None

truth_to_tids = defaultdict(set)
tid_seq = 0
for p in plots:
    if p.category not in (1, 21, 48, 62):
        continue
    tid, why = correlate(p)
    reasons[why] += 1
    if tid is None:
        tid_seq += 1
        x, y = xy(p.lat, p.lon)
        tid = f"NEW_{tid_seq}_{p.sac_sic}"
        tracks[tid] = dict(x=x, y=y, mode_s=norm_s(p.mode_s), sq=norm_sq(p.mode3a),
                           fl=p.flight_level, sac_sic=p.sac_sic, cat=p.category)
    else:
        t = tracks[tid]
        x, y = xy(p.lat, p.lon)
        t["x"], t["y"] = x, y
        if not t["mode_s"] and norm_s(p.mode_s):
            t["mode_s"] = norm_s(p.mode_s)
        if p.flight_level is not None:
            t["fl"] = p.flight_level
    tk = truth_key(p)
    if tk:
        truth_to_tids[tk].add(tid)

print("\nDecisiones de correlación:")
for k, v in sorted(reasons.items(), key=lambda kv: -kv[1]):
    print(f"  {k:10s} {v}")

print("\n=== AVIONES CON DUPLICADOS (mismo avión -> >1 track_id) ===")
ndup = 0
for tk, tids in sorted(truth_to_tids.items()):
    if len(tids) > 1:
        ndup += 1
        kind, val = tk
        print(f"\n[{kind} {val}] -> {len(tids)} pistas:")
        for tid in sorted(tids):
            t = tracks[tid]
            print(f"   {tid:28s} sensor={t['sac_sic']:8s} modeS={t['mode_s'] or '-':7s} "
                  f"sq={t['sq'] or '-':5s} fl={t['fl']} x={t['x']:.0f} y={t['y']:.0f}")
print(f"\nTotal aviones duplicados: {ndup}")
