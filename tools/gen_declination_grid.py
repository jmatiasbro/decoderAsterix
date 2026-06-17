"""Genera la grilla offline de declinación magnética y la cartografía de isógonas
a partir del World Magnetic Model (pygeomag). Re-ejecutar para actualizar la época.

  python tools/gen_declination_grid.py
"""
import datetime
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from player.geo.isogonic import contour_lines  # noqa: E402

LAT_MIN, LAT_MAX = -56.0, -21.0
LON_MIN, LON_MAX = -76.0, -52.0
STEP = 1.0
OUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "data", "magnetic")


def _anio_decimal(fecha=None):
    fecha = fecha or datetime.date.today()
    ini = datetime.date(fecha.year, 1, 1).toordinal()
    fin = datetime.date(fecha.year + 1, 1, 1).toordinal()
    return round(fecha.year + (fecha.toordinal() - ini) / (fin - ini), 2)


def build_grid(geomag, epoch):
    n_lat = int(round((LAT_MAX - LAT_MIN) / STEP)) + 1
    n_lon = int(round((LON_MAX - LON_MIN) / STEP)) + 1
    values = []
    for i in range(n_lat):
        lat = LAT_MIN + i * STEP
        row = []
        for j in range(n_lon):
            lon = LON_MIN + j * STEP
            row.append(round(float(geomag.calculate(glat=lat, glon=lon, alt=0,
                                                     time=epoch).d), 3))
        values.append(row)
    return {"convention": "west-negative", "epoch": epoch,
            "lat_min": LAT_MIN, "lat_max": LAT_MAX,
            "lon_min": LON_MIN, "lon_max": LON_MAX,
            "step": STEP, "n_lat": n_lat, "n_lon": n_lon, "values": values}


def grid_to_geojson(grid):
    lines = contour_lines(grid["values"], grid["lat_min"], grid["lon_min"],
                          grid["step"])
    features = []
    for level in sorted(lines):
        segs = lines[level]
        for poly in segs:
            features.append({
                "type": "Feature",
                "properties": {"layer": "ISOGONAS", "name": f"{level:.0f}°"},
                "geometry": {"type": "LineString",
                             "coordinates": [[lon, lat] for (lat, lon) in poly]},
            })
        # una etiqueta por nivel, en el punto medio del segmento central
        if segs:
            mid = segs[len(segs) // 2]
            la, lo = mid[0]
            features.append({
                "type": "Feature",
                "properties": {"layer": "NOMBRES_WAYPOINTS", "type": "text",
                               "name": f"{level:.0f}°"},
                "geometry": {"type": "Point", "coordinates": [lo, la]},
            })
    return {"type": "FeatureCollection", "color": "#FF40FF", "features": features}


def main():
    from pygeomag import GeoMag
    os.makedirs(OUT_DIR, exist_ok=True)
    epoch = _anio_decimal()
    grid = build_grid(GeoMag(), epoch)
    with open(os.path.join(OUT_DIR, "declination_grid.json"), "w",
              encoding="utf-8") as f:
        json.dump(grid, f)
    with open(os.path.join(OUT_DIR, "isogonic_lines.geojson"), "w",
              encoding="utf-8") as f:
        json.dump(grid_to_geojson(grid), f)
    print(f"OK epoch={epoch} grid={grid['n_lat']}x{grid['n_lon']} "
          f"isogonas={sum(1 for x in grid_to_geojson(grid)['features'] if x['geometry']['type']=='LineString')}")


if __name__ == "__main__":
    main()
