# Gap Analysis — DO-278A / ED-109A

**Versión:** 1.1. **Fecha:** 2026-07-06. **SWAL de referencia:** 2 (núcleo, provisional).

> Estado por objetivo: ✅ Cumplido · ⚠️ Parcial · ❌ Ausente. La columna *Evidencia* apunta a lo que
> existe hoy en el repositorio. Los objetivos se agrupan por proceso DO-278A. La numeración es
> indicativa; al adquirir la norma debe alinearse con sus tablas A-1…A-9 oficiales.

---

## Resumen ejecutivo

| Proceso | Objetivos | ✅ | ⚠️ | ❌ | % cobertura aprox. |
|---------|-----------|----|----|----|--------------------|
| Planificación | 5 | 4 | 1 | 0 | 90% |
| Desarrollo (requisitos/diseño/código) | 6 | 6 | 0 | 0 | 100% |
| Verificación | 7 | 4 | 2 | 1 | 70% |
| Gestión de configuración (SCM) | 4 | 2 | 2 | 0 | 78% |
| Aseguramiento de calidad (SQA) | 3 | 3 | 0 | 0 | 100% |
| Enlace con autoridad | 2 | 0 | 1 | 1 | 15% |
| Análisis de seguridad | 3 | 1 | 2 | 0 | 75% |
| **Total** | **30** | **20** | **8** | **2** | **~80%** |

Conclusión: **la capa de evidencia de proceso está sustancialmente construida** (planes, FHA, SRS con
57 HLR, matriz de trazabilidad, CI con cobertura de decisiones al 88.5 % sobre módulos SWAL 2,
estándares formales de código/diseño (con linter en CI) y de requisitos, y registros de revisión de
código, SDD con LLR para todas las capas, y PSSA/SSA con argumento de seguridad). Las brechas restantes
se concentran en: **independencia de verificación** (equipo unipersonal), **validación con la autoridad**
de los supuestos de seguridad (EANA/ANAC) e **higiene de configuración** (purga de binarios del histórico
git, RNC-010). El sistema no está aún aprobado, pero el paquete es coherente para presentar SOI-1 y avanzar
hacia SOI-2.

> **Nota de trazabilidad de este documento:** la v0.1 (2026-06-28) precedía a la creación de los planes
> y la FHA/SRS; esta v0.2 actualiza el estado a lo efectivamente producido.

---

## 1. Proceso de Planificación

| Obj | Descripción | Estado | Evidencia / Brecha |
|-----|-------------|--------|--------------------|
| P-1 | PSAC definido y acordado con la autoridad | ⚠️ | [01_PSAC.md](01_PSAC.md) borrador; sin acuerdo ANAC |
| P-2 | SDP (plan de desarrollo) | ✅ | [08_SDP.md](08_SDP.md) |
| P-3 | SVP (plan de verificación) | ✅ | [09_SVP.md](09_SVP.md) |
| P-4 | SCMP + SQAP | ✅ | [10_SCMP.md](10_SCMP.md), [11_SQAP.md](11_SQAP.md) |
| P-5 | Estándares de requisitos/diseño/código | ✅ | Código/diseño en [13](13_estandar_codificacion.md) (EC/ED, linter en CI) y requisitos en [14](14_estandar_requisitos.md) (ER/RR/CJ/VF/LR + checklist QR) |

## 2. Proceso de Desarrollo

| Obj | Descripción | Estado | Evidencia / Brecha |
|-----|-------------|--------|--------------------|
| D-1 | Requisitos de alto nivel (HLR) | ✅ | [07_SRS.md](07_SRS.md) — 57 HLR trazados a FHA/specs |
| D-2 | Requisitos de bajo nivel (LLR) | ✅ | [SDD §3-10](15_SDD.md): **todo HLR del SRS tiene ≥1 LLR** (LIF/COR/STC/APW/MSA, HMI, DEC/GEO, AUD/ROL, PRF), trazado a HLR y test; refinamientos por categoría/diagramas de estados pendientes ([SDD §13](15_SDD.md)) |
| D-3 | Arquitectura de software | ✅ | [SDD (doc 15)](15_SDD.md) v0.4: capas, flujo, decisiones DD-1..5 y diagramas de **secuencia (§2.3), estados (§2.4) y despliegue (§2.5)** |
| D-4 | Código fuente conforme a estándares | ✅ | Estándar formal en [13](13_estandar_codificacion.md); módulos SWAL 2 revisados (RR-01..05) y **linter automatizado en CI** (`tools/lint_swal2.py`, prohibiciones EC-5/6/7) |
| D-5 | Trazabilidad requisitos↔diseño↔test | ✅ | [04_matriz_trazabilidad.md](04_matriz_trazabilidad.md) — sin huecos de test |
| D-6 | Determinismo / reproducibilidad | ✅ | Ciclo de vida por ToD; `time.time()` vedado (`lifecycle.py`) |

## 3. Proceso de Verificación

| Obj | Descripción | Estado | Evidencia / Brecha |
|-----|-------------|--------|--------------------|
| V-1 | Revisión de requisitos | ⚠️ | SRS existe; auditoría de revisión definida en SQAP §3.2, sin registro firmado |
| V-2 | Revisión de diseño | ⚠️ | Arquitectura documentada; revisión de diseño no registrada formalmente |
| V-3 | Revisión/análisis de código | ✅ | [12_registros_revision_codigo.md](12_registros_revision_codigo.md) (RR-01..05, 5 módulos SWAL 2) |
| V-4 | Pruebas basadas en requisitos | ✅ | 536 tests; trazabilidad HLR↔test completa ([04](04_matriz_trazabilidad.md)) |
| V-5 | Cobertura estructural acorde a SWAL | ✅ | Cobertura de decisiones (branch) **88.5 %** en módulos SWAL 2, gate ≥80 % en CI ([SVP §4.4](09_SVP.md)) |
| V-6 | Pruebas de integración del sistema | ✅ | `tests/integration/test_pcap_e2e.py` + escenarios STCA end-to-end; CI ejecuta la suite en cada push |
| V-7 | Independencia de la verificación | ❌ | Equipo unipersonal (RNC-006); requiere revisor externo o acuerdo ANAC |

## 4. Gestión de Configuración (SCM)

| Obj | Descripción | Estado | Evidencia / Brecha |
|-----|-------------|--------|--------------------|
| C-1 | Identificación de la configuración | ✅ | Baselines etiquetados `v0.1.0-soi1` … `v0.4.0`; lockfile y checksums |
| C-2 | Control de cambios / problem reporting | ⚠️ | Commits convencionales + tabla de RNCs (SQAP §5.3); falta herramienta formal de seguimiento |
| C-3 | Integridad del árbol de fuentes | ⚠️ | `.gitignore` endurecido; purga del histórico **con procedimiento listo para ejecutar** ([doc 18](18_procedimiento_purga_RNC010.md), RNC-010) — requiere decisión del responsable (destructivo) |
| C-4 | Control de entornos de build | ✅ | Runtime documentado; `requirements.txt`/`-linux`/`.lock`; CI reproducible en Linux |

## 5. Aseguramiento de Calidad (SQA)

| Obj | Descripción | Estado | Evidencia / Brecha |
|-----|-------------|--------|--------------------|
| Q-1 | Auditorías de proceso | ✅ | Ejecutadas y registradas: AUD-P/V/C/G-01 sobre baseline v0.4.0+ ([doc 17](17_registros_auditoria_SQA.md)) |
| Q-2 | Auditorías de conformidad de productos | ✅ | Revisión de producto AUD-PR-01 ([doc 17 §5](17_registros_auditoria_SQA.md)) + [doc 12](12_registros_revision_codigo.md); independencia sigue como RNC-006 |
| Q-3 | Aseguramiento de transición del ciclo de vida | ✅ | Criterios de entrada a SOI-1 evaluados y registrados: AUD-T-01 ([doc 17 §6](17_registros_auditoria_SQA.md)) |

## 6. Enlace con la Autoridad

| Obj | Descripción | Estado | Evidencia / Brecha |
|-----|-------------|--------|--------------------|
| A-1 | Acuerdo del PSAC y puntos de revisión (SOI) | ⚠️ | PSAC borrador; sin coordinación ANAC |
| A-2 | Presentación del cierre (SAS/Accomplishment Summary) | ❌ | No existe (corresponde a SOI-4) |

## 7. Análisis de seguridad (transversal, exigido por marco ATM)

| Obj | Descripción | Estado | Evidencia / Brecha |
|-----|-------------|--------|--------------------|
| S-1 | FHA (Functional Hazard Assessment) | ✅ | [06_FHA.md](06_FHA.md) — condiciones de falla, SSR y clasificación de severidad |
| S-2 | PSSA / SSA | ⚠️ | [16_PSSA_SSA.md](16_PSSA_SSA.md): estrategia de arquitectura (SA-1..4), CCA, asignación FC→SSR→diseño→SWAL y verificación SSA de 11 SSR; falta validación EANA/ANAC |
| S-3 | Safety case / argumento de seguridad | ⚠️ | [16 §7](16_PSSA_SSA.md): argumento C0..C4 con evidencia; **todas las acciones técnicas SSA-A1..A4/A7 cerradas** (11/11 SSR, sin residual interno); falta solo validar supuestos H-AS-1..6 con EANA/ANAC (externo) |

### Hallazgos de verificación (seguimiento)

> Estado al 2026-07-06: **STCA-1 cerrado** (HLR-STCA-06 + tests de contrato); **ROB-1 mitigado**;
> **TRK-1 cerrado** (ver abajo); **STCA-2 cerrado** (segmentación TMA/Ruta, HLR-STCA-01/02/07/08).

**TRK-1 — Fusión errónea por proximidad en el paso E** (severidad: **ALTA** — FC-TRK-01/SWAL 2; estado: **CERRADO** 2026-07-06, RNC-011).
El gate de proximidad del matching (paso E) fusionaba dos aeronaves con **Mode S válidos distintos**
a <3 NM co-altitud, violando HLR-TRK-06/SSR-06: una de las dos desaparecía de pantalla y el **STCA
quedaba suprimido exactamente en la geometría de conflicto**. Detectado al construir el escenario de
verificación TMA del STCA segmentado (el test e2e falló revelando la fusión). *Cierre:* veto de
identidad contradictoria antes de fusionar por cercanía (LLR-COR-08, coherente con DD-2 «fusión
conservadora»); verificado unitario (`test_matching.py`) y e2e (`test_stca_scenarios.py`).

**STCA-2 — Banda y umbrales STCA hardcodeados** (severidad: MEDIA — operativa; estado: **CERRADO** 2026-07-06).
El motor fijaba FL245–450 / 10 NM / 900 ft sin configuración: el TMA quedaba **sin protección STCA** y
la implementación no trazaba a HLR-STCA-01/02. *Cierre:* segmentación por volúmenes RAAC/Doc 4444
(TMA 3 NM/800 ft, Ruta 5 NM/1000 ft, transición conservadora, fallback seguro) — HLR-STCA-01/02/07/08
y LLR-STC-01..09, con banco de pruebas de segmentación.

**STCA-1 — Doble marco de coordenadas en el motor STCA** (severidad: BAJA; estado: **CERRADO** 2026-07-05).
`STCA_Engine.evaluar_conflictos` resuelve la **separación actual** con haversine sobre
`lat_render/lon_render` (posición cruda reportada) y la **predicción de CPA** con `x/y`. El caller
`radar_widget.evaluar_stca` alimenta `x/y` con la posición proyectada **suavizada alpha-beta**
([radar_widget.py:1827](../../player/radar_widget.py)), de un linaje distinto a `lat_render`. Además
hay un mismatch de prioridad de campo (`lat or lat_render` en la reproyección vs `lat_render or lat`
en el builder STCA).
- *Riesgo acotado:* la fase VIOLATION (crítica) usa la posición cruda → un conflicto real cercano
  (<10 NM) **siempre** dispara, sin depender de `x/y`. El efecto es una discontinuidad de precisión
  en el borde de los 10 NM (predicción adelantada/atrasada, posible falso positivo transitorio), no
  un conflicto omitido.
- *Riesgo acotado:* la fase VIOLATION (crítica) usa la posición cruda → un conflicto real cercano
  (<10 NM) **siempre** dispara, sin depender de `x/y`. El efecto es una discontinuidad de precisión
  en el borde de los 10 NM (predicción adelantada/atrasada, posible falso positivo transitorio), no
  un conflicto omitido.
- *Cierre (2026-07-05):* se formalizó el contrato como requisito **[HLR-STCA-06](07_SRS.md)** («marco
  de posición único y consistente»): el caller debe suministrar `x/y` como la proyección local de
  `lat_render/lon_render`, y la VIOLATION se decide siempre sobre la posición cruda. El requisito queda
  verificado por `tests/stca/test_stca_engine.py`:
  - `test_contrato_marco_unico_prediccion_coherente` — bajo el contrato (marco único), la PREDICTION es
    geométricamente coherente con la geometría cruda de la VIOLATION.
  - `test_contrato_xy_inconsistente_no_oculta_violacion` — un `x/y` inconsistente **no puede** ocultar
    una violación real (residual acotado a la precisión de la PREDICTION, nunca a un conflicto omitido).
  Complementado end-to-end por `tests/stca/test_stca_scenarios.py`. Con el requisito trazado y verificado,
  el hallazgo se considera **cerrado**.

**ROB-1 — Descarte silencioso de plots en el procesamiento** (severidad: BAJA; estado: mitigado).
`radar_widget._process_plot_data` envuelve el procesamiento en `except Exception: return None`. Ante
una excepción inesperada en cualquier campo, el plot se descartaba **sin traza** — equivalente a una
aeronave no pintada (mismo modo de falla que FC-HMI-01). No es un defecto activo (el decoder emite los
campos bien tipados: `flight_level` es `float`/`None`, nunca string), sino una brecha de
*observabilidad*.
- *Mitigación aplicada (2026-07-05):* se añadió un **contador de descartes** (`_plots_descartados`) y
  logging con throttle (`_registrar_descarte_plot`), de modo que un descarte deja de ser silencioso.
  Verificado por `tests/tracking/test_plot_descarte.py` (3 casos).
- *Acción de certificación:* considerar exponer el contador en la HMI/telemetría técnica y acotar el
  alcance del `except` a las secciones que realmente lo requieren (evitar tragar errores de programación).

## 8. Prioridades de cierre (top 5)

Reordenadas al estado actual (cerrados: planes/FHA/SRS/CI en v0.2; P-5/D-4 en v0.3; SDD+LLR completos y D-2 en v0.4-0.6):

1. **Independencia de verificación** (V-7 / RNC-006): revisor externo o acuerdo ANAC.
2. **Validar el análisis de seguridad** con EANA/ANAC: PSSA/SSA y safety case redactados y con todas las acciones técnicas cerradas ([doc 16](16_PSSA_SSA.md)); resta solo validar supuestos H-AS-1..6 (FHA-A1/A2, externo).
3. **Enlace con la autoridad** (A-1): coordinar SOI-1 con ANAC sobre el paquete ya construido.
4. **Higiene de configuración**: ejecutar la purga de binarios (C-3 / RNC-010) según el [procedimiento listo](18_procedimiento_purga_RNC010.md) — requiere decisión del responsable (destructivo).
5. **Refinamiento menor**: LLR por categoría de decodificación y contratos por función ([SDD §13](15_SDD.md)).

## 9. Registro de cambios

| Ver | Fecha | Cambio |
|-----|-------|--------|
| 0.1 | 2026-06-28 | Creación inicial (previo a planes/FHA/SRS). |
| 0.2 | 2026-07-05 | Actualización al estado real: cierre de P-2/3/4, D-1/5, V-3/4/5/6, C-1/4, S-1; reclasificación de SQA y prioridades. Cobertura de proceso ~30 % → ~62 %. |
| 0.3 | 2026-07-05 | Cierre de **P-5** (estándar de requisitos, doc 14) y **D-4** (linter SWAL 2 en CI). Cobertura ~63 % → ~67 %; prioridades reordenadas (LLR/SDD #1). |
| 0.4 | 2026-07-05 | **SDD (doc 15)** con arquitectura y LLR de los 4 motores núcleo SWAL 2: **D-2** ❌→⚠️, **D-3** mejorado. Cobertura ~67 % → ~68 %. |
| 0.5 | 2026-07-05 | SDD v0.2: LLR de HMI/DEC/GEO/AUD/ROL + diagramas de secuencia (profundiza D-2/D-3, sin cambio de estado). |
| 0.6 | 2026-07-05 | SDD v0.3: LLR de robustez/altimetría/prestaciones/HMI secundaria — **todo HLR con LLR**. **D-2** ⚠️→✅. Cobertura ~68 % → ~70 %. |
| 0.7 | 2026-07-05 | **STCA-1 cerrado** vía HLR-STCA-06 (marco de posición único) + tests de contrato. Sin cambio de % (S-2/S-3 siguen abiertos). |
| 0.8 | 2026-07-05 | **PSSA/SSA + safety case (doc 16)**: **S-2/S-3** ❌→⚠️. Análisis de seguridad 33 % → 67 %; cobertura total ~70 % → ~73 %. |
| 0.9 | 2026-07-05 | Cierre de SSA-A1/A3/A7 (SSR-03/09/10 verificados, 11/11) y **registros de auditoría SQA (doc 17)**: **Q-1/Q-2/Q-3** ⚠️→✅. SQA 50 % → 100 %; total ~73 % → ~78 %. |
| 1.0 | 2026-07-05 | Cierre de **SSA-A2** (regresión visual) y **SSA-A4** (STCA denso PCAP) — sin residual técnico interno; **D-3 ✅** (diagramas estados/despliegue, SDD v0.4); procedimiento de purga RNC-010 listo ([doc 18](18_procedimiento_purga_RNC010.md)). Desarrollo 100 %; total ~78 % → **~80 %**. |
| 1.1 | 2026-07-06 | **STCA segmentado TMA/Ruta** (cierra hallazgo STCA-2: el TMA quedaba sin protección) y **TRK-1/RNC-011 cerrado**: fusión errónea por proximidad con Mode S distintos (FC-TRK-01, detectada por el nuevo escenario TMA y corregida con veto de identidad en paso E). |
