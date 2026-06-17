"""Simple runtime test for garbling detection pipeline.

This script reproduces the same checks as the pytest version but runs
without any external testing framework. It prints a clear summary and
exits with code 0 on success or non‑zero on failure.
"""
import struct, sys, os

# Ensure project root is importable.
os.environ["PYTHONPATH"] = os.getenv("PYTHONPATH", "") + os.pathsep + os.getcwd()

from decoder.decoders.cat048 import decode
from decoder.data_engine import DataEngine
from analysis.quality_manager import QualityManager

def build_payload(garbled_mode3a=False, garbled_fl=False, fl_value=350):
    # FSPEC: FRN1 + FRN5 + FRN6 present → 0b10001100 = 0x8C
    fspec = bytes([0x8C])
    ds_id = struct.pack('>BB', 10, 20)
    mode3a = 0x049D
    if garbled_mode3a:
        mode3a |= 0x4000
    mode3a_bytes = struct.pack('>H', mode3a)
    fl_raw = int(fl_value * 4)
    if garbled_fl:
        fl_raw |= 0x4000
    fl_bytes = struct.pack('>H', fl_raw)
    payload = fspec + ds_id + mode3a_bytes + fl_bytes
    block_len = len(payload) + 3
    return payload, block_len

def assert_equal(a, b, msg):
    if a != b:
        print(f"[FAIL] {msg}: {a!r} != {b!r}")
        sys.exit(1)
def run():
    # Instantiate QualityManager once.
    qm = QualityManager()

    # ---------- Test garbled both (Mode‑3/A and FL garbled) ----------
    payload, bl = build_payload(garbled_mode3a=True, garbled_fl=True)
    recs = decode(payload, 0, bl, 48)
    assert_equal(len(recs), 1, "Rec count (garbled both)")
    rec = recs[0]
    assert_equal(rec.get('garbled'), True, "Decoder garbled flag (both)")
    from player.radar_widget import RadarPlot
    plot = RadarPlot(
        x=0.0,
        y=0.0,
        sac_sic='10/20',
        category=48,
        timestamp=0.0,
        mode3a=rec.get('mode_3a'),
        callsign='',
        flight_level=rec.get('flight_level'),
        is_track=True,
        mode_s=None,
        track_angle=None,
        ground_speed=None,
        altitude_ft=None,
        raw_azimuth=rec.get('raw_azimuth'),
        plot_id=None,
        track_number=None,
        raw_range=rec.get('raw_range')
    )
    plot.garbled = rec.get('garbled')
    degrad, razon = qm.evaluar_pista(plot.id, {'garbled': plot.garbled, 'update_count': 1, 'age': 0})
    assert_equal(degrad, True, "Quality degrades garbled track")
    assert_equal(razon, "GARBLING", "Reason is GARBLING (both)")

    # ---------- Test no garbling ----------
    payload, bl = build_payload(garbled_mode3a=False, garbled_fl=False)
    recs = decode(payload, 0, bl, 48)
    assert_equal(len(recs), 1, "Rec count (clean)")
    rec = recs[0]
    assert_equal(rec.get('garbled'), False, "Decoder garbled flag (clean)")
    plot = RadarPlot(
        x=0.0,
        y=0.0,
        sac_sic='10/20',
        category=48,
        timestamp=0.0,
        mode3a=rec.get('mode_3a'),
        callsign='',
        flight_level=rec.get('flight_level'),
        is_track=True,
        mode_s=None,
        track_angle=None,
        ground_speed=None,
        altitude_ft=None,
        raw_azimuth=rec.get('raw_azimuth'),
        plot_id=None,
        track_number=None,
        raw_range=rec.get('raw_range')
    )
    plot.garbled = rec.get('garbled')
    degrad, razon = qm.evaluar_pista(plot.id, {'garbled': plot.garbled, 'update_count': 1, 'age': 0})
    # With a single update and no garbling, should be INMADURA.
    assert_equal(degrad, True, "Quality degrades inmadura track (clean)")
    assert_equal(razon, "PISTA INMADURA", "Reason is INMADURA (clean)")

    # ---------- Test normal track (2 updates, no garble) ----------
    degrad, razon = qm.evaluar_pista('normal_track', {'garbled': False, 'update_count': 2, 'age': 5})
    assert_equal(degrad, False, "Normal track not degraded")
    assert_equal(razon, "", "Normal track reason empty")

    print("All garbling integration checks passed.")
    sys.exit(0)

if __name__ == '__main__':
    run()
