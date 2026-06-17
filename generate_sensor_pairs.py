import os
import json

def generate_sensor_pairs():
    """
    Recorre la carpeta default-site-params y genera las configuraciones faltantes.
    Si encuentra un Radar, genera su par ADS-B (SIC - 100).
    Si encuentra un ADS-B, genera su par Radar (SIC + 100).
    """
    # Ruta absoluta al directorio de parámetros
    base_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'default-site-params')
    
    if not os.path.exists(base_dir):
        print(f"[ERROR] El directorio no existe: {base_dir}")
        return

    for filename in os.listdir(base_dir):
        if not filename.endswith('.json') or filename == 'radar_list.json':
            continue
            
        filepath = os.path.join(base_dir, filename)
        
        with open(filepath, 'r', encoding='utf-8') as f:
            try:
                data = json.load(f)
            except json.JSONDecodeError:
                print(f"[WARNING] Error leyendo {filename}. Saltando...")
                continue
        
        sac = data.get('sac')
        sic = data.get('sic')
        sensor_type = data.get('type', '').lower()
        name = data.get('name', 'Unknown')
        location = data.get('location')
        category = data.get('category', '').upper()
        
        if sac is None or sic is None or not location:
            continue

        # Detección flexible: por tipo, categoría o convención del SIC
        is_adsb = ('ads' in sensor_type) or ('021' in category) or (100 <= sic < 200)
        
        if is_adsb:
            pair_sic = sic - 100
            if pair_sic < 0:
                print(f"[WARNING] {filename} tiene SIC {sic} (menor a 100). Imposible generar par Radar con SIC negativo.")
                continue
                
            clean_name = name.replace("ADS-B_", "").replace("ADS-B ", "")
            pair_data = {
                "radar_id": f"RADAR_{sac}_{pair_sic}",
                "name": clean_name,
                "type": "SSR/PSR",
                "category": "CAT048",
                "sac": sac,
                "sic": pair_sic,
                "location": location
            }
        else: # Asumimos que es un Radar
            pair_sic = sic + 100
                
            pair_data = {
                "radar_id": f"ADS-B_{sac}_{pair_sic}",
                "name": f"ADS-B_{name}",
                "type": "ads-b",
                "category": "CAT021",
                "sac": sac,
                "sic": pair_sic,
                "location": location
            }
            
        pair_filename = f"{sac}_{pair_sic}.json"
        pair_filepath = os.path.join(base_dir, pair_filename)
        
        # Solo crearlo si no existe previamente
        if not os.path.exists(pair_filepath):
            with open(pair_filepath, 'w', encoding='utf-8') as pf:
                json.dump(pair_data, pf, indent=2)
            print(f"[INFO] Generado exitosamente: {pair_filename} a partir de {filename}")

if __name__ == '__main__':
    print("Iniciando generación automática de pares de sensores (Radar <-> ADS-B)...")
    generate_sensor_pairs()
    print("Proceso finalizado.")