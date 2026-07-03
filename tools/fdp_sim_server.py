"""Simulador de feed FDP: servidor TCP que emite tramas ADEXP de ejemplo.

Sirve para probar el FdpWorker sin un FDS real. Levanta un servidor en
127.0.0.1:4000 (por defecto) y, en cuanto la app se conecta, emite una
secuencia de tramas FPL/EST/CHG/CNL separadas por ETX (\\x03), con una pausa
configurable entre cada una.

Uso:
    python tools/fdp_sim_server.py                 # 127.0.0.1:4000, 2 s entre tramas
    python tools/fdp_sim_server.py --port 5000
    python tools/fdp_sim_server.py --delay 0.5 --loop
"""
import argparse
import socket
import time

ETX = b"\x03"

# Secuencia que ejercita las 4 operaciones del dispatcher.
# Los ARCID coinciden con callsigns reales de CAT062 en fds260429.pcap, para
# poder validar la correlación track↔plan en el diálogo de detalle del PPI.
TRAMAS = [
    "-TITLE FPL -ARCID ARG1273 -ADEP SAEZ -ADES SACO -ARCTYP B738 -WKTRC M "
    "-EOBT 1330 -RFL F350 -ROUTE N0450F350 DCT GENOA UW14 CBA",

    "-TITLE FPL -ARCID LAN491 -ADEP SCEL -ADES SAEZ -EQPT A320/M-SDE1FGHIRWY "
    "-EOBT 1345 -RFL F370 -ROUTE N0460F370 DCT MENDO UL776 EZE",

    "-TITLE FPL -ARCID TAM8049 -ADEP SBGR -ADES SAEZ -ARCTYP A320 -WKTRC M "
    "-EOBT 1310 -RFL F380 -ROUTE N0470F380 DCT FLABA UZ6 EZE",

    "-TITLE EST -ARCID ARG1273 -ADEP SAEZ -ADES SACO -COP GENOA -RFL F350",

    "-TITLE CHG -ARCID LAN491 -RFL F390",

    "-TITLE FPL -ARCID JES3107 -ADEP SAME -ADES SAEZ -ARCTYP E190 -WKTRC M "
    "-EOBT 1400 -RFL F360 -ROUTE N0440F360 DCT DORES",

    "-TITLE CNL -ARCID JES3107",
]


def servir(host: str, port: int, delay: float, loop: bool):
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((host, port))
    srv.listen(1)
    print(f"[FDP-SIM] Escuchando en {host}:{port} — esperando a la app…")

    try:
        while True:
            conn, addr = srv.accept()
            print(f"[FDP-SIM] Cliente conectado: {addr}")
            try:
                while True:
                    for raw in TRAMAS:
                        conn.sendall(raw.encode("ascii") + ETX)
                        title = raw.split()[1]
                        arcid = raw.split("-ARCID ")[1].split()[0]
                        print(f"[FDP-SIM] → {title:5} {arcid}")
                        time.sleep(delay)
                    if not loop:
                        print("[FDP-SIM] Secuencia completa. Cerrando cliente.")
                        break
            except (BrokenPipeError, ConnectionResetError):
                print("[FDP-SIM] Cliente desconectado.")
            finally:
                conn.close()
            if not loop:
                # Sigue aceptando nuevas conexiones igualmente.
                print("[FDP-SIM] Esperando próxima conexión…")
    except KeyboardInterrupt:
        print("\n[FDP-SIM] Detenido.")
    finally:
        srv.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=4000)
    ap.add_argument("--delay", type=float, default=2.0,
                    help="segundos entre tramas")
    ap.add_argument("--loop", action="store_true",
                    help="repetir la secuencia indefinidamente")
    args = ap.parse_args()
    servir(args.host, args.port, args.delay, args.loop)
