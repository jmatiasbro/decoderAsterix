"""
Exportadores de Datos ASTERIX

Módulo para exportar datos decodificados a diferentes formatos:
- KML (Google Earth)
- GeoJSON (QGIS/Mapas web)
- CSV (Análisis)
"""

import csv
import json
import math
import time
from datetime import datetime
from typing import List, Dict, Optional, Tuple
from pathlib import Path

try:
    from fpdf import FPDF
    HAS_FPDF = True
except ImportError:
    HAS_FPDF = False
    FPDF = None

class KMLExporter:
    """Exportador para formato KML (Google Earth)."""
    
    # Colores KML (AABBGGRR) - Naranja (48), Cian (62), Verde (21), Magenta (01)
    COLORS = {
        48: "ff00a5ff",  # Naranja
        62: "ffffff00",  # Cian
        21: "ff00ff00",  # Verde (Green)
        1:  "ffff00ff",  # Magenta
        'default': "ffffffff" # Blanco
    }

    @staticmethod
    def export(records: List[Dict], output_path: str, sensor_registry=None, 
               include_trajectories: bool = True, include_rings: bool = True):
        """
        Exporta registros a KML con estilos y <gx:Track> para trayectorias.
        """
        # Agrupar por un identificador de traza único
        tracks = {}
        for r in records:
            # Priorizar Track Number, luego Mode S, luego Squawk
            tid = r.get('track_number') or r.get('mode_s') or r.get('mode_3a')
            if tid:
                if tid not in tracks: tracks[tid] = []
                tracks[tid].append(r)

        kml_parts = [
            '<?xml version="1.0" encoding="UTF-8"?>',
            '<kml xmlns="http://www.opengis.net/kml/2.2" xmlns:gx="http://www.google.com/kml/ext/2.2">',
            '<Document>',
            '<name>ASTERIX Track Export</name>',
            '<description>Datos de trazas ASTERIX con animación de tiempo.</description>'
        ]

        # Definir estilos por categoría
        for cat, color in KMLExporter.COLORS.items():
            if isinstance(cat, int):
                kml_parts.append(f'''
                <Style id="style_cat{cat}">
                    <IconStyle><scale>0</scale></IconStyle>
                    <LineStyle><color>{color}</color><width>3</width></LineStyle>
                </Style>''')
        
        # Crear Placemarks para cada traza
        for track_id, track_records in tracks.items():
            # Ordenar por tiempo para que la animación sea correcta
            track_records.sort(key=lambda x: x.get('timestamp', 0))
            kml_parts.append(KMLExporter._create_track_placemark(track_id, track_records))
        
        kml_parts.extend([
            '</Document>',
            '</kml>'
        ])
        
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(kml_parts))

    @staticmethod
    def _create_track_placemark(track_id: str, records: List[Dict]) -> str:
        """Crea un Placemark KML con un <gx:Track> para una traza."""
        if not records:
            return ""

        first_rec = records[0]
        cat = first_rec.get('category', 'default')
        
        # Construir el <gx:Track>
        track_coords = []
        for rec in records:
            if rec.get('timestamp') and rec.get('longitude') and rec.get('latitude'):
                # KML timestamp format: YYYY-MM-DDTHH:MM:SSZ
                # ASTERIX timestamp is seconds from midnight. Usamos una fecha dummy.
                ts = time.strftime("2024-01-01T%H:%M:%SZ", time.gmtime(rec.get('timestamp')))
                alt_m = (rec.get('flight_level', 0) * 100) * 0.3048
                track_coords.append(f"<when>{ts}</when>")
                track_coords.append(f"<gx:coord>{rec['longitude']} {rec['latitude']} {alt_m}</gx:coord>")

        if not track_coords:
            return ""

        # Construir el <LineString> para la ruta visual
        line_coords = " ".join([f"{rec['longitude']},{rec['latitude']},{(rec.get('flight_level', 0) * 100) * 0.3048}" for rec in records if rec.get('longitude')])
        
        placemark = f"""
        <Placemark>
            <name>Track {track_id}</name>
            <styleUrl>#style_cat{cat}</styleUrl>
            <gx:Track>
                <altitudeMode>absolute</altitudeMode>
                {''.join(track_coords)}
            </gx:Track>
            <LineString>
                <extrude>1</extrude>
                <tessellate>1</tessellate>
                <altitudeMode>absolute</altitudeMode>
                <coordinates>{line_coords}</coordinates>
            </LineString>
        </Placemark>
        """.strip()
        
        return placemark


class GeoJSONExporter:
    """Exportador para formato GeoJSON."""
    
    @staticmethod
    def export(records: List[Dict], output_path: str):
        """
        Exporta registros a GeoJSON.
        
        Args:
            records: Lista de registros procesados
            output_path: Ruta del archivo GeoJSON de salida
        """
        features = []
        
        for record in records:
            if record['latitude'] is None or record['longitude'] is None:
                continue
            
            feature = {
                'type': 'Feature',
                'geometry': {
                    'type': 'Point',
                    'coordinates': [record['longitude'], record['latitude']]
                },
                'properties': {
                    'category': record['category'],
                    'sac': record['sac'],
                    'sic': record['sic'],
                    'mode_3a': record['mode_3a'],
                    'flight_level': record['flight_level'],
                    'altitude': record['altitude'],
                    'timestamp': record['timestamp'],
                    'raw_range': record['raw_range'],
                    'raw_azimuth': record['raw_azimuth'],
                    'ground_range': record.get('ground_range'),
                    'radar_position': record.get('radar_position')
                }
            }
            features.append(feature)
        
        geojson = {
            'type': 'FeatureCollection',
            'features': features,
            'properties': {
                'name': 'ASTERIX Air Traffic Surveillance Data',
                'description': 'Exported from ASTERIX decoder',
                'generated': datetime.now().isoformat()
            }
        }
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(geojson, f, indent=2, ensure_ascii=False)


class CSVExporter:
    """Exportador para formato CSV."""
    
    @staticmethod
    def export(records: List[Dict], output_path: str):
        """
        Exporta registros a CSV para análisis en Excel/QGIS.
        
        Args:
            records: Lista de registros procesados
            output_path: Ruta del archivo CSV de salida
        """
        fieldnames = [
            'timestamp',
            'category',
            'sac',
            'sic',
            'latitude',
            'longitude',
            'altitude',
            'flight_level',
            'mode_3a',
            'raw_range_nm',
            'raw_azimuth_deg',
            'ground_range_nm',
            'radar_lat',
            'radar_lon'
        ]
        
        with open(output_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            
            for record in records:
                radar_pos = record.get('radar_position')
                row = {
                    'timestamp': record.get('timestamp'),
                    'category': record.get('category'),
                    'sac': record.get('sac'),
                    'sic': record.get('sic'),
                    'latitude': record.get('latitude'),
                    'longitude': record.get('longitude'),
                    'altitude': record.get('altitude'),
                    'flight_level': record.get('flight_level'),
                    'mode_3a': record.get('mode_3a'),
                    'raw_range_nm': record.get('raw_range'),
                    'raw_azimuth_deg': record.get('raw_azimuth'),
                    'ground_range_nm': record.get('ground_range'),
                    'radar_lat': radar_pos[0] if radar_pos else None,
                    'radar_lon': radar_pos[1] if radar_pos else None,
                }
                writer.writerow(row)


class ReportGenerator:
    """Generador de reportes de análisis."""
    
    @staticmethod
    def generate_summary(records: List[Dict], sensor_registry) -> str:
        """
        Genera un reporte de resumen.
        
        Args:
            records: Lista de registros
            sensor_registry: Registro de sensores
        
        Returns:
            String con el reporte
        """
        report = []
        report.append("=" * 70)
        report.append("ASTERIX DATA ANALYSIS REPORT")
        report.append("=" * 70)
        report.append(f"Generated: {datetime.now().isoformat()}")
        report.append("")
        
        # Estadísticas generales
        report.append("GENERAL STATISTICS")
        report.append("-" * 70)
        report.append(f"Total Records: {len(records)}")
        
        # Contar por categoría
        categories = {}
        for record in records:
            cat = record['category']
            categories[cat] = categories.get(cat, 0) + 1
        
        report.append("\nRecords by Category:")
        sorted_cats = sorted(categories.keys())
        for cat in sorted_cats:
            note = ""
            # Añadir notas sobre la relación entre categorías
            if cat == 48 and 34 in sorted_cats:
                note = " (Trazas de radar secundario, asociado con CAT034)"
            elif cat == 34 and 48 in sorted_cats:
                note = " (Mensajes de servicio para CAT048)"
            elif cat == 1 and 2 in sorted_cats:
                note = " (Trazas de radar primario, asociado con CAT002)"
            elif cat == 2 and 1 in sorted_cats:
                note = " (Mensajes de servicio para CAT001)"
            elif cat == 21:
                note = " (Vigilancia dependiente ADS-B)"
            elif cat == 62:
                note = " (Trazas de sistema fusionadas)"

            report.append(f"  CAT {cat:03d}: {categories[cat]} records{note}")
        
        # Información de sensores
        report.append("\n" + "=" * 70)
        report.append("SENSOR INFORMATION")
        report.append("-" * 70)
        
        for (sac, sic), sensor_info in sensor_registry.get_all_sensors().items():
            report.append(f"\nSensor {sac:03d}/{sic:03d}")
            report.append(f"  Records: {sensor_info['records_count']}")
            if sensor_info['latitude'] is not None and sensor_info['longitude'] is not None:
                report.append(f"  Position: {sensor_info['latitude']:.6f}°, {sensor_info['longitude']:.6f}°")
                report.append(f"  Elevation: {sensor_info['elevation']:.1f} ft")
            else:
                report.append("  Position: Not specified")
        
        # Estadísticas de cobertura
        report.append("\n" + "=" * 70)
        report.append("COVERAGE STATISTICS")
        report.append("-" * 70)
        
        records_with_position = len([r for r in records if r['latitude'] is not None and r['longitude'] is not None])
        report.append(f"Records with valid coordinates: {records_with_position}/{len(records)}")
        
        if records_with_position > 0:
            lats = [r['latitude'] for r in records if r['latitude'] is not None]
            lons = [r['longitude'] for r in records if r['longitude'] is not None]
            altitudes = [r['altitude'] for r in records if r['altitude'] is not None]
            
            report.append(f"\nLatitude range: {min(lats):.6f}° to {max(lats):.6f}°")
            report.append(f"Longitude range: {min(lons):.6f}° to {max(lons):.6f}°")
            
            if altitudes:
                report.append(f"Altitude range: {min(altitudes):.0f} to {max(altitudes):.0f} feet")
        
        report.append("\n" + "=" * 70)
        
        return '\n'.join(report)
    
    @staticmethod
    def save_report(report_text: str, output_path: str):
        """Guarda el reporte en archivo."""
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(report_text)

class PDFReportGenerator:
    """Generador de reportes PDF profesionales (Requiere fpdf2 o similar)."""

    @staticmethod
    def export_pdf(report_text: str, output_path: str):
        """
        Genera un reporte de auditoría simple en PDF a partir de un texto.
        
        Args:
            report_text: El texto del resumen a incluir en el PDF.
            output_path: Ruta de salida del PDF.
        """
        if not HAS_FPDF:
            print("[!] Error: La librería 'fpdf' no está instalada. Instale con: pip install fpdf2")
            return

        try:
            pdf = FPDF()
            pdf.add_page()
            
            # --- HEADER ---
            pdf.set_font("Helvetica", 'B', 16)
            pdf.cell(0, 10, "ASTERIX Data Analysis Report", 0, 1, 'C')
            pdf.ln(10)

            # --- BODY ---
            pdf.set_font("Courier", '', 10)
            # Usar multi_cell para manejar saltos de línea
            pdf.multi_cell(0, 5, report_text)

            # --- FOOTER ---
            pdf.set_y(-15)
            pdf.set_font("Helvetica", 'I', 8)
            pdf.set_text_color(128)
            pdf.cell(0, 10, f'Page {pdf.page_no()}', 0, 0, 'C')

            pdf.output(output_path)
            print(f"[✓] Reporte PDF exportado: {output_path}")
        except Exception as e:
            print(f"[!] Error al generar PDF: {e}")
