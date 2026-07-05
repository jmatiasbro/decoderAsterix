# SQAP — Software Quality Assurance Plan

**Sistema:** Decodificador ASTERIX + Display PPI ATC.
**Norma:** EUROCAE ED-109A / RTCA DO-278A — Sección 8 (Aseguramiento de la Calidad del Software).
**Versión:** 0.2 (borrador). **Fecha:** 2026-07-05. **Estado:** PROPUESTO — no aprobado por ANAC.

---

## 1. Propósito y alcance

Este plan define cómo el proceso de Aseguramiento de la Calidad del Software (SQA) verifica que
los procesos de desarrollo, verificación y gestión de configuración se están ejecutando según los
planes aprobados ([SDP](08_SDP.md), [SVP](09_SVP.md), [SCMP](10_SCMP.md)).

SQA es independiente del desarrollo: su función es auditar el proceso, no producir el software.
En un equipo unipersonal como el actual, esta independencia es limitada y se declara
explícitamente como brecha (ver §8).

---

## 2. Organización y responsabilidades

### 2.1 Roles DO-278A

| Rol | Descripción | Estado actual |
|---|---|---|
| Desarrollador | Implementa el software según el SDP | Matias (único desarrollador) |
| Verificador | Ejecuta y documenta la verificación según el SVP | Matias (mismo — brecha de independencia) |
| Responsable SQA | Audita procesos; reporta no conformidades | Matias (mismo — brecha declarada) |
| Enlace con autoridad | Coordina SOI-1..4 con ANAC | Matias |

> **Declaración de independencia:** El equipo es unipersonal. La independencia requerida por
> DO-278A para SWAL 2 no puede satisfacerse internamente en este estado. Las opciones son:
> (a) incorporar un revisor externo para módulos SWAL 2, (b) acordar con ANAC un medio
> alternativo de satisfacción, o (c) justificar que la naturaleza del sistema permite reducir
> la independencia requerida. Esta decisión se documenta en el PSAC y se negocia en SOI-1.

### 2.2 Autoridad SQA

El responsable SQA tiene autoridad para:
- Detener un merge a `main` si el proceso no se ha seguido.
- Emitir un Registro de No Conformidad (RNC).
- Elevar una no conformidad al enlace con la autoridad si no se resuelve en el plazo acordado.

---

## 3. Actividades SQA

### 3.1 Auditorías de proceso

Se realizan auditorías planificadas para verificar que los procesos se ejecutan según los planes.

| Auditoría | Frecuencia | Alcance |
|---|---|---|
| Auditoría de desarrollo | Por baseline | Verifica SDP §4 (proceso, estándares, ciclo por elemento) |
| Auditoría de verificación | Por baseline | Verifica SVP §4–6 (ejecución, trazabilidad, cobertura) |
| Auditoría SCM | Por baseline | Verifica SCMP §5–7 (etiquetas, archivo de resultados, .gitignore) |
| Auditoría de cierre de brecha | Pre-SOI | Verifica que las brechas documentadas se están cerrando |

### 3.2 Revisiones de producto (Product Reviews)

DO-278A distingue revisión de proceso (SQA) de revisión de producto (verificación). La SQA
confirma que las revisiones de producto se realizaron; no las sustituye.

| Revisión | Qué se audita |
|---|---|
| Revisión de SRS | SRS completa, consistente; cada HLR tiene fuente (FHA o análisis operacional) |
| Revisión de código (módulos SWAL 2) | Checklist SVP §7.1 completado; registrado antes del merge |
| Revisión de resultados de test | Resultados archivados, trazados a HLR, firmados por el verificador |

### 3.3 Registro de Conformidad por Objetivo (OCC — Objective Compliance Checklist)

Para cada objetivo DO-278A aplicable al SWAL del módulo, la SQA mantiene una fila en el
[Gap Analysis](03_gap_analysis_DO-278A.md) con estado CUMPLIDO / PARCIAL / AUSENTE y la
referencia al artefacto de evidencia.

---

## 4. Criterios de transición entre fases

### 4.1 Criterios de entrada a SOI-1 (revisión con ANAC de los planes)

| Criterio | Estado |
|---|---|
| PSAC borrador entregado | ✅ |
| SDP, SVP, SCMP, SQAP borradores entregados | ✅ (este documento) |
| FHA borrador entregado | ✅ |
| SRS borrador entregado (≥ 50 HLR formalizados) | ✅ (56 HLR) |
| Gap analysis actualizado | ✅ |
| Suite de tests ≥ 400 tests pasando | ✅ (526) |
| Baseline SCM etiquetado | ✅ `v0.1.0-soi1`, `v0.2.0-perf`, `v0.3.0` |
| Resultados de tests archivados | ✅ `documentacion/certificacion/resultados_soi1.html` |

### 4.2 Criterios de entrada a SOI-2 (revisión de verificación)

| Criterio | Estado |
|---|---|
| SRS aprobada internamente | Parcial |
| 100 % de HLR con test asociado | ✅ HLR-HMI-01..06 y HLR-PERF-01..03 con test; HLR-PERF-04/05 verificados manualmente (SVP §5.4) |
| Cobertura de decisiones ≥ objetivo en módulos SWAL 2 | ✅ 88.5 % (branch) ≥ 80 %; medida y en CI |
| Registros de revisión de código para SWAL 2 | ❌ No existen |
| Resultados de verificación archivados en baseline | ✅ `resultados_soi1.html` (regenerar por baseline en CI) |
| No conformidades abiertas: ninguna Clase A | ✅ Ninguna Clase A abierta; seguimiento en §5.3 |

---

## 5. Gestión de no conformidades

### 5.1 Clasificación

| Clase | Descripción | Plazo de cierre |
|---|---|---|
| A — Crítica | Incumplimiento de un HLR de SWAL 2; defecto en safety net | Antes del siguiente baseline |
| B — Mayor | Incumplimiento de un objetivo DO-278A; test sin traza a HLR | Antes de SOI siguiente |
| C — Menor | Desviación de estándar de codificación; documento desactualizado | Próximo sprint |

### 5.2 Proceso de no conformidad

1. **Detección**: por auditoría SQA, revisión de código, o análisis de resultados de test.
2. **Registro**: RNC con identificador, clase, descripción, HLR afectado, fecha de apertura.
3. **Análisis de causa raíz**: ¿defecto en código, en requisito, en test, en proceso?
4. **Acción correctiva**: implementación de la corrección.
5. **Verificación de cierre**: nueva ejecución del test o nueva auditoría.
6. **Cierre**: RNC marcada como CERRADA con referencia al commit de corrección.

> **Brecha:** No existe sistema de seguimiento de RNCs. Se propone usar issues del repositorio Git
> con etiquetas `RNC-A`, `RNC-B`, `RNC-C` como mecanismo mínimo hasta disponer de herramienta formal.

### 5.3 No conformidades conocidas al momento de este documento

| RNC | Clase | Descripción | Estado |
|---|---|---|---|
| RNC-001 | B | Sin lockfile de dependencias (riesgo de reproducibilidad) | **CERRADA** — `requirements.lock` (commit `d74eb85`) |
| RNC-002 | B | Sin resultados de tests archivados vinculados a baseline | **CERRADA** — `resultados_soi1.html` (commit `e717855`); pendiente automatizar en CI |
| RNC-003 | B | Tests HLR-HMI-04 y HLR-PERF-01..05 ausentes | **CERRADA** — `test_track_state`, `test_safety_watchdog`, `test_perf` (commit `d74eb85`); HLR-PERF-04/05 verificados manualmente (SVP §5.4) |
| RNC-004 | C | `requirements.txt` incompleto (no refleja paquetes realmente usados) | **CERRADA** — depurado contra los imports reales del app canónico; añadidos `qtawesome`/`pyqtgraph`/`simplekml`, `flask` marcado opcional, dependencias comentadas por origen |
| RNC-005 | C | Artefacto binario `baires.pcap` en el árbol sin hash verificable | **CERRADA** — `tests/data/checksums.txt` (commit `d74eb85`) |
| RNC-006 | B | Sin independencia de verificación para módulos SWAL 2 | Abierta (acuerdo con ANAC) |
| RNC-007 | C | Cobertura de decisiones no medida en módulos SWAL 2 | **CERRADA** — medida con `pytest-cov` (branch), línea base **88.5 %** ≥ objetivo 80 %; automatizada en CI (`.github/workflows/ci.yml`). Ver SVP §4.4 |
| RNC-008 | B | Sin registros de revisión de código para módulos SWAL 2 | Abierta |

> **Nota de estado (2026-07-05):** de las seis RNC iniciales, cuatro (001/002/003/005) quedaron cerradas
> con evidencia versionada. Se incorporan RNC-007 y RNC-008 para trazar las dos brechas de proceso aún
> abiertas (cobertura estructural y revisiones de código), antes implícitas en los criterios de SOI-2.

---

## 6. Métricas de calidad

El SQA monitorea las siguientes métricas como indicadores del estado del proceso:

| Métrica | Valor actual | Objetivo SOI-2 |
|---|---|---|
| Tests pasando / total | 526/526 (100 %) | 100 % |
| HLR con test asociado | ~56/56 (100 %) — HLR-PERF-04/05 por verificación manual | 100 % |
| RNCs Clase A abiertas | 0 | 0 |
| RNCs Clase B abiertas | 2 (RNC-006, RNC-008) | 0 |
| Cobertura de decisiones (SWAL 2) | 88.5 % (medida) | ≥ 80 % (objetivo propuesto) |
| Commits con referencia a HLR (mensajes) | ~65 % | ≥ 90 % |

---

## 7. Coordinación con la autoridad (ANAC)

### 7.1 Puntos de enlace (SOI)

| SOI | Contenido | Estado |
|---|---|---|
| SOI-1 | Revisión de planes y FHA/SRS borradores | Pendiente (target: post este documento) |
| SOI-2 | Revisión de verificación: cobertura, trazabilidad, resultados | Pendiente |
| SOI-3 | Revisión de integración: pruebas de sistema con tráfico real | Pendiente |
| SOI-4 | Revisión final: cierre de no conformidades, aprobación | Pendiente |

### 7.2 Documentos a presentar en SOI-1

- Este SQAP, más PSAC, SDP, SVP, SCMP (todos como borradores v0.1).
- FHA y SRS.
- Gap analysis DO-278A.
- Suite de tests ejecutada y resultado archivado.
- Lista de brechas declaradas (§8) con plan de cierre y fechas.

---

## 8. Brechas declaradas de independencia y proceso

Esta sección es la declaración honesta requerida por DO-278A §8.3 cuando no se alcanzan los
objetivos de independencia:

| Brecha | Descripción | Mitigación propuesta |
|---|---|---|
| Independencia de verificación | Verificador = Desarrollador para módulos SWAL 2 | Revisor externo para módulos tracking/APW/MSAW; o acuerdo con ANAC |
| Independencia SQA | Auditor SQA = Desarrollador | Ídem o auditoría por pares con tercero |
| ~~Sin CI/CD~~ | **Mitigada** — GitHub Actions (`.github/workflows/ci.yml`) ejecuta la suite y mide cobertura de decisiones en cada *push*/PR, publicando reportes como artefactos | — |
| Sin herramienta de seguimiento de defectos | Git issues como sustituto mínimo | Suficiente para estado actual; migrar a Jira/linear si escala |

---

## 9. Registro de cambios

| Ver | Fecha | Cambio |
|-----|-------|--------|
| 0.1 | 2026-07-03 | Creación del borrador inicial. |
| 0.2 | 2026-07-05 | Cierre de RNC-001/002/003/005 con evidencia versionada; alta de RNC-007/008 (cobertura y revisiones de código); actualización de criterios SOI-1/2, métricas (526 tests, 100 % HLR con test) y baselines etiquetados. |
