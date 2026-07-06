# SDD — Software Design Description

**Sistema:** Decodificador ASTERIX + Display PPI ATC.
**Norma:** EUROCAE ED-109A / RTCA DO-278A — diseño de software (D-3) y requisitos de bajo nivel (D-2).
**Versión:** 0.4 (borrador). **Fecha:** 2026-07-05. **Estado:** PROPUESTO — no aprobado por ANAC.

> Formaliza la **arquitectura** y los **Requisitos de Bajo Nivel (LLR)** del software. Los LLR derivan
> de los HLR del [SRS (doc 07)](07_SRS.md) y de la arquitectura, redactados conforme al
> [estándar de requisitos (doc 14)](14_estandar_requisitos.md) y al estándar de diseño
> ([doc 13 §4](13_estandar_codificacion.md)). Cierra la parte de diseño/LLR de las brechas **D-2/D-3**
> del [gap analysis](03_gap_analysis_DO-278A.md).
>
> **Alcance de esta edición (v0.3):** LLR para **todas las capas** — motores núcleo SWAL 2 (§3-6),
> HMI/PPI (§7), decodificación/proyección/robustez/altimetría (§8), persistencia/auditoría y roles (§9)
> y prestaciones (§10) — con diagramas de secuencia (§2.3). **Todo HLR del SRS tiene al menos un LLR
> asociado.** Los refinamientos restantes (LLR por categoría, diagramas de estados/despliegue) se listan
> en §13.

---

## 1. Documentos aplicables

| ID | Documento |
|----|-----------|
| DA-1 | [SRS — 07_SRS.md](07_SRS.md) (HLR) |
| DA-2 | [FHA — 06_FHA.md](06_FHA.md) (condiciones de falla, SSR) |
| DA-3 | [Estándar de codificación y diseño — 13](13_estandar_codificacion.md) (EC/ED) |
| DA-4 | [Estándar de requisitos — 14](14_estandar_requisitos.md) (ER/RR/LR) |
| DA-5 | [Clasificación SWAL — 02](02_clasificacion_SWAL.md) |
| DA-6 | [../../CLAUDE.md](../../CLAUDE.md), [../../TECHNICAL.md](../../TECHNICAL.md) (arquitectura de referencia) |

---

## 2. Diseño arquitectónico

### 2.1 Descomposición en capas

Separación estricta **núcleo agnóstico a Qt** ↔ **UI PyQt6** (regla [ED-1](13_estandar_codificacion.md)):

| Capa | Paquetes | Responsabilidad | Qt |
|------|----------|-----------------|----|
| Decodificación | `decoder/` | Parsing ASTERIX, proyección polar→WGS-84, registro de sensores | No |
| Núcleo de seguridad | `analysis/stca_analyzer.py`, `player/areas/`, `player/msaw/`, `player/tracking/`, `fusion/` | Ciclo de vida, matching/correlación, STCA/APW/MSAW | No |
| Persistencia/análisis | `storage/`, `analysis/` | Auditoría, exportación, coberturas | No |
| Presentación (HMI) | `player/` (`radar_widget`, `main_window`, diálogos) | PPI, etiquetas, menús, roles | Sí |

El **núcleo de seguridad es headless**: verificable sin GUI y reproducible por ToD ([ED-1], [EC-6],
[EC-7]). Los motores reciben *tracks* por **duck-typing** (objeto o dict), lo que desacopla la lógica
del modelo concreto de la UI.

### 2.2 Flujo de datos

```
UDP/PCAP → DataEngine (decode+proyección) → batches de plots
   → radar_widget: matching/reconciliación (Correlator + MonoradarLifecycle)
   → cadena de seguridad coalescida ~1 Hz: STCA_Engine → evaluar_apw → evaluar_msaw
   → alertas visuales + persistencia asíncrona
```

La cadena de seguridad se coalesce a ~1 Hz independientemente del repintado ([ED-2], HLR-PERF-02).

### 2.3 Diagramas de secuencia

**Ingreso y matching de un batch de plots:**

```
PlaybackWorker            radar_widget                Correlator      MonoradarLifecycle
     │  new_plot_batch          │                          │                 │
     │─────────────────────────►│ _procesar_plots()        │                 │
     │                          │ por cada plot:           │                 │
     │                          │  claves_identidad()─────►│                 │
     │                          │  son_misma_aeronave()───►│ (extrapola+gate)│
     │                          │  ◄──── track asociado ───│                 │
     │                          │  procesar(plot)─────────────────────────►  │ (M-de-N por ToD)
     │                          │  calcular_velocidades()  │                 │
     │                          │ _schedule_safety()       │                 │
```

**Cadena de seguridad coalescida (~1 Hz):**

```
_schedule_safety()  →  (gate por *_habilitado)  →  evaluar_stca()  → STCA_Engine.evaluar_conflictos
                                                 →  evaluar_apw()   → evaluar_apw()
                                                 →  evaluar_msaw()  → evaluar_msaw()
                                                 →  finally: _safety_wall_last = wall-clock
_watchdog_timer (2 s)  →  _check_safety_watchdog()  →  si elapsed > 5 s: system_bus CRITICAL
```

### 2.4 Diagrama de estados del ciclo de vida monoradar

Estados y transiciones de `MonoradarLifecycle` (LLR-LIF-01..07); todas las transiciones se
gobiernan por ToD ASTERIX, nunca por reloj de pared:

```
                    plot con identidad nueva
                             │
                             ▼
                       ┌───────────┐  detección en vuelta posterior
                       │ TENTATIVE │  (detecciones++ ; salto ≥1.5·T reinicia racha)
                       └─────┬─────┘◄──────────────┐
        pierde 1 vuelta      │                     │
        (tick) → DELETED ◄───┤  detecciones ≥ confirm_n (4)
                             ▼
                       ┌───────────┐   tick: ≥1 vuelta sin detección
                       │ CONFIRMED │ ─────────────────────────────► ┌──────────┐
                       └───────────┘ ◄───────────────────────────── │ COASTING │
                             ▲          nueva detección (recupera)  └────┬─────┘
                             │                                          │ faltas ≥ drop_misses (4)
             plot misma vuelta a <pair_nm:                              ▼
             colapsa (no cambia estado);                           ┌─────────┐
             lejano → DUPLICADO_LEJANO                             │ DELETED │
                                                                   └─────────┘
```

### 2.5 Diagrama de despliegue (procesos e hilos)

```
┌────────────────────────── Proceso Python (main.py) ──────────────────────────┐
│                                                                              │
│  Hilo UI (Qt)                     QThread PlaybackWorker      Hilo worker    │
│  ┌───────────────────────┐        ┌─────────────────────┐     storage        │
│  │ MainWindow / Radar-   │ new_   │ decode UDP/PCAP     │     ┌───────────┐  │
│  │ Widget: matching,     │◄───────│ (DataEngine),       │     │ DuckDB    │  │
│  │ ciclo de vida, cadena │ plot_  │ deque(150k),        │     │ batches / │  │
│  │ STCA→APW→MSAW (~1 Hz),│ batch  │ batch cada 0.10 s   │     │ flush     │  │
│  │ render (≤15 Hz),      │        └──────────▲──────────┘     └─────▲─────┘  │
│  │ watchdog (2 s)        │────── cola no bloqueante ────────────────┘        │
│  └───────────┬───────────┘                   │                               │
└──────────────┼───────────────────────────────┼───────────────────────────────┘
               │ lectura RO                    │ UDP :20000+ (1 puerto = 1 sensor)
       ┌───────▼────────┐              ┌───────▼────────┐      ┌──────────────┐
       │ data/atm/      │              │ Sensores radar │      │ profiles/*.json
       │ atm.duckdb (RO)│              │ (red) o PCAP   │      │ config/ (RW)  │
       └────────────────┘              └────────────────┘      └──────────────┘
```

Las funciones de seguridad corren **en el hilo UI** (evaluación coalescida, no por plot); el
worker de red y el de persistencia no toman decisiones de seguridad ([ED-1/ED-2], LLR-AUD-01).

### 2.6 Decisiones de diseño con justificación (rationale)

| Id | Decisión | Justificación | Traza |
|----|----------|---------------|-------|
| DD-1 | Ciclo de vida gobernado por ToD; `time.time()` vedado en el núcleo | Reproducibilidad en playback; verificación determinista | HLR-TRK-01, [EC-7] |
| DD-2 | Fusión conservadora: ante duda, **no fusionar** | Un merge erróneo oculta tráfico y puede suprimir un STCA real; un duplicado visible es un fallo benigno comparado | HLR-TRK-06, [SSR-06], [ED-3] |
| DD-3 | Motores por duck-typing sobre objeto/dict | Compartir la lógica entre el motor en vivo y las herramientas offline sin acoplar a Qt | [ED-1] |
| DD-4 | STCA de doble fase: violación sobre posición cruda, predicción sobre cartesiano+velocidad | La fase crítica (<10 NM) no depende del suavizado → un conflicto real siempre dispara | HLR-STCA-01, hallazgo STCA-1 (gap §7) |
| DD-5 | Umbrales de seguridad como constantes/parámetros nombrados | Trazabilidad y ajuste auditable | [EC-11], [LR-3] |

---

## 3. LLR — Ciclo de vida monoradar (`player/tracking/lifecycle.py`)

> Implementa HLR-TRK-01/02. Confirmación M-de-N y coasting por vueltas de antena, por ToD.
> Clase `MonoradarLifecycle`; estados `TENTATIVE`/`CONFIRMED`/`COASTING`/`DELETED`/`DUPLICADO_LEJANO`.

| LLR | Enunciado | HLR |
|-----|-----------|-----|
| LLR-LIF-01 | La identidad de un plot **DEBE** derivarse como: squawk Modo 3/A no genérico si existe; en su defecto, para CAT021, callsign; en su defecto, dirección Mode S. Sin ninguno → el plot **NO DEBE** crear pista (`identidad_codigo` devuelve `None`). | HLR-TRK-03 |
| LLR-LIF-02 | El período de barrido **DEBE** obtenerse de `scan_period_fn(sac, sic)`; ante valor ausente o ≤ 0, **DEBE** usarse el valor por defecto de 4.0 s. | HLR-TRK-02 |
| LLR-LIF-03 | El conteo de vueltas **DEBE** basarse en el **tiempo transcurrido** (`plot.timestamp − ultima_tod`) contra el período, no en `floor(tod/período)`, para ser robusto a saltos de ToD y ráfagas de carga. | HLR-TRK-01 |
| LLR-LIF-04 | Una detección con `elapsed < 0.5·período` **DEBE** tratarse como misma vuelta (duplicado): si dista < `pair_nm` (1.0 NM) se colapsa en la pista; si no, se devuelve `DUPLICADO_LEJANO` sin alterar la racha. | HLR-TRK-02 |
| LLR-LIF-05 | Una pista `TENTATIVE` **DEBE** pasar a `CONFIRMED` al alcanzar `confirm_n` (4) detecciones en vueltas sucesivas; si se salta ≥ 1 vuelta entera (`elapsed ≥ 1.5·período`) la racha **DEBE** reiniciarse a 0. | HLR-TRK-02 |
| LLR-LIF-06 | En `tick(tod_actual)`, una pista `TENTATIVE` que pierde una vuelta **DEBE** eliminarse (`DELETED`); una `CONFIRMED`/`COASTING` **DEBE** pasar a `COASTING` y eliminarse al acumular `drop_misses` (4) vueltas sin detección. | HLR-TRK-02, [SSR-04] |
| LLR-LIF-07 | Ninguna operación del ciclo de vida **DEBE** invocar `time.time()` ni otro reloj de pared; el único tiempo admitido es `plot.timestamp` (ToD). | HLR-TRK-01, [EC-7] |

## 4. LLR — Correlación multisensor (`fusion/correlator.py`)

> Implementa HLR-TRK-03..08 y HLR-FUS-01..04. Clase `Correlator` + `CorrelatorConfig`.
> Tiempo inyectado por `now_fn` (TTL de asociación aprendida).

| LLR | Enunciado | HLR |
|-----|-----------|-----|
| LLR-COR-01 | Las claves de identidad de un track **DEBEN** ser `('MS', mode_s)` si Mode S es no vacío/≠`----`, y `('SQ', mode3a)` si el squawk es discreto (excluidos `----`,`0000`,`1200`,`2000`,`7000`). | HLR-FUS-01 |
| LLR-COR-02 | `son_misma_aeronave(a,b)` **NO DEBE** devolver True si `a` y `b` tienen Mode S ambos válidos y distintos, o squawks discretos ambos presentes y distintos. | HLR-TRK-06, [SSR-06] |
| LLR-COR-03 | Con ambos FL conocidos, `son_misma_aeronave` **NO DEBE** devolver True si `|ΔFL|·100 ≥ gate_vertical_ft` (1500 ft). | HLR-FUS-04 |
| LLR-COR-04 | La comparación de posición **DEBE** extrapolar ambos tracks al mayor de sus `timestamp` mediante `(vx,vy)`; la extrapolación **DEBE** limitarse a `|dt| ≤ extrapol_max_dt_s` (30 s), con corrección de rollover de medianoche (`dt += 86400` si `dt < −40000`). | HLR-FUS-03 |
| LLR-COR-05 | Con identidades no contradictorias, dos tracks **DEBEN** considerarse la misma aeronave si su distancia extrapolada ≤ `gate_estricto_nm` (0.7 NM). | HLR-TRK-05, HLR-FUS-02 |
| LLR-COR-06 | Una asociación aprendida squawk↔Mode S **DEBE** mantener la fusión hasta `gate_asociado_nm` (5 NM) solo mientras su antigüedad ≤ `assoc_ttl_s` (300 s), medida con `now_fn`. | HLR-FUS-02 |
| LLR-COR-07 | La velocidad **DEBE** tomarse de `_smooth_vx/_smooth_vy` si existe; en su defecto derivarse de `ground_speed`·(convención x=Este=sin, y=Norte=cos) solo si `1.0 ≤ v ≤ vel_fallback_max_mps` (600 m/s); si no, `(0,0)`. | HLR-FUS-03 |

## 5. LLR — STCA (`analysis/stca_analyzer.py`)

> Implementa HLR-STCA-01/02/05. Clase `STCA_Engine`. Doble fase (violación cruda + predicción CPA).
> Parámetros: `min_horizontal_nm=10`, `min_vertical_ft=900`, banda `fl_min=245`..`fl_max=450`.

| LLR | Enunciado | HLR |
|-----|-----------|-----|
| LLR-STC-01 | Un track con `speed_kt` conocido < 40 kt **DEBE** excluirse de la evaluación (blancos estáticos: calibración, reflectores). | HLR-STCA-01 |
| LLR-STC-02 | Solo **DEBEN** evaluarse tracks con `flight_level` entero dentro de `[fl_min, fl_max]` (245..450); un FL no numérico **DEBE** excluir el track. | HLR-STCA-01 |
| LLR-STC-03 | Un par **DEBE** suprimirse (misma aeronave) si comparten Modo 3/A no genérico o el mismo Mode S. | HLR-STCA-01, [SSR-06] |
| LLR-STC-04 | Un par con separación vertical `|ΔFL|·100 ≥ min_vertical_ft` (900 ft) **NO DEBE** generar alerta. | HLR-STCA-02 |
| LLR-STC-05 | La **fase de violación** **DEBE** usar la distancia haversine sobre `lat_render/lon_render` (posición cruda): si < `min_horizontal_nm` (10 NM) → `VIOLATION` con tiempo 0. Esta fase **NO DEBE** depender de `x/y` suavizados. | HLR-STCA-01, DD-4 |
| LLR-STC-06 | Un par co-ubicado (`dist_actual < 0.5 NM` y `ΔFL·100 < 200 ft`) **DEBE** suprimirse como duplicado del mismo blanco (dos aeronaves distintas nunca vuelan a < 0.5 NM co-altitud → no oculta STCA real). | HLR-STCA-01, DD-2 |
| LLR-STC-07 | La **fase de predicción** **DEBE** calcular `t_cpa` a partir de posición/velocidad relativas cartesianas y, solo si `0 < t_cpa ≤ 120 s` y la distancia proyectada en el CPA < `min_horizontal_nm`, emitir `PREDICTION` con `t_cpa` redondeado. | HLR-STCA-01/05 |

## 6. LLR — APW y MSAW (`player/areas/apw.py`, `player/msaw/engine.py`)

> APW implementa HLR-APW-01/03; MSAW implementa HLR-MSAW-01/03. Ambos reusan `predecir_posicion`
> y `_get_val` (lectura tolerante objeto/dict).

| LLR | Enunciado | HLR |
|-----|-----------|-----|
| LLR-APW-01 | Un track sin identificador, sin FL numérico o sin lat/lon numéricas **DEBE** excluirse; un track `degradada` o `is_reflection` **NO DEBE** evaluarse. | HLR-APW-01, [SSR-01] |
| LLR-APW-02 | Solo **DEBEN** evaluarse áreas con vigencia activa (`area.vigencia.activa`) y cuya banda vertical intersecte el FL del track (`area.banda(fl, margen=0)`). | HLR-APW-03 |
| LLR-APW-03 | Antes de la prueba geométrica **DEBE** aplicarse un prefiltro de *bounding box* entre la caja del área y la caja de la trayectoria `[posición, predicción a limit_s]`. | HLR-APW-01 (prestacional) |
| LLR-APW-04 | Si el punto actual está dentro del área → `VIOLATION` (eta 0). Si está fuera pero la trayectoria paso a paso (1..`limit_s`, `limit_s`=`prediction_time` o 120 s) entra → `PREDICTED` con la primera `eta` de entrada. | HLR-APW-01 |
| LLR-MSA-01 | La altitud del track **DEBE** derivarse como `FL·100` ft; un track sin FL/lat/lon numéricos, `degradada` o `is_reflection` **DEBE** excluirse; las categorías en `exentos` **DEBEN** inhibirse. | HLR-MSAW-01 |
| LLR-MSA-02 | La MSA aplicable **DEBE** buscarse primero en polígonos (`.identifier`) y luego en círculos (`.icao`); fuera de toda zona el track **DEBE** ignorarse. | HLR-MSAW-01 |
| LLR-MSA-03 | Si `suppression.suprime(lat,lon,alt)` es verdadero, la alerta **DEBE** suprimirse tanto en la violación inmediata como en cada paso de la predicción. | HLR-MSAW-03 |
| LLR-MSA-04 | `VIOLATION` **DEBE** emitirse si `alt < MSA`. La predicción **DEBE** evaluarse solo con `vertical_rate < 0` (descenso), proyectando altitud y posición hasta `time_to_prediction` y emitiendo `PREDICTED` en el primer paso que cruce por debajo de la MSA del sector proyectado. | HLR-MSAW-01 |

## 7. LLR — Presentación HMI / PPI (`player/radar_widget.py`)

> Implementa HLR-HMI-01..06. Capa Qt; los LLR describen el **contrato observable** de render y
> supervisión, no el detalle de pintado. El watchdog es la única función de seguridad que usa reloj de
> pared (`time.time()`), admitido por [EC-7] al ser un watchdog de UI, no lógica de decisión.

| LLR | Enunciado | HLR |
|-----|-----------|-----|
| LLR-HMI-01 | Todo track vivo (dentro de timeout, no ocultado por el operador) **DEBE** renderizarse con símbolo visible; un track no **DEBE** omitirse silenciosamente del PPI. | HLR-HMI-01, [SSR-04] |
| LLR-HMI-02 | La etiqueta **DEBE** mostrar callsign, Modo 3/A y FL tal como fueron decodificados y asociados; el render **NO DEBE** alterar esos campos. | HLR-HMI-02, [SSR-01] |
| LLR-HMI-03 | Un track `degradada` (DQF) o `is_reflection` **DEBE** excluirse de la evaluación de las redes de seguridad (STCA/APW/MSAW), pero **DEBE** seguir siendo visible en el PPI con simbología diferenciada. | HLR-HMI-04, DD-2 |
| LLR-HMI-04 | La cadena de seguridad **DEBE** registrar su instante de finalización (éxito o error) en `_safety_wall_last` dentro de un bloque `finally`. | HLR-HMI-06, [SSR-05] |
| LLR-HMI-05 | Un temporizador de 2 s **DEBE** comprobar que la cadena completó en los últimos **5 s** habiendo tracks activos; si `elapsed > 5 s`, **DEBE** inyectarse un evento `CRITICAL/WATCHDOG` en el bus del sistema (una sola vez hasta la recuperación). | HLR-HMI-06, [SSR-05] |
| LLR-HMI-06 | El estado habilitado/inhibido de cada red de seguridad **DEBE** estar reflejado en la HMI en todo momento sin acción del operador, mediante `estado_redes_seguridad()` y un indicador HUD siempre visible (no requiere abrir menú). | HLR-HMI-05, [SSR-10] |
| LLR-HMI-07 | El nivel de detalle de la etiqueta (declutter, en `player/ods/`) **DEBE** ser seleccionable por el operador (mínimo: símbolo + Modo 3/A; completo: FDB con callsign/FL/velocidad); el cambio de nivel **NO DEBE** hacer desaparecer tracks activos. | HLR-HMI-07 |
| LLR-HMI-08 | La vista FIR satelital (`player/firmap/`) **DEBE** ofrecerse como presentación alternativa superponible con los tracks activos, sin sustituir el PPI operativo. | HLR-HMI-08 |

## 8. LLR — Decodificación y proyección (`decoder/`)

> Implementa HLR-DEC-01/02/05/06/07/08 y HLR-GEO-01/03/04/05. `AsterixRouter` (troceo por LEN y
> enrutamiento por categoría), `adexp_parser` (FDP), `SensorRegistry` (parámetros de sensor),
> `TargetProcessor` (proyección polar→WGS-84→cartesiano) y `AltimetryManager` (TL / toggle A/F).

| LLR | Enunciado | HLR |
|-----|-----------|-----|
| LLR-DEC-01 | Los parámetros de sensor **DEBEN** cargarse de `<config_dir>/*.json` indexados por clave `"{sac}_{sic}"`; ante `sac/sic` no convertibles a entero, `get_sensor_coordinates` **DEBE** devolver `(None, None)`. | HLR-DEC-05, HLR-INTF-04 |
| LLR-DEC-02 | Un sensor sin posición configurada **DEBE** advertirse una sola vez (`_warned_sensors`) y **NO DEBE** producir proyección; el plot se marca `valid_position=False`. | HLR-DEC-06, [SSR-02] |
| LLR-GEO-01 | El primer sensor con posición **DEBE** fijar el centro de proyección (`set_radar_center`) solo si aún no hay centro (`center_lat is None`); las categorías CAT062 **NO DEBEN** requerir sensor local (inmunidad). | HLR-GEO-01/05 |
| LLR-GEO-02 | Para plots polares (rho/theta), la posición WGS-84 **DEBE** derivarse con `Geod(WGS84).fwd(lon,lat,azimuth,rho·1852)` (Vincenty) y luego proyectarse a cartesiano; la fidelidad **NO DEBE** degradar más allá del error de cuantización de la categoría. | HLR-GEO-01, HLR-DEC-02, [SSR-01] |
| LLR-GEO-03 | Sin centro de proyección o sin coordenadas de sensor, el plot **NO DEBE** presentarse con `x/y` por defecto silenciosos: `valid_position` permanece `False`. | HLR-GEO-03, [SSR-03] |
| LLR-DEC-03 | Los flags de calidad `invalid_a`/`invalid_c` **DEBEN** derivarse de la ausencia de `mode_3a`/`flight_level` respectivamente. | HLR-DEC-01 |
| LLR-DEC-04 | El router **DEBE** trocear el payload por la longitud declarada (`LEN` = bytes 1-2 del bloque) y **DEBE** cortar el bucle sin excepción cuando falten bytes de cabecera (`pointer+3 > total`) o cuando `msg_len ≤ 0` o `pointer+msg_len > total` (bloque corrupto/truncado). | HLR-DEC-07 |
| LLR-DEC-05 | El decode por categoría **DEBE** envolverse en captura de excepción que **loguee** el error (CAT + causa) y **continúe** con el siguiente mensaje; una trama malformada **NO DEBE** abortar el procesamiento del datagram. | HLR-DEC-07, [EC-9] |
| LLR-DEC-06 | El parser ADEXP (`parsear_trama`, SPEC-107) **DEBE** extraer los campos en mayúsculas (TITLE, ARCID, ADEP, ADES, RFL, …) y asociarse al track radar por coincidencia de callsign (`ARCID` ↔ callsign). | HLR-DEC-08 |
| LLR-GEO-04 | El nivel de transición **DEBE** calcularse como `TA/100 + capa(QNH)` según las bandas de presión ENR 1.7; `formatear_altitud` **DEBE** rotular `A###` (altitud corregida por QNH) si `≤ transition_altitude`, y `F###` (FL estándar) si está por encima; FL nulo → `F---`. | HLR-GEO-04, HLR-HMI-02 |

## 9. LLR — Persistencia/auditoría (`storage/`) y roles (`player/profile_manager.py`)

> Persistencia implementa HLR-AUD-01..04; roles implementan HLR-ROL-01..03.

| LLR | Enunciado | HLR |
|-----|-----------|-----|
| LLR-AUD-01 | `guardar_evento_safety` **DEBE** encolar el evento en `cola_insercion` (no bloqueante) solo si el worker está activo; la escritura ocurre en el hilo worker, **NO DEBE** bloquear el hilo principal. | HLR-AUD-01, [SSR-11] |
| LLR-AUD-02 | `flush()` **DEBE** encolar el centinela `"FLUSH"` y bloquear con `join()` hasta que el worker vacíe la cola; el cierre normal **DEBE** invocar `flush` antes de terminar. | HLR-AUD-02, [SSR-11] |
| LLR-AUD-03 | `query_safety_events` **DEBE** soportar filtros por subsistema, sesión y rango `ts_wall`, devolviendo filas **ordenadas por `ts_wall` ascendente**. | HLR-AUD-04 |
| LLR-AUD-04 | La exportación CSV **DEBE** emitir las columnas `fecha_hora_utc, ts_epoch, subsistema, transicion, nivel, aeronave_1, aeronave_2, descripcion, duracion_s, sesion_id`; `duracion_s` **DEBE** calcularse pareando cada `ONSET` con su primer `CLEAR` posterior de la misma `(subsistema, clave)`; un ONSET sin CLEAR queda con duración vacía. | HLR-AUD-03 |
| LLR-ROL-01 | Todo perfil cargado **DEBE** normalizarse por `to_strict_schema`: `rol` fuera de `{tecnico, controlador}` **DEBE** coercionarse a `tecnico`; un perfil ilegible **DEBE** caer al perfil por defecto, no cargarse parcialmente. | HLR-ROL-03 |
| LLR-ROL-02 | `get_rol()` **DEBE** devolver el rol activo normalizado (minúsculas, sin espacios); las funciones restringidas (playback, fusión, exportación, Centro Técnico) **DEBEN** gatearse por este valor. | HLR-ROL-01/02 |
| LLR-ROL-03 | Los perfiles **DEBEN** persistir en JSON `profiles/*.json` en formato estricto; un nombre vacío al guardar **DEBE** rechazarse con `ValueError`. | HLR-ROL-03 |

## 10. LLR — Prestaciones (`player/playback_worker.py`, `player/radar_widget.py`)

> Implementan HLR-PERF-01..05. **Contrato de medición:** condiciones nominales ≤ 200 plots/s por
> sensor; benchmarks reproducibles con factor de holgura en CI (ver [SVP §5.4](09_SVP.md)).

| LLR | Enunciado | HLR |
|-----|-----------|-----|
| LLR-PRF-01 | El worker UDP **DEBE** drenar como máximo `MAX_DRAIN` (200) datagramas por socket y ciclo de `select`, para no monopolizar el hilo ante ráfagas. | HLR-PERF-01/05 |
| LLR-PRF-02 | Los plots recibidos **DEBEN** almacenarse en un búfer acotado `deque(maxlen=150_000)`; al excederlo, los más antiguos se descartan automáticamente (no hay crecimiento ilimitado de memoria). | HLR-PERF-03/05, [EC-15] |
| LLR-PRF-03 | La emisión de batches al hilo de UI **DEBE** coalescerse: emitir cuando transcurran ≥ 0.10 s o se alcance `batch_size`; el evento `sensor_detected` **DEBE** emitirse una sola vez por sensor (`sensores_emitidos`). | HLR-PERF-01 |
| LLR-PRF-04 | La cadena de seguridad **DEBE** coalescerse a `_safety_interval` (1.0 s) con disparo *trailing* para no perder la última actualización; **NO DEBE** acoplarse al repintado. | HLR-PERF-02, [ED-2] |
| LLR-PRF-05 | El repintado del PPI **DEBE** limitarse a `_repaint_min_dt` (1/15 s ≈ 15 Hz máx) para desacoplar la tasa de refresco de la cadencia de ingreso de plots. | HLR-PERF-04 |

## 11. Trazabilidad y cobertura de verificación (núcleo SWAL 2)

| Módulo | LLR | Test de verificación |
|--------|-----|----------------------|
| `tracking/lifecycle.py` | LLR-LIF-01..07 | `tests/tracking/test_lifecycle*.py` |
| `fusion/correlator.py` | LLR-COR-01..07 | `tests/tracking/test_matching.py`, `tests/**/test_correlator.py` |
| `analysis/stca_analyzer.py` | LLR-STC-01..07 | `tests/stca/test_stca_engine.py`, `test_stca_scenarios.py` |
| `areas/apw.py` | LLR-APW-01..04 | `tests/areas/test_apw.py` |
| `msaw/engine.py` | LLR-MSA-01..04 | `tests/msaw/test_engine.py`, `test_suppression.py` |
| `player/radar_widget.py` | LLR-HMI-01..06 | `tests/tracking/test_hmi.py`, `tests/tracking/test_safety_state.py`, `tests/msaw/test_render.py` |
| `decoder/sensor_registry.py` | LLR-DEC-01..03, LLR-GEO-01..03 | `tests/decoders/test_sensor_registry.py`, `tests/geo/test_stereographic.py` |
| `storage/duckdb_repo.py` + `analysis/exporters.py` | LLR-AUD-01..04 | `tests/**/test_safety_audit.py` |
| `player/profile_manager.py` | LLR-ROL-01..03 | `tests/**/test_profile_manager.py` |
| `decoder/asterix_router.py` + `adexp_parser.py` | LLR-DEC-04..06 | `tests/decoders/`, `tests/fdp/` |
| `decoder/altimetry.py` | LLR-GEO-04 | `tests/decoders/test_altimetry.py` |
| `player/playback_worker.py` + `radar_widget.py` | LLR-PRF-01..05 | `tests/tracking/test_perf.py` |

Además, el [linter SWAL 2](../../tools/lint_swal2.py) verifica mecánicamente [EC-6/EC-7] sobre los
módulos del núcleo (headless, sin `time.time()`), reforzando LLR-LIF-07 en CI.

Todos los LLR de esta edición tienen test de verificación asociado (LLR-GEO-04 se cubrió con
`tests/decoders/test_altimetry.py` al detectarse la brecha).

## 12. Requisitos derivados (realimentar a seguridad)

Conforme a [doc 14 §2](14_estandar_requisitos.md), estos LLR nacen de decisiones de diseño (no de un
HLR operacional externo) y **deben** revisarse en el análisis de seguridad:

| LLR derivado | Origen de diseño | Nota de seguridad |
|--------------|------------------|-------------------|
| LLR-STC-06 | Supresión de duplicados co-ubicados (DD-2) | Umbral 0.5 NM/200 ft acotado para no ocultar STCA real; ver hallazgo STCA-1 |
| LLR-LIF-04 | Colapso de duplicados de la misma vuelta | `pair_nm`=1.0 NM; debe cubrirse por test de no-fusión errónea |
| LLR-COR-06 | Asociación aprendida con TTL | Extiende el gate a 5 NM; el TTL de 300 s acota el riesgo de arrastre |

## 13. Pendiente de esta edición

Con esta edición todos los HLR del [SRS](07_SRS.md) tienen al menos un LLR asociado y los diagramas
de secuencia (§2.3), estados (§2.4) y despliegue (§2.5) están incluidos. Resta como refinamiento
(no bloqueante para SOI-1):

- LLR por **categoría de decodificación** individual (CAT001/002/010/020/034/048/062) más allá del
  contrato de troceo/robustez ya cubierto por LLR-DEC-04/05.
- Formalización de precondiciones/poscondiciones por función en notación de contrato ([LR-3]).

## 14. Registro de cambios

| Ver | Fecha | Cambio |
|-----|-------|--------|
| 0.1 | 2026-07-05 | Emisión inicial: arquitectura (capas, flujo, decisiones DD-1..5) y LLR de los 4 motores núcleo SWAL 2 (LLR-LIF/COR/STC/APW/MSA), trazados a HLR y test. |
| 0.2 | 2026-07-05 | Añadidos LLR de **HMI/PPI** (LLR-HMI-01..06), **decodificación/proyección** (LLR-DEC/GEO), **persistencia/auditoría** (LLR-AUD) y **roles** (LLR-ROL); diagramas de secuencia (§2.3). |
| 0.3 | 2026-07-05 | Completados LLR de **robustez de decodificación** (LLR-DEC-04..06: troceo por LEN, excepción acotada, ADEXP), **altimetría** (LLR-GEO-04: TL/A-F, + test nuevo), **prestaciones** (LLR-PRF-01..05, §10) y **HMI secundaria** (LLR-HMI-07/08). Todos los HLR quedan con LLR asociado y todos los LLR con test. |
| 0.4 | 2026-07-05 | Diagramas de **estados** del ciclo de vida (§2.4) y de **despliegue** (§2.5). Cierra los refinamientos de arquitectura de D-3. |
