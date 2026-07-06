# PSSA / SSA — Evaluación de Seguridad del Software

**Sistema:** Decodificador ASTERIX + Display PPI ATC.
**Norma:** EUROCAE ED-109A / RTCA DO-278A; método de ED-135 / ARP4761 adaptado a software de tierra CNS/ATM.
**Versión:** 0.3 (borrador). **Fecha:** 2026-07-05. **Estado:** PROPUESTO — requiere validación con EANA/explotador y ANAC.

> Este documento cubre la **PSSA** (asignación descendente de requisitos de seguridad al diseño) y la
> **SSA** (verificación ascendente de que el diseño implementado los satisface), más un **argumento de
> seguridad** resumido. Toma como entrada el [FHA (doc 06)](06_FHA.md), y usa como evidencia el
> [SRS (doc 07)](07_SRS.md), el [SDD (doc 15)](15_SDD.md) y la suite de tests. Cierra las brechas
> **S-2/S-3** del [gap analysis](03_gap_analysis_DO-278A.md).
>
> **Nota de método (importante):** DO-278A/ED-109A asegura el software mediante **niveles de aseguramiento
> (SWAL)**, no mediante un presupuesto cuantitativo de probabilidad de fallo por ítem de software (eso
> corresponde al nivel de *sistema*, con hardware y procedimientos). Por ello esta PSSA es **cualitativa**:
> asigna SWAL, define el medio de diseño que mitiga cada condición de falla, y argumenta independencia y
> ausencia de causa común. Los presupuestos de probabilidad (10⁻ˣ/h del FHA §2) se satisfacen a nivel de
> sistema con las mitigaciones externas (H-AS-1..6) y la arquitectura, no por el software aislado.

---

## 1. Alcance y relación con otros documentos

| Entrada | Aporta |
|---------|--------|
| [FHA (06)](06_FHA.md) | 37 condiciones de falla (FC), severidad, SWAL, 11 SSR, supuestos H-AS-1..6 |
| [SRS (07)](07_SRS.md) | HLR y HLR-SSR-01..11 que formalizan los SSR |
| [SDD (15)](15_SDD.md) | Arquitectura, decisiones de diseño DD-1..5, LLR trazados |
| Suite `tests/` + CI | Evidencia de verificación reproducible |

La PSSA/SSA **no** re-deriva las FC (eso es el FHA); parte de ellas y demuestra que la arquitectura y la
implementación las controlan al nivel de aseguramiento requerido.

---

## 2. Estrategia de seguridad de la arquitectura (PSSA)

La seguridad se sostiene sobre cuatro argumentos arquitectónicos, cada uno con su evidencia:

| Arg | Argumento de diseño | Efecto de seguridad | Evidencia |
|-----|---------------------|---------------------|-----------|
| SA-1 | **Separación núcleo agnóstico a Qt ↔ UI** ([DD-3], [ED-1]) | Las funciones de seguridad son verificables headless y de forma reproducible; la falla de la UI no corrompe la lógica de decisión | Linter SWAL 2 en CI (`tools/lint_swal2.py`); LLR-*; tests unitarios headless |
| SA-2 | **Determinismo por ToD** ([DD-1], [EC-7]) | Reproducibilidad total en playback → toda FC de la lógica de decisión es re-ejecutable y testeable; sin dependencia de reloj de pared en decisiones | LLR-LIF-07; linter prohíbe `time.time(` en el núcleo |
| SA-3 | **Fusión conservadora** ([DD-2], [ED-3]) | Ante duda de identidad no se fusiona → se prefiere un duplicado visible (fallo benigno) a un merge que oculte tráfico o suprima un STCA (FC-TRK-01) | LLR-COR-02, LLR-STC-03/06; `test_matching.py`, `test_stca_engine.py` |
| SA-4 | **Sin descarte/omisión silenciosos** ([EC-9]) | Toda pérdida de un plot/track o bloqueo de la cadena es observable (contador/log/watchdog) → mitiga FC-HMI-01/04, FC-DEC-01 | LLR-HMI-04/05 (watchdog), ROB-1 mitigado; `test_plot_descarte.py` |

### 2.1 Independencia y particionamiento

- **Cadena de seguridad vs. render** ([ED-2]): la evaluación STCA/APW/MSAW se coalesce a ~1 Hz de forma
  independiente del repintado (LLR-PRF-04/05). Un bloqueo de render no detiene la evaluación, y viceversa;
  el **watchdog** (LLR-HMI-05) detecta si la cadena se detiene y lo comunica (mitiga FC-HMI-04).
- **Persistencia asíncrona** (LLR-AUD-01): la auditoría corre en hilo worker; su fallo (FC-AUD-01, SWAL 4)
  no bloquea ni degrada la cadena de seguridad (aislamiento de un componente de baja criticidad).
- **Rol técnico aislado** (LLR-ROL-02): fusión/calibración (FC-FUS-01/02) no operan en tiempo real para el
  controlador → su fallo no entra en el lazo operacional en vivo.

### 2.2 Análisis de causa común (CCA) y cascada

| Riesgo de causa común | Evaluación | Control |
|-----------------------|------------|---------|
| Proyección compartida corrompe todos los tracks de un sensor (FC-GEO-01) | Real: una constante errónea sesga sistemáticamente | SSR-03 / LLR-GEO-03: proyección no inicializada bloquea presentación; multi-sensor con proyección independiente por sensor (LLR-GEO-01) permite cruce |
| Un `except` amplio traga errores de todo el pipeline (FC-DEC-01) | Mitigado: `except` por categoría acotado, loguea y continúa | LLR-DEC-05, [EC-9/EC-10] |
| ToD anómalo (salto/rollover) desestabiliza ciclo de vida y correlación | Controlado: conteo por tiempo transcurrido y corrección de rollover | LLR-LIF-03, LLR-COR-04 |
| Cadena de seguridad se bloquea y congela alarmas (FC-HMI-04) | Detectado por watchdog independiente (timer de 2 s, umbral 5 s) | LLR-HMI-05, SSR-05 |

---

## 3. Asignación de requisitos de seguridad (PSSA — matriz FC → SSR → diseño → SWAL)

Para cada condición de falla SWAL 2/3 del FHA, el medio de diseño que la controla y su verificación.

| FC (sev./SWAL) | SSR | Medio de diseño (LLR / decisión) | Verificación |
|----------------|-----|----------------------------------|--------------|
| FC-DEC-02/03/04 — dato silenciosamente erróneo (SWAL 2) | SSR-01 | LLR-GEO-02 (fidelidad Vincenty), LLR-DEC-03 (flags de calidad), LLR-HMI-02 (etiqueta sin alterar) | `test_cat048_062.py`, `test_altimetry.py` |
| FC-DEC-02 — fuera de cobertura (SWAL 2) | SSR-02 | LLR-DEC-02 (sensor sin posición → `valid_position=False`, aviso) | `test_sensor_registry.py` |
| FC-GEO-01 — desplazamiento sistemático (SWAL 2) | SSR-03 | LLR-GEO-03 (proyección no inicializada no presenta), LLR-GEO-01 (centro válido) | `test_stereographic.py` |
| FC-HMI-01 / FC-TRK-03 / FC-LIF-02 — track omitido/caído (SWAL 2) | SSR-04 | LLR-HMI-01 (no omisión), LLR-LIF-06 (timeout trazable por ToD), LLR-LIF-03 | `test_hmi.py`, `test_lifecycle.py` |
| FC-HMI-04 — alarma no visible (SWAL 2) | SSR-05 | LLR-HMI-04/05 (watchdog `finally` + timer, umbral 5 s) | `test_hmi.py` (watchdog) |
| FC-TRK-01 — fusión errónea (SWAL 2) | SSR-06 | LLR-COR-02 (Mode S distintos ⇒ no fusión), [DD-2] fusión conservadora | `test_matching.py`, `test_correlator.py` |
| FC-STCA-01 — falso negativo STCA (SWAL 3) | SSR-07 | LLR-STC-05/07 (VIOLATION + PREDICTION), **LLR HLR-STCA-06 marco único** | `test_stca_engine.py`, `test_stca_scenarios.py` |
| FC-MSAW-01 — falso negativo MSAW (SWAL 3) | SSR-08 | LLR-MSA-01/04 (violación + predicción de descenso), LLR-MSA-03 (supresión) | `test_engine.py`, `test_suppression.py` |
| FC-APW-03 / FC-MSAW-04 — geometría/terreno corrupto (SWAL 3) | SSR-09 | HLR-APW-02 / HLR-MSAW-02 (validación en carga) | `test_apw.py`, `test_engine.py` |
| FC-STCA-03 — estado safety-net no visible (SWAL 3) | SSR-10 | LLR-HMI-06 (estado siempre visible) | inspección HMI (revisión) |
| FC-AUD-01 — pérdida de eventos (SWAL 4) | SSR-11 | LLR-AUD-02 (flush con `join` en cierre) | `test_safety_audit.py` |

---

## 4. SSA — Evidencia de verificación por SSR

Cierre ascendente: cada SSR con su estado de verificación real.

| SSR | Estado | Evidencia | Residual |
|-----|--------|-----------|----------|
| SSR-01 | ✅ Verificado (unitario) | Parsing fiel CAT048/062; altimetría A/F | Falta test de propagación al render (regresión visual) — ver FHA-A5 |
| SSR-02 | ✅ Verificado | `valid_position=False` sin sensor | — |
| SSR-03 | ✅ Verificado | Roundtrip + **rechazo de centro fuera de rango** (`test_projection_range.py`); caller trata el sensor como no configurado | — |
| SSR-04 | ✅ Verificado | Completitud de tracks vivos + timeout por ToD | Regresión visual pendiente (FHA-A5) |
| SSR-05 | ✅ Verificado | Watchdog 5 s → evento CRITICAL | — |
| SSR-06 | ✅ Verificado | No fusión de Mode S distintos (31 casos matching) | — |
| SSR-07 | ✅ Verificado | Geometría CPA + escenarios end-to-end + **contrato marco único (STCA-1 cerrado)** | Escenario de tráfico denso desde PCAP real (SOI-3) |
| SSR-08 | ✅ Verificado | Alerta + supresión MSAW | Test con datos de terreno límite |
| SSR-09 | ✅ Verificado | Rechazo en carga: áreas (`test_store.py`) y **zonas MSAW** (`test_data_load.py`, `filtrar_zonas_validas`) | — |
| SSR-10 | ✅ Verificado | Indicador HMI **siempre visible** (`estado_redes_seguridad()` + HUD); `test_safety_state.py` | — |
| SSR-11 | ✅ Verificado | Flush + query auditoría | — |

**Resumen SSA:** **11/11 SSR verificados** por test automatizado. Ninguna barrera crítica queda sin
verificar. El único residual es la **regresión visual pixel-level** del render (SSR-01/04, FC-HMI-01/02),
cubierta hoy a nivel de modelo/widget y mitigada por detección humana inmediata; acción SSA-A2 asignada.

---

## 5. Hallazgos de seguridad y riesgo residual

| Hallazgo | Estado | Argumento de aceptación |
|----------|--------|-------------------------|
| **STCA-1** — doble marco de coordenadas | **CERRADO** (2026-07-05) | Formalizado por HLR-STCA-06 (marco único); VIOLATION siempre sobre posición cruda; verificado por `test_contrato_*`. Residual acotado a precisión de PREDICTION, nunca conflicto omitido |
| **ROB-1** — descarte silencioso de plots | **MITIGADO** | Contador + log (LLR-HMI de observabilidad); no es defecto activo (campos bien tipados); `test_plot_descarte.py` |
| Regresión visual del render (FC-HMI-01/02) | Abierto (acción FHA-A5) | Cubierto a nivel de modelo/widget; falta pixel-level. Mitigado por detección humana inmediata de anomalía grosera |
| Carga corrupta de geometría/terreno (SSR-09) | **CERRADO** (2026-07-05) | Rechazo en carga verificado: áreas (`test_store.py`) y MSAW (`filtrar_zonas_validas`, `test_data_load.py`) |
| Centro de proyección fuera de rango (SSR-03) | **CERRADO** (2026-07-05) | `_build_proj` rechaza con ValueError; caller lo trata como sensor no configurado (`test_projection_range.py`) |
| Estado safety-net visible (SSR-10) | **CERRADO** (2026-07-05) | Indicador HUD siempre visible (esquina superior izquierda) desde `estado_redes_seguridad()`; `test_safety_state.py` |

**Riesgo residual global:** las barreras críticas de seguridad (no omitir tráfico, no fusionar aeronaves
distintas, generar STCA/MSAW ante conflicto real) están **verificadas**. El riesgo residual se concentra
en robustez ante datos de configuración corruptos y en regresión visual, ambos con mitigación operacional
(auditoría de carga, detección humana) y acción de cierre asignada. **Aceptable para SOI-1**, sujeto a
validación de supuestos H-AS-1..6 con EANA.

---

## 6. Requisitos de seguridad derivados (del diseño)

Conforme a [SDD §12](15_SDD.md) y [doc 14 §2](14_estandar_requisitos.md), estos requisitos nacen de
decisiones de diseño y se realimentan aquí al análisis de seguridad:

| Derivado | Riesgo de seguridad | Control / acotación |
|----------|---------------------|---------------------|
| LLR-STC-06 (supresión de duplicados co-ubicados) | Podría suprimir un conflicto real | Umbral 0.5 NM/200 ft: dos aeronaves distintas co-altitud a <0.5 NM ya es colisión → no oculta STCA real |
| LLR-COR-06 (asociación aprendida, gate 5 NM) | Arrastre de una asociación obsoleta | TTL 300 s acota la vida de la asociación |
| LLR-LIF-04 (colapso de duplicados misma vuelta, 1.0 NM) | Fusión de dos blancos cercanos distintos | Solo dentro de la misma vuelta y misma identidad de código |

---

## 7. Argumento de seguridad (safety case — resumen)

**Claim (C0):** el software del sistema es apto para operar como **ayuda a la vigilancia y red de
seguridad de respaldo** en el rol de controlador, al nivel de aseguramiento SWAL 2 asignado, bajo los
supuestos H-AS-1..6.

- **C1 — La imagen de tráfico presentada es fiel y completa.**
  - *Arg:* fidelidad de decodificación/proyección (SSR-01/02/03) + no omisión de tracks (SSR-04) +
    fusión conservadora (SSR-06).
  - *Ev:* §4 SSR-01..04/06 verificados; SA-3.
- **C2 — Las redes de seguridad detectan los conflictos reales que les competen.**
  - *Arg:* STCA (SSR-07, con STCA-1 cerrado) y MSAW (SSR-08) generan alerta ante conflicto/terreno real;
    validación de datos (SSR-09).
  - *Ev:* §4 SSR-07/08 verificados; §5 STCA-1 cerrado.
- **C3 — Los fallos de la función de seguridad son observables, no silenciosos.**
  - *Arg:* watchdog de la cadena (SSR-05), estado visible (SSR-10), sin descarte silencioso ([EC-9]).
  - *Ev:* §2.1; SA-4; ROB-1 mitigado.
- **C4 — La lógica de seguridad es verificable y reproducible.**
  - *Arg:* núcleo headless determinista por ToD; linter + suite en CI.
  - *Ev:* SA-1/SA-2; linter SWAL 2; cobertura de decisiones 88.5 % ([SVP §4.4](09_SVP.md)).

**Condiciones de validez del argumento:** (a) presencia de controlador humano y separación procedural
primaria (H-AS-1/2); (b) TCAS y GPWS/EGPWS a bordo como salvaguardas autónomas (H-AS-3/5); (c) auditoría
pre-operacional de los datos de configuración (áreas/terreno). Estas condiciones **deben** validarse con
EANA (acciones FHA-A1/A2) antes de la aprobación.

---

## 8. Acciones de cierre hacia SOI-2

| # | Acción | Deriva de | Estado |
|---|--------|-----------|--------|
| SSA-A1 | Test de rechazo de geometría/terreno corrupto en carga (cierra SSR-09) | §4 | ✅ Hecho (`test_store.py`, `test_data_load.py`) |
| SSA-A2 | Test de regresión visual del render ODS (cierra residual FC-HMI-01/02) | §5, FHA-A5 | Pendiente (pixel-level) |
| SSA-A3 | Test de parámetros de proyección fuera de rango (cierra SSR-03) | §4 | ✅ Hecho (`test_projection_range.py`) |
| SSA-A4 | Escenario STCA de tráfico denso desde PCAP real (refuerza SSR-07) | §4 | Pendiente (SOI-3) |
| SSA-A5 | Validar H-AS-1..6 con EANA y registrar en acta (habilita el safety case) | §7 | Pendiente (externo) |
| SSA-A6 | Presentar PSSA/SSA a ANAC en SOI-1/2 | §7 | Pendiente (externo) |
| SSA-A7 | Test automatizado de HMI de estado de safety-nets (cierra SSR-10) | §4 | ✅ Hecho (`test_safety_state.py` + HUD siempre visible) |

---

## 9. Registro de cambios

| Ver | Fecha | Cambio |
|-----|-------|--------|
| 0.1 | 2026-07-05 | Emisión inicial: estrategia de arquitectura (SA-1..4), CCA, PSSA (FC→SSR→diseño→SWAL), SSA (verificación de 11 SSR), riesgo residual, requisitos derivados y argumento de seguridad (C0..C4). |
| 0.2 | 2026-07-05 | Cerradas acciones **SSA-A1** (rechazo de zonas MSAW corruptas en carga) y **SSA-A3** (rechazo de centro de proyección fuera de rango). SSR-03/09 ⚠️→✅ (10/11 verificados). |
| 0.3 | 2026-07-05 | Cerrada **SSA-A7**: indicador HUD de estado de safety-nets siempre visible (`estado_redes_seguridad()`) + `test_safety_state.py`. **SSR-10 ✅ → 11/11 SSR verificados.** |
