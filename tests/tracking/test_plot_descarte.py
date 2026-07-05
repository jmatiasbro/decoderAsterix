"""Observabilidad de descartes en _process_plot_data (hallazgo STCA-2 / robustez).

Un plot que provoca una excepción durante el procesamiento se descarta (para no
caer el render), pero DEBE contabilizarse — un descarte silencioso equivale a una
aeronave no pintada (FC-HMI-01). Ver 03_gap_analysis_DO-278A.
"""
import pytest

from tests.tracking.test_matching import app  # noqa: F401


@pytest.fixture
def w(app):
    from player.radar_widget import RadarWidget
    widget = RadarWidget()
    widget.sensores_visibles = None
    widget.limpiar_pantalla()
    widget.reset_origin_for_new_file(-31.0, -64.0, 226, 210, "TEST")
    return widget


def _plot_valido():
    return {"sac_sic": "226/210", "category": 21, "time": 1000.0,
            "x_meters": 0.0, "y_meters": 0.0, "mode_s": "AAAAAA"}


def test_plot_valido_no_incrementa_descartes(w):
    base = w._plots_descartados
    w._process_plot_data(_plot_valido())
    assert w._plots_descartados == base
    assert "AAAAAA" in w.tracks


def test_plot_con_campo_malformado_se_cuenta(w):
    """Un flight_level string rompe una comparación numérica interna; el plot se
    descarta pero AHORA queda contabilizado (antes era silencioso)."""
    base = w._plots_descartados
    d = _plot_valido()
    d["flight_level"] = "300"   # tipo inválido (el decoder real emite float/None)
    ret = w._process_plot_data(d)
    assert ret is None                       # se descarta
    assert w._plots_descartados == base + 1   # pero no en silencio
    assert "AAAAAA" not in w.tracks


def test_contador_acumula_multiples_descartes(w):
    base = w._plots_descartados
    for _ in range(3):
        d = _plot_valido()
        d["flight_level"] = "BAD"
        w._process_plot_data(d)
    assert w._plots_descartados == base + 3
