import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
pytest.importorskip("PyQt6.QtWidgets")
from PyQt6.QtWidgets import QApplication
from player.centro_tecnico.stats_widget import StatsWidget
from player.stats.data_source import SessionSource


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def _session_provider():
    rows = [{"sac_sic": "25/01", "time": float(i), "flight_level": "100",
             "mode3a": "7000", "raw_range": 100.0 + i, "raw_azimuth": 10.0}
            for i in range(5)]
    src = SessionSource(rows)
    return lambda: src


def test_stats_widget_generate_renders(app):
    sw = StatsWidget(_session_provider())
    sw.set_metric("count"); sw.set_dimension("radar"); sw.set_chart("bar")
    sw.generate()
    assert sw.figure.axes               # algo se dibujó
    assert len(sw.figure.axes[0].patches) == 1   # 1 radar -> 1 barra
