"""Test de integración end-to-end: PCAP → DataEngine → RadarWidget → tracks → safety.

Ejercita la cadena completa sin GUI con un PCAP de referencia pequeño y determinista
(`tests/data/cat_034_048.pcap`, CAT034+CAT048 multi-sensor). Cierra el hueco de
trazabilidad "integración end-to-end PCAP" de la matriz (SWAL 2).

HLR cubiertos (integración): REQ-DEC-1/4 (decode CAT048/034) + REQ-GEO-1 (proyección)
+ REQ-TRK-2 (matching) + cadena de safety-nets, verificados juntos sobre datos reales.
"""
import os
import pytest

from tests.tracking.test_matching import app  # noqa: F401  (fixture QApplication)

# Fixture versionado en el repo (vendorizado con la extensión C). Determinista y
# pequeño (CAT034+CAT048 multi-sensor). No se copia un binario nuevo al árbol.
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
PCAP = os.path.join(_REPO_ROOT, "asterix_decoder-0.7.4", "asterix",
                    "sample_data", "cat_034_048.pcap")


@pytest.fixture(scope="module")
def scan():
    """Decodifica el PCAP una vez para todo el módulo. Retorna (plots, dur, sensores)."""
    if not os.path.exists(PCAP):
        pytest.skip("Falta el fixture cat_034_048.pcap")
    from decoder.data_engine import DataEngine
    eng = DataEngine(sensores={})
    return eng.scan_pcap(PCAP)


def _alimentar(widget, plots):
    """Fija la proyección en la posición del primer plot con lat/lon y alimenta
    todos los plots al widget en orden temporal, tal como lo haría el worker."""
    # Origen de proyección: primer plot posicionado
    origen = next((p for p in plots
                   if p.to_dict().get('lat') and p.to_dict().get('lon')), None)
    assert origen is not None, "El PCAP no tiene ningún plot con lat/lon"
    d0 = origen.to_dict()
    sac, sic = map(int, d0['sac_sic'].split('/'))
    widget.reset_origin_for_new_file(d0['lat'], d0['lon'], sac, sic, "TEST")

    batch = [p.to_dict() for p in sorted(plots, key=lambda p: p.time)]
    widget.on_new_plot_batch(batch)
    return batch


@pytest.fixture
def widget(app):
    from player.radar_widget import RadarWidget
    w = RadarWidget()
    w.sensores_visibles = None
    w.limpiar_pantalla()
    return w


# ── Decodificación ───────────────────────────────────────────────────────────

def test_scan_produce_plots(scan):
    plots, dur, sensores = scan
    assert len(plots) > 0, "El scan no produjo plots"
    cats = {p.category for p in plots}
    assert 48 in cats, "Se esperaban target reports CAT048"
    assert len(sensores) >= 1, "Se esperaba al menos un sensor detectado"


def test_scan_es_determinista(scan):
    """Mismo PCAP → misma cantidad de plots (reproducibilidad para verificación)."""
    from decoder.data_engine import DataEngine
    plots1, _, _ = scan
    eng2 = DataEngine(sensores={})
    plots2, _, _ = eng2.scan_pcap(PCAP)
    assert len(plots1) == len(plots2)


# ── Pipeline completo ────────────────────────────────────────────────────────

def test_pipeline_crea_tracks(widget, scan):
    plots, _, _ = scan
    _alimentar(widget, plots)
    assert widget.projection_set is True
    total = len(widget.tracks) + len(widget.pending_tracks)
    assert total > 0, "La cadena PCAP→widget no creó ningún track"


def test_pipeline_no_crashea_con_safety(widget, scan):
    """La cadena de safety-nets corre sobre datos reales sin excepción."""
    plots, _, _ = scan
    _alimentar(widget, plots)
    # _schedule_safety ya se disparó dentro de on_new_plot_batch; forzar directa
    widget.evaluar_stca()  # STCA → APW → MSAW encadenados
    # Si llegó acá sin excepción, la cadena es robusta con este tráfico.
    assert isinstance(getattr(widget, 'conflictos_activos', []), list)


def test_pipeline_determinista(app, scan):
    """Mismo PCAP alimentado dos veces → misma cantidad de tracks."""
    from player.radar_widget import RadarWidget
    plots, _, _ = scan

    def correr():
        w = RadarWidget()
        w.sensores_visibles = None
        w.limpiar_pantalla()
        _alimentar(w, plots)
        return len(w.tracks) + len(w.pending_tracks)

    assert correr() == correr()


def test_tracks_dentro_de_coordenadas_validas(widget, scan):
    """Todo track creado tiene coordenadas cartesianas finitas (proyección OK)."""
    from player.radar_widget import is_valid_coord
    plots, _, _ = scan
    _alimentar(widget, plots)
    for tid, t in list(widget.tracks.items()) + list(widget.pending_tracks.items()):
        assert is_valid_coord(t.x, t.y), f"Track {tid} con coords inválidas ({t.x},{t.y})"
