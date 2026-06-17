# MSAW: Zonas poligonales de altitud mínima + Supresión en aproximación

Fecha: 2026-06-16
Estado: Aprobado (diseño)

## Objetivo

Mejorar el MSAW (Minimum Safe Altitude Warning) con dos capacidades:

1. **Zonas poligonales de altitud mínima** (`minimums_zones`): MSA precisa por
   polígono geográfico para SACO, complementando el modelo circular de sectores
   radiales existente.
2. **Supresión en aproximación/salida**: inhibir la alerta MSAW cuando una
   aeronave está establecida en un corredor de aproximación/salida y desciende
   bajo la MSA (situación operativamente normal).

## Contexto actual

- MSAW vive en `player/msaw/` (`model.py`, `data.py`, `engine.py`, `render.py`),
  sin dependencias de Qt y testeable en aislamiento.
- Modelo actual: zonas **circulares** por ICAO (`MsaZone`, radio 25 NM) divididas
  en sectores radiales **magnéticos** con MSA en ft MSL. Hardcodeadas en
  `data.py` para 8 ICAOs de la FIR Córdoba. La declinación sale del compensador
  WMM/grilla.
- El motor (`engine.py:evaluar_msaw`) emite `VIOLATION` (alt < MSA) y `PREDICTED`
  (descenso proyectado bajo MSA), con inhibición por categorías (`exentos`).
- Cableado en `player/radar_widget.py:evaluar_msaw()`; parámetros del algoritmo
  desde `atm_db.msaw_params()`.
- DB en `data/atm/atm.duckdb`, lectura vía `player/atm_db.py` (`DB_PATH`,
  `_con()` read-only). Las tablas nuevas (`minimums_zones_*`, `profiles_*`,
  `apm_profiles_*`) **aún no están cargadas**.
- Datos APM con coordenadas de eje (near/far) cargadas solo para **SACO**
  (pistas 01/05/19/23). El resto de aeropuertos es plantilla con near/far NULL.
- Verificado: SACO ARP `311836S 0641230W`, elev 1604 ft; pistas 01/23/19/05
  presentes en `airports_runways` → los joins APM funcionan.

## Decisiones (brainstorming)

1. **Alcance**: zonas poligonales **+** supresión en aproximación.
2. **Modelo MSA**: cascada — polígonos para SACO, círculos para el resto. El
   motor consulta primero polígonos; si ningún polígono contiene el punto, cae al
   modelo circular existente. No se pierde cobertura.
3. **Corredor de supresión**: **ambos** modelos — APM paramétrico como corredor
   principal y `profile_points` (waypoints) como complemento.
4. **Comportamiento de supresión**: suprimir **solo si la aeronave está dentro del
   envelope vertical** (entre lower y upper slope para APM; perfil interpolado ±
   tol_altitude para waypoints). Si está en el corredor lateral pero fuera del
   envelope vertical, la alarma se mantiene.

## Supuestos

- **Escala de altitud de `minimums_zones_kernel.altitude`**: los valores
  (36, 60, 80, 100, 110) se interpretan como **centenas de pies** (×100 →
  3600..11000 ft MSL), coherente con los sectores circulares actuales (4100,
  8300 ft). El comentario del esquema dice "(ft)" pero la magnitud indica ×100.
- `profile_points.altitude` es **ft × 100** (según comentario del esquema; 21 →
  2100 ft).
- `profile_parameters.tol_altitude` es **ft × 100** (3 → 300 ft).
- Identificadores con espacios de relleno (`'80E   '`, `'SACO'`, `'01 '`) se
  normalizan con `TRIM` en todos los readers.

## Arquitectura

### 1. Capa de datos

**Carga única** — script `tools/load_msaw_profiles.py`:
- Idempotente: `CREATE TABLE IF NOT EXISTS` (del schema) + `DELETE FROM` +
  re-`INSERT` (de los datos) sobre `data/atm/atm.duckdb` (conexión read-write,
  reusando `DB_PATH` de `atm_db`).
- Tablas creadas/pobladas: `minimums_zones_kernel`, `minimums_zones_vertices`,
  `profile_parameters`, `profiles_kernel`, `profile_points`,
  `apm_profiles_kernel`.
- Fuente: los dos archivos SQL provistos (`msaw_profiles_schema-1.sql`,
  `msaw_profiles_data.sql`). **Pendiente**: estos archivos llegaron como
  adjuntos y aún no están en disco; el primer paso de implementación es
  escribirlos bajo `data/atm/` con el contenido provisto.

**Readers** en `player/atm_db.py` (con `TRIM` y `dms_to_dd`; el helper
`dms_to_dd` ya existe en `queries_map.py` y se replica/importa):
- `minimums_zones()` → `[ {identifier, msa_ft, coords: [(lat,lon)...]} ]`
- `apm_corridors(airport='SACO')` → `[ {airport, runway, near:(lat,lon),
  far:(lat,lon), half_wide_nm, min_dist, max_dist, lower_slope, upper_slope,
  glide_slope, thr_elev_ft} ]` (solo filas con near/far no nulos).
- `profile_corridors(airport='SACO')` → `[ {profile, airport, runway, kind,
  points: [(lat,lon,min_ft,distance_lateral,azimut)...] } ]` ordenados por
  `seq_num`.
- `profile_parameters()` → `{tol_heading, tol_altitude_ft, tol_distance_nm,
  entorno_aerodrome_nm}` (con escalas ya aplicadas).

### 2. Capa de modelo (`player/msaw/model.py`, sin Qt)

- `MsaPolygon(identifier, msa_ft, coords)`:
  - `contiene(lat, lon)` → ray-casting point-in-polygon.
  - `msa_en(lat, lon)` → `msa_ft` si dentro, si no `None`.
- `ApmCorridor(airport, runway, near, far, half_wide_nm, min_dist, max_dist,
  lower_slope, upper_slope, glide_slope, thr_elev_ft)`:
  - Proyección along-track / cross-track del punto sobre el segmento near→far.
  - `en_corredor(lat, lon)` → `|cross| ≤ half_wide_nm` y `min_dist ≤ along ≤
    max_dist`.
  - `en_envelope(lat, lon, alt_ft)` → con `d` = distancia along desde el umbral,
    `alt_lo = thr_elev_ft + d_nm·6076·tan(lower_slope)` y `alt_hi` análogo con
    `upper_slope`; True si `alt_lo ≤ alt_ft ≤ alt_hi`.
- `ProfileCorridor(profile, kind, points)`:
  - Interpola la altitud mínima a lo largo del polilínea por distancia acumulada.
  - `en_corredor(lat, lon)` → cross-track al tramo más cercano ≤
    `distance_lateral` del tramo.
  - `en_envelope(lat, lon, alt_ft)` → `|alt_ft − min_interp| ≤ tol_altitude_ft`
    o `alt_ft ≥ min_interp − tol_altitude_ft` (perfil de mínimos esperado).
- `SuppressionSet(apm: list, profiles: list, params)`:
  - `suprime(lat, lon, alt_ft)` → True si **algún** corredor cumple
    `en_corredor(...) AND en_envelope(...)`.

### 3. Geometría

Reusar `haversine_nm` (de `player/areas/model`) y `bearing_true` (ya en
`model.py`). Agregar:
- `cross_track_nm(lat, lon, lat1, lon1, lat2, lon2)` y
  `along_track_nm(...)` — distancias cross/along respecto del segmento.
- `point_in_polygon(lat, lon, coords)` — ray-casting.

Ubicación: helpers en `player/msaw/model.py` (junto a `bearing_true`/`in_arc`)
para mantener el módulo autocontenido y testeable sin Qt.

### 4. Motor (`player/msaw/engine.py`)

- Firma extendida: `evaluar_msaw(tracks, zones, params=None, exentos=None,
  suppression=None)`.
- **Cascada MSA**: una función `msa_lookup(zones, lat, lon)` que recorre primero
  los `MsaPolygon` y, si ninguno contiene el punto, los `MsaZone` circulares.
  `zones` pasa a ser una estructura con ambos conjuntos (ver §5).
- Antes de registrar `VIOLATION`: si `suppression and
  suppression.suprime(lat, lon, alt_ft)` → continuar sin emitir.
- En el lazo de `PREDICTED`: si en el paso `t` el punto proyectado está suprimido
  (`suppression.suprime(lat_t, lon_t, alt_t)`) → no emitir en ese paso.
- Conserva la inhibición por `exentos` y los filtros de track existentes.

### 5. Wiring (`player/radar_widget.py`)

- En `evaluar_msaw()`:
  - `_msaw_zones`: estructura/tupla `(poligonos, circulos)` — polígonos desde
    `atm_db.minimums_zones()` (mapeados a `MsaPolygon`) + circulares desde
    `player.msaw.data.msa_zones()`. Carga perezosa (igual que hoy).
  - `_msaw_suppression`: `SuppressionSet` construido una vez desde
    `atm_db.apm_corridors()`, `atm_db.profile_corridors()` y
    `atm_db.profile_parameters()`.
  - Pasar `suppression=self._msaw_suppression` a `_engine(...)`.
- Tolerante a ausencia de tablas: si los readers devuelven vacío, el MSAW se
  comporta como hoy (solo círculos, sin supresión).

### 6. Render (Fase 2, fuera de alcance inmediato)

Dibujo de polígonos MSA y corredores de aproximación en el PPI (`render.py`).
No se implementa en esta iteración; se documenta como trabajo futuro.

## Manejo de errores / degradación

- Readers devuelven listas/dicts vacíos si la tabla no existe → MSAW funciona en
  modo actual (círculos, sin supresión). Sin excepciones propagadas al motor.
- `dms_to_dd` devuelve `None` ante formato inválido; esos vértices/puntos se
  descartan (un polígono con < 3 vértices válidos se ignora).
- El script de carga es idempotente y no aborta el arranque de la app (se ejecuta
  manualmente / como paso de setup, no en el hot path).

## Testing (`player/tests/`, sin Qt)

- `point_in_polygon`: dentro, fuera, sobre borde, polígono cóncavo (ej. `36N`).
- `cross_track_nm` / `along_track_nm`: casos conocidos sobre eje SACO 01.
- `ApmCorridor.en_corredor` / `en_envelope`: punto en eje a 6 NM dentro del
  envelope (suprime), mismo lateral pero muy bajo (no suprime), fuera del
  corredor lateral (no suprime), fuera de la banda de distancia (no suprime).
- `ProfileCorridor`: interpolación de mínima entre dos waypoints; supresión
  dentro de tol_altitude.
- `msa_lookup`: punto en polígono SACO devuelve MSA del polígono; punto fuera de
  todo polígono pero dentro de círculo devuelve MSA del sector.
- `evaluar_msaw` con `suppression`: track en final aproximación bajo MSA → sin
  alerta; mismo track desplazado fuera del corredor → `VIOLATION`.

## Secuencia de construcción

0. Escribir `data/atm/msaw_profiles_schema-1.sql` y
   `data/atm/msaw_profiles_data.sql` con el contenido provisto.
1. `tools/load_msaw_profiles.py` + cargar datos a `atm.duckdb`.
2. Readers en `atm_db.py` (+ test rápido de lectura).
3. Helpers de geometría + `MsaPolygon` (+ tests).
4. `ApmCorridor`, `ProfileCorridor`, `SuppressionSet` (+ tests).
5. Cascada `msa_lookup` y firma `suppression` en `engine.py` (+ tests).
6. Wiring en `radar_widget.py`.
7. Verificación manual con tráfico SACO.
