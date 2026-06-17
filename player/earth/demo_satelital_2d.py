"""
SPIKE (aislado) — Vista 2D cenital satelital con iconos de avion.

Objetivo: evaluar el ASPECTO antes de integrar a la app. No toca el radar real.
- Fondo: carga player/earth/assets/basemap.png (+ basemap.json con bounds) si
  existe; si no, genera un satelital PROCEDURAL de relleno.
- Trafico: aviones sinteticos que se mueven en tiempo real (QTimer).
- Cada avion: silueta orientada por proa + datablock (callsign / Fxxx GS / rumbo).

Correr:  python player/earth/demo_satelital_2d.py
"""
import json
import math
import os
import random
import sys

from PyQt6.QtCore import Qt, QTimer, QPointF, QRectF
from PyQt6.QtGui import (QPainter, QColor, QPen, QBrush, QFont, QPainterPath,
                         QPixmap, QPolygonF, QLinearGradient)
from PyQt6.QtWidgets import QApplication, QWidget

ASSETS = os.path.join(os.path.dirname(__file__), "assets")

# Bounding box por defecto del area (lat/lon). Si hay basemap.json, se sobreescribe.
DEFAULT_BOUNDS = {"lat_min": -25.30, "lat_max": -24.40,
                  "lon_min": -65.90, "lon_max": -65.00}


class Aircraft:
    def __init__(self, lat, lon, hdg, gs, fl, callsign):
        self.lat, self.lon = lat, lon
        self.hdg = hdg            # grados, 0=N horario
        self.gs = gs              # kt
        self.fl = fl              # nivel
        self.callsign = callsign
        self.vrate = random.choice([-1, 0, 0, 1])

    def step(self, dt_s):
        # distancia recorrida en grados (1 kt = 1 NM/h; 1 NM ~ 1/60 grado lat)
        nm = self.gs * (dt_s / 3600.0)
        dlat = nm / 60.0 * math.cos(math.radians(self.hdg))
        dlon = nm / 60.0 * math.sin(math.radians(self.hdg)) / max(0.2, math.cos(math.radians(self.lat)))
        self.lat += dlat
        self.lon += dlon
        self.fl = max(20, min(420, self.fl + self.vrate))


class Satelital2DDemo(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("SPIKE — Vista 2D satelital (aviones)")
        self.resize(1000, 760)
        self.bounds = dict(DEFAULT_BOUNDS)
        self._bg = None
        self._load_or_make_basemap()
        self.aircraft = self._spawn_traffic(14)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(100)  # 10 Hz

    # ---------- Basemap ----------
    def _load_or_make_basemap(self):
        png = os.path.join(ASSETS, "basemap.png")
        meta = os.path.join(ASSETS, "basemap.json")
        if os.path.exists(png) and os.path.exists(meta):
            try:
                with open(meta) as f:
                    self.bounds = json.load(f)
                self._bg = QPixmap(png)
                print(f"[demo] basemap real cargado: {png}")
                return
            except Exception as e:
                print(f"[demo] fallo basemap real ({e}); uso procedural")
        self._bg = self._make_procedural(1600, 1200)
        print("[demo] usando satelital PROCEDURAL (placeholder)")

    def _make_procedural(self, w, h):
        """Satelital de relleno: agua + masas de tierra + textura. Solo aspecto."""
        pm = QPixmap(w, h)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        # Agua
        grad = QLinearGradient(0, 0, 0, h)
        grad.setColorAt(0.0, QColor(28, 58, 74))
        grad.setColorAt(1.0, QColor(18, 42, 56))
        p.fillRect(0, 0, w, h, QBrush(grad))
        rnd = random.Random(7)
        # Masas de tierra
        for _ in range(5):
            cx, cy = rnd.uniform(0, w), rnd.uniform(0, h)
            poly = QPolygonF()
            n = rnd.randint(7, 12)
            r = rnd.uniform(180, 360)
            for k in range(n):
                a = 2 * math.pi * k / n
                rr = r * rnd.uniform(0.55, 1.2)
                poly.append(QPointF(cx + rr * math.cos(a), cy + rr * math.sin(a)))
            shade = rnd.randint(60, 95)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(shade - 10, shade + 20, shade - 25))
            p.drawPolygon(poly)
        # Textura/ruido suave
        for _ in range(2600):
            x, y = rnd.uniform(0, w), rnd.uniform(0, h)
            c = rnd.randint(0, 40)
            p.fillRect(int(x), int(y), 2, 2, QColor(c, c, c, 22))
        p.end()
        return pm

    # ---------- Trafico ----------
    def _spawn_traffic(self, n):
        b = self.bounds
        out = []
        carriers = ["KAL", "AAR", "JJA", "ANA", "CCA", "RPC", "CES", "ESR"]
        for _ in range(n):
            lat = random.uniform(b["lat_min"], b["lat_max"])
            lon = random.uniform(b["lon_min"], b["lon_max"])
            cs = f"{random.choice(carriers)}{random.randint(100,9999)}"
            out.append(Aircraft(lat, lon, random.uniform(0, 360),
                                random.uniform(180, 480),
                                random.randint(70, 410), cs))
        return out

    def _tick(self):
        b = self.bounds
        for ac in self.aircraft:
            ac.step(0.1 * 60)  # x60: acelerado para ver movimiento
            # rebote suave en los bordes
            if not (b["lat_min"] < ac.lat < b["lat_max"]) or not (b["lon_min"] < ac.lon < b["lon_max"]):
                ac.lat = min(max(ac.lat, b["lat_min"]), b["lat_max"])
                ac.lon = min(max(ac.lon, b["lon_min"]), b["lon_max"])
                ac.hdg = (ac.hdg + 137) % 360
        self.update()

    # ---------- Proyeccion plana ----------
    def _to_screen(self, lat, lon):
        b = self.bounds
        w, h = self.width(), self.height()
        x = (lon - b["lon_min"]) / (b["lon_max"] - b["lon_min"]) * w
        y = (b["lat_max"] - lat) / (b["lat_max"] - b["lat_min"]) * h  # norte arriba
        return QPointF(x, y)

    # ---------- Icono de avion ----------
    @staticmethod
    def _plane_path():
        """Silueta cenital apuntando al NORTE (proa = -y). Escala ~ +-9 px."""
        p = QPainterPath()
        p.moveTo(0, -9)            # morro
        p.lineTo(1.6, -3)
        p.lineTo(9, 1.5)           # ala derecha
        p.lineTo(9, 3)
        p.lineTo(1.6, 1)
        p.lineTo(1.4, 6)
        p.lineTo(4, 8.5)           # estabilizador derecho
        p.lineTo(4, 9.5)
        p.lineTo(0, 7.8)
        p.lineTo(-4, 9.5)
        p.lineTo(-4, 8.5)
        p.lineTo(-1.4, 6)
        p.lineTo(-1.6, 1)
        p.lineTo(-9, 3)
        p.lineTo(-9, 1.5)
        p.lineTo(-1.6, -3)
        p.closeSubpath()
        return p

    def paintEvent(self, _e):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        # Fondo satelital (escalado al widget, recortado a bounds)
        if self._bg is not None:
            painter.drawPixmap(self.rect(), self._bg)
        else:
            painter.fillRect(self.rect(), QColor(20, 40, 52))

        plane = self._plane_path()
        icon_col = QColor(120, 200, 255)
        font = QFont("Consolas", 8)
        painter.setFont(font)
        fm = painter.fontMetrics()

        for ac in self.aircraft:
            sp = self._to_screen(ac.lat, ac.lon)
            # Icono rotado por proa
            painter.save()
            painter.translate(sp)
            painter.rotate(ac.hdg)
            painter.setPen(QPen(QColor(10, 20, 30), 0.8))
            painter.setBrush(QBrush(icon_col))
            painter.drawPath(plane)
            painter.restore()
            # Datablock (callsign / Fxxx GS / rumbo) con leader corto
            arrow = "↑" if ac.vrate > 0 else ("↓" if ac.vrate < 0 else "=")
            lines = [ac.callsign,
                     f"F{int(ac.fl):03d}{arrow} {int(ac.gs):03d}",
                     f"{int(ac.hdg):03d}°"]
            lx, ly = sp.x() + 12, sp.y() - 10
            painter.setPen(QPen(QColor(30, 40, 50, 160)))
            painter.drawLine(sp, QPointF(lx, ly))
            for i, ln in enumerate(lines):
                ty = ly + i * (fm.height() - 2)
                # sombra para legibilidad sobre el satelital
                painter.setPen(QColor(0, 0, 0, 200))
                painter.drawText(QPointF(lx + 1, ty + 1), ln)
                painter.setPen(QColor(210, 235, 255))
                painter.drawText(QPointF(lx, ty), ln)

        # Pie
        painter.setPen(QColor(220, 230, 240))
        painter.setFont(QFont("Consolas", 8))
        modo = "BASEMAP REAL" if os.path.exists(os.path.join(ASSETS, "basemap.png")) else "SATELITAL PROCEDURAL (placeholder)"
        painter.drawText(10, self.height() - 10,
                         f"SPIKE 2D · {len(self.aircraft)} blancos · {modo} · "
                         f"bounds {self.bounds['lat_min']:.2f}..{self.bounds['lat_max']:.2f} / "
                         f"{self.bounds['lon_min']:.2f}..{self.bounds['lon_max']:.2f}")
        painter.end()


def main():
    app = QApplication(sys.argv)
    w = Satelital2DDemo()
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
