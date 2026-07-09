# Registros de Auditoría SQA

**Sistema:** Decodificador ASTERIX + Display PPI ATC.
**Norma:** EUROCAE ED-109A / RTCA DO-278A — aseguramiento de la calidad (Q-1/Q-2/Q-3).
**Versión:** 0.2. **Fecha:** 2026-07-09. **Estado:** PROPUESTO.

> Registra la **ejecución** de las auditorías definidas en el [SQAP §3](11_SQAP.md) sobre el baseline
> vigente, cerrando la brecha de *ejecución sin registro* de los objetivos **Q-1** (auditorías de
> proceso), **Q-2** (conformidad de producto) y **Q-3** (transición del ciclo de vida) del
> [gap analysis](03_gap_analysis_DO-278A.md). Cada auditoría lista criterio, hallazgos (conforme / no
> conforme) y evidencia. Los hallazgos que impliquen incumplimiento se registran como RNC en el
> [SQAP §5.3](11_SQAP.md).

---

## 0. Baseline auditado

| Campo | Valor |
|-------|-------|
| Baseline de referencia | `v0.4.0` (última etiqueta anotada) + trabajo de certificación en `feature/monoradar-track-lifecycle` |
| Fecha de auditoría | 2026-07-05 |
| Auditor | SQA del proyecto (rol interno; independencia formal pendiente — RNC-006) |
| Método | Inspección de artefactos versionados, ejecución de CI/tests y cotejo contra los planes |

> **Limitación de independencia:** el equipo es unipersonal; estas auditorías son de **autoevaluación**.
> La independencia de SQA respecto del desarrollo queda como **RNC-006** (acuerdo con ANAC). Se registran
> igualmente para dejar traza objetiva del estado por baseline.

---

## 1. AUD-P-01 — Auditoría de proceso de desarrollo (Q-1)

**Criterio:** SDP §4 (proceso, estándares, ciclo por elemento). **Resultado: CONFORME con observaciones.**

| # | Comprobación | Estado | Evidencia |
|---|--------------|--------|-----------|
| P-01.1 | Existe estándar de codificación/diseño y se aplica a módulos SWAL 2 | ✅ | [doc 13](13_estandar_codificacion.md); linter `tools/lint_swal2.py` en CI |
| P-01.2 | Existe estándar de requisitos | ✅ | [doc 14](14_estandar_requisitos.md) |
| P-01.3 | HLR formalizados y trazados | ✅ | [SRS](07_SRS.md) (57 HLR) |
| P-01.4 | LLR y diseño formal (SDD) | ✅ | [SDD](15_SDD.md) — todo HLR con LLR |
| P-01.5 | Determinismo del núcleo (ToD, sin `time.time()`) verificado mecánicamente | ✅ | Linter EC-7; `test_lifecycle.py` |
| P-01.6 | Commits con Conventional Commits + scope | ✅ | Historial git |
| P-01.7 | Comentarios/UI en español (EC-1) | ⚠️ Obs. | Mayoritariamente conforme; algunos textos de log heredados en inglés |

**Hallazgos:** ninguno de clase A/B. Observación P-01.7 (menor, sin RNC): homogeneizar idioma de logs heredados.

---

## 2. AUD-V-01 — Auditoría de verificación (Q-1)

**Criterio:** SVP §4–6 (ejecución, trazabilidad, cobertura). **Resultado: CONFORME.**

| # | Comprobación | Estado | Evidencia |
|---|--------------|--------|-----------|
| V-01.1 | Suite ejecuta en CI en cada push | ✅ | `.github/workflows/tests.yml` |
| V-01.2 | Cobertura de decisiones ≥ 80 % en módulos SWAL 2 | ✅ | 88.5 % ([SVP §4.4](09_SVP.md)); gate `fail_under=80` |
| V-01.3 | Trazabilidad HLR↔test sin huecos | ✅ | [matriz](04_matriz_trazabilidad.md); [SRS §17](07_SRS.md) |
| V-01.4 | Requisitos de seguridad (SSR) verificados | ✅ | [PSSA/SSA §4](16_PSSA_SSA.md) — 11/11 SSR |
| V-01.5 | Linter del estándar automatizado | ✅ | Step «Linter del estándar SWAL 2» en CI; `test_lint_swal2.py` |
| V-01.6 | Hallazgos de verificación gestionados | ✅ | STCA-1 cerrado (HLR-STCA-06); ROB-1 mitigado |
| V-01.7 | Regresión visual pixel-level del render | ❌ Brecha | Pendiente (SSA-A2 / FHA-A5) — no bloqueante, mitigado por modelo/widget + detección humana |

**Hallazgos:** V-01.7 se mantiene como acción abierta (SSA-A2), ya trazada; no se abre RNC nueva (brecha conocida y documentada).

---

## 3. AUD-C-01 — Auditoría de gestión de configuración (Q-1)

**Criterio:** SCMP §5–7 (etiquetas, archivo de resultados, `.gitignore`). **Resultado: CONFORME.**

| # | Comprobación | Estado | Evidencia |
|---|--------------|--------|-----------|
| C-01.1 | Baselines etiquetados anotados | ✅ | `v0.1.0-soi1`…`v0.4.0` |
| C-01.2 | Lockfile de dependencias | ✅ | `requirements.lock` (RNC-001 cerrada) |
| C-01.3 | Checksums de binarios de datos | ✅ | `tests/data/checksums.txt` (RNC-005 cerrada) |
| C-01.4 | Resultados de verificación archivados | ✅ | `resultados_soi1.html`; artefactos de cobertura en CI |
| C-01.5 | `.gitignore` endurecido (excluye entorno/artefactos nuevos) | ✅ | `.gitignore` |
| C-01.6 | Histórico libre de binarios versionados (`.pcap`/`.duckdb`/`.venv`) | ✅ | **RNC-010 CERRADA** (2026-07-09): purga con `git filter-repo`, remoto 114 MB → 25 MB; verificado 0 blobs purgados alcanzables y árbol de la app completo ([doc 18](18_procedimiento_purga_RNC010.md)) |

**Hallazgos:** ninguno abierto. **RNC-010 cerrada** con la ejecución de la fase B (purga del histórico); respaldo espejo pre-purga conservado y tabla de equivalencia de hashes en [SCMP §5.4](10_SCMP.md).

---

## 4. AUD-G-01 — Auditoría de cierre de brecha (Q-1, pre-SOI)

**Criterio:** las brechas documentadas se están cerrando de forma trazable. **Resultado: CONFORME.**

| Objetivo | Estado al baseline | Δ desde v0.4.0 |
|----------|--------------------|----------------|
| Planificación | 90 % (P-5 cerrado) | ↑ |
| Desarrollo (D-2/D-3) | 92 % (todo HLR con LLR) | ↑ |
| Verificación | 70 % | = |
| SCM | 88 % (RNC-010 cerrada) | ↑ |
| SQA | ↑ con este documento | ↑ |
| Análisis de seguridad | 67 % (PSSA/SSA + safety case) | ↑↑ |

**Hallazgos:** progresión coherente; sin regresiones. La cobertura de proceso pasó de ~30 % (v0.1) a ~73 %.

---

## 5. AUD-PR-01 — Revisión de conformidad de producto (Q-2)

**Criterio:** SQAP §3.2 (product reviews). **Resultado: CONFORME.**

| # | Producto | Comprobación | Estado |
|---|----------|--------------|--------|
| PR.1 | Módulos SWAL 2 | Revisión de código por checklist CR-1..8 | ✅ [doc 12](12_registros_revision_codigo.md) (RR-01..05) |
| PR.2 | Requisitos (SRS/SDD) | Checklist de revisión de requisitos QR-1..8 | ⚠️ Definido ([doc 14 §8](14_estandar_requisitos.md)); ejecución formal por baseline pendiente de registro firmado |
| PR.3 | Análisis de seguridad | FHA→PSSA/SSA coherentes y trazados | ✅ [doc 16](16_PSSA_SSA.md) |

**Hallazgos:** PR.2 — falta el registro **firmado** de la revisión de requisitos (la revisión técnica está hecha; falta la formalidad de independencia, ligada a RNC-006).

---

## 6. AUD-T-01 — Aseguramiento de transición del ciclo de vida (Q-3)

**Criterio:** SQAP §4.1 (criterios de entrada a SOI-1). **Resultado: CRITERIOS SUSTANCIALMENTE SATISFECHOS.**

| Criterio de entrada a SOI-1 | Estado |
|-----------------------------|--------|
| Planes (PSAC/SDP/SVP/SCMP/SQAP) en borrador coherente | ✅ |
| FHA y clasificación SWAL | ✅ |
| SRS con HLR trazados | ✅ |
| Análisis de seguridad (PSSA/SSA + safety case) | ✅ (borrador, validación EANA/ANAC pendiente) |
| CI con cobertura y linter | ✅ |
| Baseline etiquetado + resultados archivados | ✅ |
| Independencia de verificación | ❌ RNC-006 (externo) |
| Validación de supuestos H-AS-1..6 con EANA | ❌ FHA-A1/A2 (externo) |

**Conclusión de transición:** el paquete cumple los criterios **técnicos** de entrada a SOI-1. Los dos
criterios abiertos (independencia y validación de supuestos) son **externos** (ANAC/EANA) y no
dependen de trabajo interno adicional.

---

## 7. Resumen de hallazgos y RNC

| Hallazgo | Auditoría | Clase | Estado |
|----------|-----------|-------|--------|
| RNC-010 — binarios en histórico git | AUD-C-01 | C | **CERRADA** (2026-07-09, purga fase B) |
| RNC-006 — independencia de verificación | AUD-T-01, AUD-PR-01 | B | Abierta (acuerdo ANAC) |
| Obs. P-01.7 — idioma de logs heredados | AUD-P-01 | Obs. | Sin RNC (menor) |
| Acción SSA-A2 — regresión visual | AUD-V-01 | — | Abierta (trazada) |

**Conclusión global:** sin no conformidades de clase A. Tras cerrar RNC-010, queda **una sola RNC abierta
(RNC-006, clase B, independencia de verificación)**, de resolución externa (acuerdo ANAC) y fuera de la
ruta crítica de una barrera de seguridad. El baseline es apto para presentación SOI-1.

---

## 8. Registro de cambios

| Ver | Fecha | Cambio |
|-----|-------|--------|
| 0.1 | 2026-07-05 | Emisión inicial: ejecución y registro de las auditorías AUD-P/V/C/G/PR/T-01 sobre el baseline v0.4.0+; cierra la ejecución de Q-1/Q-2/Q-3. Hallazgos RNC-010 y confirmación de RNC-006. |
| 0.2 | 2026-07-09 | **Cierre de RNC-010** en AUD-C-01 (C-01.6 ✅, purga del histórico ejecutada). Única RNC abierta: RNC-006. |
