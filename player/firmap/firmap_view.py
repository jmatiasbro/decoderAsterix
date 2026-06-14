"""Widget slippy-map 2D (WebMercator) que lee tiles de un MBTiles offline.

Pan (arrastre), zoom (rueda). Si no hay MBTiles o falta el tile, dibuja un
placeholder. Pure-Qt, sin deps externas. La capa de tráfico se dibuja encima
sobreescribiendo `draw_overlay`.
"""
import math
import os

from PyQt6.QtCore import Qt, QPointF
from PyQt6.QtGui import QPainter, QColor, QPixmap, QFont
from PyQt6.QtWidgets import QWidget

from player.firmap import webmercator as wm
from player.firmap.mbtiles import MBTilesReader

TILE = wm.TILE_SIZE


class FirMapView(QWidget):
    def __init__(self, mbtiles_path: str = None, parent=None):
        super().__init__(parent)
        self.setMinimumSize(640, 480)
        self.setMouseTracking(True)
        # Centro inicial: Argentina aprox.
        self.center_lon = -64.0
        self.center_lat = -38.0
        self.zoom = 5
        self.min_zoom, self.max_zoom = 3, 16
        self._reader = None
        self._cache = {}            # (z,x,y) -> QPixmap | None
        self._drag_last = None
        self._attribution = ""
        self.tracks = []            # lista de dicts (ver traffic.draw_traffic)
        if mbtiles_path and os.path.exists(mbtiles_path):
            self._open(mbtiles_path)

    def _open(self, path):
        self._reader = MBTilesReader(path)
        meta = self._reader.metadata()
        self._attribution = meta.get("attribution", "")
        try:
            self.min_zoom = int(meta.get("minzoom", self.min_zoom))
            self.max_zoom = int(meta.get("maxzoom", self.max_zoom))
        except (TypeError, ValueError):
            pass

    # ---------- API ----------
    def set_center(self, lon, lat):
        self.center_lon, self.center_lat = lon, lat
        self.update()

    def set_zoom(self, z):
        self.zoom = max(self.min_zoom, min(self.max_zoom, int(z)))
        self.update()

    def set_tracks(self, tracks):
        """Reemplaza el set de tráfico a dibujar (lista de dicts) y repinta."""
        self.tracks = tracks or []
        self.update()

    # ---------- Tiles ----------
    def _tile_pixmap(self, z, x, y):
        key = (z, x, y)
        if key in self._cache:
            return self._cache[key]
        pm = None
        if self._reader is not None:
            data = self._reader.get_tile(z, x, y)
            if data:
                pm = QPixmap()
                if not pm.loadFromData(data):
                    pm = None
        self._cache[key] = pm
        return pm

    def _lonlat_to_screen(self, lon, lat):
        cpx, cpy = wm.lonlat_to_pixel(self.center_lon, self.center_lat, self.zoom)
        px, py = wm.lonlat_to_pixel(lon, lat, self.zoom)
        return QPointF(px - cpx + self.width() / 2.0, py - cpy + self.height() / 2.0)

    # ---------- Pintado ----------
    def paintEvent(self, _e):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(16, 24, 32))
        w, h = self.width(), self.height()
        z = self.zoom
        cpx, cpy = wm.lonlat_to_pixel(self.center_lon, self.center_lat, z)
        # esquina superior-izquierda del viewport en pixel global
        ox = cpx - w / 2.0
        oy = cpy - h / 2.0
        n = int(2 ** z)
        x0 = int(math.floor(ox / TILE))
        y0 = int(math.floor(oy / TILE))
        x1 = int(math.floor((ox + w) / TILE))
        y1 = int(math.floor((oy + h) / TILE))
        any_tile = False
        for tx in range(x0, x1 + 1):
            for ty in range(y0, y1 + 1):
                if not (0 <= tx < n and 0 <= ty < n):
                    continue
                sx = tx * TILE - ox
                sy = ty * TILE - oy
                pm = self._tile_pixmap(z, tx % n, ty)
                if pm is not None:
                    p.drawPixmap(int(sx), int(sy), pm)
                    any_tile = True
                else:
                    p.fillRect(int(sx), int(sy), TILE, TILE, QColor(22, 32, 42))
                    p.setPen(QColor(40, 54, 66))
                    p.drawRect(int(sx), int(sy), TILE, TILE)

        if not any_tile:
            p.setPen(QColor(150, 165, 180))
            p.setFont(QFont("Consolas", 10))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter,
                       "Sin tiles. Corré tools/seed_tiles.py para sembrar el MBTiles.")

        self.draw_overlay(p)

        if self._attribution:
            p.setFont(QFont("Consolas", 7))
            txt = self._attribution
            fm = p.fontMetrics()
            tw = fm.horizontalAdvance(txt)
            p.fillRect(w - tw - 8, h - fm.height() - 2, tw + 8, fm.height() + 2,
                       QColor(0, 0, 0, 120))
            p.setPen(QColor(210, 220, 230))
            p.drawText(w - tw - 4, h - 4, txt)
        p.end()

    def draw_overlay(self, painter: QPainter):
        """Dibuja el tráfico sobre el mapa."""
        if self.tracks:
            from player.firmap import traffic as _t
            _t.draw_traffic(painter, self, self.tracks)

    # ---------- Interacción ----------
    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._drag_last = e.position()

    def mouseMoveEvent(self, e):
        if self._drag_last is not None:
            d = e.position() - self._drag_last
            self._drag_last = e.position()
            cpx, cpy = wm.lonlat_to_pixel(self.center_lon, self.center_lat, self.zoom)
            self.center_lon, self.center_lat = wm.pixel_to_lonlat(
                cpx - d.x(), cpy - d.y(), self.zoom)
            self.update()

    def mouseReleaseEvent(self, _e):
        self._drag_last = None

    def wheelEvent(self, e):
        self.set_zoom(self.zoom + (1 if e.angleDelta().y() > 0 else -1))


if __name__ == "__main__":
    import sys
    from PyQt6.QtWidgets import QApplication
    path = sys.argv[1] if len(sys.argv) > 1 else "data/firmap/argentina.mbtiles"
    app = QApplication(sys.argv)
    v = FirMapView(path)
    v.setWindowTitle("FIR map (slippy) — Sentinel-2 cloudless")
    v.resize(1000, 740)
    v.show()
    sys.exit(app.exec())
