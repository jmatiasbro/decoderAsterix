# Estándar de Requisitos — Software SWAL 2

**Sistema:** Decodificador ASTERIX + Display PPI ATC.
**Norma:** EUROCAE ED-109A / RTCA DO-278A — objetivo de estándares de requisitos (P-5).
**Versión:** 0.1. **Fecha:** 2026-07-05. **Estado:** PROPUESTO — no aprobado por ANAC.

> Formaliza las reglas de **redacción, estructura, atributos de calidad y trazabilidad** que deben
> cumplir los requisitos de software (HLR y LLR). Cierra el ítem pendiente de la brecha **P-5**
> «Estándares» del [gap analysis](03_gap_analysis_DO-278A.md) — complementa el
> [estándar de codificación y diseño (doc 13)](13_estandar_codificacion.md). El
> [SRS (doc 07)](07_SRS.md) es el producto que debe conformar a este estándar; el SDD (por elaborar)
> aloja los LLR bajo las mismas reglas.

---

## 1. Propósito y alcance

Este estándar aplica a **todo requisito de software** del sistema, en dos niveles:

- **HLR (Requisitos de Alto Nivel):** qué debe hacer el software, derivados de los requisitos
  operacionales (Doc 4444, specs ASTERIX), del [FHA (doc 06)](06_FHA.md) y de los REQ-\* preexistentes.
  Se documentan en el [SRS](07_SRS.md).
- **LLR (Requisitos de Bajo Nivel):** cómo lo hace a nivel de diseño detallado, derivados de los HLR y
  de la arquitectura. Se documentarán en el SDD.

Rigor reforzado **[SWAL2]** sobre los requisitos de las funciones de seguridad (decodificación que
afecta el dato presentado, proyección, ciclo de vida/matching, HMI de separación) y los **HLR-SSR**
derivados del FHA.

## 2. Fuentes y tipos de requisito

| Tipo | Origen | Prefijo | Documento |
|------|--------|---------|-----------|
| Operacional / funcional | Doc 4444, ODS, specs ASTERIX | `HLR-<subsistema>-nn` | [SRS](07_SRS.md) |
| Seguridad (SSR) | [FHA](06_FHA.md) — condiciones de falla | `HLR-SSR-nn` | [SRS §16](07_SRS.md) |
| Derivado informal (histórico) | Comportamiento fijado por tests | `REQ-<subsistema>-n` | [matriz](04_matriz_trazabilidad.md) |
| Bajo nivel (diseño) | HLR + arquitectura | `LLR-<módulo>-nn` | SDD (por elaborar) |

Todo **requisito derivado** (que no traza a una necesidad operacional externa sino que nace de una
decisión de diseño) **DEBE** marcarse como tal y ser visible para el análisis de seguridad (DO-278A
exige realimentar los derivados al proceso de seguridad).

## 3. Estructura de un requisito (ER)

| Id | Regla |
|----|-------|
| ER-1 | **Identificador único e inmutable:** `HLR-<subsistema>-nn` / `LLR-<módulo>-nn`. Un id no se reutiliza ni se renumera; si un requisito se retira, su id queda **obsoleto**, no reasignado. |
| ER-2 | **Enunciado único (atómico):** un requisito expresa **una** obligación verificable. Enunciados con «y»/«o» que encubran dos obligaciones se dividen. |
| ER-3 | **Nivel de aseguramiento explícito:** cada requisito lleva su `SWAL` (según [doc 02](02_clasificacion_SWAL.md)). |
| ER-4 | **Trazabilidad hacia arriba:** referencia a su origen — `[SSR-nn]` del FHA, `[REQ-*]` histórico, o la fuente operacional (DA-n del SRS §1). |
| ER-5 | **Trazabilidad hacia abajo:** referencia (en la matriz) al diseño/módulo que lo implementa y al **test o análisis** que lo verifica. |
| ER-6 **[SWAL2]** | **Rationale cuando no es obvio:** los umbrales y decisiones de seguridad llevan la razón/derivación (p. ej. de dónde sale el gate de 30 NM, el look-ahead de 120 s). |

## 4. Redacción (RR)

| Id | Regla |
|----|-------|
| RR-1 | **Verbos normativos (estilo RFC-2119, en español):** **DEBE**/**NO DEBE** = obligatorio (*shall*/*shall not*); **DEBERÍA** = recomendado, su omisión se justifica; **PUEDE** = opcional. Prohibido «se procura», «idealmente», «en lo posible» en enunciados normativos. |
| RR-2 | **Idioma español**, terminología del dominio consistente (track, plot, squawk, FL, ToD, gate). Un mismo concepto, un mismo término en todo el SRS. |
| RR-3 **[SWAL2]** | **Sin ambigüedad:** prohibidos «rápido», «apropiado», «suficiente», «etc.», «según corresponda» sin cuantificar. Todo umbral es un **valor con unidad** o un **parámetro nombrado** (p. ej. `stca_horizontal_nm`). |
| RR-4 | **Verificable/medible:** el enunciado debe permitir construir un test o análisis que lo confirme o refute (ver §6). Si no es verificable como está escrito, se reescribe. |
| RR-5 **[SWAL2]** | **HLR libre de implementación:** el HLR dice *qué*, no *cómo* (no nombra clases/funciones internas). El *cómo* pertenece al LLR/SDD. (Referencias a estructuras de datos concretas como clave de matching se admiten cuando son parte del contrato observable.) |
| RR-6 | **Condición + acción + criterio:** forma preferida «Cuando \<condición\>, el sistema DEBE \<acción\> \<criterio cuantificado\>». |
| RR-7 | **Requisitos negativos de seguridad explícitos:** las prohibiciones de seguridad (no fusionar aeronaves distintas, no omitir tracks, no presentar dato inválido) se enuncian como **NO DEBE** propio, no como nota. |

## 5. Atributos de calidad del conjunto (CJ)

| Id | Regla |
|----|-------|
| CJ-1 | **Consistencia:** ningún par de requisitos se contradice (umbrales, prioridades). Los conflictos se resuelven documentando la precedencia. |
| CJ-2 | **Completitud vertical:** toda condición de falla del FHA con SSR tiene al menos un HLR que la satisface (ver mapa SSR→HLR del [SRS §16](07_SRS.md)). |
| CJ-3 | **Completitud descendente:** todo HLR de función implementada tiene LLR o justificación de por qué el HLR es directamente verificable sin descomponer. |
| CJ-4 | **Sin huérfanos:** todo HLR traza hacia arriba (origen) y hacia abajo (implementación + verificación); las excepciones se registran como brecha en el propio SRS (§18). |
| CJ-5 | **Factibilidad:** cada requisito es realizable con la arquitectura y el runtime declarados (Python 3.12/PyQt6, sin red en funciones de seguridad). |

## 6. Verificabilidad (VF)

| Id | Regla |
|----|-------|
| VF-1 | Cada requisito declara (en la matriz) su **método de verificación**: *test*, *análisis*, *inspección/revisión* o *demostración*. |
| VF-2 **[SWAL2]** | Los requisitos SWAL 2 se verifican por **test automatizado** salvo justificación; el test corre en CI y es reproducible por ToD (sin `time.time()`). |
| VF-3 | Un requisito de **prestaciones** (HLR-PERF) declara la condición de medición (carga, plataforma) y tolera el ajuste documentado por entorno de CI (ver [SVP §5.4](09_SVP.md)). |
| VF-4 | Un requisito **NO DEBE** (prohibición) se verifica con un caso negativo que confirme la ausencia del comportamiento (p. ej. dos Mode S distintos → nunca mismo track). |

## 7. Reglas específicas de LLR (LR)

| Id | Regla |
|----|-------|
| LR-1 | Cada LLR traza a **exactamente uno o más HLR**; un LLR sin HLR padre es un **requisito derivado** y se marca y realimenta a seguridad (§2). |
| LR-2 **[SWAL2]** | Los LLR de los módulos SWAL 2 respetan el [estándar de diseño (doc 13 §4)](13_estandar_codificacion.md): agnósticos a Qt, deterministas por ToD, fusión conservadora. |
| LR-3 | Un LLR describe interfaz, precondiciones, poscondiciones e invariantes de un componente de diseño; los umbrales de seguridad se expresan como **constantes/parámetros nombrados** (coherente con EC-11). |

## 8. Verificación de este estándar (revisión de requisitos)

La conformidad de los requisitos con este estándar se comprueba en la **revisión de requisitos**
(objetivo V-1), con el siguiente checklist. Se registra por baseline junto a los [registros de
revisión (doc 12)](12_registros_revision_codigo.md).

| Ck | Comprobación | Regla |
|----|--------------|-------|
| QR-1 | Id único, inmutable y con SWAL asignado | ER-1, ER-3 |
| QR-2 | Enunciado atómico y con verbo normativo | ER-2, RR-1 |
| QR-3 | Sin términos ambiguos; umbrales cuantificados o parametrizados | RR-3 |
| QR-4 | Verificable; método de verificación declarado | RR-4, VF-1 |
| QR-5 | Traza hacia arriba (origen/SSR) y hacia abajo (impl + test) | ER-4, ER-5, CJ-4 |
| QR-6 | Consistente con el resto (sin contradicción de umbrales) | CJ-1 |
| QR-7 | HLR libre de detalle de implementación | RR-5 |
| QR-8 | Cobertura SSR del FHA completa (sin condición de falla sin HLR) | CJ-2 |

## 9. Prohibiciones (resumen duro)

1. Enunciado normativo con término ambiguo o umbral sin cuantificar **[SWAL2]** (RR-3).
2. Requisito no verificable / sin método de verificación (RR-4, VF-1).
3. Reutilizar o renumerar un id de requisito (ER-1).
4. HLR de seguridad sin trazabilidad hacia arriba **y** hacia abajo (CJ-4).
5. Requisito derivado no marcado ni realimentado a seguridad (§2, LR-1).

## 10. Registro de desviaciones

| Id | Regla | Requisito | Justificación | Estado |
|----|-------|-----------|---------------|--------|
| — | — | — | — | — |

## 11. Registro de cambios

| Ver | Fecha | Cambio |
|-----|-------|--------|
| 0.1 | 2026-07-05 | Emisión inicial: reglas ER/RR/CJ/VF/LR, checklist de revisión QR-1..8 y prohibiciones. Cierra el ítem pendiente de P-5. |
