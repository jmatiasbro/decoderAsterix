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
import os
import duckdb
import simplekml

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


class PassExporter:
    def __init__(self, db_path="pass_analytics.duckdb", repo_db=None):
        self.repo_db = repo_db
        if repo_db:
            self.db_path = repo_db.db_path
        else:
            # Si db_path no existe, buscar en subdirectorios o en la carpeta raíz
            if not os.path.exists(db_path):
                alt_path = os.path.join("storage", "pass_analytics.duckdb")
                if os.path.exists(alt_path):
                    db_path = alt_path
                else:
                    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                    root_path = os.path.join(base_dir, "pass_analytics.duckdb")
                    if os.path.exists(root_path):
                        db_path = root_path
                    else:
                        storage_root_path = os.path.join(base_dir, "storage", "pass_analytics.duckdb")
                        if os.path.exists(storage_root_path):
                            db_path = storage_root_path
            self.db_path = db_path
            
        print(f"[PassExporter] Conectado a base de datos en: {self.db_path} (Memoria/Compartida: {repo_db is not None})")

    def export_to_powerbi(self, output_file="export_powerbi.parquet"):
        try:
            output_file = os.path.abspath(output_file).replace('\\', '/')
            # Asegurar directorio de salida
            dir_name = os.path.dirname(output_file)
            if dir_name:
                os.makedirs(dir_name, exist_ok=True)
                
            if self.repo_db and self.repo_db.conn:
                cursor = self.repo_db.conn.cursor()
                cursor.execute(f"COPY (SELECT * FROM asterix_plots) TO '{output_file}' (FORMAT PARQUET)")
                cursor.close()
            else:
                with duckdb.connect(self.db_path, read_only=True) as conn:
                    conn.execute(f"COPY (SELECT * FROM asterix_plots) TO '{output_file}' (FORMAT PARQUET)")
            print(f"[PassExporter] Parquet generado exitosamente: {output_file}")
            return True
        except Exception as e:
            print(f"[PassExporter] Error al generar Parquet: {e}")
            return False

    def export_heatmap_qgis(self, output_file="export_qgis_heatmap.csv"):
        try:
            output_file = os.path.abspath(output_file).replace('\\', '/')
            # Asegurar directorio de salida
            dir_name = os.path.dirname(output_file)
            if dir_name:
                os.makedirs(dir_name, exist_ok=True)
                
            if self.repo_db and self.repo_db.conn:
                cursor = self.repo_db.conn.cursor()
                cursor.execute(f"COPY (SELECT timestamp, category, sac_sic, lat, lon, flight_level FROM asterix_plots WHERE lat != 0.0 AND lon != 0.0) TO '{output_file}' (HEADER, DELIMITER ',')")
                cursor.close()
            else:
                with duckdb.connect(self.db_path, read_only=True) as conn:
                    conn.execute(f"COPY (SELECT timestamp, category, sac_sic, lat, lon, flight_level FROM asterix_plots WHERE lat != 0.0 AND lon != 0.0) TO '{output_file}' (HEADER, DELIMITER ',')")
            print(f"[PassExporter] CSV generado exitosamente: {output_file}")
            return True
        except Exception as e:
            print(f"[PassExporter] Error al generar CSV: {e}")
            return False

    def export_trajectories_kmz(self, output_file="trajectories.kmz", min_points=5):
        try:
            output_file = os.path.abspath(output_file).replace('\\', '/')
            # Asegurar directorio de salida
            dir_name = os.path.dirname(output_file)
            if dir_name:
                os.makedirs(dir_name, exist_ok=True)
            kml = simplekml.Kml(name="Trayectorias ASTERIX")
            
            # Helper to run queries on shared connection or read-only connection
            def run_queries(conn):
                tracks = conn.execute(f"SELECT track_id, COUNT(*) as pt_count FROM asterix_plots WHERE track_id != '' AND lat != 0.0 AND lon != 0.0 GROUP BY track_id HAVING pt_count >= {min_points}").fetchall()
                for track in tracks:
                    tid = track[0]
                    coords = conn.execute(f"SELECT lon, lat FROM asterix_plots WHERE track_id = '{tid}' AND lat != 0.0 AND lon != 0.0 ORDER BY timestamp ASC").fetchall()
                    linestring = kml.newlinestring(name=f"Track {tid}")
                    linestring.coords = coords
                    linestring.style.linestyle.width = 2
                    linestring.style.linestyle.color = simplekml.Color.green
            
            if self.repo_db and self.repo_db.conn:
                cursor = self.repo_db.conn.cursor()
                run_queries(cursor)
                cursor.close()
            else:
                with duckdb.connect(self.db_path, read_only=True) as conn:
                    run_queries(conn)
                    
            # Guardado nativo en formato comprimido KMZ
            kml.savekmz(output_file)
            print(f"[PassExporter] KMZ generado exitosamente: {output_file}")
            return True
        except Exception as e:
            print(f"[PassExporter] Error al generar KMZ: {e}")
            return False

    def export_flight_playback_kmz(self, track_id, output_file=None):
        """
        Genera un KMZ con animación temporal (gx:Track) para un vuelo específico.
        Permite reproducir el vuelo en Google Earth usando el Time Slider.
        """
        import datetime
        
        if output_file is None:
            output_file = f"playback_track_{track_id}.kmz"
            
        try:
            output_file = os.path.abspath(output_file).replace('\\', '/')
            # Asegurar directorio de salida
            dir_name = os.path.dirname(output_file)
            if dir_name:
                os.makedirs(dir_name, exist_ok=True)
                
            kml = simplekml.Kml(name=f"Playback Vuelo {track_id}")
            
            # Extraemos datos ordenados estrictamente por tiempo, usando la conexión compartida si existe
            def query_points(conn):
                return conn.execute(f"""
                    SELECT timestamp, lon, lat, flight_level 
                    FROM asterix_plots 
                    WHERE track_id = '{track_id}' AND lat != 0.0 AND lon != 0.0
                    ORDER BY timestamp ASC
                """).fetchall()

            if self.repo_db and self.repo_db.conn:
                cursor = self.repo_db.conn.cursor()
                puntos = query_points(cursor)
                cursor.close()
            else:
                with duckdb.connect(self.db_path, read_only=True) as conn:
                    puntos = query_points(conn)

            if not puntos:
                print(f"[Exporter] No se encontraron datos para el track: {track_id}")
                return False

            # Crear el objeto de Track animado
            trk = kml.newgxtrack(name=f"Track {track_id}")
            
            # Configurar estilo de la línea y del ícono
            trk.altitudemode = simplekml.AltitudeMode.absolute
            trk.extrude = 1 # Dibuja una línea hacia el suelo
            trk.style.linestyle.width = 3
            trk.style.linestyle.color = simplekml.Color.cyan
            
            # Opcional: Cambiar el icono por defecto por uno de avión
            trk.iconstyle.icon.href = 'http://maps.google.com/mapfiles/kml/shapes/airports.png'

            for pt in puntos:
                ts_raw = pt[0]
                lon = pt[1]
                lat = pt[2]
                fl_str = pt[3]

                # Convertir Flight Level a Metros de altitud para el 3D (exclusivamente no negativos)
                alt_metros = 0.0
                if fl_str is not None:
                    try:
                        fl_val = float(fl_str)
                        if fl_val >= 0.0:
                            alt_metros = fl_val * 100 * 0.3048
                    except (ValueError, TypeError):
                        pass 

                # Convertir Timestamp UNIX o Segundos desde medianoche a cadena ISO 8601 (Requerido por Google Earth)
                # Si el timestamp es 0 o inválido, se omite
                if ts_raw is not None and ts_raw > 0:
                    try:
                        # Si es un valor pequeño (ej. segundos de día, < 1000000), usar fecha base de hoy
                        if ts_raw < 1000000:
                            hoy = datetime.datetime.now().date()
                            dt = datetime.datetime.combine(hoy, datetime.time()) + datetime.timedelta(seconds=ts_raw)
                        else:
                            dt = datetime.datetime.utcfromtimestamp(ts_raw)
                        fecha_iso = dt.strftime('%Y-%m-%dT%H:%M:%SZ')
                        # Inyectar el tiempo y la coordenada 3D en la animación
                        trk.newwhen(fecha_iso)
                        trk.newgxcoord([(lon, lat, alt_metros)])
                    except Exception as e_ts:
                        # Si falla por cualquier motivo, intentar fallback con fecha de hoy
                        try:
                            hoy = datetime.datetime.now().date()
                            dt = datetime.datetime.combine(hoy, datetime.time()) + datetime.timedelta(seconds=float(ts_raw))
                            fecha_iso = dt.strftime('%Y-%m-%dT%H:%M:%SZ')
                            trk.newwhen(fecha_iso)
                            trk.newgxcoord([(lon, lat, alt_metros)])
                        except Exception:
                            pass

            kml.savekmz(output_file)
            print(f"[Exporter] Playback 3D generado exitosamente: {output_file}")
            return True
            
        except Exception as e:
            print(f"[Exporter] Error exportando Playback KMZ: {e}")
            return False

    def export_coverage_map_kmz(self, sac_sic, output_file=None, theoretical_range_nm=240):
        """
        Genera un KMZ estructurado por carpetas para distintos niveles de vuelo (FL 50, 100, 150, 200, 250, 300).
        Cada nivel de vuelo tiene su propio polígono de cobertura real calculado con percentiles robustos (95%)
        y con colores neón diferenciados y translúcidos para permitir encenderlos/apagarlos en Google Earth.
        También inyecta el pin del radar y el círculo de cobertura teórica en rojo.
        """
        from utils.geo import cargar_sensores, GeoTools
        
        # Parsear SAC/SIC
        sac, sic = None, None
        if isinstance(sac_sic, str):
            parts = sac_sic.split('/')
            if len(parts) == 2:
                sac, sic = int(parts[0]), int(parts[1])
        elif isinstance(sac_sic, tuple):
            sac, sic = sac_sic[0], sac_sic[1]
            
        if sac is None or sic is None:
            print(f"[Exporter] Identificador sac_sic inválido: {sac_sic}")
            return False
            
        if output_file is None:
            output_file = f"cobertura_radar_{sac}_{sic}.kmz"
            
        try:
            output_file = os.path.abspath(output_file).replace('\\', '/')
            # Asegurar directorio de salida
            dir_name = os.path.dirname(output_file)
            if dir_name:
                os.makedirs(dir_name, exist_ok=True)
                
            # Cargar parámetros del sitio
            sensores = cargar_sensores("default-site-params")
            if not sensores:
                # Buscar en directorio padre por si acaso
                base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                sensores = cargar_sensores(os.path.join(base_dir, "default-site-params"))
                
            radar_info = sensores.get((sac, sic))
            if not radar_info:
                print(f"[Exporter] Parámetros del sitio no encontrados para el radar {sac}/{sic}")
                return False
                
            radar_lat = radar_info['lat']
            radar_lon = radar_info['lon']
            radar_name = radar_info.get('name', f"Radar {sac}/{sic}")
            
            # Consultar todos los ploteos del sensor con lat, lon y flight_level
            def query_plots(conn):
                return conn.execute(f"""
                    SELECT lat, lon, flight_level 
                    FROM asterix_plots 
                    WHERE sac_sic = '{sac}/{sic}' AND lat != 0.0 AND lon != 0.0
                """).fetchall()

            if self.repo_db and self.repo_db.conn:
                cursor = self.repo_db.conn.cursor()
                plots = query_plots(cursor)
                cursor.close()
            else:
                with duckdb.connect(self.db_path, read_only=True) as conn:
                    plots = query_plots(conn)
                    
            if not plots:
                print(f"[Exporter] No se encontraron ploteos válidos en la base de datos para el radar {sac}/{sic}")
                return False
                
            print(f"[Exporter] Generando mapa de cobertura multinivel para {radar_name} con {len(plots)} ploteos...")
            
            # Clasificar los ploteos por bandas de Flight Level
            plots_by_level = {
                50: [],
                100: [],
                150: [],
                200: [],
                250: [],
                300: []
            }
            
            for lat, lon, fl_str in plots:
                fl_val = None
                if fl_str is not None and fl_str != "---":
                    try:
                        fl_val = float(fl_str)
                        # Detección y normalización robusta: Si el valor está en pies (ej. 25000 o 5000), 
                        # convertir a Flight Level (FL) dividiendo por 100.
                        # Consideramos valores mayores a 450 como pies (el techo de vuelo comercial es ~FL450).
                        if fl_val > 450.0:
                            fl_val = fl_val / 100.0
                    except (ValueError, TypeError):
                        pass
                
                if fl_val is None:
                    continue  # Requiere nivel de vuelo para clasificar en el mapa multinivel
                    
                # Clasificar
                if 25 <= fl_val < 75:
                    plots_by_level[50].append((lat, lon))
                elif 75 <= fl_val < 125:
                    plots_by_level[100].append((lat, lon))
                elif 125 <= fl_val < 175:
                    plots_by_level[150].append((lat, lon))
                elif 175 <= fl_val < 225:
                    plots_by_level[200].append((lat, lon))
                elif 225 <= fl_val < 275:
                    plots_by_level[250].append((lat, lon))
                elif fl_val >= 275:
                    plots_by_level[300].append((lat, lon))
                    
            # Inicializar KML principal
            kml = simplekml.Kml(name=f"Cobertura Real - {radar_name}")
            
            # 1. Añadir el pin del radar en el root
            radar_pin = kml.newpoint(name=radar_name, coords=[(radar_lon, radar_lat)])
            radar_pin.style.iconstyle.icon.href = 'http://maps.google.com/mapfiles/kml/shapes/target.png'
            radar_pin.style.iconstyle.scale = 1.2
            
            # Helper interno para construir el contorno suavizado de cada nivel
            def build_level_contour(level_plots):
                if len(level_plots) < 10:
                    return None
                    
                # Dividir en 360 sectores acimutales
                sectores = [[] for _ in range(360)]
                for lat, lon in level_plots:
                    dist_m, az_deg = GeoTools.calculate_distance_and_azimuth(radar_lat, radar_lon, lat, lon)
                    r_nm = GeoTools.meters_to_nm(dist_m)
                    sector_idx = int(math.floor(az_deg)) % 360
                    sectores[sector_idx].append(r_nm)
                    
                # Percentil 95
                rangos_max = [0.0] * 360
                for idx in range(360):
                    val_sector = sectores[idx]
                    if val_sector:
                        val_sector.sort()
                        k = (len(val_sector) - 1) * 0.95
                        f = math.floor(k)
                        c = math.ceil(k)
                        if f == c:
                            rangos_max[idx] = float(val_sector[int(k)])
                        else:
                            rangos_max[idx] = float(val_sector[f] * (c - k) + val_sector[c] * (k - f))
                    else:
                        rangos_max[idx] = 0.0
                        
                # Encontrar sectores no vacíos
                non_empty_indices = [i for i, r in enumerate(rangos_max) if r > 0.0]
                if not non_empty_indices:
                    return None
                    
                # Interpolación lineal circular
                if len(non_empty_indices) < 360:
                    for idx in range(360):
                        if rangos_max[idx] == 0.0:
                            prev_idx = max([i for i in non_empty_indices if i < idx], default=None)
                            if prev_idx is None:
                                prev_idx = max(non_empty_indices)
                            next_idx = min([i for i in non_empty_indices if i > idx], default=None)
                            if next_idx is None:
                                next_idx = min(non_empty_indices)
                                
                            d1 = (idx - prev_idx) % 360
                            d2 = (next_idx - idx) % 360
                            total_d = d1 + d2
                            if total_d > 0:
                                rangos_max[idx] = (rangos_max[prev_idx] * (d2 / total_d) + 
                                                   rangos_max[next_idx] * (d1 / total_d))
                            else:
                                rangos_max[idx] = rangos_max[prev_idx]
                                
                # Suavizado de bordes con promedio móvil circular (ventana 15°)
                rangos_suaves = [0.0] * 360
                window_size = 15
                half_w = window_size // 2
                for idx in range(360):
                    vals = []
                    for w in range(-half_w, half_w + 1):
                        vals.append(rangos_max[(idx + w) % 360])
                    rangos_suaves[idx] = sum(vals) / len(vals)
                    
                # Convertir a coordenadas geodésicas destino
                coords = []
                for idx in range(360):
                    r_nm = rangos_suaves[idx]
                    lat_dest, lon_dest = GeoTools.polar_to_wgs84(radar_lat, radar_lon, float(idx), r_nm)
                    coords.append((lon_dest, lat_dest))
                coords.append(coords[0])
                return coords

            # Colores ABGR estéticos y vibrantes para cada nivel
            level_styles = {
                50:  {"fill": "50003aff", "border": "ff003aff", "name": "FL 050 (Bajo Nivel - Rojo Coral)"},
                100: {"fill": "5000a5ff", "border": "ff00a5ff", "name": "FL 100 (Naranja)"},
                150: {"fill": "5000ffff", "border": "ff00ffff", "name": "FL 150 (Amarillo Neón)"},
                200: {"fill": "5000ff00", "border": "ff00ff00", "name": "FL 200 (Medio Nivel - Verde)"},
                250: {"fill": "50ffff00", "border": "ffffff00", "name": "FL 250 (Cian / Celeste)"},
                300: {"fill": "50ff00ff", "border": "ffff00ff", "name": "FL 300 (Alto Nivel - Magenta)"}
            }

            any_generated = False

            # Generar carpeta y polígono para cada uno de los 6 niveles solicitados
            for lvl in sorted(level_styles.keys()):
                lvl_plots = plots_by_level[lvl]
                style = level_styles[lvl]
                
                print(f"[Exporter] Procesando nivel {style['name']} con {len(lvl_plots)} ploteos...")
                coords_poly = build_level_contour(lvl_plots)
                
                if coords_poly:
                    # Crear carpeta dedicada para el nivel
                    folder = kml.newfolder(name=style['name'])
                    
                    # Añadir el polígono de cobertura
                    poly = folder.newpolygon(name=f"Cobertura Real - FL {lvl:03d}")
                    poly.outerboundaryis = coords_poly
                    poly.style.polystyle.color = style['fill']
                    poly.style.polystyle.fill = 1
                    poly.style.polystyle.outline = 1
                    poly.style.linestyle.color = style['border']
                    poly.style.linestyle.width = 2
                    
                    any_generated = True
                else:
                    print(f"[Exporter] Sin ploteos suficientes en FL {lvl:03d} para estimar su contorno.")

            if not any_generated:
                print("[Exporter] No se encontraron suficientes ploteos en ninguna de las bandas FL para generar coberturas.")
                return False

            # 3. Añadir carpeta para Límite Teórico (240 NM)
            folder_teorico = kml.newfolder(name="Límite Cobertura Teórica")
            coords_circulo = []
            for idx in range(360):
                lat_dest, lon_dest = GeoTools.polar_to_wgs84(radar_lat, radar_lon, float(idx), theoretical_range_nm)
                coords_circulo.append((lon_dest, lat_dest))
            coords_circulo.append(coords_circulo[0])
            
            circ = folder_teorico.newlinestring(name=f"Cobertura Teórica ({theoretical_range_nm} NM)")
            circ.coords = coords_circulo
            circ.style.linestyle.color = "ff0000ff"  # Rojo sólido
            circ.style.linestyle.width = 2
            
            kml.savekmz(output_file)
            print(f"[Exporter] Mapa de Cobertura Multinivel generado exitosamente: {output_file}")
            return True
            
        except Exception as e:
            print(f"[Exporter] Error al generar Mapa de Cobertura: {e}")
            return False

