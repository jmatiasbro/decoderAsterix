# player/stats/chart_renderer.py
"""Render de gráficos del constructor sobre una matplotlib Figure.

Formatos de `data` por tipo:
- bar / line:      list[(label, value)].
- curves / scatter:list[(serie_label, [(x, y), ...])]; cada serie es un color.
- ppi:             list[(serie_label, [(rango_nm, azimut_deg), ...])] — polar, 0°=Norte, horario.
- rose:            list[(serie_label, [(azimut_centro_deg, valor), ...])] — barras polares.
"""
import numpy as np

CHART_TYPES = ("bar", "line", "curves", "scatter", "ppi", "rose")


def _labels_values(data):
    labels = [str(d[0]) for d in data]
    values = [float(d[1]) for d in data]
    return labels, values


def _polar_axes(figure):
    ax = figure.add_subplot(111, projection="polar")
    ax.set_theta_zero_location("N")   # 0° = Norte arriba
    ax.set_theta_direction(-1)        # sentido horario (convención radar)
    return ax


def render(figure, data, chart_type, *, title="", xlabel="", ylabel=""):
    if chart_type not in CHART_TYPES:
        raise ValueError(f"tipo de gráfico desconocido: {chart_type}")
    figure.clear()

    if chart_type == "bar":
        ax = figure.add_subplot(111)
        labels, values = _labels_values(data)
        ax.bar(labels, values)
        ax.set_xlabel(xlabel); ax.set_ylabel(ylabel)
        if len(labels) > 8:
            ax.tick_params(axis="x", labelrotation=90, labelsize=7)

    elif chart_type == "line":
        ax = figure.add_subplot(111)
        labels, values = _labels_values(data)
        ax.plot(labels, values, marker="o")
        ax.set_xlabel(xlabel); ax.set_ylabel(ylabel)

    elif chart_type == "curves":
        ax = figure.add_subplot(111)
        for serie, pts in data:
            if not pts:
                continue
            xs = [float(p[0]) for p in pts]
            ys = [float(p[1]) for p in pts]
            ax.plot(xs, ys, marker="o", ms=3, label=str(serie))
        ax.set_xlabel(xlabel); ax.set_ylabel(ylabel)
        if len([d for d in data if d[1]]) > 1:
            ax.legend(fontsize=7)

    elif chart_type == "scatter":
        ax = figure.add_subplot(111)
        for serie, pts in data:
            if not pts:
                continue
            xs = [float(p[0]) for p in pts]
            ys = [float(p[1]) for p in pts]
            ax.scatter(xs, ys, s=6, alpha=0.5, label=str(serie))
        ax.set_xlabel(xlabel); ax.set_ylabel(ylabel)
        if len(data) > 1:
            ax.legend(fontsize=7, markerscale=2)

    elif chart_type == "ppi":
        ax = _polar_axes(figure)
        for serie, pts in data:
            if not pts:
                continue
            r = [float(p[0]) for p in pts]
            th = np.deg2rad([float(p[1]) for p in pts])
            ax.scatter(th, r, s=4, alpha=0.4, label=str(serie))
        if len(data) > 1:
            ax.legend(fontsize=7, markerscale=2, loc="upper right",
                      bbox_to_anchor=(1.18, 1.12))

    elif chart_type == "rose":
        ax = _polar_axes(figure)
        for serie, pts in data:
            if not pts:
                continue
            th = np.deg2rad([float(p[0]) for p in pts])
            vals = [float(p[1]) for p in pts]
            width = np.deg2rad(360.0 / max(1, len(pts)))
            ax.bar(th, vals, width=width, alpha=0.5,
                   label=(str(serie) if serie else None))
        if len([d for d in data if d[0]]) > 1:
            ax.legend(fontsize=7, loc="upper right", bbox_to_anchor=(1.18, 1.12))

    ax = figure.axes[0]
    ax.set_title(title)
    figure.tight_layout()
    return figure
