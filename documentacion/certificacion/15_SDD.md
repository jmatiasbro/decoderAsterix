# SDD — Software Design Description

**Sistema:** Decodificador ASTERIX + Display PPI ATC.
**Norma:** EUROCAE ED-109A / RTCA DO-278A — diseño de software (D-3) y requisitos de bajo nivel (D-2).
**Versión:** 0.1 (borrador). **Fecha:** 2026-07-05. **Estado:** PROPUESTO — no aprobado por ANAC.

> Formaliza la **arquitectura** y los **Requisitos de Bajo Nivel (LLR)** del software. Los LLR derivan
> de los HLR del [SRS (doc 07)](07_SRS.md) y de la arquitectura, redactados conforme al
> [estándar de requisitos (doc 14)](14_estandar_requisitos.md) y al estándar de diseño
> ([doc 13 §4](13_estandar_codificacion.md)). Cierra la parte de diseño/LLR de las brechas **D-2/D-3**
> del [gap analysis](03_gap_analysis_DO-278A.md).
>
> **Alcance de esta edición:** LLR completos para los **cuatro motores núcleo SWAL 2** (ciclo de vida,
> correlación, STCA, APW/MSAW), que concentran el riesgo de seguridad. Los LLR de HMI, decodificación
> y persistencia se incorporarán en ediciones sucesivas (ver §7).

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

### 2.3 Decisiones de diseño con justificación (rationale)

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

## 7. Trazabilidad y cobertura de verificación (núcleo SWAL 2)

| Módulo | LLR | Test de verificación |
|--------|-----|----------------------|
| `tracking/lifecycle.py` | LLR-LIF-01..07 | `tests/tracking/test_lifecycle*.py` |
| `fusion/correlator.py` | LLR-COR-01..07 | `tests/tracking/test_matching.py`, `tests/**/test_correlator.py` |
| `analysis/stca_analyzer.py` | LLR-STC-01..07 | `tests/stca/test_stca_engine.py`, `test_stca_scenarios.py` |
| `areas/apw.py` | LLR-APW-01..04 | `tests/areas/test_apw.py` |
| `msaw/engine.py` | LLR-MSA-01..04 | `tests/msaw/test_engine.py`, `test_suppression.py` |

Además, el [linter SWAL 2](../../tools/lint_swal2.py) verifica mecánicamente [EC-6/EC-7] sobre estos
módulos (headless, sin `time.time()`), reforzando LLR-LIF-07 en CI.

## 8. Requisitos derivados (realimentar a seguridad)

Conforme a [doc 14 §2](14_estandar_requisitos.md), estos LLR nacen de decisiones de diseño (no de un
HLR operacional externo) y **deben** revisarse en el análisis de seguridad:

| LLR derivado | Origen de diseño | Nota de seguridad |
|--------------|------------------|-------------------|
| LLR-STC-06 | Supresión de duplicados co-ubicados (DD-2) | Umbral 0.5 NM/200 ft acotado para no ocultar STCA real; ver hallazgo STCA-1 |
| LLR-LIF-04 | Colapso de duplicados de la misma vuelta | `pair_nm`=1.0 NM; debe cubrirse por test de no-fusión errónea |
| LLR-COR-06 | Asociación aprendida con TTL | Extiende el gate a 5 NM; el TTL de 300 s acota el riesgo de arrastre |

## 9. Pendiente de esta edición

- LLR de **HMI/PPI** (HLR-HMI-01..08): render, etiquetas, watchdog de la cadena (FC-HMI).
- LLR de **decodificación** (HLR-DEC-01..08) y **proyección** (HLR-GEO-01..05).
- LLR de **persistencia/auditoría** (HLR-AUD-01..04) y **roles** (HLR-ROL-01..03).
- Diagramas de secuencia de la cadena de seguridad y del matching.

## 10. Registro de cambios

| Ver | Fecha | Cambio |
|-----|-------|--------|
| 0.1 | 2026-07-05 | Emisión inicial: arquitectura (capas, flujo, decisiones DD-1..5) y LLR de los 4 motores núcleo SWAL 2 (LLR-LIF/COR/STC/APW/MSA), trazados a HLR y test. |
