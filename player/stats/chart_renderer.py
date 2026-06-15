# player/stats/chart_renderer.py
"""Render de gráficos del constructor sobre una matplotlib Figure.

`data` para bar/line/pie/box/stacked100/spider es list[(label, value)].
Para heatmap_hourday es list[(hour_label, day_label, value)].
"""
CHART_TYPES = ("bar", "line", "pie", "box", "stacked100", "heatmap_hourday", "spider")


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
    # implementado en Task 8
    raise ValueError(f"tipo de gráfico no implementado aún: {chart_type}")
