"""Escenario STCA de tráfico denso desde PCAP real (SSA-A4, refuerza SSR-07).

Alimenta el pipeline completo (decode → proyección → matching → tracks) con un
tramo real de `baires.pcap` (multi-sensor, tráfico denso) y verifica invariantes
de la evaluación STCA bajo carga:
  - la cadena completa corre sin excepción y en tiempo acotado;
  - ningún conflicto es consigo mismo ni duplicado de par;
  - todo id reportado corresponde a un track existente;
  - los estados son únicamente VIOLATION/PREDICTION.

Se salta si `baires.pcap` no está (igual criterio que los tests de atm.duckdb).
El PCAP se trunca por registros (formato pcap clásico) para acotar el costo.
"""
import os
import struct
import time as _wall
import pytest

from tests.tracking.test_matching import app  # noqa: F401

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
BAIRES = os.path.join(_REPO_ROOT, "baires.pcap")

_CI = bool(os.environ.get("CI") or os.environ.get("GITHUB_ACTIONS"))
_F = 5.0 if _CI else 1.0            # holgura para runners lentos (patrón de test_perf)
MAX_PAQUETES = 30_000               # tramo denso pero acotado (~3 MB de 28.5 MB)


def _truncar_pcap(origen, destino, max_paquetes):
    """Copia el header global (24 B) y los primeros N registros del pcap clásico."""
    with open(origen, "rb") as f, open(destino, "wb") as out:
        header = f.read(24)
        magic = header[:4]
        assert magic in (b"\xd4\xc3\xb2\xa1", b"\xa1\xb2\xc3\xd4"), "No es pcap clásico"
        endian = "<" if magic == b"\xd4\xc3\xb2\xa1" else ">"
        out.write(header)
        for _ in range(max_paquetes):
            rec = f.read(16)
            if len(rec) < 16:
                break
            incl_len = struct.unpack(endian + "I", rec[8:12])[0]
            datos = f.read(incl_len)
            if len(datos) < incl_len:
                break
            out.write(rec)
            out.write(datos)


@pytest.fixture(scope="module")
def scan(tmp_path_factory):
    if not os.path.exists(BAIRES):
        pytest.skip("Falta baires.pcap (fixture de tráfico denso, no versionado)")
    recorte = str(tmp_path_factory.mktemp("denso") / "baires_head.pcap")
    _truncar_pcap(BAIRES, recorte, MAX_PAQUETES)
    from decoder.data_engine import DataEngine
    eng = DataEngine(sensores={})
    return eng.scan_pcap(recorte)


@pytest.fixture
def widget(app, scan):
    from player.radar_widget import RadarWidget
    w = RadarWidget()
    w.sensores_visibles = None
    w.limpiar_pantalla()
    plots, _, _ = scan
    origen = next((p for p in plots
                   if p.to_dict().get("lat") and p.to_dict().get("lon")), None)
    assert origen is not None
    d0 = origen.to_dict()
    sac, sic = map(int, d0["sac_sic"].split("/"))
    w.reset_origin_for_new_file(d0["lat"], d0["lon"], sac, sic, "DENSO")
    w.on_new_plot_batch([p.to_dict() for p in sorted(plots, key=lambda p: p.time)])
    return w


def test_trafico_es_realmente_denso(scan, widget):
    """Precondición del escenario: multi-sensor y decenas de tracks simultáneos."""
    plots, _, sensores = scan
    assert len(plots) > 5_000, f"Tramo poco denso: {len(plots)} plots"
    assert len(sensores) >= 2, "Se esperaba tráfico multi-sensor"
    total = len(widget.tracks) + len(widget.pending_tracks)
    assert total >= 30, f"Pocos tracks para escenario denso: {total}"


def test_stca_bajo_carga_invariantes(widget):
    """SSR-07 bajo carga: la evaluación termina, en tiempo acotado y coherente."""
    t0 = _wall.monotonic()
    widget.evaluar_stca()                     # STCA → APW → MSAW encadenados
    dur = _wall.monotonic() - t0
    assert dur < 5.0 * _F, f"Cadena safety tardó {dur:.1f}s bajo carga"

    conflictos = widget.conflictos_activos
    assert isinstance(conflictos, list)
    vistos = set()
    ids_validos = set(widget.tracks) | set(widget.pending_tracks)
    for t1, t2, estado, tiempo in conflictos:
        assert t1 != t2, f"Conflicto consigo mismo: {t1}"
        par = frozenset((t1, t2))
        assert par not in vistos, f"Par duplicado en la salida: {t1}/{t2}"
        vistos.add(par)
        assert estado in ("VIOLATION", "PREDICTION"), f"Estado inesperado: {estado}"
        assert t1 in ids_validos and t2 in ids_validos, \
            f"Conflicto referencia track inexistente: {t1}/{t2}"


def test_stca_bajo_carga_es_reproducible(widget):
    """Dos evaluaciones consecutivas sobre el mismo estado → mismos conflictos."""
    widget.evaluar_stca()
    primera = sorted((tuple(sorted((a, b))), e) for a, b, e, _ in widget.conflictos_activos)
    widget.evaluar_stca()
    segunda = sorted((tuple(sorted((a, b))), e) for a, b, e, _ in widget.conflictos_activos)
    assert primera == segunda
