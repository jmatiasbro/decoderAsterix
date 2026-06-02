"""Integration test for garbling detection in the decoding pipeline.

This test verifies that:
1. The CAT048 decoder extracts the garbled flag from the correct bits (I048/070 and I048/090).
2. The DataEngine propagates the `garbled` field into the generated `AsterixPlot`.
3. The QualityManager correctly degrades the track with reason 'GARBLING' when the flag is True.
4. A non‑garbled track is **not** degraded.

The test uses the in‑memory classes, no filesystem I/O is required.
"""
import struct
import pytest

# Ensure the project root is on PYTHONPATH when the test runs.
# In CI this will be configured, but we also set it here for local execution.
import os
os.environ["PYTHONPATH"] = os.getenv("PYTHONPATH", "") + os.pathsep + os.getcwd()

from decoder.decoders.cat048 import decode
from decoder.data_engine import DataEngine
from analysis.quality_manager import QualityManager
from player.radar_widget import SimulationTime

# Helper to build a minimal CAT048 payload with the desired garbled flag.
def build_cat048_payload(garbled_mode3a: bool = False, garbled_fl: bool = False, fl_value: int = 350):
    """Return (payload_bytes, block_length) for a minimal CAT048 packet.

    Parameters
    ----------
    garbled_mode3a: bool – set the G‑bit in I048/070 (Mode‑3/A code).
    garbled_fl: bool – set the G‑bit in I048/090 (Flight Level).
    fl_value: int – flight level in hundreds of feet (e.g. 350 → FL350).
    """
    # FSPEC: FRN1 (Data Source Identifier) + FRN5 (Mode‑3/A) + FRN6 (Flight Level) present.
    # Bits: FRN1=1, FRN2‑4=0, FRN5=1, FRN6=1, FX=0 → 0b10001100 = 0x8C
    fspec = bytes([0x8C])
    # FRN1 – SAC=10, SIC=20
    ds_id = struct.pack('>BB', 10, 20)
    # FRN5 – Mode‑3/A code (12 bits) + V/G/L bits.
    mode3a_code = 0x049D  # arbitrary octal 2335 → 0x49D
    if garbled_mode3a:
        mode3a_code |= 0x4000  # set G‑bit
    # V‑bit left as 0 (validated)
    mode3a_bytes = struct.pack('>H', mode3a_code)
    # FRN6 – Flight Level (14‑bit value) + V/G bits.
    fl_raw = int(fl_value * 4)  # LSB = 1/4 FL
    if garbled_fl:
        fl_raw |= 0x4000  # set G‑bit
    fl_bytes = struct.pack('>H', fl_raw)
    payload = fspec + ds_id + mode3a_bytes + fl_bytes
    block_length = len(payload) + 3  # +3 for the ASTERIX header (category, length, etc.)
    return payload, block_length

@pytest.fixture(scope="module")
def data_engine():
    return DataEngine()

@pytest.fixture(scope="module")
def qm():
    return QualityManager()

def test_garbling_flag_extracted_and_degraded(data_engine, qm):
    # Build a packet where both Mode‑3/A and Flight Level are garbled.
    payload, bl = build_cat048_payload(garbled_mode3a=True, garbled_fl=True, fl_value=350)
    plots = decode(payload, 0, bl, 48)
    assert len(plots) == 1
    rec = plots[0]
    # Verify decoder extracted the garbled flag correctly.
    assert rec.get('garbled') is True
    # Convert record to AsterixPlot using the engine.
    plot = data_engine._record_to_plot(rec, {})
    assert plot is not None
    # The plot should carry the garbled flag.
    assert getattr(plot, 'garbled', False) is True
    # Pass the plot to QualityManager.
    degradada, razon = qm.evaluar_pista(plot.id, {'garbled': plot.garbled, 'update_count': 1, 'age': 0})
    assert degradada is True
    assert razon == qm.DQF_GARBLING

def test_non_garbled_not_degraded(data_engine, qm):
    payload, bl = build_cat048_payload(garbled_mode3a=False, garbled_fl=False, fl_value=350)
    plots = decode(payload, 0, bl, 48)
    assert len(plots) == 1
    rec = plots[0]
    assert rec.get('garbled') is False
    plot = data_engine._record_to_plot(rec, {})
    assert plot is not None
    assert getattr(plot, 'garbled', False) is False
    degradada, razon = qm.evaluar_pista(plot.id, {'garbled': plot.garbled, 'update_count': 1, 'age': 0})
    # With a single update and no garbling, the track is considered INMADURA, not GARBLING.
    assert degradada is True
    assert razon == qm.DQF_INMADURA

# Additional sanity check: a normal track (2+ updates) with garbled=False must be clean.
def test_normal_track_without_garbling(qm):
    # Simulate a track that has already been seen twice.
    track_id = "test_normal"
    degradada, razon = qm.evaluar_pista(track_id, {'garbled': False, 'update_count': 2, 'age': 5})
    assert degradada is False
    assert razon == ""
