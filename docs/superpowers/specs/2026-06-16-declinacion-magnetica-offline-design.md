# Declinación magnética offline (grilla + WMM)

Fecha: 2026-06-16
Estado: aprobado (diseño)

## Problema

La app obtiene la declinación magnética por coordenada con el World Magnetic
Model vía `pygeomag` (`player/magnetic_compensator.py`). Esto exige que
`pygeomag` esté instalado en cada máquina de despliegue. En un entorno ATC
offline y portátil no se puede garantizar la instalación del paquete, y hoy el
único respaldo es el offset estático del perfil (−7°), que es incorrecto para
casi todo el país (la declinación real va de ~−10° en Buenos Aires a ~+4° en
Comodoro).

Se necesita una fuente de declinación **garantizada offline y sin
dependencias**, conservando el WMM completo cuando esté disponible.

## Objetivo

Jerarquía de fuentes de declinación, sin tocar la API pública de
`MagneticCompensator.obtener_declinacion(lat, lon, alt_ft)`:

1. **WMM** (`pygeomag`) si el modelo está disponible → valor exacto, con fecha
   actual y variación secular.
2. **Grilla offline** precalculada (Python puro, sin deps) → respaldo siempre
   disponible.
3. **Offset estático** del perfil → último recurso.

"Online/offline" se interpreta como "modelo WMM disponible vs no". **No se
agregan llamadas de red**: una caja ATC offline no debe acceder a internet.

## Componentes

### 1. Generador — `tools/gen_declination_grid.py`
- Recorre un bbox sobre Argentina continental + FIR oceánica:
  - lat −56 … −21, lon −76 … −52, paso **1°** (~35 × 24 ≈ 840 nodos).
- Para cada nodo llama a `pygeomag` (`alt=0`, época = año decimal actual) y toma
  `res.d` (grados, **oeste negativo**).
- Escribe `data/magnetic/declination_grid.json`.
- Además genera la cartografía de isógonas (ver componente 5):
  `data/magnetic/isogonic_lines.geojson`.
- Se re-ejecuta manualmente para actualizar la época. Requiere `pygeomag` (solo
  en tiempo de generación, no en runtime).

### 2. Datos — `data/magnetic/declination_grid.json`
Versionado en git. Estructura:
```json
{
  "convention": "west-negative",
  "epoch": 2026.46,
  "lat_min": -56.0, "lat_max": -21.0,
  "lon_min": -76.0, "lon_max": -52.0,
  "step": 1.0,
  "n_lat": 36, "n_lon": 25,
  "values": [[...], ...]   // [fila lat][col lon], grados
}
```
`values[i][j]` = declinación en (lat_min + i·step, lon_min + j·step).

### 3. Loader + interpolación — `player/geo/declination_grid.py`
- Carga el JSON una sola vez (lazy, cacheado a nivel módulo).
- `declinacion(lat, lon) -> float | None`: interpolación **bilineal** sobre los
  4 nodos que rodean el punto.
- Fuera del bbox: **clamp** al borde (la cobertura radar cae dentro; clamp evita
  saltos en los límites).
- Si el archivo falta o no parsea: devuelve `None` (deja decidir al llamador).
- Cero dependencias (solo `json` y stdlib). Sin Qt.

### 4. Integración — `player/magnetic_compensator.py`
`obtener_declinacion(lat, lon, alt_ft)` aplica la cascada:
1. Si `pygeomag` disponible → cálculo WMM (como hoy).
2. Sino → `declination_grid.declinacion(lat, lon)`.
3. Sino (grilla `None`) → `self.fallback_deg` (offset estático).
- Se conserva el caché por celda (~1 km) existente.
- `self.disponible` pasa a ser `True` si hay WMM **o** grilla.
- Convención de signo idéntica en las tres fuentes (oeste negativo), consistente
  con `analysis/geo_math.calcular_rumbo_magnetico`.

Los consumidores (RBL y rumbos del PPI en `radar_widget.py`) no se modifican.

### 5. Capa visual de líneas isógonas
Curvas de igual declinación (como la imagen de referencia), dibujadas en **PPI +
satélite** reusando el pipeline de cartografía.

- **Extracción de contornos** — `player/geo/isogonic.py`
  Marching squares en Python puro: dada la grilla, devuelve polilíneas
  `[(lat,lon),...]` por nivel entero (cada **1°**, p. ej. de +5° a −12° según el
  rango real). Sin dependencias.
- **Artefacto** — `data/magnetic/isogonic_lines.geojson`
  Generado por `tools/gen_declination_grid.py`. `LineString` por contorno
  (property `layer = "ISOGONAS"`) + `Point` `type:"text"` con la etiqueta del
  nivel (`"-10°"`) en el medio de cada contorno. Formato ya soportado por
  `VideoMapManager.load_geojson`.
- **Toggle** — acción de menú en `main_window.py` (junto a áreas / sectores MSA):
  carga el geojson como capa `MAGVAR::ISOGONAS` (`tipo="TACTICO"`, color propio
  p. ej. magenta `#FF40FF` para no chocar con áreas/aerovías) y reproyecta.
  Al ser una capa visible del `map_manager`, el PPI la pinta (reproyectada) y la
  vista FIR vía `build_maps` la incluye **automáticamente en ambas**. Off → se
  quita la capa.

No requiere tocar `radar_widget`/`firmap` salvo, si hace falta, distinguir la
capa por nombre para estilo (línea fina, no relleno).

## Tests — `tests/geo/test_declination_grid.py`
- **Interpolación vs WMM**: para una muestra de coordenadas dentro del bbox, la
  grilla interpolada coincide con `pygeomag` dentro de ~0.1° (se omite si
  `pygeomag` no está instalado).
- **Clamp** fuera del bbox: no lanza, devuelve un valor finito del borde.
- **Cascada de fallback** en `MagneticCompensator`: con WMM ausente usa la
  grilla; con grilla ausente usa el offset estático. Se simula la ausencia de
  cada fuente.
- **Carga**: archivo faltante → `declinacion` devuelve `None` sin excepción.
- **Isógonas** (`tests/geo/test_isogonic.py`): marching squares sobre una grilla
  sintética con gradiente conocido produce polilíneas en los niveles esperados y
  monótonas; cada contorno cae cerca del valor de su nivel al muestrear la grilla.

## Fuera de alcance (YAGNI)
- Variación con altitud (despreciable para los FL de interés; `alt=0`).
- Actualización automática de la época / descarga de coeficientes.
