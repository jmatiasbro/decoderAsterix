# SAS — Software Accomplishment Summary

**Sistema:** Decodificador ASTERIX (EUROCONTROL) + Display PPI ATC.
**Norma:** RTCA DO-278A / EUROCAE ED-109A. **SWAL de referencia:** 2 (núcleo).
**Versión:** 0.1 (BORRADOR). **Fecha:** 2026-07-09. **Estado:** PROPUESTO — no aprobado por ANAC.

> El SAS es el documento de **cierre** (corresponde a SOI-4). Esta versión es un **borrador vivo**:
> resume lo alcanzado hasta la fecha y deja explícito lo que resta (mayoritariamente validación externa
> con ANAC/EANA). No constituye una declaración de conformidad aprobada.

---

## 1. Identificación del software

| Campo | Valor |
|-------|-------|
| Producto | Decodificador ASTERIX + Display PPI en tiempo real (PyQt6) |
| Entry point canónico | `main.py` → `player/main_window.py` |
| Categorías ASTERIX | CAT 001/002/010/020/021/034/048/062 |
| Redes de seguridad | STCA, APW, MSAW (SWAL 2/3) |
| Repositorio / SCM | Git (`decoderAsterix`), baselines etiquetados; ver [SCMP](10_SCMP.md) |
| Runtime de referencia | Python 3.12 + `requirements.lock`; CI reproducible en Linux |

## 2. Resumen del software

Sistema de tierra CNS/ATM que decodifica ASTERIX, proyecta a WGS-84 y presenta tracks sobre cartografía,
con redes de seguridad (STCA/APW/MSAW), fusión multi-radar y vista EUROCONTROL ODS. Arquitectura de capas
con **núcleo agnóstico a Qt** ([SDD §2](15_SDD.md)); ciclo de vida de tracks **determinista por ToD**
(`time.time()` vedado en el motor de ciclo de vida). Roles operativos controlador/técnico.

## 3. Resumen de conformidad (objetivos DO-278A)

Estado por proceso — detalle en [gap analysis](03_gap_analysis_DO-278A.md):

| Proceso | Estado |
|---------|--------|
| Planificación (PSAC/SDP/SVP/SCMP/SQAP) | ✅ Borradores coherentes; PSAC sin acuerdo ANAC (A-1) |
| Desarrollo (HLR/LLR/arquitectura/código/trazabilidad) | ✅ SRS + SDD (todo HLR con LLR); estándares con linter en CI |
| Verificación | ⚠️ Pruebas + cobertura de decisiones 88.5 % OK; independencia pendiente (RNC-006) |
| Gestión de configuración (SCM) | ✅ Baselines, lockfile, `.gitignore`, histórico purgado (RNC-010) |
| Aseguramiento de calidad (SQA) | ✅ Auditorías de proceso/producto/transición registradas ([doc 17](17_registros_auditoria_SQA.md)) |
| Análisis de seguridad | ⚠️ FHA + PSSA/SSA + safety case; validación EANA/ANAC pendiente (S-2/S-3) |
| Enlace con la autoridad | ⚠️ SOI-1 no coordinado; SAS (este doc) en borrador |

## 4. Configuración del baseline

- Baselines etiquetados; tras la purga del histórico (RNC-010, 2026-07-09) los hashes se reescribieron —
  tabla de equivalencia viejo→nuevo en [SCMP §5.4](10_SCMP.md).
- **Acción pendiente:** etiquetar un baseline nuevo (`v0.x`) sobre `main` tras el merge del trabajo actual.
- Dependencias fijadas (`requirements.lock`); COTS/SOUP: extensión C `asterix_decoder-0.7.4` (análisis de
  impacto pendiente de formalizar).

## 5. Resultados de verificación

- Suite estructurada en `tests/` por subsistema; ejecución en CI (`.github/workflows/tests.yml`) en cada push.
- **Cobertura de decisiones (branch) 88.5 %** sobre módulos SWAL 2 (gate ≥ 80 %).
- Trazabilidad HLR↔test sin huecos ([SRS §17](07_SRS.md), [matriz](04_matriz_trazabilidad.md)).
- Bancos núcleo: STCA (motor + escenarios end-to-end, incl. parrots por identidad y tráfico lento),
  decodificadores CAT, matching A–E, fusión, geo, MSAW/APW, integración PCAP, auditoría safety,
  vector velocidad y RBL.
- Regresión visual del render y watchdog de la cadena de safety verificados.

## 6. Registro de problemas abiertos (Problem Reports / RNC)

| RNC | Clase | Estado |
|-----|-------|--------|
| RNC-001..005, 007..011 | B/C | **CERRADAS** (ver [SQAP §5.3](11_SQAP.md)) |
| RNC-010 (purga del histórico) | C | **CERRADA** (2026-07-09) |
| **RNC-006 (independencia de verificación)** | B | **Abierta** — externa (acuerdo ANAC / revisor independiente) |

**Hallazgos de seguridad:** STCA-1/2/3/4, TRK-1, ROB-1 — todos cerrados ([safety case §5](16_PSSA_SSA.md)).

## 7. Software life cycle & desviaciones

- Ciclo de vida y entorno según [SDP](08_SDP.md); estándares de código/diseño/requisitos aplicados con
  linter automatizado (cierra P-5/D-4).
- Desviación declarada: **equipo unipersonal** → las revisiones/auditorías son de autoevaluación
  (independencia formal = RNC-006).

## 8. Declaración de conformidad (borrador)

El software cumple **sustancialmente** los objetivos de proceso y producto de DO-278A/ED-109A a nivel
técnico interno para SWAL 2, con evidencia versionada y trazable. **No** se declara conformidad aprobada:
restan acciones **externas** — independencia de verificación (RNC-006), validación de los supuestos de
seguridad H-AS-1..6 con EANA (SSA-A5) y la coordinación/aprobación con ANAC (SOI-1..4). Este SAS se
completará y firmará en SOI-4.

## 9. Registro de cambios

| Ver | Fecha | Cambio |
|-----|-------|--------|
| 0.1 | 2026-07-09 | Emisión inicial (borrador): resumen de conformidad, verificación, PR/RNC y declaración preliminar. Cierra el ítem A-2 como borrador (formalmente SOI-4). |
