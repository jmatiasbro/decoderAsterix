# Centro Técnico ATSEP — Hub unificado de herramientas técnicas

Fecha: 2026-06-15
Estado: diseño aprobado (pendiente de plan de implementación)

## 1. Propósito

Un hub unificado que integra, en una sola ventana, las herramientas técnicas que
hoy están dispersas en menús y diálogos de la aplicación, y que agrega un
**constructor configurable de estadísticas y gráficos** y una **vista de cobertura
de radar** con exportación.

Usuario objetivo: rol **TÉCNICO (ATSEP)**. La ventana se abre desde el menú y queda
deshabilitada para otros roles (mismo criterio que la calibración).

## 2. Alcance v1

Cinco pestañas:

1. **Estadísticas** — constructor configurable (pieza nueva principal).
2. **PASS / SASS-C** — embebe el `pass_dashboard.py` actual.
3. **Monitor ATSEP** — embebe `technical_monitor.py` (ya es `QWidget`).
4. **Inspector** — embebe `packet_analyzer.py` / `asterix_inspector.py`.
5. **Cobertura** — vista mapa + polar con exportación (pieza nueva).

Fuera de alcance v1: integración de safety nets (STCA/APW/MSAW) como pestaña;
calibración/fusión; configuración de radar/mapas. Pueden sumarse en v2.

## 3. Arquitectura del contenedor

**Ventana dedicada** `CentroTecnicoWindow(QMainWindow)` con un `QTabWidget` central.

- Se instancia desde `main_window.py` (acción de menú gateada por
  `profile_manager.get_rol() == "tecnico"`).
- Barra inferior global: conmutador de **fuente de datos**
  (`● DuckDB  ○ Sesión actual`) + indicador de rol. El conmutador alimenta tanto
  el constructor de Estadísticas como la pestaña Cobertura.
- No usa los docks de la vista operativa; se maximiza idealmente en segundo monitor.

Decisión: ventana dedicada (vs. dock acoplable o workspace conmutable) para dar
espacio a gráficos e inspector sin pelear con los docks existentes, y para que el
refactor de diálogos→widgets quede reutilizable.

## 4. Refactor de diálogos a widgets embebibles

Las herramientas existentes se extraen de su `QDialog`/ventana a un `QWidget`
embebible, manteniendo su lógica intacta:

| Herramienta | Estado actual | Acción |
|---|---|---|
| `pass_dashboard.py` (`PassDashboardDialog`) | QDialog | Extraer el cuerpo a `PassDashboardWidget`; el diálogo pasa a ser un wrapper fino |
| `technical_monitor.py` (`TechnicalMonitorWidget`) | Ya `QWidget` | Reusar tal cual |
| `packet_analyzer.py` (`AsterixAnalyzerWindow`) / `asterix_inspector.py` | Ventana | Extraer a `InspectorWidget` |

Regla: la lógica de negocio no se reescribe; solo se cambia el contenedor Qt.

## 5. Constructor configurable de estadísticas (pestaña 1)

Enfoque: **registro de métricas + capa de consulta unificada** (sin exponer SQL).

### 5.1 Componentes

- **Catálogo de métricas** (`stats/metric_registry.py`): lista declarativa de
  métricas. Cada entrada define: `id`, `nombre`, `fuente` (qué tabla/campo),
  `agregación` (count/avg/p95/…), `dimensiones` admitidas y `filtros` aplicables.
- **`DataSource` unificado** (`stats/data_source.py`): interfaz común que abstrae
  las dos fuentes detrás del mismo contrato (devuelve un `DataFrame`):
  - `DuckDBSource` → consulta `pass_analytics.duckdb` (sesiones grabadas).
  - `SessionSource` → opera sobre los plots/tracks de la sesión cargada en memoria.
  El conmutador inferior elige cuál se usa.
- **UI del constructor**: panel izquierdo de configuración
  (Fuente → Métrica → Dimensión → Tipo de gráfico → Filtros) + canvas matplotlib a
  la derecha. Botones **Generar** / **Limpiar**. Pie con conteo de filas y
  export (CSV de los datos, PNG del gráfico).
- **Renderer** (`stats/chart_renderer.py`): toma `(DataFrame, tipo_gráfico)` y
  pinta en un `FigureCanvas`.

### 5.2 Métricas (ejemplos del catálogo)

Nº detecciones · Probabilidad de detección (Pd) · Tasa de pérdidas (track loss) ·
RMS posición · Distribución de modos (A/C/S) · Disparos STCA/APW/MSAW ·
Latencia / edad de plot.

Dimensiones: Radar · Tiempo (hora/día) · Sector · Modo · Rango/Azimut.

Filtros comunes: Radar (multi) · Período · Modo · Sector.

### 5.3 Catálogo de tipos de gráfico (v1)

Complementan a PASS (que ya cubre Pd-vs-rango, residuos polares, histogramas de
error, cobertura polar/vertical SASS-C y dispersión). El constructor agrega:

- **Serie de tiempo** — métrica por hora/día (detecta degradación progresiva).
- **Heatmap hora × día** — patrón de carga/calidad tipo calendario.
- **Barras agrupadas** — comparación de una métrica entre radares.
- **Barras apiladas 100%** — composición por categoría (ej. tipo de mensaje por radar).
- **Torta / dona** — reparto categórico (modos A/C/S, causas de pérdida).
- **Box / violin plot** — dispersión y outliers de latencia/error por radar.
- **Spider / radar chart** — perfil multi-métrica por sensor.

Reserva v2 (no en v1): banda de control (mean ± σ), Pareto, barras divergentes
(real vs teórico), heatmap espacial 2D.

Los gráficos polares/SASS-C permanecen en la pestaña PASS; el constructor no los
reimplementa.

## 6. Pestaña Cobertura (pestaña 5)

Muestra la cobertura real del radar y permite exportarla. Vista **mapa + polar**
(split).

### 6.1 Cálculo

Reutiliza la lógica de `analysis/exporters.py :: PassExporter.export_coverage_map_kmz`
(consulta `asterix_plots` por `sac/sic`, contornos por percentil-95 por nivel de
vuelo FL50–FL300). Se **extrae** esa lógica a una función que devuelve los
polígonos **en memoria** (no solo escribe KMZ), para poder pintarlos y para que la
exportación los reuse.

### 6.2 Controles

Radar (SAC/SIC) · Rango teórico (NM) · Niveles FL (toggles por nivel) ·
Percentil (configurable, default 95) · botón Calcular.

### 6.3 Vistas

- **Mapa (lat/lon)**: polígonos de cobertura por FL translúcidos con toggles +
  pin del radar + círculo de cobertura teórica. Espeja la estructura del KMZ.
- **Polar (rango/azimut)**: alcance vs azimut con anillos de rango; revela
  sombras, lóbulos y conos de silencio.
- Pie: conteo de plots y % cobertura real vs teórica.

### 6.4 Exportación (menú)

- **KMZ** (Google Earth, por FL) — reusa `export_coverage_map_kmz`.
- **Heatmap QGIS (CSV)** — reusa `export_heatmap_qgis`.
- **Imagen PNG** — captura de la vista actual (nuevo).
- **GeoJSON** — polígonos de cobertura (nuevo).

Respeta el conmutador de fuente (DuckDB ↔ sesión actual).

## 7. Estructura de archivos propuesta

```
player/
  centro_tecnico/
    __init__.py
    window.py            # CentroTecnicoWindow (QMainWindow + QTabWidget)
    pass_widget.py       # PassDashboardWidget (extraído de pass_dashboard)
    inspector_widget.py  # InspectorWidget (extraído de packet_analyzer)
    coverage_widget.py   # Pestaña Cobertura (mapa + polar + export)
    stats_widget.py      # UI del constructor
  stats/
    metric_registry.py   # catálogo declarativo de métricas
    data_source.py       # DataSource / DuckDBSource / SessionSource
    chart_renderer.py     # (DataFrame, tipo) -> FigureCanvas
analysis/
  coverage.py            # lógica de cobertura extraída (polígonos en memoria)
```

`technical_monitor.py` se reusa sin mover.

## 8. Flujo de datos

```
Conmutador fuente ──> DataSource (DuckDBSource | SessionSource)
                          │
         ┌────────────────┼─────────────────────┐
         ▼                ▼                       ▼
  metric_registry   coverage.py            (PASS usa su propio
   (consulta)       (polígonos)             pipeline DuckDB actual)
         │                │
         ▼                ▼
  chart_renderer    mapa + polar
         │                │
         ▼                ▼
   canvas + export   canvas + export (KMZ/CSV/PNG/GeoJSON)
```

## 9. Manejo de errores

- Fuente sin datos / DuckDB no disponible: mensaje claro en el panel, no excepción.
- Métrica/dimensión incompatibles: el constructor deshabilita combinaciones inválidas.
- Cobertura sin parámetros de sitio para el radar elegido: aviso y deshabilita Calcular.
- Exportación: validar ruta y reportar éxito/fallo sin tirar la ventana.

## 10. Testing

- `stats/data_source.py`: tests con DuckDB de prueba y con dataset en memoria;
  verificar que ambas fuentes devuelven el mismo esquema de DataFrame.
- `stats/metric_registry.py`: cada métrica produce una consulta válida.
- `analysis/coverage.py`: polígonos en memoria coinciden con los del KMZ existente
  (mismo input → mismos contornos).
- `chart_renderer.py`: cada tipo de gráfico renderiza sin error con datos mínimos.
- Smoke test de apertura de la ventana gateada por rol.

## 11. Gating por rol

La acción de menú que abre `CentroTecnicoWindow` se habilita solo si
`profile_manager.get_rol() == "tecnico"`, replicando el criterio ya usado para
"Análisis y Calibración (Técnico)".
