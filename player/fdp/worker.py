"""FdpWorker — QThread que recibe tramas ADEXP por TCP y las persiste.

Independiente de PlaybackWorker (TCP FDP vs. UDP ASTERIX). Abre su propia
conexión DuckDB dentro de run() (las conexiones DuckDB no se comparten entre
hilos) y delega cada trama al FdpDispatcher.

Reconexión automática con backoff exponencial: la FD_LAN puede tirar la
conexión. Los mensajes ADEXP pueden llegar fragmentados en varios recv() o
varios concatenados en uno; el buffer se separa por delimitador (ETX por
defecto, configurable).
"""
import socket
from typing import List, Tuple

from PyQt6.QtCore import QThread, pyqtSignal

from decoder.adexp_parser import parsear_trama


# Delimitador de fin de mensaje por defecto: ETX (AFTN/AMHS).
DELIM_DEFECTO = b"\x03"

_BACKOFF_INICIAL = 1.0
_BACKOFF_MAX     = 30.0


def extraer_mensajes(buffer: bytes, delim: bytes) -> Tuple[List[bytes], bytes]:
    """Separa `buffer` en mensajes completos por `delim`.

    Función pura (sin Qt ni sockets) para poder testear el manejo de
    fragmentación. Devuelve (mensajes_completos, resto_sin_delimitar).
    """
    if delim not in buffer:
        return [], buffer
    partes = buffer.split(delim)
    resto = partes.pop()          # lo que viene tras el último delimitador
    mensajes = [p for p in partes if p.strip()]
    return mensajes, resto


class FdpWorker(QThread):
    """Cliente TCP que recibe ADEXP, parsea y persiste en fdp.duckdb."""

    mensaje_procesado = pyqtSignal(str, str)   # (tipo, arcid)
    error_conexion    = pyqtSignal(str)
    conectado         = pyqtSignal(bool)       # True al conectar, False al caer

    def __init__(self, host: str, port: int, db_path: str,
                 delimiter: bytes = DELIM_DEFECTO, parent=None):
        super().__init__(parent)
        self.host = host
        self.port = port
        self.db_path = db_path
        self.delimiter = delimiter
        self._running = True
        self._sock = None

    def stop(self):
        """Detiene el loop y cierra el socket de forma segura."""
        self._running = False
        s = self._sock
        if s is not None:
            try:
                s.shutdown(socket.SHUT_RDWR)
            except Exception:
                pass
            try:
                s.close()
            except Exception:
                pass

    def run(self):
        import duckdb
        from player.fdp.dispatcher import FdpDispatcher

        conn = duckdb.connect(self.db_path)
        dispatcher = FdpDispatcher(conn)
        backoff = _BACKOFF_INICIAL

        try:
            while self._running:
                try:
                    self._sock = socket.create_connection(
                        (self.host, self.port), timeout=5.0)
                    self._sock.settimeout(1.0)
                    self.conectado.emit(True)
                    backoff = _BACKOFF_INICIAL
                    self._recv_loop(dispatcher)
                    self.conectado.emit(False)
                except OSError as e:
                    if not self._running:
                        break
                    self.error_conexion.emit(f"{self.host}:{self.port} — {e}")
                    # Backoff antes de reintentar (interrumpible)
                    self._dormir_interrumpible(backoff)
                    backoff = min(backoff * 2, _BACKOFF_MAX)
                finally:
                    if self._sock is not None:
                        try:
                            self._sock.close()
                        except Exception:
                            pass
                        self._sock = None
        finally:
            try:
                conn.close()
            except Exception:
                pass

    # ------------------------------------------------------------------
    def _recv_loop(self, dispatcher):
        """Recibe del socket hasta que se cierre o se detenga el worker."""
        buffer = b""
        while self._running:
            try:
                chunk = self._sock.recv(4096)
            except socket.timeout:
                continue
            except OSError:
                break
            if not chunk:
                break   # peer cerró la conexión → reconectar
            buffer += chunk
            mensajes, buffer = extraer_mensajes(buffer, self.delimiter)
            for raw_bytes in mensajes:
                self._despachar(dispatcher, raw_bytes)

    def _despachar(self, dispatcher, raw_bytes: bytes):
        try:
            raw = raw_bytes.decode("ascii", errors="replace").strip()
            data = parsear_trama(raw)
            dispatcher.procesar(data, raw)
            self.mensaje_procesado.emit(
                data.get("TITLE", ""), data.get("ARCID", ""))
        except Exception as e:
            self.error_conexion.emit(f"Error procesando trama: {e}")

    def _dormir_interrumpible(self, segundos: float):
        """Duerme en tramos cortos para poder abortar rápido al hacer stop()."""
        restante = segundos
        while restante > 0 and self._running:
            paso = min(0.2, restante)
            self.msleep(int(paso * 1000))
            restante -= paso
