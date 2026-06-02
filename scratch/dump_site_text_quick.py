import os
import glob

directorio = r"c:\documentos\decode_asterix\default-site-params"
for fp in sorted(glob.glob(os.path.join(directorio, "*"))):
    if fp.endswith(".json") or os.path.isdir(fp):
        continue
    try:
        with open(fp, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        name = ""
        sac = ""
        sic = ""
        for line in lines:
            if "SITE_NAME=" in line or "name=" in line or "NAME=" in line:
                name = line.strip()
            if "RADAR_SAC=" in line:
                sac = line.strip()
            if "RADAR_SIC=" in line:
                sic = line.strip()
        print(f"File: {os.path.basename(fp)} -> {name}, {sac}, {sic}")
    except Exception as e:
        print(f"Error reading {fp}: {e}")
