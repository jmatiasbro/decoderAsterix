import os
import json
import glob

directorio = r"c:\documentos\decode_asterix\default-site-params"
for fp in sorted(glob.glob(os.path.join(directorio, "*.json"))):
    try:
        with open(fp, 'r', encoding='utf-8') as f:
            data = json.load(f)
        sac = data.get('sac')
        sic = data.get('sic')
        name = data.get('name')
        print(f"SAC: {sac}, SIC: {sic} -> Name: '{name}'")
    except Exception as e:
        print(f"Error parsing {fp}: {e}")
