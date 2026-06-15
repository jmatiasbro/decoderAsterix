# tests/stats/test_chart_renderer.py
import matplotlib
matplotlib.use("Agg")
from matplotlib.figure import Figure
from player.stats.chart_renderer import render, CHART_TYPES

DATA = [("25/01", 12.0), ("07/10", 8.0), ("MTR", 5.0)]

def test_chart_types_v1():
    assert {"bar", "line", "pie", "box", "stacked100",
            "heatmap_hourday", "spider"}.issubset(set(CHART_TYPES))

def test_render_bar_draws_axes():
    fig = Figure()
    render(fig, DATA, "bar", title="t", xlabel="x", ylabel="y")
    ax = fig.axes[0]
    assert len(ax.patches) == 3            # 3 barras
    assert ax.get_title() == "t"

def test_render_line_and_pie_no_error():
    for ct in ("line", "pie"):
        fig = Figure()
        render(fig, DATA, ct)
        assert fig.axes                     # algo dibujado

def test_render_unknown_type_raises():
    import pytest
    with pytest.raises(ValueError):
        render(Figure(), DATA, "nope")
