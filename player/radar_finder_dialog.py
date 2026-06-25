"""Finder táctico de consola: ventana flotante no-modal sobre el PPI.

Busca pistas vivas (Callsign / SSR Mode 3-A) o elementos fijos de la base ATM
offline (Aeropuertos ICAO, Fixes/Waypoints) o coordenadas "lat,lon", centra la
vista del RadarWidget en el objetivo y dispara un marcador de mira parpadeante.

API real respetada:
- tracks vivos: RadarWidget.tracks: Dict[str, RadarPlot] (.callsign, .mode3a,
  .raw_dict['lat'/'lon']).
- base geográfica: player.atm_db.airports() / fixes().
- centrado no destructivo: RadarWidget.centrar_en_coordenadas(lat, lon).
"""
import re

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLineEdit, QPushButton, QLabel, QMessageBox,
)
from PyQt6.QtCore import Qt, pyqtSignal

from player import atm_db


class RadarFinderDialog(QDialog):
    # lat, lon, tipo ("COORD" | "FIXED" | "AIRCRAFT"), identificador
    target_located = pyqtSignal(float, float, str, str)

    def __init__(self, radar_widget, parent=None):
        super().__init__(parent)
        self.radar = radar_widget
        self._geo_index = self._build_geo_index()

        self.setWindowFlags(Qt.WindowType.Tool | Qt.WindowType.WindowStaysOnTopHint)
        self.setWindowTitle("Finder Táctico de Consola")
        self.resize(380, 110)
        self._init_ui()

    # ---- Índice geográfico offline (una sola vez) ----
    def _build_geo_index(self):
        """{NOMBRE_UPPER: (lat, lon, tipo)} desde aeropuertos + fixes de la base ATM."""
        idx = {}
        try:
            for icao, d in atm_db.airports().items():
                idx[icao.upper()] = (d["lat"], d["lon"], "APTO")
            for f in atm_db.fixes():
                idx.setdefault(f["name"].upper(), (f["lat"], f["lon"], "FIX"))
        except Exception:
            pass
        return idx

    # ---- UI ----
    def _init_ui(self):
        self.setStyleSheet("background-color: #0a0f18; color: #ffffff; font-family: 'Consolas';")
        layout = QVBoxLayout(self)

        lbl_info = QLabel("BUSCAR POR: CALLSIGN | SSR | WAYPOINT | APTO | LAT,LON")
        lbl_info.setStyleSheet("color: #8fa0bc; font-size: 9px; font-weight: bold;")
        layout.addWidget(lbl_info)

        row = QHBoxLayout()
        self.txt_search = QLineEdit()
        self.txt_search.setPlaceholderText("Ej: ARG1340, 4321, DILOM, SACO, -31.4,-64.2, 312436S 0641048W")
        self.txt_search.setStyleSheet(
            "QLineEdit { background-color: #101724; border: 1px solid #23334d; "
            "border-radius: 4px; padding: 6px; color: #00ff66; font-size: 12px; "
            "font-weight: bold; }")
        self.txt_search.returnPressed.connect(self.ejecutar_busqueda_finder)
        row.addWidget(self.txt_search)

        btn_find = QPushButton("🔍 LOCALIZAR")
        btn_find.setStyleSheet(
            "QPushButton { background-color: #162338; border: 1px solid #2d456e; "
            "border-radius: 4px; padding: 6px 12px; font-weight: bold; }"
            "QPushButton:hover { background-color: #213454; border-color: #00ff66; }")
        btn_find.clicked.connect(self.ejecutar_busqueda_finder)
        row.addWidget(btn_find)
        layout.addLayout(row)

    # ---- Parseo de coordenadas ----
    @staticmethod
    def _one_dms(num, hemi):
        """Un valor DMS -> grados decimales (con signo según hemisferio).
        Admite componentes separados ('31 24 36') y formato AIP empacado ('0640721')."""
        num = num.strip()
        parts = num.split()
        if len(parts) >= 2:                       # D M [S] separados por espacio
            try:
                d = float(parts[0])
                m = float(parts[1]) if len(parts) > 1 else 0.0
                s = float(parts[2]) if len(parts) > 2 else 0.0
            except ValueError:
                return None
            val = d + m / 60.0 + s / 3600.0
            return -val if hemi in ("S", "W") else val
        # Empacado AIP (DDMMSS / DDDMMSS, con segundos decimales opcionales)
        packed = num.replace(" ", "") + hemi
        v = atm_db._dms_dot_to_dd(packed) if "." in num else atm_db.parse_dms(packed)
        return v if v is not None else atm_db.parse_dms(packed)

    def _parse_coords(self, q):
        """Devuelve (lat, lon) desde decimal 'lat,lon' o DMS con hemisferio, o None."""
        # 1) Decimal con coma: "-31.41,-64.18"
        if "," in q and not re.search(r"[NSEW]", q):
            try:
                lat, lon = (float(p) for p in q.split(",", 1))
                if abs(lat) <= 90.0 and abs(lon) <= 180.0:
                    return lat, lon
            except ValueError:
                pass
        # 2) DMS con sufijo de hemisferio (admite espacios, coma y seg. decimales)
        toks = re.findall(r"([\d\s.]+?)\s*([NSEW])", q)
        if len(toks) == 2:
            vals = {h: self._one_dms(n, h) for n, h in toks}
            lat = next((v for h, v in vals.items() if h in ("N", "S")), None)
            lon = next((v for h, v in vals.items() if h in ("E", "W")), None)
            if (lat is not None and lon is not None
                    and abs(lat) <= 90.0 and abs(lon) <= 180.0):
                return lat, lon
        return None

    # ---- Lógica de búsqueda ----
    def ejecutar_busqueda_finder(self):
        query = self.txt_search.text().strip().upper()
        if not query:
            return

        # A) Coordenadas (decimal o DMS)
        coords = self._parse_coords(query)
        if coords:
            lat, lon = coords
            self.target_located.emit(lat, lon, "COORD", f"{lat:.4f},{lon:.4f}")
            return

        # B) Base ATM offline (aeropuerto / fix)
        hit = self._geo_index.get(query)
        if hit:
            self.target_located.emit(float(hit[0]), float(hit[1]), "FIXED",
                                     f"{hit[2]} {query}")
            return

        # C) Tránsito vivo: callsign o SSR (mode3a) en RadarWidget.tracks
        for t in self.radar.tracks.values():
            cs = (t.callsign or "").upper()
            ssr = (t.mode3a or "")
            if (cs and cs == query) or (ssr and ssr == query):
                lat = t.raw_dict.get("lat")
                lon = t.raw_dict.get("lon")
                if lat is not None and lon is not None:
                    self.target_located.emit(float(lat), float(lon), "AIRCRAFT",
                                             cs or f"TRK-{t.id}")
                    return

        QMessageBox.information(self, "Finder",
                                f"'{query}' no disponible o fuera de cobertura.")
