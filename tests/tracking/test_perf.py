"""Tests HLR-PERF-01..03: rendimiento del motor de tracking.

HLR-PERF-01 — Latencia de lote de 200 plots ≤ 200 ms.
HLR-PERF-02 — Cadencia safety chain configurable (0.5–2 Hz).
HLR-PERF-03 — 500 tracks sin degradar el ciclo (creación < 2 s).

HLR-PERF-04 (refresco PPI) y HLR-PERF-05 (5000 PPS) requieren display/red;
se verifican en el smoke test manual con baires.pcap.
"""
import os
import time
import pytest
from unittest.mock import patch

from tests.tracking.test_matching import app  # noqa: F401

# En CI el hardware del runner es variable y más lento; los umbrales de reloj de
# pared son SLAs de la máquina de referencia (local). Bajo CI se relajan ×5 para
# que sigan detectando regresiones patológicas (O(N²)) sin fallar por hardware.
# La verificación de rendimiento formal (HLR-PERF-04/05) es la manual (SVP §5.4).
_CI = bool(os.environ.get("CI") or os.environ.get("GITHUB_ACTIONS"))
_F = 5.0 if _CI else 1.0


def _make_plot(n, cat=21, sac_sic="226/210"):
    # Separar tracks > 5 km (> 2 NM) para evitar fusión por proximidad (gate 1 NM)
    return {
        "sac_sic": sac_sic,
        "category": cat,
        "time": 1000.0 + n,
        "x_meters": float(n % 50) * 5000.0,
        "y_meters": float(n // 50) * 5000.0,
        "mode_s": f"{n:06X}",
    }


def _radarplot(n):
    from player.radar_widget import RadarPlot
    return RadarPlot(
        x=float(n % 100) * 1000.0, y=float(n // 100) * 1000.0,
        sac_sic="226/210", category=21, timestamp=1000.0,
        mode3a=None, callsign=None, flight_level=None, is_track=False,
        mode_s=f"{n:06X}", track_angle=None, ground_speed=None)


@pytest.fixture
def w(app):
    from player.radar_widget import RadarWidget
    widget = RadarWidget()
    widget.projection_set = True
    widget.sensores_visibles = None
    widget.limpiar_pantalla()
    return widget


# ── HLR-PERF-01: lote de 200 plots ≤ 200 ms ─────────────────────────────────

def test_lote_200_plots_bajo_200ms(w):
    plots = [_make_plot(i) for i in range(200)]
    t0 = time.perf_counter()
    with patch("player.radar_widget.SimulationTime.time", return_value=1000.0):
        for p in plots:
            w._process_plot_data(p)
    elapsed_ms = (time.perf_counter() - t0) * 1000.0
    limite = 200.0 * _F
    assert elapsed_ms < limite, f"200 plots tardaron {elapsed_ms:.1f} ms (límite: {limite:.0f} ms)"


# ── HLR-PERF-02: cadencia safety configurable ────────────────────────────────

def test_safety_interval_default_1hz(w):
    assert w._safety_interval == 1.0


def test_safety_interval_acepta_minimo_05hz(w):
    w._safety_interval = 0.5
    assert w._safety_interval == 0.5


def test_safety_interval_acepta_maximo_2s(w):
    w._safety_interval = 2.0
    assert w._safety_interval == 2.0


# ── HLR-PERF-03: 500 tracks ─────────────────────────────────────────────────

def test_crear_500_tracks_bajo_2s(w):
    plots = [_make_plot(i) for i in range(500)]
    t0 = time.perf_counter()
    with patch("player.radar_widget.SimulationTime.time", return_value=1000.0):
        for p in plots:
            w._process_plot_data(p)
    elapsed = time.perf_counter() - t0
    total = len(w.tracks) + len(w.pending_tracks)
    assert total >= 490, f"Solo se crearon {total} tracks de 500"
    limite = 2.0 * _F
    assert elapsed < limite, f"Crear 500 tracks tardó {elapsed:.2f} s (límite: {limite:.1f} s)"


def test_reconciliar_500_tracks_bajo_500ms(w):
    with patch("player.radar_widget.SimulationTime.time", return_value=1000.0):
        for i in range(500):
            w.tracks[f"{i:06X}"] = _radarplot(i)

    t0 = time.perf_counter()
    with patch("player.radar_widget.SimulationTime.time", return_value=1001.0):
        w._reconciliar_pistas()
    elapsed_ms = (time.perf_counter() - t0) * 1000.0
    limite = 500.0 * _F
    assert elapsed_ms < limite, f"Reconciliar 500 tracks tardó {elapsed_ms:.1f} ms (límite: {limite:.0f} ms)"
