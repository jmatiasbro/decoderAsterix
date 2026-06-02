import os
import shutil

base_dir = r"c:\documentos\decode_asterix"

# Directorios a crear
dirs = [
    "decoder",
    "player",
    "utils",
    "analysis",
    "decoder/decoders",
    "decoder/asterix"
]

for d in dirs:
    os.makedirs(os.path.join(base_dir, d), exist_ok=True)

# Crear __init__.py
inits = {
    "decoder/__init__.py": '"""\ndecoder — Librería pura de decodificación ASTERIX (sin dependencias Qt)\n======================================================================\nSoporta categorías: CAT 001, 002, 021, 034, 048, 062\n"""\nfrom .data_engine import DataEngine, AsterixPlot\nfrom .asterix_router import AsterixRouter\nfrom .native_asterix import parse_payload\n',
    "player/__init__.py": '"""\nplayer — Aplicación de reproducción y visualización (PyQt6)\n==========================================================\n"""\nfrom .playback_worker import PlaybackWorker\n',
    "utils/__init__.py": '"""\nutils — Utilidades compartidas\n"""\nfrom .geo import StereographicLocal, GeoTools, cargar_sensores, METERS_PER_NM, WGS84_GEOD\n',
    "analysis/__init__.py": '"""\nanalysis — Herramientas de análisis post-decodificación\n"""\n'
}

for path, content in inits.items():
    with open(os.path.join(base_dir, path), "w", encoding="utf-8") as f:
        f.write(content)

# Copiar archivos
copies = [
    # To decoder/
    ("native_asterix.py", "decoder/native_asterix.py"),
    ("asterix_router.py", "decoder/asterix_router.py"),
    ("asterix_utils.py", "decoder/asterix_utils.py"),
    ("io_tools.py", "decoder/io_tools.py"),
    ("config.py", "decoder/config.py"),
    
    # To player/
    ("radar_widget.py", "player/radar_widget.py"),
    ("dashboard_widget.py", "player/dashboard_widget.py"),
    ("projection.py", "player/projection.py"),
    ("osm_layer.py", "player/osm_layer.py"),
    ("web_server.py", "player/web_server.py"),
    
    # To analysis/
    ("mode_analyzer.py", "analysis/mode_analyzer.py"),
    ("flight_loss_analyzer.py", "analysis/flight_loss_analyzer.py"),
    ("atm_analytics.py", "analysis/atm_analytics.py"),
    ("exporters.py", "analysis/exporters.py"),
    ("radar_selector.py", "analysis/radar_selector.py")
]

for src, dst in copies:
    src_path = os.path.join(base_dir, src)
    dst_path = os.path.join(base_dir, dst)
    if os.path.exists(src_path):
        shutil.copy2(src_path, dst_path)
        print(f"Copied {src} to {dst}")
    else:
        print(f"WARNING: Source file not found: {src_path}")

# Copiar directorio decoders
decoders_src = os.path.join(base_dir, "decoders")
decoders_dst = os.path.join(base_dir, "decoder", "decoders")
if os.path.exists(decoders_src):
    for item in os.listdir(decoders_src):
        s = os.path.join(decoders_src, item)
        d = os.path.join(decoders_dst, item)
        if os.path.isfile(s):
            shutil.copy2(s, d)
            print(f"Copied {item} to decoder/decoders/")
else:
    print("WARNING: decoders directory not found.")

# Copiar directorio asterix (XMLs)
asterix_src = os.path.join(base_dir, "asterix")
asterix_dst = os.path.join(base_dir, "decoder", "asterix")
if os.path.exists(asterix_src):
    for item in os.listdir(asterix_src):
        s = os.path.join(asterix_src, item)
        d = os.path.join(asterix_dst, item)
        if os.path.isfile(s):
            shutil.copy2(s, d)
            print(f"Copied {item} to decoder/asterix/")
else:
    print("WARNING: asterix directory not found.")

print("Done.")
