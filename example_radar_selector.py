#!/usr/bin/env python3
"""
Ejemplo de uso del Radar Selector

Este script demuestra cómo usar el módulo radar_selector.py
para seleccionar y ver datos de radares disponibles.
"""

from radar_selector import RadarSelector


def ejemplo_basico():
    """Ejemplo básico de uso."""
    print("\n=== Ejemplo 1: Carga automática de radares ===\n")
    
    selector = RadarSelector()
    
    if selector.radars:
        print(f"Se encontraron {len(selector.radars)} radares disponibles")
        selector.display_available_radars()
    else:
        print("No se encontraron radares en default_site_params/")


def ejemplo_seleccion_unica():
    """Ejemplo de selección única."""
    print("\n=== Ejemplo 2: Seleccionar un radar ===\n")
    
    selector = RadarSelector()
    
    if selector.radars:
        radar_ids = list(selector.radars.keys())
        print(f"Primer radar disponible: {radar_ids[0]}")
        
        radar_data = selector.get_radar_data(radar_ids[0])
        print(f"Nombre: {radar_data.get('name')}")
        print(f"Tipo: {radar_data.get('type')}")
        print(f"Ubicación: {radar_data.get('location')}")


def ejemplo_seleccion_multiple():
    """Ejemplo de selección múltiple."""
    print("\n=== Ejemplo 3: Seleccionar múltiples radares ===\n")
    
    selector = RadarSelector()
    
    if selector.radars:
        # Seleccionar todos los radares
        all_radars = list(selector.radars.keys())
        print(f"Seleccionando todos los {len(all_radars)} radares disponibles...")
        
        selector.display_radar_details(all_radars)


def ejemplo_exportar():
    """Ejemplo de exportación de datos."""
    print("\n=== Ejemplo 4: Exportar datos de radares ===\n")
    
    selector = RadarSelector()
    
    if selector.radars:
        radar_ids = list(selector.radars.keys())
        
        if len(radar_ids) > 1:
            # Exportar los primeros 2 radares
            selected = radar_ids[:2]
            print(f"Exportando datos de {len(selected)} radares a 'example_radars.json'")
            selector.export_selected_radars(selected, "example_radars.json")
        else:
            print(f"Exportando datos del único radar disponible a 'example_radars.json'")
            selector.export_selected_radars(radar_ids, "example_radars.json")


if __name__ == "__main__":
    print("\n" + "="*70)
    print("RADAR SELECTOR - EJEMPLOS DE USO")
    print("="*70)
    
    try:
        ejemplo_basico()
        ejemplo_seleccion_unica()
        ejemplo_seleccion_multiple()
        ejemplo_exportar()
    except Exception as e:
        print(f"\nError: {e}")
    
    print("\n" + "="*70)
    print("Ejemplos completados.")
    print("="*70 + "\n")
