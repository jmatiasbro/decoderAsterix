#!/usr/bin/env python3
"""
RADAR SELECTOR DOCUMENTATION

El módulo radar_selector.py permite seleccionar y visualizar
parámetros de radares disponibles en el directorio default-site-params/.

CARACTERÍSTICAS:
================

1. SELECCIÓN INTERACTIVA
   - Elegir uno o más radares de la lista disponible
   - Opción para seleccionar todos los radares
   - Opción para cancelar la selección

2. VISUALIZACIÓN DE DETALLES
   - Parámetros técnicos del radar (tipo, rango, frecuencia)
   - Ubicación geográfica (latitud, longitud, altitud)
   - Características operacionales

3. EXPORTACIÓN
   - Guardar configuración en archivo JSON
   - Fácil integración con otras herramientas

USO DESDE LÍNEA DE COMANDOS
============================

Ejecutar selector independiente:
    python radar_selector.py

Seleccionar un radar específico:
    Ingresa: 1
    (Muestra detalles del primer radar)

Seleccionar múltiples radares:
    Ingresa: 1,2,3
    (Muestra detalles de radares 1, 2 y 3)

Seleccionar todos los radares:
    Ingresa: all
    (Muestra todos los radares disponibles)

Cancelar selección:
    Ingresa: none
    (Vuelve al menú anterior)

USO DESDE PYTHON
=================

from radar_selector import RadarSelector

# Crear instancia del selector
selector = RadarSelector()

# Ver todos los radares disponibles
selector.display_available_radars()

# Obtener datos de un radar específico
data = selector.get_radar_data("RADAR001")
print(f"Radar: {data['name']}")
print(f"Tipo: {data['type']}")
print(f"Ubicación: {data['location']}")

# Obtener datos de múltiples radares
all_radars = list(selector.radars.keys())
multi_data = selector.get_all_radar_data(all_radars[:2])

# Exportar a JSON
selector.export_selected_radars(all_radars[:2], "mi_radares.json")

ESTRUCTURA DE DATOS RADAR
==========================

{
  "radar_id": "RADAR001",
  "name": "Nombre del Radar",
  "type": "PSR|SSR|MLAT",           # Tipo de radar
  "category": "CAT001|CAT048|...",  # Categoría ASTERIX
  "location": {
    "latitude": 40.416775,          # Latitud (decimales)
    "longitude": -3.703790,         # Longitud (decimales)
    "altitude": 650,                # Altitud (metros)
    "coordinates_dms": "..."        # Formato DMS
  },
  "range": 280,                     # Rango de detección (km)
  "azimuth_coverage": 360,          # Cobertura acimut (grados)
  "elevation_angle": 1.5,           # Ángulo de elevación (grados)
  "frequency": "C-band",            # Banda de frecuencia
  "pulse_repetition_frequency": 400,# PRF (Hz)
  "antenna_rotation_speed": 12,     # Velocidad rotación (rpm)
  "detection_probability": 0.95,    # Probabilidad detección
  "false_alarm_rate": 1e-6          # Tasa falsa alarma
}

TIPOS DE RADAR SOPORTADOS
==========================

PSR (Primary Surveillance Radar)
- Radar primario convencional
- Detección basada en reflexión
- Categoría ASTERIX: CAT001

SSR (Secondary Surveillance Radar)
- Radar secundario Mode S/A/C
- Detección con transpondedor de aeronave
- Categoría ASTERIX: CAT048

MLAT (Multilateration System)
- Sistema de multilateración
- Basado en Mode S TDOA
- Categoría ASTERIX: CAT021

INTEGRACIÓN CON MAIN.PY
=======================

En el menú principal (opción 8):
1. Se abre el selector de radares
2. Elige los radares que deseas consultar
3. Visualiza los parámetros técnicos
4. Opción de exportar a JSON

Esto es útil para:
- Verificar configuración de radares antes de decodificar
- Documentar los radares utilizados
- Compartir configuraciones entre usuarios

EJEMPLOS
========

Ejemplo 1: Ver un radar específico
----------------------------------
selector = RadarSelector()
radar_id = list(selector.radars.keys())[0]
selector.display_radar_details([radar_id])

Ejemplo 2: Filtrar radares por tipo
-----------------------------------
selector = RadarSelector()
psr_radars = [
    rid for rid, data in selector.radars.items()
    if data['data'].get('type') == 'PSR'
]
selector.display_radar_details(psr_radars)

Ejemplo 3: Listar frecuencias de todos los radares
-------------------------------------------------
selector = RadarSelector()
for rid, data in selector.radars.items():
    freq = data['data'].get('frequency', 'Unknown')
    print(f"{rid}: {freq}")

RESOLUCIÓN DE PROBLEMAS
=======================

¿No encuentra radares?
- Verifica que exista carpeta: default-site-params/
- Verifica que haya archivos .json en esa carpeta

¿Error al cargar radares?
- Verifica la sintaxis de los archivos JSON
- Comprueba permisos de lectura en los archivos

¿No exporta correctamente?
- Verifica permisos de escritura en el directorio
- Comprueba espacio en disco disponible

NOTA TÉCNICA
============

El selector automáticamente:
1. Busca la carpeta default-site-params/
2. Lee el archivo radar_list.json (si existe)
3. Carga los archivos JSON individuales de cada radar
4. Indexa por radar_id para acceso rápido

Los datos se mantienen en memoria durante la sesión
sin modificar los archivos originales.
"""

if __name__ == "__main__":
    print(__doc__)
