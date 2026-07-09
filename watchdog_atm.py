import os
import signal
import subprocess
import sys
import time
import logging
from logging.handlers import RotatingFileHandler

_handler = RotatingFileHandler(
    "watchdog_sys.log", maxBytes=5_000_000, backupCount=3, encoding="utf-8"
)
logging.basicConfig(
    handlers=[_handler],
    level=logging.INFO,
    format="%(asctime)s | WATCHDOG | %(levelname)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)


class ATMWatchdog:
    MAX_REINICIOS = 5
    BACKOFF_BASE  = 3.0
    # Segundos mínimos de uptime para considerar que el reinicio fue exitoso
    # y resetear el contador de fallos consecutivos.
    UPTIME_MINIMO = 10.0

    def __init__(self, comando: list[str]):
        self.comando    = comando
        self.ejecutando = True
        self._proceso: subprocess.Popen | None = None
        signal.signal(signal.SIGTERM, self._apagar)

    def _apagar(self, *_):
        logging.info("SIGTERM recibido — terminando proceso hijo y watchdog.")
        if self._proceso and self._proceso.poll() is None:
            self._proceso.terminate()
        self.ejecutando = False

    def _env(self) -> dict:
        e = os.environ.copy()
        e["PYTHONUTF8"]      = "1"
        e["QT_QPA_PLATFORM"] = "windows"
        return e

    def iniciar(self):
        logging.info("="*60)
        logging.info("Servicio Watchdog ATM iniciado.")
        logging.info(f"Comando supervisado: {' '.join(self.comando)}")
        print("[*] Watchdog ATM activado. Supervisando consola...")

        fallos_consecutivos = 0

        while self.ejecutando:
            try:
                t_inicio = time.monotonic()
                logging.info(f"Lanzando proceso principal: {' '.join(self.comando)}")

                self._proceso = subprocess.Popen(self.comando, env=self._env())
                self._proceso.wait()

                uptime = time.monotonic() - t_inicio
                codigo = self._proceso.returncode

                if codigo == 0:
                    logging.info(
                        f"Cierre normal detectado (exit code 0, uptime={uptime:.1f}s). "
                        "Apagando Watchdog."
                    )
                    print("[*] Consola ATM cerrada normalmente. Watchdog termina.")
                    self.ejecutando = False
                    break

                # Crash: código de salida distinto de 0
                if uptime >= self.UPTIME_MINIMO:
                    fallos_consecutivos = 0

                fallos_consecutivos += 1
                logging.critical(
                    f"CRASH DETECTADO — exit code={codigo}, "
                    f"uptime={uptime:.1f}s, fallo #{fallos_consecutivos}/{self.MAX_REINICIOS}"
                )

                if fallos_consecutivos >= self.MAX_REINICIOS:
                    logging.critical(
                        "Límite de reinicios consecutivos alcanzado. "
                        "Watchdog se detiene para evitar bucle infinito."
                    )
                    print("[!] Demasiados fallos consecutivos. Watchdog termina.")
                    self.ejecutando = False
                    break

                espera = self.BACKOFF_BASE * fallos_consecutivos
                logging.info(f"Reiniciando en {espera:.0f} segundos...")
                print(f"[!] Crash #{fallos_consecutivos}. Reintentando en {espera:.0f}s...")
                time.sleep(espera)

            except KeyboardInterrupt:
                logging.info("Interrupción manual (Ctrl+C). Watchdog termina.")
                if self._proceso and self._proceso.poll() is None:
                    self._proceso.terminate()
                self.ejecutando = False

            except Exception as e:
                logging.error(f"Error interno en el Watchdog: {e}", exc_info=True)
                time.sleep(self.BACKOFF_BASE)

        logging.info("Servicio Watchdog ATM detenido.")
        logging.info("="*60)


if __name__ == "__main__":
    # Desarrollo:   sys.executable + "main.py"
    # Producción:   ["System-ATM.exe"]
    # Para deshabilitar temporalmente: poner WATCHDOG_ENABLED = False
    WATCHDOG_ENABLED = True

    if not WATCHDOG_ENABLED:
        subprocess.run([sys.executable, "main.py"])
        sys.exit()

    comando_objetivo = [sys.executable, "main.py"]
    ATMWatchdog(comando=comando_objetivo).iniciar()
