# ASTERIX Air Traffic Surveillance Data Analyzer

Herramienta profesional para procesar, decodificar y analizar datos **ASTERIX** (All Purpose Structured Radar Information eXchange) de sistemas de vigilancia de tráfico aéreo (ATS).

Genera mapas de cobertura geoespaciales y analiza datos de múltiples categorías de radar con conversión automática de coordenadas polares a WGS-84.

## Características Principales

### 📡 Decodificación de Categorías ASTERIX

- **CAT 048** (Monoradar Mode S) - Targets primarios Mode S
- **CAT 001** (Monoradar Estándar) - Targets primarios básicos  
- **CAT 021** (ADS-B) - Datos de vigilancia dependiente automática
- **CAT 034** (Service Messages) - Información de posición y configuración del radar
- **CAT 062** (System Track Data) - Trazas procesadas por el sistema
- **CAT 002** (Service Messages) - Información de velocidad de antena

### 🗺️ Procesamiento Geoespacial

- Conversión de coordenadas polares (Azimut, Rango Oblicuo) a WGS-84
- Conversión de Slant Range a Ground Range usando Flight Level
- Fórmulas de trigonometría esférica (Great Circle) y Vincenty
- Manejo automático de SAC/SIC (System Area Code / System Identification Code)
- Soporte para múltiples sensores independientes

### 📊 Exportación de Datos

- **KML** - Organizado por sensores (compatible con Google Earth)
- **GeoJSON** - Para QGIS, mapas web y análisis SIG
- **CSV** - Tablas de análisis con timestamps y altitudes
- **Reportes de Análisis** - Estadísticas de cobertura y sensores

### 📥 Formatos Soportados

- **.pcap** - Archivos de captura de paquetes de red
- **.ast** - Archivos de datos ASTERIX crudos

## Instalación

### Requisitos
- Python 3.8+
- pip (gestor de paquetes de Python)

### Pasos

1. **Clonar o descargar el repositorio**
```bash
git clone <repository-url>
cd decode_asterix
```

2. **Crear entorno virtual (recomendado)**
```bash
python -m venv venv

# Activar en Windows
venv\Scripts\activate

# Activar en Linux/Mac
source venv/bin/activate
```

3. **Instalar dependencias**
```bash
pip install -r requirements.txt
```

## Uso

### Modo Línea de Comandos

#### Decodificar archivo PCAP
```bash
python main.py archivo.pcap
```

#### Decodificar archivo AST
```bash
python main.py archivo.ast
```

#### Especificar directorio de salida
```bash
python main.py archivo.pcap --output resultados/
```

#### Configurar posición de sensor
```bash
python main.py archivo.pcap --sensor 1 1 40.416775 -3.703790 --elevation 2000
```

**Parámetros:**
- `SAC`: System Area Code (0-255)
- `SIC`: System Identification Code (0-255)
- `LATITUD`: En grados decimales
- `LONGITUD`: En grados decimales
- `--elevation`: Elevación en pies (opcional, default: 0)

### Modo Interactivo

```bash
python main.py --interactive
```

Permite:
1. Cargar archivos
2. Configurar sensores manualmente
3. Decodificar datos
4. Exportar resultados
5. Ver estadísticas de cobertura

## Estructura del Proyecto

```
decode_asterix/
├── main.py                 # Punto de entrada principal
├── decoders.py            # Decodificadores de categorías ASTERIX
├── geo_tools.py           # Herramientas geoespaciales y conversiones
├── exporters.py           # Exportadores KML, GeoJSON, CSV
├── requirements.txt       # Dependencias del proyecto
└── README.md              # Este archivo
```

## Módulos Principales

### decoders.py

**Clases:**
- `BitStream` - Lectura bit a bit de datos binarios
- `AsterixDecoder` - Parser genérico de FSPEC
- `CAT048Decoder` - Decodificador CAT 048 (Monoradar Mode S)
- `CAT001Decoder` - Decodificador CAT 001 (Monoradar Estándar)
- `CAT021Decoder` - Decodificador CAT 021 (ADS-B)
- `CAT034Decoder` - Decodificador CAT 034 (Service Messages)
- `CAT002Decoder` - Decodificador CAT 002 (Configuración Radar)

**Funciones:**
- `decode_asterix_stream(data)` - Decodifica flujo completo

### geo_tools.py

**Clases:**
- `GeoTools` - Herramientas geoespaciales estáticas
- `SensorRegistry` - Registro de sensores únicos (SAC/SIC)
- `TargetProcessor` - Procesador de targets con conversión de coordenadas

**Conversiones Soportadas:**
- Slant Range → Ground Range (considerando Flight Level)
- Coordenadas Polares → WGS-84 (Great Circle)
- Fórmula Vincenty para mayor precisión

**Factores de Escala LSB (Least Significant Bit):**
- Latitud/Longitud: 180 / 2²³ grados
- Azimut: 360 / 2¹⁶ grados  
- Altitud: 1/4 FL o 25 pies
- Flight Level: expresado en 1/4 de FL

### exporters.py

**Clases:**
- `KMLExporter` - Genera KML para Google Earth
- `GeoJSONExporter` - Genera GeoJSON para QGIS
- `CSVExporter` - Genera CSV para análisis
- `ReportGenerator` - Genera reportes de análisis

## Flujo de Procesamiento

```
Archivo PCAP/AST
    ↓
┌─────────────────────┐
│  Extracción de datos│
│  ASTERIX del pcap   │
└──────────┬──────────┘
           ↓
┌──────────────────────┐
│  Decodificación de   │
│  Categorías ASTERIX  │
│(048,001,021,034,062,02)│
└──────────┬───────────┘
           ↓
┌──────────────────────┐
│  Registro de Sensores│
│  (SAC/SIC únicos)    │
└──────────┬───────────┘
           ↓
┌──────────────────────┐
│  Conversión de       │
│  Coordenadas         │
│  Polares → WGS-84    │
└──────────┬───────────┘
           ↓
┌──────────────────────────────────────┐
│  Exportación a Múltiples Formatos    │
│  KML | GeoJSON | CSV | Reportes      │
└──────────────────────────────────────┘
```

## Campos ASTERIX Soportados

### CAT 048 (Monoradar Mode S)
- **I048/010** - Data Source Identifier (SAC/SIC)
- **I048/020** - Target Report Descriptor
- **I048/040** - Posición Polar (Azimut, Rango)
- **I048/042** - Posición Cartesiana Calculada
- **I048/070** - Mode-3/A Code
- **I048/080** - Mode-C Code
- **I048/090** - Flight Level (Nivel de Vuelo)
- **I048/140** - Time of Day
- **I048/250** - Estado de la Traza (Track Status)
- **I048/200** - Velocidad Polar Calculada

### CAT 001 (Monoradar Standard)
- **I001/010** - Data Source Identifier
- **I001/020** - Plot/Track Descriptor
- **I001/040** - Posición Polar
- **I001/070** - Mode-3/A Code

### CAT 021 (ADS-B)
- **I021/010** - Data Source Identifier
- **I021/170** - Target Identification (Callsign)
- **I021/080** - Mode S Code
- **I021/070** - Mode-3/A Code (Squawk)
- **I021/130** - Posición WGS-84
- **I021/131** - Posición WGS-84 de Alta Resolución
- **I021/145** - Flight Level
- **I021/140** - Altitud Geométrica
- **I021/160** - Vector de Velocidad en Tierra
### CAT 034 (Service Messages)
- **I034/010** - Data Source Identifier
- **I034/120** - 3D Radar Position (Lat, Lon, Altura)

### CAT 062 (System Track Data)
- **I062/010** - Data Source Identifier (SAC/SIC)
- **I062/040** - Track Number
- **I062/100** - Calculated Track Position (WGS-84)
- **I062/185** - Calculated Track Velocity (Cartesian, Vx/Vy)
- **I062/380** - Aircraft Derived Data (Mode S, Callsign, etc.)

### CAT 002 (Configuración Radar)
- **I002/010** - Data Source Identifier
- **I002/150** - Antenna Rotation Speed

## Ejemplos de Uso

### Ejemplo 1: Análisis Básico de PCAP

```bash
python main.py Martescordoba_radar2.pcap
```

### Ejemplo 2: Análisis con Posición Manual del Radar

```bash
python main.py datos.ast --sensor 1 1 40.416775 -3.703790 --elevation 2000 --output resultados/
```

### Ejemplo 3: Procesamiento Interactivo

```bash
python main.py --interactive
# Luego cargar archivos y configurar sensores interactivamente
```

## Salida

### Archivos Generados

En el directorio de salida (`output/` por defecto):

1. **asterix_data.kml** - Mapa para Google Earth
   - Carpetas organizadas por sensor (SAC/SIC)
   - Placemarks con información de targets
   - Etiquetas Mode-3/A y altitud

2. **asterix_data.geojson** - Mapa para QGIS/Web
   - GeoJSON estándar con todas las propiedades
   - Compatible con aplicaciones GIS

3. **asterix_data.csv** - Tabla de análisis
   - Columnas: timestamp, categoría, SAC, SIC, lat, lon, altitud, etc.
   - Importable en Excel, QGIS, R, Python

4. **analysis_report.txt** - Reporte de análisis
   - Estadísticas por categoría
   - Información de sensores
   - Cobertura geográfica

## Consideraciones Técnicas

### Manejo de FSPEC

La herramienta decodifica automáticamente el **FSPEC** (Field Specification) para identificar qué campos opcionales están presentes en cada mensaje, sin necesidad de configuración manual.

### Factores de Escala

Se aplican correctamente los LSB (Least Significant Bit) especificados en la norma ASTERIX:

- **Posición**: LSB = 180 / 2²³ grados
- **Azimut**: LSB = 360 / 2¹⁶ grados
- **Altitud**: LSB = 25 pies (1/4 FL)
- **Rango Oblicuo**: LSB = 1/256 NM

### Conversiones Geodésicas

Se utilizan fórmulas de **trigonometría esférica** para conversiones estándar y **fórmula de Vincenty** para cálculos más precisos en distancias largas.

## Depuración y Troubleshooting

### Error: "No ASTERIX data found in pcap"
- Verificar que el PCAP contenga paquetes UDP/TCP con datos ASTERIX
- Los datos pueden estar en puertos no estándar

### Error: "Archivo no encontrado"
- Verificar ruta completa o relativa del archivo
- En Windows, usar `/` o `\\` en rutas

### Registros sin coordenadas WGS-84
- Requiere que el radar especifique su posición (CAT 034/120) O
- Configurar manualmente con `--sensor`

## Selector de Radares (Radar Selector)

El módulo `radar_selector.py` permite seleccionar y ver parámetros de radares disponibles desde el directorio `default_site_params/`.

### Uso

#### Modo Independiente
```bash
python radar_selector.py
```

#### Integrado en Menú Principal
```bash
python main.py
# Seleccionar opción 8 en el menú interactivo
```

### Características

- **Selección Interactiva**: Elige uno, varios o todos los radares disponibles
- **Visualización**: Consulta parámetros detallados de cada radar
- **Exportación**: Guarda configuraciones en JSON

### Ejemplos de Uso

```python
from radar_selector import RadarSelector

# Crear selector
selector = RadarSelector()

# Ver radares disponibles
selector.display_available_radars()

# Seleccionar radares interactivamente
selected_ids = selector.select_radars_interactive()

# Ver detalles de los seleccionados
selector.display_radar_details(selected_ids)

# Exportar a archivo JSON
selector.export_selected_radars(selected_ids, "radares_configurados.json")
```

### Opciones de Selección

- Ingrese números separados por comas: `1,2,3`
- Seleccionar todos: `all`
- Cancelar: `none`

### Estructura de Datos de Radar

```json
{
  "radar_id": "RADAR001",
  "name": "Primary Surveillance Radar - Madrid",
  "type": "PSR",
  "category": "CAT001",
  "location": {
    "latitude": 40.416775,
    "longitude": -3.703790,
    "altitude": 650,
    "coordinates_dms": "40°25'00.39\"N 3°42'14.04\"W"
  },
  "range": 280,
  "azimuth_coverage": 360,
  "elevation_angle": 1.5,
  "frequency": "C-band",
  "pulse_repetition_frequency": 400,
  "antenna_rotation_speed": 12,
  "detection_probability": 0.95,
  "false_alarm_rate": 1e-6
}
```

### Scripts de Ejemplo

Ver `example_radar_selector.py` para ejemplos de uso programático.

```bash
python example_radar_selector.py
```

## Próximas Mejoras

- [ ] Visualización de cobertura de radar en tiempo real
- [ ] Análisis de rendimiento y gaps de cobertura
- [ ] Soporte para múltiples archivos en batch
- [ ] API REST para integración

## Licencia

[Especificar licencia si es necesario]

## Contacto y Soporte

Para reportar issues o sugerencias, consultar la documentación oficial de ASTERIX en:
- https://www.eurocontrol.int/asterix

## Referencias

- **EUROCONTROL ASTERIX** - Especificación oficial
- **WGS-84** - World Geodetic System 1984
- **Vincenty Formula** - Geodetic calculations on an ellipsoid# decoderAsterix
