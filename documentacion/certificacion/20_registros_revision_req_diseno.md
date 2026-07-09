# Registros de Revisión de Requisitos y Diseño (V-1 / V-2)

**Sistema:** Decodificador ASTERIX + Display PPI ATC.
**Norma:** RTCA DO-278A / EUROCAE ED-109A — objetivos de verificación **V-1** (revisión de requisitos) y
**V-2** (revisión de diseño). **Versión:** 0.1. **Fecha:** 2026-07-09. **Estado:** PROPUESTO.

> Registra la **ejecución** de las revisiones de requisitos (SRS) y de diseño (SDD) contra los checklists
> definidos: **QR-1..8** ([estándar de requisitos §8](14_estandar_requisitos.md)) y las reglas de diseño
> **ED** ([estándar de codificación/diseño](13_estandar_codificacion.md)). Cierra la brecha de *ejecución
> sin registro* de V-1/V-2 ([gap analysis §3](03_gap_analysis_DO-278A.md)).
>
> **Limitación de independencia:** equipo unipersonal → revisión por **autoevaluación**. La independencia
> formal (revisor distinto del autor) queda como **RNC-006** (acuerdo ANAC). Se registra igualmente para
> dejar traza objetiva.

---

## 1. RR-REQ-01 — Revisión del SRS (V-1)

**Artefacto:** [07_SRS.md](07_SRS.md) (HLR + HLR-SSR). **Criterio:** checklist QR-1..8. **Resultado: CONFORME con observaciones.**

| # (QR) | Comprobación | Estado | Evidencia / Observación |
|--------|--------------|--------|-------------------------|
| QR-1 | Cada HLR es **verificable** (test o análisis asociado) | ✅ | Matriz §17 SRS: todo HLR con test; sin huecos |
| QR-2 | Cada HLR es **atómico** y sin ambigüedad ("DEBE"/"NO DEBE") | ✅ | Redacción normativa uniforme |
| QR-3 | Trazabilidad a origen (SSR/FC/REQ) | ✅ | Columnas SSR/FC en §17; FHA→SSR |
| QR-4 | Sin requisitos en conflicto | ✅ | STCA vertical: normativo 800 ft coherente con fallback 1000 ft (degradado) documentado |
| QR-5 | Cobertura de las condiciones de falla del FHA | ✅ | 11 HLR-SSR; FC-STCA/MSAW/HMI/TRK cubiertas |
| QR-6 | Requisitos de seguridad marcados con SWAL | ✅ | Cada HLR etiquetado (SWAL 2/3/4) |
| QR-7 | Consistencia con el diseño (SDD) | ✅ | Umbrales STCA, exclusiones y HMI reflejados en LLR |
| QR-8 | Requisitos derivados realimentados a seguridad | ✅ | HLR-STCA-06/09 y config operativa trazados al safety case |

**Hallazgos:** ninguno de clase A/B. Observación: los HLR-HMI-09/10 (vector velocidad, RBL) son ayudas de
presentación SWAL 4 — verificación funcional suficiente, sin impacto en redes de seguridad.

---

## 2. RR-DIS-01 — Revisión del SDD (V-2)

**Artefacto:** [15_SDD.md](15_SDD.md) (arquitectura + LLR). **Criterio:** reglas ED + trazabilidad LLR↔HLR↔test. **Resultado: CONFORME.**

| # | Comprobación | Estado | Evidencia |
|---|--------------|--------|-----------|
| D.1 | Todo HLR tiene ≥1 LLR | ✅ | SDD §3–10; SRS §17 |
| D.2 | Todo LLR traza a HLR y a test | ✅ | Tablas por subsistema + §11 |
| D.3 | Arquitectura de capas (núcleo agnóstico a Qt) coherente | ✅ | SDD §2.1–2.5 (flujo, secuencia, estados, despliegue) |
| D.4 | Decisiones de diseño con rationale | ✅ | DD-1..5 (§2.6) |
| D.5 | Barreras de seguridad diseñadas explícitamente | ✅ | Exclusiones STCA (LLR-STC-10), marco único (STC-05), veto de identidad (COR-08) |
| D.6 | Determinismo del núcleo (ToD, sin `time.time()`) | ✅ | Linter EC-7; `test_lifecycle.py` |
| D.7 | Notas de diseño actualizadas al código vigente | ✅ | Nota obsoleta de §5 (valores hardcodeados) corregida (SDD v0.6) |

**Hallazgos:** ninguno. Refinamientos pendientes no bloqueantes: LLR por categoría de decodificación y
contratos por función ([SDD §13](15_SDD.md)).

---

## 3. Conclusión

Las revisiones **técnicas** de requisitos (V-1) y diseño (V-2) están ejecutadas y registradas, sin
hallazgos de clase A/B. El único pendiente es la **firma con independencia** (revisor ≠ autor), ligado a
**RNC-006** (externo). Con ello, V-1/V-2 pasan de *ejecutadas sin registro* a **registradas** (la
independencia formal se resolverá con ANAC).

## 4. Registro de cambios

| Ver | Fecha | Cambio |
|-----|-------|--------|
| 0.1 | 2026-07-09 | Emisión inicial: RR-REQ-01 (SRS/QR-1..8) y RR-DIS-01 (SDD/ED). Cierra la ejecución de V-1/V-2; independencia pendiente (RNC-006). |
