# Dossier de Presentación a la Autoridad — SOI-1

**Sistema:** Decodificador ASTERIX (EUROCONTROL) + Display PPI ATC.
**Autoridad:** ANAC — Dirección de Control de Sistemas de Navegación Aérea.
**Marco:** RTCA DO-278A / EUROCAE ED-109A; RAAC Parte 211; OACI Doc 4444.
**Versión:** 0.1. **Fecha:** 2026-07-09. **Estado:** PROPUESTO — paquete de entrada a SOI-1.

> **SOI-1 (Stage of Involvement 1)** es la *revisión de planificación*: la autoridad revisa los planes,
> la clasificación SWAL y la estrategia de aseguramiento **antes** del grueso del desarrollo/verificación.
> Este dossier consolida qué se presenta, el estado de conformidad y lo que se solicita acordar.

---

## 1. Identificación

| Campo | Valor |
|-------|-------|
| Producto | Decodificador ASTERIX + Display PPI en tiempo real (PyQt6) |
| Función | Vigilancia ATC: decodificación, proyección, presentación y redes de seguridad (STCA/APW/MSAW) |
| SWAL propuesto | **2** (núcleo de seguridad), **4** (análisis/exportación y ayudas de presentación) |
| Baseline | Git; etiqueta a fijar sobre `main` tras el merge de la línea vigente |
| Responsable del software | (a completar) |

## 2. Objeto de la revisión SOI-1

Obtener de ANAC:
1. **Acuerdo sobre el PSAC** ([doc 01](01_PSAC.md)) y los planes asociados (SDP/SVP/SCMP/SQAP + estándares).
2. **Confirmación de la clasificación SWAL** ([doc 02](02_clasificacion_SWAL.md)), respaldada por la FHA.
3. **Acuerdo sobre el arreglo de independencia de verificación** (RNC-006 — ver [doc 22](22_plan_independencia_verificacion.md)).
4. **Acuerdo de coordinación** de la validación de supuestos de seguridad con EANA ([doc 23](23_protocolo_validacion_eana.md)).
5. **Cronograma** de las revisiones SOI-2 (desarrollo/verificación), SOI-3 (verificación) y SOI-4 (cierre).

## 3. Índice del paquete presentado

| # | Documento | Rol | Estado |
|---|-----------|-----|--------|
| 01 | [PSAC](01_PSAC.md) | Plan de aspectos de certificación | v1.0 |
| 02 | [Clasificación SWAL](02_clasificacion_SWAL.md) | Nivel de aseguramiento | Borrador |
| 03 | [Gap Analysis DO-278A](03_gap_analysis_DO-278A.md) | Estado objetivo-por-objetivo (~88 %) | v1.3 |
| 04 | [Matriz de trazabilidad](04_matriz_trazabilidad.md) | Req↔diseño↔código↔test | v0.3 |
| 05 | [Hoja de ruta](05_hoja_de_ruta.md) | Planificación de fases | Borrador |
| 06 | [FHA](06_FHA.md) | 37 FC, 11 SSR, supuestos H-AS-1..6 | Borrador |
| 07 | [SRS](07_SRS.md) | HLR + HLR-SSR, trazados | Borrador |
| 08–11 | [SDP](08_SDP.md)/[SVP](09_SVP.md)/[SCMP](10_SCMP.md)/[SQAP](11_SQAP.md) | Planes de proceso | Emitidos |
| 12 | [Registros de revisión de código](12_registros_revision_codigo.md) | RR-01..05 (SWAL 2) | Emitido |
| 13–14 | [Estándares](13_estandar_codificacion.md) de código/diseño y [requisitos](14_estandar_requisitos.md) | Reglas + linter/checklist | Emitidos |
| 15 | [SDD](15_SDD.md) | Arquitectura + LLR de todas las capas | Borrador |
| 16 | [PSSA/SSA](16_PSSA_SSA.md) | 11/11 SSR verificados + safety case | Borrador |
| 17 | [Auditorías SQA](17_registros_auditoria_SQA.md) | Proceso/producto/transición | Emitido |
| 18 | [Purga RNC-010](18_procedimiento_purga_RNC010.md) | Higiene de configuración (ejecutada) | v0.2 |
| 19 | [SAS](19_SAS.md) | Accomplishment Summary (cierre, SOI-4) | Borrador |
| 20 | [Revisiones de requisitos/diseño](20_registros_revision_req_diseno.md) | V-1/V-2 | Emitido |
| 22 | [Plan de independencia de verificación](22_plan_independencia_verificacion.md) | Propuesta RNC-006 | Este paquete |
| 23 | [Protocolo de validación con EANA](23_protocolo_validacion_eana.md) | Supuestos H-AS-1..6 | Este paquete |

## 4. Resumen de conformidad (a SOI-1)

| Proceso DO-278A | Cobertura interna |
|-----------------|-------------------|
| Planificación | 90 % (planes emitidos; falta acuerdo ANAC = objeto de SOI-1) |
| Desarrollo | **100 %** |
| Verificación | 86 % (cobertura de decisiones 88.5 %; falta independencia = RNC-006) |
| Gestión de configuración | **100 %** |
| Aseguramiento de calidad | **100 %** |
| Análisis de seguridad | 75 % (11/11 SSR verificados; falta validación EANA de H-AS-1..6) |
| Enlace con la autoridad | 40 % (**objeto de este SOI-1**) |
| **Total** | **~88 %** |

## 5. Criterios de entrada a SOI-1 (cumplimiento)

De la auditoría de transición [AUD-T-01](17_registros_auditoria_SQA.md):

| Criterio | Estado |
|----------|--------|
| Planes (PSAC/SDP/SVP/SCMP/SQAP) en borrador coherente | ✅ |
| FHA y clasificación SWAL | ✅ |
| SRS con HLR trazados | ✅ |
| Análisis de seguridad (PSSA/SSA + safety case) | ✅ (validación EANA pendiente) |
| CI con cobertura y linter | ✅ |
| Baseline etiquetado + resultados archivados | ✅ |
| Independencia de verificación | ❌ RNC-006 (a acordar en este SOI-1) |
| Validación de supuestos H-AS-1..6 con EANA | ❌ (a coordinar — doc 23) |

**Conclusión:** los criterios **técnicos** de entrada a SOI-1 están satisfechos; los dos abiertos son
externos y constituyen precisamente la agenda de coordinación con la autoridad.

## 6. Puntos abiertos a resolver con la autoridad

| Ítem | Naturaleza | Propuesta |
|------|-----------|-----------|
| **RNC-006** — independencia de verificación | Equipo unipersonal | Arreglo de independencia ([doc 22](22_plan_independencia_verificacion.md)) |
| **S-2/S-3** — validación de supuestos de seguridad | Requiere EANA/explotador | Protocolo de validación ([doc 23](23_protocolo_validacion_eana.md)) |
| **A-1** — aprobación del PSAC y calendario SOI | Coordinación ANAC | Acordar en la reunión SOI-1 |

## 7. Agenda propuesta para la reunión SOI-1

1. Presentación del sistema, alcance y arquitectura de aseguramiento (PSAC §1–2).
2. Revisión de la clasificación SWAL y la FHA (docs 02, 06).
3. Revisión de los planes de proceso (SDP/SVP/SCMP/SQAP) y estándares.
4. Estado de conformidad (gap analysis, ~88 %) y evidencia de verificación (CI/cobertura).
5. **Acuerdo sobre independencia de verificación** (doc 22).
6. **Coordinación de la validación con EANA** (doc 23) y del safety case.
7. Cronograma SOI-2/3/4 y criterios de transición.
8. Acta de la reunión y acciones acordadas.

## 8. Registro de cambios

| Ver | Fecha | Cambio |
|-----|-------|--------|
| 0.1 | 2026-07-09 | Emisión inicial: índice del paquete, resumen de conformidad, criterios de entrada, puntos abiertos y agenda de SOI-1. |
