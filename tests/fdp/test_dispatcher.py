"""Tests de integración FdpDispatcher con DuckDB en memoria."""
import duckdb
import pytest
from pathlib import Path

from decoder.adexp_parser import parsear_trama
from player.fdp.dispatcher import FdpDispatcher

SCHEMA = (Path(__file__).resolve().parent.parent.parent
          / "data" / "fdp" / "fdp_schema.sql")


@pytest.fixture
def disp():
    conn = duckdb.connect(":memory:")
    conn.execute(SCHEMA.read_text(encoding="utf-8"))
    yield FdpDispatcher(conn)
    conn.close()


def _fila(disp, arcid):
    return disp.conn.execute(
        "SELECT arcid, adep, ades, aircraft_type, wtc, requested_fl, "
        "route, eobt, cop, status FROM flight_plans WHERE arcid = ?",
        [arcid]).fetchone()


# ---------------------------------------------------------------------------
# FPL / upsert
# ---------------------------------------------------------------------------

def test_fpl_crea_plan(disp):
    raw = ("-TITLE FPL -ARCID KIM1 -ADEP EDDF -ADES LGTS -ARCTYP B738 "
           "-WKTRC M -EOBT 0715 -RFL F330 -ROUTE N0417F330 ANEKI DCT EDASI")
    accion = disp.procesar(parsear_trama(raw), raw)
    assert accion == "UPSERTED"

    f = _fila(disp, "KIM1")
    assert f[0] == "KIM1"
    assert f[1] == "EDDF"
    assert f[2] == "LGTS"
    assert f[3] == "B738"
    assert f[4] == "M"
    assert f[5] == "F330"
    assert f[9] == "ACTIVE"


def test_fpl_guarda_raw(disp):
    raw = "-TITLE FPL -ARCID IBE9 -ADEP LEMD -ADES LEBL"
    disp.procesar(parsear_trama(raw), raw)
    rm = disp.conn.execute(
        "SELECT raw_msg FROM flight_plans WHERE arcid = ?", ["IBE9"]).fetchone()
    assert rm[0] == raw


def test_est_upsert(disp):
    raw = "-TITLE EST -ARCID AMC101 -ADEP EGLL -ADES LMML -COP BNE -RFL F350"
    accion = disp.procesar(parsear_trama(raw), raw)
    assert accion == "UPSERTED"
    f = _fila(disp, "AMC101")
    assert f[8] == "BNE"   # cop


def test_upsert_preserva_campos_previos(disp):
    """Un segundo mensaje con menos campos no debe borrar los anteriores."""
    raw1 = "-TITLE FPL -ARCID KIM1 -ADEP EDDF -ADES LGTS -ARCTYP B738 -RFL F330"
    disp.procesar(parsear_trama(raw1), raw1)
    raw2 = "-TITLE EST -ARCID KIM1 -COP NATOR"
    disp.procesar(parsear_trama(raw2), raw2)

    f = _fila(disp, "KIM1")
    assert f[1] == "EDDF"   # adep preservado
    assert f[3] == "B738"   # aircraft_type preservado
    assert f[8] == "NATOR"  # cop nuevo

# ---------------------------------------------------------------------------
# CHG
# ---------------------------------------------------------------------------

def test_chg_actualiza_solo_presentes(disp):
    raw1 = "-TITLE FPL -ARCID KIM1 -ADEP EDDF -ADES LGTS -RFL F330"
    disp.procesar(parsear_trama(raw1), raw1)

    raw2 = "-TITLE CHG -ARCID KIM1 -RFL F350"
    accion = disp.procesar(parsear_trama(raw2), raw2)
    assert accion == "UPDATED"

    f = _fila(disp, "KIM1")
    assert f[5] == "F350"   # rfl cambiado
    assert f[1] == "EDDF"   # adep intacto
    assert f[2] == "LGTS"   # ades intacto


def test_chg_sobre_inexistente_no_crea(disp):
    raw = "-TITLE CHG -ARCID NOPE1 -RFL F350"
    disp.procesar(parsear_trama(raw), raw)
    assert _fila(disp, "NOPE1") is None

# ---------------------------------------------------------------------------
# CNL
# ---------------------------------------------------------------------------

def test_cnl_marca_cancelado(disp):
    raw1 = "-TITLE FPL -ARCID KIM1 -ADEP EDDF -ADES LGTS"
    disp.procesar(parsear_trama(raw1), raw1)

    raw2 = "-TITLE CNL -ARCID KIM1"
    accion = disp.procesar(parsear_trama(raw2), raw2)
    assert accion == "CANCELLED"

    f = _fila(disp, "KIM1")
    assert f[9] == "CANCELLED"

# ---------------------------------------------------------------------------
# Log y casos borde
# ---------------------------------------------------------------------------

def test_log_registra_todos_los_mensajes(disp):
    for raw in ["-TITLE FPL -ARCID A1 -ADEP X",
                "-TITLE CHG -ARCID A1 -RFL F100",
                "-TITLE CNL -ARCID A1"]:
        disp.procesar(parsear_trama(raw), raw)
    n = disp.conn.execute("SELECT count(*) FROM fdp_log").fetchone()[0]
    assert n == 3


def test_sin_arcid_se_loguea_pero_no_crea_plan(disp):
    raw = "-TITLE FPL -ADEP EDDF -ADES LGTS"
    accion = disp.procesar(parsear_trama(raw), raw)
    assert accion == "IGNORED_NO_ARCID"
    n = disp.conn.execute("SELECT count(*) FROM flight_plans").fetchone()[0]
    assert n == 0
    n_log = disp.conn.execute("SELECT count(*) FROM fdp_log").fetchone()[0]
    assert n_log == 1


def test_titulo_desconocido_ignora_plan(disp):
    raw = "-TITLE FOOBAR -ARCID A1 -ADEP X"
    accion = disp.procesar(parsear_trama(raw), raw)
    assert accion == "IGNORED_UNKNOWN_TITLE"
    assert _fila(disp, "A1") is None
