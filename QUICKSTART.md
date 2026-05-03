# ASTERIX Analyzer - Guía de Inicio Rápido

## ✅ Checklist de Instalación

- [ ] Python 3.8+ instalado
- [ ] Dependencias instaladas: `pip install -r requirements.txt`
- [ ] Suite de pruebas pasada: `python test_suite.py`

## 📦 Contenido del Proyecto

```
decode_asterix/
├── main.py                 # Punto de entrada principal
├── decoders.py             # Decodificadores ASTERIX (048, 001, 021, 034, 002)
├── geo_tools.py            # Conversiones geoespaciales y sensores
├── exporters.py            # Exportadores (KML, GeoJSON, CSV, Reportes)
├── config.py               # Configuración de sensores conocidos
├── examples.py             # Ejemplos de uso programático
├── test_suite.py           # Suite de pruebas automatizadas
├── requirements.txt        # Dependencias del proyecto
├── README.md               # Documentación completa
├── TECHNICAL.md            # Documentación técnica detallada
└── QUICKSTART.md           # Este archivo
```

## 🚀 Inicio Rápido

### 1. Instalación Básica

```bash
# Instalar dependencias
pip install -r requirements.txt

# Verificar instalación
python test_suite.py
```

### 2. Uso Más Común: Procesar un PCAP

```bash
# Modo automático
python main.py archivo.pcap

# Especificar directorio de salida
python main.py archivo.pcap --output resultados/

# Con posición manual del radar
python main.py archivo.pcap --sensor 1 1 40.4167 -3.7038 --elevation 2000
```

### 3. Modo Interactivo

```bash
python main.py --interactive
```

## 🗂️ Archivos de Salida

En la carpeta de salida (default: `output/`):

| Archivo | Formato | Uso |
|---------|---------|-----|
| `asterix_data.kml` | KML | Google Earth, visualización 3D |
| `asterix_data.geojson` | GeoJSON | QGIS, mapas web, análisis SIG |
| `asterix_data.csv` | CSV | Excel, análisis de datos |
| `analysis_report.txt` | Texto | Estadísticas de cobertura |

## 📊 Categorías Soportadas

| Código | Nombre | Soporte |
|--------|--------|---------|
| CAT 048 | Monoradar Mode S | ✅ Completo |
| CAT 001 | Monoradar Estándar | ✅ Completo |
| CAT 021 | ADS-B | ✅ Completo |
| CAT 034 | Service Messages (Pos. Radar) | ✅ Completo |
| CAT 002 | Configuración Radar | ✅ Completo |

## 🔍 Características Principales

### ✅ Decodificación
- Parseo automático de FSPEC
- Manejo de campos opcionales
- 5 categorías ASTERIX soportadas
- Factores de escala LSB correctos

### ✅ Geoespacial
- Conversión Slant Range → Ground Range
- Coordenadas Polares → WGS-84
- Great Circle + Vincenty (opcional)
- Manejo de múltiples sensores (SAC/SIC)

### ✅ Exportación
- KML con sensores organizados
- GeoJSON estándar
- CSV importable
- Reportes de análisis

## 💡 Ejemplos Comunes

### Analizar PCAP de Madrid-Barajas
```bash
python main.py barajas_radar.pcap --sensor 1 1 40.4746 -3.5889 --elevation 2000 --output barajas/
```

### Procesar múltiples archivos
```bash
for f in *.pcap; do
  python main.py "$f" --output "resultados/$f"
done
```

### Modo interactivo con configuración avanzada
```bash
python main.py --interactive
# En el menú:
# 1. Cargar archivo
# 2. Configurar sensor (si no viene en CAT 034)
# 3. Decodificar
# 4. Exportar
# 5. Ver estadísticas
```

## ⚙️ Configuración Avanzada

### Agregar Sensor con Ingreso Interactivo (Recomendado)

Desde Python, usar la función interactiva:

```python
from config import input_sensor_interactive, add_sensor

# Ingreso interactivo completo con soporte para DMS
sensor_data = input_sensor_interactive()
```

Esto te preguntará interactivamente:
```
SAC (0-255): 3
SIC (0-255): 1
Nombre del sensor (ej: Madrid-Barajas): Mi Radar
Ingrese Latitud (formato: GD o DMS)
Ejemplos: 40.474635 o "40 28 28.686 N"
Latitud: 41 30 0 N
Ingrese Longitud (formato: GD o DMS)
Ejemplos: -3.588860 o "-3 35 19.896 W"
Longitud: -3 30 0 W
Elevación (pies, default 0): 1500
Descripción (opcional): Radar en zona de pruebas
```

### Agregar Sensor Programáticamente

Formato de grados decimales:
```python
from config import add_sensor

add_sensor(
    sac=3, 
    sic=1, 
    name='Mi Radar',
    latitude=41.5,
    longitude=-3.5,
    elevation=1500
)
```

### Conversión de Coordenadas - Formatos Soportados

#### Grados Decimales (DD)
```python
from config import dms_to_string
print(dms_to_string(40.474635))  # → "40° 28' 28.686" N"
```

#### Grados, Minutos, Segundos (DMS)
```python
from config import dms_to_decimal, parse_dms_string

# Convierte DMS a decimal
lat = dms_to_decimal(40, 28, 28.686, 'N')  # → 40.474635

# Parsea string DMS
lat2 = parse_dms_string("40 28 28.686 N")   # → 40.474635
lat3 = parse_dms_string("40:28:28.686N")    # → 40.474635
```

### Entrada Interactiva de Coordenadas

```python
from config import input_coordinate_interactive

# Solicita interactivamente latitud o longitud
latitude = input_coordinate_interactive("Latitud")
longitude = input_coordinate_interactive("Longitud")

# Acepta ambos formatos:
# 40.474635 ← Grados decimales
# 40 28 28.686 N ← DMS
```

### Configuración Avanzada del Sistema

Editar `config.py`:

```python
# Usar fórmula Vincenty (más preciso)
GEO_CONFIG['use_vincenty'] = True

# Saltar categorías desconocidas silenciosamente
DECODER_CONFIG['skip_unknown_categories'] = True
```

## 📚 Documentación

- **README.md** - Documentación completa de uso
- **TECHNICAL.md** - Especificación técnica (algoritmos, fórmulas)
- **examples.py** - Ejemplos de código Python
- **config.py** - Referencia de configuración

## 🧪 Pruebas

```bash
# Ejecutar suite completa
python test_suite.py

# Pruebas individuales disponibles:
# - test_imports: Verificar módulos
# - test_bitstream: Lectura de bits
# - test_geo_conversion: Conversiones
# - test_sensor_registry: Sensores
# - test_exporters: Exportación
```

## ⚡ Troubleshooting

### Error: "No ASTERIX data found in pcap"
→ El PCAP no contiene datos ASTERIX o están en puertos no estándar

### Error: "FileNotFoundError"
→ Verificar ruta del archivo (usar rutas relativas o absolutas consistentemente)

### Coordenadas WGS-84 no aparecen
→ Necesita posición del radar (CAT 034) o usar `--sensor` para especificar

### Lentitud en procesamiento
→ Esto es normal para archivos > 100 MB. Para ver progreso, editar `main.py`

## 📞 Soporte

Para reportar issues:
1. Verificar requirements.txt
2. Ejecutar `test_suite.py`
3. Consultar TECHNICAL.md para entender el algoritmo
4. Revisar ejemplos.py para casos de uso

## 📝 Próximas Mejoras Previstas

- [ ] Soporte para RASS-S (.sr4d)
- [ ] Visualización en tiempo real
- [ ] Análisis de gaps de cobertura
- [ ] API REST
- [ ] Interfaz web

---

**Versión:** 2.0 (Completa)  
**Última actualización:** 2026-04-27  
**Estado:** ✅ Producción
