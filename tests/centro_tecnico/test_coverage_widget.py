import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import pytest
pytest.importorskip("PyQt6.QtWidgets")
from PyQt6.QtWidgets import QApplication
from player.centro_tecnico.coverage_widget import CoverageWidget
from player.stats.data_source import SessionSource
from utils.geo import GeoTools

@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])

def _provider_with_coverage():
    rlat, rlon = -31.31, -64.21
    rows = []
    for az in range(0, 360, 4):
        plat, plon = GeoTools.vincenty_forward(rlat, rlon, float(az),
                                               GeoTools.nm_to_meters(90.0))
        rows.append({"sac_sic": "25/01", "lat": plat, "lon": plon,
                     "flight_level": "150", "time": 0.0})
    src = SessionSource(rows)
    return lambda: src

def test_coverage_widget_calculate_draws(app, monkeypatch):
    cw = CoverageWidget(_provider_with_coverage(), db_path="pass_analytics.duckdb")
    # forzar radar y centro (sin depender de default-site-params)
    cw.set_radar("25/01")
    monkeypatch.setattr(cw, "_radar_latlon", lambda sac_sic: (-31.31, -64.21))
    cw.calculate()
    assert cw.result is not None
    assert cw.result.plot_count > 0
    assert cw.fig_polar.axes and cw.fig_map.axes
