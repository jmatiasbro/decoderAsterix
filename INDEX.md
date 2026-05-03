# Índice de Archivos - ASTERIX Analyzer v2.0

## 📑 Archivos del Proyecto

### 🎯 Archivos Principales (Código)

| Archivo | Líneas | Descripción |
|---------|--------|-------------|
| [main.py](main.py) | 280 | Punto de entrada, orquestador principal, interfaz CLI e interactiva |
| [decoders.py](decoders.py) | 480 | Decodificadores de 6 categorías ASTERIX + BitStream para parseo |
| [geo_tools.py](geo_tools.py) | 380 | Conversiones geoespaciales, SensorRegistry, TargetProcessor |
| [exporters.py](exporters.py) | 250 | Exportadores KML, GeoJSON, CSV, y generador de reportes |
| [config.py](config.py) | 100 | Configuración de sensores conocidos y parámetros del sistema |

### 📚 Documentación

| Archivo | Propósito | Para Quién |
|---------|-----------|-----------|
| [README.md](README.md) | Guía completa de instalación y uso | Usuarios finales |
| [QUICKSTART.md](QUICKSTART.md) | Inicio rápido en 5 minutos | Usuarios primerizos |
| [TECHNICAL.md](TECHNICAL.md) | Especificación técnica detallada | Desarrolladores |
| [IMPLEMENTATION_SUMMARY.md](IMPLEMENTATION_SUMMARY.md) | Resumen de implementación | Administradores de proyecto |
| [INDEX.md](INDEX.md) | Este archivo - Índice completo | Cualquiera |

### 🧪 Desarrollo y Pruebas

| Archivo | Descripción |
|---------|-------------|
| [test_suite.py](test_suite.py) | Suite completa de pruebas automáticas |
| [examples.py](examples.py) | 10 ejemplos prácticos de uso |

### ⚙️ Configuración

| Archivo | Contenido |
|---------|----------|
| [requirements.txt](requirements.txt) | Dependencias del proyecto |

### 📦 Datos de Ejemplo

| Archivo | Descripción |
|---------|-------------|
| [Martescordoba_radar2.pcap](Martescordoba_radar2.pcap) | Archivo PCAP de ejemplo para pruebas |

---

## 🗂️ Estructura de Directorios

```
decode_asterix/
│
├── 📄 CÓDIGO FUENTE
│   ├── main.py              (Entrada principal)
│   ├── decoders.py          (Decodificadores)
│   ├── geo_tools.py         (Herramientas geoespaciales)
│   ├── exporters.py         (Exportadores)
│   └── config.py            (Configuración)
│
├── 📚 DOCUMENTACIÓN
│   ├── README.md            (Guía principal)
│   ├── QUICKSTART.md        (Inicio rápido)
│   ├── TECHNICAL.md         (Especificación técnica)
│   ├── IMPLEMENTATION_SUMMARY.md (Resumen de implementación)
│   └── INDEX.md             (Este archivo)
│
├── 🧪 PRUEBAS Y EJEMPLOS
│   ├── test_suite.py        (Suite de pruebas)
│   └── examples.py          (Ejemplos de código)
│
├── ⚙️ CONFIGURACIÓN
│   └── requirements.txt     (Dependencias)
│
├── 📦 DATOS
│   └── Martescordoba_radar2.pcap (PCAP de ejemplo)
│
└── 📁 output/               (Directorio de salida - generado al ejecutar)
    ├── asterix_data.kml     (Mapa para Google Earth)
    ├── asterix_data.geojson (Mapa para QGIS)
    ├── asterix_data.csv     (Tabla de datos)
    └── analysis_report.txt  (Reporte de análisis)
```

---

## 🚀 Cómo Usar Este Proyecto

### Paso 1: Leer la Documentación
1. **Primero:** [QUICKSTART.md](QUICKSTART.md) - 5 minutos
2. **Luego:** [README.md](README.md) - 15 minutos
3. **Si necesitas detalles:** [TECHNICAL.md](TECHNICAL.md) - 30 minutos

### Paso 2: Ejecutar las Pruebas
```bash
python test_suite.py
```

### Paso 3: Probar con el PCAP de Ejemplo
```bash
python main.py Martescordoba_radar2.pcap
```

### Paso 4: Ver Ejemplos de Código
- Consultar [examples.py](examples.py) para 10 casos de uso diferentes
- Copiar snippets según sea necesario

---

## 📖 Guía de Lectura por Rol

### 👨‍💼 Gestor de Proyecto / Stakeholder
1. Leer: [IMPLEMENTATION_SUMMARY.md](IMPLEMENTATION_SUMMARY.md)
2. Consultar: [QUICKSTART.md](QUICKSTART.md) - Checklist
3. Ver: [test_suite.py](test_suite.py) - Resultados de pruebas

### 👨‍💻 Desarrollador Principal
1. Leer: [TECHNICAL.md](TECHNICAL.md) - Completo
2. Estudiar: [decoders.py](decoders.py) - Lógica de decodificación
3. Revisar: [geo_tools.py](geo_tools.py) - Algoritmos geoespaciales
4. Examinar: [test_suite.py](test_suite.py) - Casos de prueba

### 🔧 Administrador del Sistema
1. Leer: [README.md](README.md) - Sección Instalación
2. Ejecutar: [test_suite.py](test_suite.py)
3. Configurar: [config.py](config.py) - Sensores conocidos
4. Mantener: Monitorear [requirements.txt](requirements.txt)

### 📊 Analista de Datos
1. Leer: [QUICKSTART.md](QUICKSTART.md) - Casos de uso
2. Usar: [examples.py](examples.py) - Ejemplos prácticos
3. Consultar: [README.md](README.md) - Sección Exportación

### 🎓 Estudiante / Aprendiz
1. Leer: [QUICKSTART.md](QUICKSTART.md)
2. Ver: [examples.py](examples.py)
3. Experimentar: [test_suite.py](test_suite.py)
4. Profundizar: [TECHNICAL.md](TECHNICAL.md)

---

## 📊 Estadísticas del Proyecto

| Métrica | Valor |
|---------|-------|
| **Líneas de Código** | ~2,500 |
| **Líneas de Documentación** | ~1,600 |
| **Categorías ASTERIX Soportadas** | 6 (CAT 001, 002, 021, 034, 048, 062) |
| **Campos Implementados** | 20+ |
| **Formatos de Exportación** | 4 (KML, GeoJSON, CSV, TXT) |
| **Módulos Principales** | 5 |
| **Pruebas Automatizadas** | 6 suites |
| **Ejemplos Prácticos** | 10 |
| **Requisito Python** | 3.8+ |
| **Dependencias Externas** | 1 (dpkt) |

---

## 🎯 Ruta de Aprendizaje Recomendada

### 📍 Nivel 1: Usuario Básico (30 minutos)
- [ ] Leer [QUICKSTART.md](QUICKSTART.md)
- [ ] Instalar dependencias: `pip install -r requirements.txt`
- [ ] Ejecutar ejemplo: `python main.py Martescordoba_radar2.pcap`
- [ ] Ver archivos generados en `output/`

### 📍 Nivel 2: Usuario Intermedio (2 horas)
- [ ] Leer [README.md](README.md) completo
- [ ] Probar modo interactivo: `python main.py --interactive`
- [ ] Revisar [examples.py](examples.py) - primeros 5 ejemplos
- [ ] Ejecutar `test_suite.py`

### 📍 Nivel 3: Usuario Avanzado (4 horas)
- [ ] Estudiar [TECHNICAL.md](TECHNICAL.md)
- [ ] Revisar todos los [examples.py](examples.py)
- [ ] Analizar [decoders.py](decoders.py) en detalle
- [ ] Personalizar [config.py](config.py) con sensores propios

### 📍 Nivel 4: Desarrollador (8+ horas)
- [ ] Leer código fuente completo
- [ ] Entender [geo_tools.py](geo_tools.py) a fondo
- [ ] Modificar [exporters.py](exporters.py) para nuevos formatos
- [ ] Contribuir con nuevas funcionalidades

---

## 🔗 Referencias Cruzadas

### Decodificación
- Implementado en: [decoders.py](decoders.py)
- Especificación: [TECHNICAL.md](TECHNICAL.md#7-categorías-asterix-y-campos-implementados)
- Ejemplos: [examples.py](examples.py#ejemplo-4-acceso-directo-a-decodificadores)
- Pruebas: [test_suite.py](test_suite.py#test_bitstream)

### Geoespacial
- Implementado en: [geo_tools.py](geo_tools.py)
- Especificación: [TECHNICAL.md](TECHNICAL.md#5-conversión-polares-a-wgs84)
- Ejemplos: [examples.py](examples.py#ejemplo-5-conversiones-geoespaciales)
- Pruebas: [test_suite.py](test_suite.py#test_geo_conversion)

### Exportación
- Implementado en: [exporters.py](exporters.py)
- Documentación: [README.md](README.md#salida)
- Ejemplos: [examples.py](examples.py#ejemplo-6-exportar-múltiples-formatos)
- Pruebas: [test_suite.py](test_suite.py#test_exporters)

### Uso CLI
- Implementado en: [main.py](main.py)
- Documentación: [README.md](README.md#uso)
- Guía rápida: [QUICKSTART.md](QUICKSTART.md)
- Ejemplos: [examples.py](examples.py#ejemplo-1-análisis-básico-desde-línea-de-comandos)

---

## ✅ Checklist de Implementación Completada

### Funcionalidad Principal
- [x] Lectura de archivos PCAP
- [x] Lectura de archivos AST
- [x] Decodificación CAT 048
- [x] Decodificación CAT 001
- [x] Decodificación CAT 021
- [x] Decodificación CAT 034
- [x] Decodificación CAT 062
- [x] Decodificación CAT 002
- [x] Conversión Slant→Ground Range
- [x] Conversión Polares→WGS-84
- [x] Exportación KML
- [x] Exportación GeoJSON
- [x] Exportación CSV
- [x] Generación de Reportes

### Interfaz y Usabilidad
- [x] CLI con argumentos
- [x] Modo interactivo
- [x] Ayuda contextual
- [x] Manejo de errores

### Documentación
- [x] README completo
- [x] Guía rápida
- [x] Documentación técnica
- [x] Ejemplos de código
- [x] Documentación API
- [x] Especificación de algoritmos

### Pruebas
- [x] Suite de pruebas
- [x] Test de importaciones
- [x] Test de BitStream
- [x] Test de conversiones
- [x] Test de exportadores
- [x] Test de estructuras

### Código
- [x] Modular y reutilizable
- [x] Manejo de excepciones
- [x] Validación de datos
- [x] Logging de errores
- [x] Estilo PEP 8
- [x] Docstrings completos

---

## 🎓 Recursos Externos Referenciados

- **ASTERIX Standard**: https://www.eurocontrol.int/asterix
- **WGS-84**: https://en.wikipedia.org/wiki/World_Geodetic_System
- **Great Circle Distance**: https://en.wikipedia.org/wiki/Great-circle_distance
- **Vincenty Formula**: https://en.wikipedia.org/wiki/Vincenty%27s_formulae
- **KML Reference**: https://developers.google.com/kml
- **GeoJSON Standard**: https://tools.ietf.org/html/rfc7946

---

## 📞 Soporte y Contacto

Para problemas:
1. Revisar [README.md](README.md#troubleshooting)
2. Ejecutar [test_suite.py](test_suite.py)
3. Consultar [examples.py](examples.py)
4. Estudiar [TECHNICAL.md](TECHNICAL.md)

---

## 📝 Historial de Cambios

### v2.0 (27 Abril 2026) - ACTUAL
- ✅ Implementación completa según especificación
- ✅ 6 categorías ASTERIX soportadas (incluye CAT 062)
- ✅ 4 formatos de exportación
- ✅ Documentación exhaustiva
- ✅ Suite de pruebas completa
- ✅ Modo interactivo

### v1.0 (Original)
- Decodificador básico CAT 048
- Lectura de archivos .ast
- Soporte pcap minimal

---

**Última actualización:** 27 de Abril, 2026  
**Versión:** 2.0  
**Estado:** ✅ COMPLETO Y PRODUCCIÓN
