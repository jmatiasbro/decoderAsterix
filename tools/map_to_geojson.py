"""Convierte mapas en formato .map (DMS) a GeoJSON (LineString, coords [lon,lat]).

Soporta: Circumference (círculo), Arc (arco por 3 puntos), Polyline y Polygon.
Círculos/arcos se muestrean como polilíneas; los polígonos se cierran.

Uso: python tools/map_to_geojson.py entrada.map salida.geojson
"""
import json
import math
import re
import sys

_COORD = re.compile(r'^(\d{6}(?:\.\d+)?)([NS])(\d{7}(?:\.\d+)?)([EW])$')


def _dms_to_dd(s, ddigits):
    deg = int(s[:ddigits])
    mm = int(s[ddigits:ddigits + 2])
    ss = float(s[ddigits + 2:])
    return deg + mm / 60.0 + ss / 3600.0


def parse_coord(token):
    """'312616.00S0641633.00W' -> [lon, lat] (orden GeoJSON) o None."""
    m = _COORD.match(token.strip())
    if not m:
        return None
    lat_s, lat_h, lon_s, lon_h = m.groups()
    lat = _dms_to_dd(lat_s, 2)
    lon = _dms_to_dd(lon_s, 3)
    if lat_h == 'S':
        lat = -lat
    if lon_h == 'W':
        lon = -lon
    return [lon, lat]


def circle_points(center, radius_nm, n=72):
    lon0, lat0 = center
    r_deg = radius_nm / 60.0
    k = math.cos(math.radians(lat0)) or 1e-6
    pts = []
    for i in range(n + 1):
        ang = 2 * math.pi * i / n
        pts.append([lon0 + r_deg * math.sin(ang) / k, lat0 + r_deg * math.cos(ang)])
    return pts


def arc_points(p1, p2, p3, n=24):
    """Arco circular que pasa por p1, p2, p3 (proyección plana local en NM)."""
    lat0 = p1[1]
    k = math.cos(math.radians(lat0)) or 1e-6
    to_xy = lambda p: (p[0] * k * 60.0, p[1] * 60.0)
    to_ll = lambda x, y: [x / (k * 60.0), y / 60.0]
    (x1, y1), (x2, y2), (x3, y3) = to_xy(p1), to_xy(p2), to_xy(p3)
    d = 2 * (x1 * (y2 - y3) + x2 * (y3 - y1) + x3 * (y1 - y2))
    if abs(d) < 1e-9:
        return [p1, p2, p3]
    ux = ((x1**2 + y1**2) * (y2 - y3) + (x2**2 + y2**2) * (y3 - y1) +
          (x3**2 + y3**2) * (y1 - y2)) / d
    uy = ((x1**2 + y1**2) * (x3 - x2) + (x2**2 + y2**2) * (x1 - x3) +
          (x3**2 + y3**2) * (x2 - x1)) / d
    r = math.hypot(x1 - ux, y1 - uy)
    a1 = math.atan2(y1 - uy, x1 - ux)
    a2 = math.atan2(y2 - uy, x2 - ux)
    a3 = math.atan2(y3 - uy, x3 - ux)

    def _ccw(a, b):
        t = b - a
        while t < 0:
            t += 2 * math.pi
        return t

    sweep = _ccw(a1, a3)
    if _ccw(a1, a2) > sweep:        # el punto medio no cae en el arco CCW -> ir CW
        sweep -= 2 * math.pi
    return [to_ll(ux + r * math.cos(a1 + sweep * i / n),
                  uy + r * math.sin(a1 + sweep * i / n)) for i in range(n + 1)]


def _feature(coords, layer="LINEAS_DE_MAPA"):
    return {"type": "Feature",
            "geometry": {"type": "LineString", "coordinates": coords},
            "properties": {"layer": layer, "name": "", "type": "polyline"}}


def convert(map_path, out_path):
    with open(map_path, 'r', encoding='utf-8', errors='ignore') as f:
        raw = f.read()
    # Quitar comentarios /* ... */
    raw = re.sub(r'/\*.*?\*/', '', raw, flags=re.DOTALL)
    lines = [ln.strip() for ln in raw.splitlines() if ln.strip()]

    features = []
    i = 0
    while i < len(lines):
        parts = lines[i].split()
        kw = parts[0].lower()
        if kw == 'circumference' and len(parts) >= 3:
            c = parse_coord(parts[1])
            if c:
                features.append(_feature(circle_points(c, float(parts[2]))))
            i += 1
        elif kw == 'arc' and len(parts) >= 4:
            p1, p2, p3 = parse_coord(parts[1]), parse_coord(parts[2]), parse_coord(parts[3])
            if p1 and p2 and p3:
                features.append(_feature(arc_points(p1, p2, p3)))
            i += 1
        elif kw in ('polyline', 'polygon') and len(parts) >= 2:
            n = int(parts[1])
            coords = []
            for j in range(i + 1, i + 1 + n):
                if j < len(lines):
                    c = parse_coord(lines[j])
                    if c:
                        coords.append(c)
            if kw == 'polygon' and coords and coords[0] != coords[-1]:
                coords.append(coords[0])
            if len(coords) >= 2:
                features.append(_feature(coords))
            i += 1 + n
        else:
            i += 1

    fc = {"type": "FeatureCollection", "features": features}
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(fc, f, indent=2)
    return len(features)


if __name__ == '__main__':
    n = convert(sys.argv[1], sys.argv[2])
    print(f"{sys.argv[2]}: {n} features")
