# Gap Analysis — DO-278A / ED-109A

**Versión:** 0.2. **Fecha:** 2026-07-05. **SWAL de referencia:** 2 (núcleo, provisional).

> Estado por objetivo: ✅ Cumplido · ⚠️ Parcial · ❌ Ausente. La columna *Evidencia* apunta a lo que
> existe hoy en el repositorio. Los objetivos se agrupan por proceso DO-278A. La numeración es
> indicativa; al adquirir la norma debe alinearse con sus tablas A-1…A-9 oficiales.

---

## Resumen ejecutivo

| Proceso | Objetivos | ✅ | ⚠️ | ❌ | % cobertura aprox. |
|---------|-----------|----|----|----|--------------------|
| Planificación | 5 | 3 | 1 | 1 | 70% |
| Desarrollo (requisitos/diseño/código) | 6 | 3 | 2 | 1 | 65% |
| Verificación | 7 | 4 | 2 | 1 | 70% |
| Gestión de configuración (SCM) | 4 | 2 | 2 | 0 | 75% |
| Aseguramiento de calidad (SQA) | 3 | 0 | 3 | 0 | 50% |
| Enlace con autoridad | 2 | 0 | 1 | 1 | 15% |
| Análisis de seguridad | 3 | 1 | 0 | 2 | 33% |
| **Total** | **30** | **13** | **11** | **6** | **~62%** |

Conclusión: **la capa de evidencia de proceso está sustancialmente construida** (planes, FHA, SRS con
56 HLR, matriz de trazabilidad, CI con cobertura de decisiones al 88.5 % sobre módulos SWAL 2, y
registros de revisión de código). Las brechas restantes se concentran en: **estándares formales** de
codificación/diseño, **requisitos de bajo nivel (LLR)**, **independencia de verificación** (equipo
unipersonal) y **análisis de seguridad avanzado** (PSSA/SSA/safety case). El sistema no está aún
aprobado, pero el paquete es coherente para presentar SOI-1 y avanzar hacia SOI-2.

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
| P-5 | Estándares de requisitos/diseño/código | ❌ | No formalizados; convenciones en CLAUDE.md y checklist de revisión (doc 12) |

## 2. Proceso de Desarrollo

| Obj | Descripción | Estado | Evidencia / Brecha |
|-----|-------------|--------|--------------------|
| D-1 | Requisitos de alto nivel (HLR) | ✅ | [07_SRS.md](07_SRS.md) — 56 HLR trazados a FHA/specs |
| D-2 | Requisitos de bajo nivel (LLR) | ❌ | No documentados formalmente |
| D-3 | Arquitectura de software | ⚠️ | CLAUDE.md, TECHNICAL.md y SRS §2; falta SDD formal |
| D-4 | Código fuente conforme a estándares | ⚠️ | Revisado (RR-01..05, doc 12); falta estándar de codificación formal contra el cual verificar |
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
| C-3 | Integridad del árbol de fuentes | ⚠️ | `.gitignore` endurecido; falta **purgar del histórico** los binarios ya versionados |
| C-4 | Control de entornos de build | ✅ | Runtime documentado; `requirements.txt`/`-linux`/`.lock`; CI reproducible en Linux |

## 5. Aseguramiento de Calidad (SQA)

| Obj | Descripción | Estado | Evidencia / Brecha |
|-----|-------------|--------|--------------------|
| Q-1 | Auditorías de proceso | ⚠️ | Definidas en [SQAP §3.1](11_SQAP.md); ejecución por baseline pendiente de registro |
| Q-2 | Auditorías de conformidad de productos | ⚠️ | Revisiones de producto realizadas (doc 12); falta auditoría SQA independiente |
| Q-3 | Aseguramiento de transición del ciclo de vida | ⚠️ | Baselines + resultados archivados iniciados; criterios de transición a formalizar |

## 6. Enlace con la Autoridad

| Obj | Descripción | Estado | Evidencia / Brecha |
|-----|-------------|--------|--------------------|
| A-1 | Acuerdo del PSAC y puntos de revisión (SOI) | ⚠️ | PSAC borrador; sin coordinación ANAC |
| A-2 | Presentación del cierre (SAS/Accomplishment Summary) | ❌ | No existe (corresponde a SOI-4) |

## 7. Análisis de seguridad (transversal, exigido por marco ATM)

| Obj | Descripción | Estado | Evidencia / Brecha |
|-----|-------------|--------|--------------------|
| S-1 | FHA (Functional Hazard Assessment) | ✅ | [06_FHA.md](06_FHA.md) — condiciones de falla, SSR y clasificación de severidad |
| S-2 | PSSA / SSA | ❌ | No existe |
| S-3 | Safety case / argumento de seguridad | ❌ | `safety_audit_dialog` audita tráfico, no es safety case de SW |

### Hallazgos de verificación abiertos

**STCA-1 — Doble marco de coordenadas en el motor STCA** (severidad: BAJA; estado: abierto).
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
- *Acción de certificación:* el SRS debe incluir un requisito de que el caller suministre un **único
  marco de posición consistente** a ambas fases, o que el motor reproyecte `x/y` desde `lat_render`.
  Contrato actual fijado por tests en `tests/stca/test_stca_engine.py` (`test_contrato_*`).
- *Cobertura del comportamiento acotado (2026-07-05):* `tests/stca/test_stca_scenarios.py` verifica
  **end-to-end por el pipeline del widget** que un conflicto real <10 NM co-altitud **siempre**
  dispara VIOLATION (fase crítica, sobre posición cruda), y que no hay falsos positivos en separación
  vertical/horizontal, misma aeronave, blancos estáticos, fuera de banda FL e inhibición. Esto acota
  empíricamente el riesgo del hallazgo a la precisión de la fase PREDICTION en el borde de los 10 NM,
  sin conflicto omitido. El defecto de diseño (doble marco) permanece **abierto** hasta el requisito SRS.

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

Reordenadas al estado actual (los ítems de v0.1 sobre planes/FHA/SRS/CI ya están cerrados):

1. **Estándares formales** de codificación/diseño/requisitos (P-5, D-4) — última brecha grande de proceso interno.
2. **Requisitos de bajo nivel (LLR)** y **SDD formal** (D-2, D-3).
3. **Independencia de verificación** (V-7 / RNC-006): revisor externo o acuerdo ANAC.
4. **Análisis de seguridad avanzado**: PSSA/SSA y safety case (S-2, S-3); cerrar STCA-1 vía requisito SRS.
5. **Higiene de configuración**: purgar binarios del histórico git (C-3) y ejecutar/registrar auditorías SQA por baseline (Q-1..Q-3).

## 9. Registro de cambios

| Ver | Fecha | Cambio |
|-----|-------|--------|
| 0.1 | 2026-06-28 | Creación inicial (previo a planes/FHA/SRS). |
| 0.2 | 2026-07-05 | Actualización al estado real: cierre de P-2/3/4, D-1/5, V-3/4/5/6, C-1/4, S-1; reclasificación de SQA y prioridades. Cobertura de proceso ~30 % → ~62 %. |
