# Ciclo de vida de pista monoradar (confirmación M-de-N + coasting por vueltas)

Fecha: 2026-06-17
Estado: Aprobado (diseño)
Rama: feature/monoradar-track-lifecycle

## Objetivo

Implementar, para pruebas con grabaciones **monoradar**, un ciclo de vida de
pista basado en **vueltas de antena** (no en segundos): confirmación M-de-N
(4 detecciones) y coasting con borrado por faltas (4 faltas), con indicador
visual de coasting (flecha diagonal hacia abajo) y color por estado.

## Contexto actual

- El player (`player/radar_widget.py`) maneja `pending_tracks → tracks`:
  promueve cuando el barrido cruza el azimut y la vida es por **tiempo**
  (`MAX_AGE_PLOT=30s`, `MAX_AGE_TRACK=60s`, `is_alive = age < max_age`). No hay
  confirmación M-de-N, ni contador de faltas, ni símbolo de coasting.
- El ciclo de vida determinista por **ToD** existe pero en el decoder
  (`decoder/data_engine.py: SystemTrack`, para PASS/técnico), no en esta vista.
  Regla de oro del proyecto: el ciclo de vida se guía **exclusivamente por ToD
  ASTERIX**; `time.time()` está prohibido en el motor de ciclo de vida
  (ver memoria arch_tod_lifecycle).
- RPM por sensor disponible en `self.sensor_rpms[(sac,sic)]` (detectado CAT34 /
  estimado). Período de vuelta = `60/RPM`.
- Color actual por tipo/estado en `_draw_oaci_track`
  ([radar_widget.py:5249-5292](player/radar_widget.py#L5249-L5292)).

## Decisiones (brainstorming, confirmadas)

1. **Identidad ("código")** por plot:
   - SSR / PSR-SSR → Modo 3/A (squawk).
   - ADS-B (CAT21) → dirección Mode S (aircraft address); si falta → callsign.
2. **Vuelta (scan)** = `60/RPM` del RPM **detectado por sensor**. Índice de
   vuelta de un plot = `floor(ToD_plot / scan_period)`. Todo por ToD.
3. **Confirmación 4/4:** 1–3 detecciones = TENTATIVE (color de categoría); la
   **4ª** detección → CONFIRMED (blanco).
4. **Doble plot en la misma vuelta:** si dos plots del mismo código en la misma
   vuelta están a **< 1 NM** → cuentan como **2 detecciones** (aceleran
   confirmación). Si están a **> 1 NM** → no se colapsan: el segundo alimenta una
   pista candidata aparte (posible duplicado real si persiste).
5. **Coasting:** confirmada sin dato en una vuelta → se mantiene con **flecha
   diagonal hacia abajo**; cuenta faltas consecutivas. Dato válido → faltas=0,
   se saca la flecha. Faltas en vueltas 1-2-3 (con flecha); en la **4ª falta →
   borrar**.
6. **Alcance:** solo **monoradar** (un único sensor activo). El modelo por tiempo
   (30/60 s) y la fusión multisensor quedan sin tocar; el nuevo motor se **gatea**
   para el caso monoradar y se valida antes de extender.

## Arquitectura

### 1. Motor headless `player/tracking/lifecycle.py` (sin Qt)

Determinista por ToD; testeable en aislamiento.

- `identidad_codigo(plot) -> str | None`: squawk; si ADS-B y sin squawk →
  Mode S addr; si falta → callsign. `None` si no hay clave (p. ej. PSR puro sin
  código → ver §Errores).
- `MonoradarLifecycle(scan_period_fn)`:
  - `scan_period_fn(sac, sic) -> float`: devuelve `60/RPM` (inyectado desde el
    player con `sensor_rpms`).
  - Estado por código:
    `Pista { codigo, estado, detecciones, faltas, ultima_vuelta, x, y, ... }`.
  - `procesar(plot) -> EventoCiclo`: registra una detección.
    - Calcula `vuelta = floor(tod / scan_period)`.
    - Si misma vuelta que la última y `dist < 1 NM` → cuenta como detección extra
      (suma 2 en esa vuelta); si `dist ≥ 1 NM` → marca candidata duplicada.
    - Si vuelta nueva consecutiva con dato → `detecciones += 1`, `faltas = 0`.
    - Transición a CONFIRMED al alcanzar `detecciones >= 4`.
  - `tick(tod_actual) -> [EventoCiclo]`: avanza el reloj de vueltas; para cada
    pista, si pasó una vuelta sin dato → `faltas += 1` (COASTING); si
    `faltas >= 4` → DELETE.
  - Estados: `TENTATIVE`, `CONFIRMED`, `COASTING`, `DELETED`.
  - Sin `time.time()`: solo ToD recibido.

### 2. Integración en el player (`radar_widget.py`)

- **Gateo monoradar:** activar el motor solo si hay **un único sensor activo**
  (`len(sensores con plots) == 1`). Si hay varios → comportamiento actual.
- En el procesamiento de plots: cuando el gateo está activo, alimentar
  `MonoradarLifecycle.procesar(plot)` y usar su estado para decidir si el plot se
  muestra (tentativo) y su color/estado.
- Un tick por vuelta (desde `_on_timer`, usando ToD) llama a `lifecycle.tick()`
  para envejecer faltas y borrar (sustituye, en modo monoradar, el envejecimiento
  por tiempo de 30/60 s).
- Mapear estado → `RadarPlot`: flags `lifecycle_estado` y `missed_scans` en el
  plot (o en una tabla paralela por código) para que el render las lea.

### 3. Render (`_draw_oaci_track`)

- **Color por estado** (solo en modo monoradar gateado):
  - TENTATIVE → color de categoría (PSR naranja, SSR verde, ADS-B amarillo…)
    (reusa el esquema actual de tipo).
  - CONFIRMED → **blanco**.
  - Emergencia/alertas siguen pisando (rojo/ámbar).
- **Flecha de coasting:** si `missed_scans >= 1`, dibujar una flecha diagonal
  hacia abajo junto al símbolo (helper `_draw_coasting_arrow`).

## Manejo de errores / degradación

- Plot sin código válido (PSR puro sin squawk): no entra al ciclo M-de-N de
  confirmación por código; se mantiene el tratamiento actual de plot primario
  (no confirma pista por código). Documentar como fuera de alcance de la prueba.
- RPM no detectado (0/None): usar `self.sweep_rpm` como fallback de período.
- Si hay >1 sensor activo: el motor monoradar se desactiva (gateo) y nada cambia.

## Testing (`tests/tracking/`, headless, ToD sintético)

- Confirmación: 4 vueltas consecutivas con dato → CONFIRMED en la 4ª; 3 → sigue
  TENTATIVE.
- Doble plot misma vuelta `< 1 NM` → cuenta 2 (confirma en menos vueltas).
- Doble plot misma vuelta `> 1 NM` → no colapsa; marca candidata duplicada.
- Coasting: confirmada, faltas 1-2-3 → COASTING (missed_scans crece); 4ª falta →
  DELETED.
- Recuperación: falta, falta, dato → missed_scans vuelve a 0, sigue CONFIRMED.
- Identidad: squawk para SSR; Mode S addr para ADS-B sin squawk; callsign si
  falta address.
- Determinismo ToD: mismos ToD → mismos eventos (sin `time.time()`).

## Secuencia de construcción

1. Motor `player/tracking/lifecycle.py` + identidad + estados (+ tests).
2. Doble-plot misma vuelta (<1NM cuenta 2 / >1NM candidata) (+ tests).
3. Coasting/borrado por `tick` (+ tests).
4. Gateo monoradar + integración en el procesamiento de plots del player.
5. Render: color por estado + flecha de coasting.
6. Prueba manual con grabación monoradar.
