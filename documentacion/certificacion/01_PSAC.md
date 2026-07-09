# PSAC — Plan for Software Aspects of Certification/Approval

**Sistema:** Decodificador ASTERIX + Display PPI ATC.
**Norma de aseguramiento:** EUROCAE ED-109A / RTCA DO-278A.
**Versión:** 1.0 (para SOI-1). **Fecha:** 2026-07-09. **Estado:** PROPUESTO — no aprobado por ANAC.

> El PSAC es el documento de entrada que se presenta a la autoridad. Declara *qué* se va a certificar,
> *con qué rigor* y *mediante qué planes y evidencia*. La v1.0 refleja el paquete **ya construido**:
> planes, FHA, SRS, SDD, PSSA/SSA, estándares con linter en CI, matriz de trazabilidad, registros de
> auditoría/revisión y cobertura de decisiones medida. La cobertura de proceso interna es **~88 %**
> ([gap analysis](03_gap_analysis_DO-278A.md)); las brechas restantes son **externas** (independencia de
> verificación, validación de supuestos de seguridad con EANA, y las revisiones SOI con ANAC).

---

## 1. Introducción

### 1.1 Propósito
Establecer el acuerdo con la ANAC sobre los medios para demostrar que el software del sistema cumple
los objetivos de aseguramiento de DO-278A correspondientes a su nivel SWAL asignado.

### 1.2 Alcance del software
El sistema comprende:
- **Núcleo de decodificación** (`decoder/`): parsing ASTERIX CAT 001/002/010/020/021/034/048/062,
  proyección polar→WGS-84, registro de sensores.
- **Display PPI** (`player/`, `radar_widget.py`): render de tracks, matching/reconciliación,
  presentación EUROCONTROL ODS.
- **Redes de seguridad** (`player/areas`, `player/msaw`, cadena STCA/APW/MSAW): funciones con
  potencial impacto en la seguridad operacional.
- **Ciclo de vida de tracks** (`player/tracking/lifecycle.py`): determinista, gobernado por ToD.
- **Fusión multi-radar y calibración** (`fusion/`): correlación y registración.
- **Persistencia y auditoría** (`storage/`, `safety_audit_dialog`): registro de eventos safety.

### 1.3 Exclusiones
Quedan fuera del alcance de software de este PSAC: cartografía base de terceros, la extensión C
`asterix_decoder-0.7.4` (a tratar como **COTS/SOUP** — ver §7), y el sistema operativo y runtime Python.

## 2. Vista general del sistema

### 2.1 Descripción funcional
Ver [../../CLAUDE.md](../../CLAUDE.md) y [../../TECHNICAL.md](../../TECHNICAL.md).
Flujo: PCAP/UDP → `DataEngine` decodifica y proyecta → batches de plots → `radar_widget` matchea/
reconcilia → cadena STCA→APW→MSAW (~1 Hz) → repintado del PPI.

### 2.2 Arquitectura de aseguramiento
Separación estricta **núcleo agnóstico a Qt** ↔ **UI PyQt6**. Esta separación es un *argumento de
diseño* favorable a la verificación: el núcleo es testeable sin GUI y de forma reproducible.

### 2.3 Determinismo
El ciclo de vida se gobierna exclusivamente por el ToD de ASTERIX (`time.time()` vedado en el motor),
habilitando verificación reproducible en playback. Es un punto fuerte a capitalizar en la estrategia
de verificación.

## 3. Nivel de aseguramiento de software (SWAL)

El nivel SWAL **se determina en** [02_clasificacion_SWAL.md](02_clasificacion_SWAL.md). Resumen propuesto:

- Funciones de **redes de seguridad (STCA/APW/MSAW)**, **matching/reconciliación** y **presentación HMI
  usada para separación**: **SWAL 2** (confirmado por FHA/PSSA — 37 FC, 11 SSR).
- Funciones de **análisis/exportación post-operación** y ayudas de presentación: **SWAL 4**.

> La asignación **ya está respaldada** por la [FHA](06_FHA.md) y la [clasificación SWAL](02_clasificacion_SWAL.md);
> el matching se escaló a SWAL 2 por FC-TRK-01. La confirmación definitiva es objeto de la validación con
> la autoridad (SOI-1/2).

## 4. Consideraciones del ciclo de vida del software

### 4.1 Procesos
Se adoptarán los procesos DO-278A: planificación, desarrollo, verificación, gestión de configuración (SCM),
aseguramiento de la calidad (SQA) y enlace con la autoridad.

### 4.2 Planes asociados (estado)
| Plan | Documento | Estado |
|------|-----------|--------|
| SDP — Plan de Desarrollo de Software | [08_SDP.md](08_SDP.md) | ✅ Emitido |
| SVP — Plan de Verificación de Software | [09_SVP.md](09_SVP.md) | ✅ Emitido |
| SCMP — Plan de Gestión de Configuración | [10_SCMP.md](10_SCMP.md) | ✅ Emitido (v0.2) |
| SQAP — Plan de Aseguramiento de Calidad | [11_SQAP.md](11_SQAP.md) | ✅ Emitido (v0.4) |
| Estándares (diseño/código) | [13_estandar_codificacion.md](13_estandar_codificacion.md) | ✅ Emitido (linter EC en CI) |
| Estándares de requisitos | [14_estandar_requisitos.md](14_estandar_requisitos.md) | ✅ Emitido (checklist QR) |

> Todos los planes están **emitidos y coherentes**; su **aprobación formal** es el objeto de SOI-1.

### 4.3 Transición de datos del ciclo de vida
Los entregables del ciclo de vida **existen bajo control de configuración**: [SRS](07_SRS.md),
[SDD](15_SDD.md) (todo HLR con LLR), casos/resultados de prueba en `tests/` con CI, y registros de
revisión de [código (doc 12)](12_registros_revision_codigo.md) y de [requisitos/diseño (doc 20)](20_registros_revision_req_diseno.md).
Los criterios de transición entre fases (SOI) se detallan en [SQAP §4](11_SQAP.md).

## 5. Datos del ciclo de vida del software (entregables)

| Dato | Existe hoy | Brecha restante |
|------|-----------|-----------------|
| Plan de aseguramiento (este PSAC) | ✅ v1.0 | Aprobación ANAC (SOI-1) |
| SRS — Especificación de Requisitos | ✅ [07_SRS.md](07_SRS.md) (HLR + HLR-SSR, trazados) + LLR en SDD | Aprobación ANAC (SOI-2) |
| FHA / PSSA / SSA — Análisis de seguridad | ✅ [06](06_FHA.md) / [16](16_PSSA_SSA.md) (11/11 SSR verificados, safety case C0..C4) | **Validar supuestos H-AS-1..6 con EANA** ([doc 23](23_protocolo_validacion_eana.md)); aprobación ANAC |
| SDD — Descripción de Diseño | ✅ [15_SDD.md](15_SDD.md) (arquitectura + diagramas + LLR de todas las capas) | LLR por categoría de decodificación (menor) |
| Código fuente | ✅ Bajo SCM, baselines etiquetados | Etiquetar baseline tras el merge de la línea actual |
| Casos y procedimientos de verificación | ✅ Suite `tests/` por subsistema, trazabilidad HLR↔test | — |
| Resultados de verificación | ✅ CI (`.github/workflows/tests.yml`) + cobertura de decisiones 88.5 % | — |
| Matriz de trazabilidad | ✅ [04](04_matriz_trazabilidad.md) + [SRS §17](07_SRS.md) | — |
| Registros SCM/SQA | ✅ Auditorías [doc 17](17_registros_auditoria_SQA.md); revisiones [doc 12](12_registros_revision_codigo.md)/[doc 20](20_registros_revision_req_diseno.md) | **Independencia** (RNC-006, externa) |

## 6. Cronograma y enlace con la autoridad
Secuencia de fases en la [hoja de ruta](05_hoja_de_ruta.md). Puntos de contacto **SOI 1–4** a coordinar
con ANAC; el paquete de entrada a **SOI-1** y su agenda están consolidados en el
[dossier de presentación (doc 21)](21_dossier_SOI1.md). El arreglo de **independencia de verificación**
(RNC-006) se propone en el [plan de independencia (doc 22)](22_plan_independencia_verificacion.md), y la
validación de los supuestos de seguridad con **EANA** en el [protocolo (doc 23)](23_protocolo_validacion_eana.md).

## 7. Componentes COTS / SOUP
La extensión `asterix_decoder-0.7.4` (binario C de terceros) se gestionará como software de origen no
controlado (SOUP): identificación de versión, análisis de impacto, y estrategia de verificación de su
salida (los parsers propios ya envuelven y validan resultados — ver `native_asterix.py`).

## 8. Gestión de configuración (resumen)
Git como SCM ([SCMP](10_SCMP.md)). ✅ Baselines etiquetados, control de cambios por PR, `.gitignore`
endurecido, lockfile de dependencias e **histórico purgado de binarios** (RNC-010, 2026-07-09). SCM al
**100 %** en el gap analysis.

## 9. Aseguramiento de calidad (resumen)
✅ Auditorías de proceso/producto/transición ejecutadas y registradas ([doc 17](17_registros_auditoria_SQA.md)),
proceso formal de problem reporting ([SQAP §5.2](11_SQAP.md)), criterios de aceptación por objetivo (OCC).
**Brecha externa:** independencia de las revisiones/auditorías (equipo unipersonal → RNC-006, acuerdo ANAC).

## 10. Verificación (estrategia — implementada)
- ✅ Revisión de requisitos y diseño registrada ([doc 20](20_registros_revision_req_diseno.md)).
- ✅ Pruebas basadas en requisitos sobre el núcleo (sin GUI, reproducibles por ToD); trazabilidad HLR↔test.
- ✅ Cobertura **estructural de decisiones (branch)** en módulos SWAL 2: **88.5 %** (gate ≥ 80 %).
- ✅ Análisis de la cadena de safety-nets con escenarios operacionales (STCA end-to-end, PCAP de referencia).
- ✅ **Integración Continua** que ejecuta `pytest tests/` y publica cobertura (`.github/workflows/tests.yml`).
- **Brecha externa:** independencia de la verificación (RNC-006).

## 11. Registro de cambios
| Ver | Fecha | Cambio |
|-----|-------|--------|
| 0.1 | 2026-06-28 | Creación del borrador inicial. |
| 1.0 | 2026-07-09 | Actualización a **estado real para SOI-1**: planes emitidos, SWAL 2 confirmado por FHA/PSSA, entregables del ciclo de vida bajo SCM, CI + cobertura 88.5 %, RNC-010 cerrada. Enlaza el dossier SOI-1 (doc 21), el plan de independencia (doc 22) y el protocolo de validación con EANA (doc 23). Brechas restantes: externas (RNC-006, S-2/S-3, aprobaciones SOI). |
