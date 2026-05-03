#!/usr/bin/env python3
"""
Radar Selector Module

Allows users to select radar parameters from default-site-params directory.
Supports selecting one, multiple, or all available radars.
"""

import json
import os
from pathlib import Path
from typing import List, Dict, Any


class RadarSelector:
    """Interactive radar parameter selector."""
    
    def __init__(self, params_dir: str = "default_site_params"):
        """
        Initialize the radar selector.
        
        Args:
            params_dir: Directory containing radar parameter JSON files
        """
        self.params_dir = params_dir
        self.radars = {}
        self._load_radars()
    
    def _load_radars(self):
        """Load all radar definitions from JSON files."""
        params_path = Path(self.params_dir)
        
        if not params_path.exists():
            print(f"Warning: {self.params_dir} directory not found.")
            return

        # Se descarta el archivo de índice restringido y se cargan todos los archivos JSON individuales
        for json_file in params_path.glob("*.json"):
            if json_file.name != "radar_list.json":
                try:
                    with open(json_file, 'r') as f:
                        radar_data = json.load(f)
                        radar_id = radar_data.get("radar_id", json_file.stem)
                        self.radars[radar_id] = {
                            "info": {"name": radar_data.get("name", json_file.stem)},
                            "data": radar_data
                        }
                except Exception as e:
                    print(f"Error loading {json_file}: {e}")
    
    def display_available_radars(self):
        """Display all available radars."""
        if not self.radars:
            print("No radars found.")
            return
        
        print("\n" + "="*60)
        print("AVAILABLE RADAR SYSTEMS")
        print("="*60)
        
        # Ordenar los radares por nombre para el listado alfabético
        sorted_radars = sorted(self.radars.items(), key=lambda x: x[1]["info"].get("name", "").lower())
        
        for idx, (radar_id, radar_info) in enumerate(sorted_radars, 1):
            name = radar_info["info"].get("name", "Unknown")
            radar_type = radar_info["data"].get("type", "Unknown")
            print(f"{idx}. [{radar_id}] {name} (Type: {radar_type})")
        
        print("="*60)
    
    def select_radars_interactive(self) -> List[str]:
        """
        Interactively select radars.
        
        Returns:
            List of selected radar IDs
        """
        if not self.radars:
            print("No radars available.")
            return []
        
        self.display_available_radars()
        
        print("\nSelect radars:")
        print("  - Enter radar numbers separated by commas (e.g., 1,2,3)")
        print("  - Enter 'all' to select all radars")
        print("  - Enter 'none' to cancel\n")
        
        choice = input("Your choice: ").strip().lower()
        
        if choice == "none":
            return []
        
        if choice == "all":
            return list(self.radars.keys())
        
        selected = []
        try:
            indices = [int(x.strip()) for x in choice.split(",")]
            
            # Asegurar que los índices coincidan con la lista ordenada mostrada al usuario
            sorted_items = sorted(self.radars.items(), key=lambda x: x[1]["info"].get("name", "").lower())
            radar_ids = [item[0] for item in sorted_items]
            
            for idx in indices:
                if 1 <= idx <= len(radar_ids):
                    selected.append(radar_ids[idx - 1])
                else:
                    print(f"Warning: Invalid selection {idx}")
            
            if not selected:
                print("No valid selections made.")
        except ValueError:
            print("Invalid input format.")
        
        return selected
    
    def get_radar_data(self, radar_id: str) -> Dict[str, Any]:
        """
        Get data for a specific radar.
        
        Args:
            radar_id: The radar ID
            
        Returns:
            Dictionary with radar data
        """
        if radar_id in self.radars:
            return self.radars[radar_id]["data"]
        return {}
    
    def get_all_radar_data(self, radar_ids: List[str]) -> Dict[str, Dict[str, Any]]:
        """
        Get data for multiple radars.
        
        Args:
            radar_ids: List of radar IDs
            
        Returns:
            Dictionary mapping radar IDs to their data
        """
        result = {}
        for radar_id in radar_ids:
            if radar_id in self.radars:
                result[radar_id] = self.radars[radar_id]["data"]
        return result
    
    def display_radar_details(self, radar_ids: List[str]):
        """
        Display detailed information for selected radars.
        
        Args:
            radar_ids: List of radar IDs to display
        """
        if not radar_ids:
            print("No radars selected.")
            return
        
        print("\n" + "="*60)
        print("SELECTED RADAR DETAILS")
        print("="*60)
        
        for radar_id in radar_ids:
            if radar_id in self.radars:
                radar_data = self.radars[radar_id]["data"]
                print(f"\n[{radar_id}] {radar_data.get('name', 'Unknown')}")
                print("-" * 60)
                
                for key, value in radar_data.items():
                    if key != "name":
                        if isinstance(value, dict):
                            print(f"  {key}:")
                            for sub_key, sub_value in value.items():
                                print(f"    - {sub_key}: {sub_value}")
                        else:
                            print(f"  {key}: {value}")
        
        print("\n" + "="*60)
    
    def export_selected_radars(self, radar_ids: List[str], output_file: str = "selected_radars.json"):
        """
        Export selected radar data to a JSON file.
        
        Args:
            radar_ids: List of radar IDs to export
            output_file: Output file path
        """
        data = {
            "selected_radars": self.get_all_radar_data(radar_ids),
            "total_radars": len(radar_ids)
        }
        
        try:
            with open(output_file, 'w') as f:
                json.dump(data, f, indent=2)
            print(f"\nRadar data exported to {output_file}")
        except Exception as e:
            print(f"Error exporting to {output_file}: {e}")


def main():
    """Interactive radar selector."""
    selector = RadarSelector()
    
    if not selector.radars:
        print("No radars found in default_site_params directory.")
        return
    
    # Interactive selection
    selected_ids = selector.select_radars_interactive()
    
    if selected_ids:
        selector.display_radar_details(selected_ids)
        
        # Option to export
        export_choice = input("\nExport to JSON file? (yes/no): ").strip().lower()
        if export_choice == "yes":
            filename = input("Enter output filename (default: selected_radars.json): ").strip()
            if not filename:
                filename = "selected_radars.json"
            selector.export_selected_radars(selected_ids, filename)


if __name__ == "__main__":
    main()
