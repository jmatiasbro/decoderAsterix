# player/stats/chart_renderer.py
"""Render de gráficos del constructor sobre una matplotlib Figure.

`data` para bar/line/pie/box/stacked100/spider es list[(label, value)].
Para heatmap_hourday es list[(hour_label, day_label, value)].
Para scatter (X vs Y) es list[(serie_label, [(x, y), ...])]; cada serie es un color.
"""
import numpy as np

CHART_TYPES = ("bar", "line", "pie", "box", "stacked100", "heatmap_hourday", "spider", "scatter")


def _labels_values(data):
    labels = [str(d[0]) for d in data]
    values = [float(d[1]) for d in data]
    return labels, values


def render(figure, data, chart_type, *, title="", xlabel="", ylabel=""):
    if chart_type not in CHART_TYPES:
        raise ValueError(f"tipo de gráfico desconocido: {chart_type}")
    figure.clear()
    if chart_type == "bar":
        ax = figure.add_subplot(111)
        labels, values = _labels_values(data)
        ax.bar(labels, values)
        ax.set_xlabel(xlabel); ax.set_ylabel(ylabel)
    elif chart_type == "line":
        ax = figure.add_subplot(111)
        labels, values = _labels_values(data)
        ax.plot(labels, values, marker="o")
        ax.set_xlabel(xlabel); ax.set_ylabel(ylabel)
    elif chart_type == "pie":
        ax = figure.add_subplot(111)
        labels, values = _labels_values(data)
        ax.pie(values, labels=labels, autopct="%1.0f%%")
    else:
        _render_extended(figure, data, chart_type, xlabel, ylabel)
        ax = figure.axes[0] if figure.axes else figure.add_subplot(111)
    ax = figure.axes[0]
    ax.set_title(title)
    figure.tight_layout()
    return figure


def _render_extended(figure, data, chart_type, xlabel, ylabel):
    if chart_type == "box":
        ax = figure.add_subplot(111)
        labels = [str(d[0]) for d in data]
        series = [list(d[1]) for d in data]
        ax.boxplot(series, tick_labels=labels)
        ax.set_xlabel(xlabel); ax.set_ylabel(ylabel)
    elif chart_type == "stacked100":
        ax = figure.add_subplot(111)
        labels, values = _labels_values(data)
        total = sum(values) or 1.0
        bottom = 0.0
        for lab, val in zip(labels, values):
            pct = 100.0 * val / total
            ax.bar(["total"], [pct], bottom=[bottom], label=lab)
            bottom += pct
        ax.legend(fontsize=7); ax.set_ylabel("%")
    elif chart_type == "spider":
        labels, values = _labels_values(data)
        ang = np.linspace(0, 2 * np.pi, len(labels), endpoint=False).tolist()
        vals = values + values[:1]
        ang = ang + ang[:1]
        ax = figure.add_subplot(111, projection="polar")
        ax.plot(ang, vals, marker="o")
        ax.fill(ang, vals, alpha=0.25)
        ax.set_xticks(ang[:-1]); ax.set_xticklabels(labels, fontsize=8)
    elif chart_type == "scatter":
        ax = figure.add_subplot(111)
        for serie_label, puntos in data:
            if not puntos:
                continue
            xs = [float(p[0]) for p in puntos]
            ys = [float(p[1]) for p in puntos]
            ax.scatter(xs, ys, s=6, alpha=0.5, label=str(serie_label))
        ax.set_xlabel(xlabel); ax.set_ylabel(ylabel)
        # Leyenda solo si hay más de una serie (color por radar/categoría/…).
        if len(data) > 1:
            ax.legend(fontsize=7, markerscale=2)
    elif chart_type == "heatmap_hourday":
        ax = figure.add_subplot(111)
        hours = sorted({d[0] for d in data})
        days = sorted({d[1] for d in data})
        hi = {h: i for i, h in enumerate(hours)}
        di = {d: i for i, d in enumerate(days)}
        grid = np.zeros((len(days), len(hours)))
        for h, d, v in data:
            grid[di[d], hi[h]] = v
        im = ax.imshow(grid, aspect="auto")
        ax.set_xticks(range(len(hours))); ax.set_xticklabels(hours, rotation=90, fontsize=7)
        ax.set_yticks(range(len(days))); ax.set_yticklabels(days, fontsize=7)
        figure.colorbar(im, ax=ax)
    else:
        raise ValueError(f"tipo de gráfico no implementado aún: {chart_type}")
