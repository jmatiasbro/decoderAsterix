"""Demo F3: tráfico sintético en movimiento sobre la vista FIR satelital.

Correr:  python player/firmap/demo_firmap_traffic.py [ruta.mbtiles]
Si no se pasa mbtiles (o no existe), el mapa va con placeholder igual.
"""
import math
import os
import random
import sys

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication

from player.firmap.firmap_view import FirMapView

CARRIERS = ["ARG", "AEP", "LAN", "AUT", "AND", "GLO", "AZU", "BAW"]
COLORS = {"sys": (208, 216, 208), "ssr": (150, 200, 160), "adsb": (150, 190, 210)}


class Plane:
    def __init__(self, lat, lon):
        self.lat, self.lon = lat, lon
        self.hdg = random.uniform(0, 360)
        self.gs = random.uniform(220, 480)
        self.fl = random.randint(180, 400)
        self.vrate = random.choice([-1, 0, 0, 1])
        self.cs = f"{random.choice(CARRIERS)}{random.randint(100, 9999)}"
        self.estado = random.choice(list(COLORS))

    def step(self, dt_s):
        nm = self.gs * (dt_s / 3600.0)
        self.lat += nm / 60.0 * math.cos(math.radians(self.hdg))
        self.lon += nm / 60.0 * math.sin(math.radians(self.hdg)) / max(0.2, math.cos(math.radians(self.lat)))
        self.fl = max(50, min(420, self.fl + self.vrate))


class Demo(FirMapView):
    def __init__(self, mbtiles):
        super().__init__(mbtiles)
        self.set_center(-64.0, -38.0)
        self.set_zoom(5)
        self.planes = [Plane(random.uniform(-52, -24), random.uniform(-71, -56))
                       for _ in range(40)]
        self.selected_idx = 0
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(100)

    def _tick(self):
        tracks = []
        for i, pl in enumerate(self.planes):
            pl.step(0.1 * 60)  # x60 acelerado
            if not (-56 < pl.lat < -20 and -74 < pl.lon < -52):
                pl.hdg = (pl.hdg + 150) % 360
            arrow = "↑" if pl.vrate > 0 else ("↓" if pl.vrate < 0 else "=")
            tracks.append({
                "lat": pl.lat, "lon": pl.lon, "heading": pl.hdg,
                "color": COLORS[pl.estado],
                "selected": (i == self.selected_idx),
                "lines": [pl.cs, f"F{int(pl.fl):03d}{arrow} {int(pl.gs):03d}",
                          f"{int(pl.hdg):03d}°"],
            })
        self.set_tracks(tracks)


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else "data/firmap/argentina.mbtiles"
    if not os.path.exists(path):
        alt = "data/firmap/_test_lowzoom.mbtiles"
        if os.path.exists(alt):
            path = alt
    app = QApplication(sys.argv)
    w = Demo(path)
    w.setWindowTitle("Demo F3 — Vista FIR satelital con tráfico")
    w.resize(1000, 760)
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
