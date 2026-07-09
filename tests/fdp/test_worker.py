"""Tests de FdpWorker: extracción de mensajes (pura) e integración TCP."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import socket
import threading
import tempfile
from pathlib import Path

import duckdb
import pytest

from player.fdp.worker import extraer_mensajes, FdpWorker, DELIM_DEFECTO

SCHEMA = (Path(__file__).resolve().parent.parent.parent
          / "data" / "fdp" / "fdp_schema.sql")

ETX = b"\x03"

# ---------------------------------------------------------------------------
# extraer_mensajes — función pura (sin Qt)
# ---------------------------------------------------------------------------

def test_un_mensaje_completo():
    msgs, resto = extraer_mensajes(b"-TITLE FPL -ARCID A1" + ETX, ETX)
    assert msgs == [b"-TITLE FPL -ARCID A1"]
    assert resto == b""


def test_varios_mensajes_concatenados():
    buf = b"MSG1" + ETX + b"MSG2" + ETX + b"MSG3" + ETX
    msgs, resto = extraer_mensajes(buf, ETX)
    assert msgs == [b"MSG1", b"MSG2", b"MSG3"]
    assert resto == b""


def test_mensaje_fragmentado_deja_resto():
    buf = b"MSG1" + ETX + b"PARCI"
    msgs, resto = extraer_mensajes(buf, ETX)
    assert msgs == [b"MSG1"]
    assert resto == b"PARCI"


def test_sin_delimitador_todo_es_resto():
    msgs, resto = extraer_mensajes(b"INCOMPLETO", ETX)
    assert msgs == []
    assert resto == b"INCOMPLETO"


def test_descarta_fragmentos_vacios():
    buf = ETX + b"MSG1" + ETX + ETX
    msgs, resto = extraer_mensajes(buf, ETX)
    assert msgs == [b"MSG1"]
    assert resto == b""

# ---------------------------------------------------------------------------
# Integración TCP en loopback
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def qapp():
    pytest.importorskip("PyQt6.QtWidgets")
    from PyQt6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def _servidor_que_envia(tramas: bytes):
    """Levanta un server TCP efímero que al conectarse envía `tramas` y cierra.

    Devuelve (port, thread). El thread termina solo tras atender 1 cliente.
    """
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    port = srv.getsockname()[1]

    def _run():
        try:
            conn, _ = srv.accept()
            conn.sendall(tramas)
            conn.close()
        finally:
            srv.close()

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    return port, t


def test_worker_recibe_y_persiste(qapp):
    from PyQt6.QtCore import QEventLoop, QTimer

    raw = b"-TITLE FPL -ARCID KIM1 -ADEP EDDF -ADES LGTS -ARCTYP B738 -RFL F330"
    port, _ = _servidor_que_envia(raw + DELIM_DEFECTO)

    db_path = tempfile.mktemp(suffix=".duckdb")
    duckdb.connect(db_path).execute(SCHEMA.read_text(encoding="utf-8")).close()

    worker = FdpWorker("127.0.0.1", port, db_path)

    recibidos = []
    loop = QEventLoop()
    worker.mensaje_procesado.connect(lambda t, a: (recibidos.append((t, a)), loop.quit()))

    timeout = QTimer()
    timeout.setSingleShot(True)
    timeout.timeout.connect(loop.quit)
    timeout.start(5000)

    worker.start()
    loop.exec()

    worker.stop()
    worker.wait(3000)

    assert recibidos, "no se recibió ninguna señal mensaje_procesado"
    assert recibidos[0] == ("FPL", "KIM1")

    # Verificar persistencia
    conn = duckdb.connect(db_path)
    fila = conn.execute(
        "SELECT arcid, adep, ades, requested_fl, status "
        "FROM flight_plans WHERE arcid = ?", ["KIM1"]).fetchone()
    conn.close()
    assert fila == ("KIM1", "EDDF", "LGTS", "F330", "ACTIVE")
