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


from player.centro_tecnico.window import CentroTecnicoWindow


def test_window_has_five_tabs(app):
    w = CentroTecnicoWindow()
    assert w.tabs.count() == 5
    titles = [w.tabs.tabText(i) for i in range(5)]
    assert any("Estad" in t for t in titles)
    assert any("Cobertura" in t for t in titles)


def test_source_toggle_default_duckdb(app):
    w = CentroTecnicoWindow()
    assert w.current_source_kind() in ("duckdb", "session")


from player.technical_monitor import TechnicalMonitorWidget


def test_monitor_tab_is_technical_monitor(app):
    w = CentroTecnicoWindow()
    idx = next(i for i in range(w.tabs.count()) if "Monitor" in w.tabs.tabText(i))
    assert isinstance(w.tabs.widget(idx), TechnicalMonitorWidget)


from PyQt6.QtWidgets import QTabWidget


def test_pass_tab_embeds_dashboard_tabs(app):
    w = CentroTecnicoWindow()
    idx = next(i for i in range(w.tabs.count()) if "PASS" in w.tabs.tabText(i))
    page = w.tabs.widget(idx)
    assert page.findChild(QTabWidget) is not None, \
        "PASS tab debe contener un QTabWidget interno del PassDashboardDialog"
