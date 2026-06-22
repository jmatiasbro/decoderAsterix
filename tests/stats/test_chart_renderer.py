# tests/stats/test_chart_renderer.py
import matplotlib
matplotlib.use("Agg")
from matplotlib.figure import Figure
from player.stats.chart_renderer import render, CHART_TYPES

DATA = [("25/01", 12.0), ("07/10", 8.0), ("MTR", 5.0)]
SERIES = [("25/01", [(10.0, 1.0), (20.0, 2.0)]), ("07/10", [(15.0, 3.0)])]


def test_chart_types_v2():
    assert set(CHART_TYPES) == {"bar", "line", "curves", "scatter", "ppi", "rose"}


def test_render_bar_draws_axes():
    fig = Figure()
    render(fig, DATA, "bar", title="t", xlabel="x", ylabel="y")
    ax = fig.axes[0]
    assert len(ax.patches) == 3            # 3 barras
    assert ax.get_title() == "t"


def test_render_line_no_error():
    fig = Figure()
    render(fig, DATA, "line")
    assert fig.axes


def test_render_unknown_type_raises():
    import pytest
    with pytest.raises(ValueError):
        render(Figure(), DATA, "nope")


def test_render_curves_multiserie():
    fig = Figure()
    render(fig, SERIES, "curves", xlabel="Rango", ylabel="Pd")
    assert len(fig.axes[0].lines) == 2     # una curva por serie


def test_render_scatter():
    fig = Figure()
    render(fig, SERIES, "scatter")
    assert fig.axes


def test_render_ppi_polar():
    fig = Figure()
    render(fig, SERIES, "ppi", title="PPI")
    assert fig.axes[0].name == "polar"


def test_render_rose_polar():
    fig = Figure()
    render(fig, [("", [(5.0, 3.0), (15.0, 7.0)])], "rose")
    assert fig.axes[0].name == "polar"
    assert fig.axes[0].patches      # barras dibujadas
