"""Seeder de tiles satelitales -> MBTiles (corre UNA vez, con internet).

Fuente por defecto: Sentinel-2 cloudless (EOX IT Services GmbH) — imagery abierta,
legal para cache offline. Atribución obligatoria:
  "Sentinel-2 cloudless - https://s2maps.eu by EOX IT Services GmbH"

Uso típico:
  # Argentina hasta z12 + alto zoom (z16) en dos aeropuertos
  python tools/seed_tiles.py --out data/firmap/argentina.mbtiles \\
         --z-nation 12 \\
         --airport -24.8597,-65.4869,40 --airport -31.31,-64.21,40 --z-airport 16

Reanudable: saltea tiles ya presentes. Respeta un delay entre requests.
"""
import argparse
import os
import sys
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from player.firmap import webmercator as wm  # noqa: E402
from player.firmap.mbtiles import MBTilesWriter  # noqa: E402

# EOX s2cloudless WMTS (GoogleMapsCompatible). WMTS order = {z}/{y}/{x}.
DEFAULT_URL = ("https://tiles.maps.eox.at/wmts/1.0.0/"
               "s2cloudless-2021_3857/default/GoogleMapsCompatible/{z}/{y}/{x}.jpg")
ATTRIBUTION = "Sentinel-2 cloudless - https://s2maps.eu by EOX IT Services GmbH"
USER_AGENT = "decode_asterix-firmap-seeder/1.0 (+offline ATC tile cache)"

# bbox Argentina (lon_min, lat_min, lon_max, lat_max).
ARGENTINA_BBOX = (-73.6, -55.1, -53.6, -21.8)


def km_to_deg(km):
    return km / 111.0


def fetch(url, retries=3, backoff=2.0):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.read()
        except Exception as e:
            if attempt == retries - 1:
                raise
            time.sleep(backoff * (attempt + 1))
    return None


def seed_bbox(writer, url_tpl, bbox, z_min, z_max, delay, label):
    lon_min, lat_min, lon_max, lat_max = bbox
    total = sum(wm.count_tiles_for_bbox(*bbox, z) for z in range(z_min, z_max + 1))
    print(f"[{label}] z{z_min}..{z_max}: ~{total} tiles")
    done = skipped = failed = 0
    for z in range(z_min, z_max + 1):
        x0, y0, x1, y1 = wm.tile_range_for_bbox(lon_min, lat_min, lon_max, lat_max, z)
        for x in range(x0, x1 + 1):
            for y in range(y0, y1 + 1):
                if writer.has_tile(z, x, y):
                    skipped += 1
                    continue
                url = url_tpl.format(z=z, x=x, y=y)
                try:
                    data = fetch(url)
                    if data:
                        writer.put_tile(z, x, y, data)
                        done += 1
                        if done % 200 == 0:
                            writer.commit()
                            print(f"  ...{done} bajados, {skipped} saltados, {failed} fallidos")
                        time.sleep(delay)
                except Exception as e:
                    failed += 1
                    print(f"  ! falló z{z}/{x}/{y}: {e}")
        writer.commit()
    print(f"[{label}] OK: {done} nuevos, {skipped} ya estaban, {failed} fallidos")


def main():
    ap = argparse.ArgumentParser(description="Seeder Sentinel-2 cloudless -> MBTiles")
    ap.add_argument("--out", default="data/firmap/argentina.mbtiles")
    ap.add_argument("--url", default=DEFAULT_URL, help="plantilla XYZ con {z}{x}{y}")
    ap.add_argument("--z-nation", type=int, default=12, help="zoom máx para todo el país")
    ap.add_argument("--z-nation-min", type=int, default=4)
    ap.add_argument("--airport", action="append", default=[],
                    help="lat,lon,radio_km (repetible) para alto zoom")
    ap.add_argument("--z-airport", type=int, default=16)
    ap.add_argument("--z-airport-min", type=int, default=13)
    ap.add_argument("--delay", type=float, default=0.1, help="seg entre requests")
    args = ap.parse_args()

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    writer = MBTilesWriter(args.out)
    writer.set_metadata(name="argentina-s2cloudless", format="jpg",
                        type="baselayer", attribution=ATTRIBUTION,
                        minzoom=args.z_nation_min, maxzoom=max(args.z_airport, args.z_nation))

    seed_bbox(writer, args.url, ARGENTINA_BBOX, args.z_nation_min, args.z_nation,
              args.delay, "NACIONAL")

    for spec in args.airport:
        try:
            lat, lon, rkm = (float(v) for v in spec.split(","))
        except ValueError:
            print(f"  ! aeropuerto inválido: {spec} (esperado lat,lon,radio_km)")
            continue
        d = km_to_deg(rkm)
        bbox = (lon - d, lat - d, lon + d, lat + d)
        seed_bbox(writer, args.url, bbox, args.z_airport_min, args.z_airport,
                  args.delay, f"AERO {lat:.3f},{lon:.3f}")

    writer.close()
    print(f"Listo -> {args.out}")


if __name__ == "__main__":
    main()
