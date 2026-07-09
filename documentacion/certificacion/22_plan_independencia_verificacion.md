# Plan de Independencia de Verificación (RNC-006)

**Sistema:** Decodificador ASTERIX + Display PPI ATC.
**Norma:** RTCA DO-278A / EUROCAE ED-109A — independencia de la verificación para SWAL 2.
**Versión:** 0.1. **Fecha:** 2026-07-09. **Estado:** PROPUESTO — a acordar con ANAC en SOI-1.

> Aborda la **RNC-006** (única RNC abierta): el equipo es **unipersonal**, por lo que las revisiones y
> auditorías han sido de **autoevaluación**. Para SWAL 2, DO-278A exige que ciertas actividades de
> verificación sean realizadas por una persona **distinta del autor**. Este plan propone el arreglo de
> independencia y su acta de acuerdo.

---

## 1. Objetivos que requieren independencia (SWAL 2)

| Objetivo | Actividad | Registro actual | Estado de independencia |
|----------|-----------|-----------------|-------------------------|
| V-1 | Revisión de requisitos (SRS) | [doc 20 · RR-REQ-01](20_registros_revision_req_diseno.md) | Autoevaluación |
| V-2 | Revisión de diseño (SDD) | [doc 20 · RR-DIS-01](20_registros_revision_req_diseno.md) | Autoevaluación |
| V-3 | Revisión/análisis de código (módulos SWAL 2) | [doc 12 · RR-01..05](12_registros_revision_codigo.md) | Autoevaluación |
| V-4/V-5 | Pruebas basadas en requisitos + cobertura | `tests/` + CI (88.5 %) | Automatizada (independencia por herramienta) |
| Q-1/Q-2 | Auditorías de proceso/producto | [doc 17](17_registros_auditoria_SQA.md) | Autoevaluación |

> Las pruebas y la cobertura (V-4/V-5) se ejecutan de forma **automatizada en CI**, lo que otorga
> independencia de *ejecución* respecto del autor. Lo que resta es la independencia de las **revisiones**
> (V-1/V-2/V-3) y **auditorías** (Q-1/Q-2).

## 2. Opciones de arreglo de independencia

| Opción | Descripción | Ventaja | Consideración |
|--------|-------------|---------|---------------|
| **A — Revisor independiente designado** | Un ingeniero ajeno al desarrollo (de EANA/explotador o subcontratado) re-ejecuta las revisiones V-1/V-2/V-3 y firma. | Cumple la letra de DO-278A | Requiere disponibilidad y calificación del revisor |
| **B — Independencia gradual por SWAL** | Independencia plena en las **barreras de seguridad** (STCA/APW/MSAW/matching, SWAL 2) y autoevaluación registrada en el resto. | Enfoca el esfuerzo en lo crítico | A acordar con ANAC el alcance |
| **C — Auditoría independiente de SQA** | SQA independiente (persona/rol distinto) audita el proceso y valida los registros de revisión existentes. | Menor costo | No sustituye la revisión técnica independiente donde se exija |

**Propuesta del proyecto:** combinación **A (barreras SWAL 2) + C (SQA)** — un revisor independiente
cubre las revisiones de los cinco módulos SWAL 2 y de los HLR/LLR de seguridad; un rol de SQA
independiente valida los registros y auditorías. El alcance exacto se acuerda con ANAC (Opción B).

## 3. Alcance de la re-verificación independiente

El revisor independiente **DEBE** cubrir, como mínimo:
- Los **5 módulos SWAL 2** (`tracking/lifecycle`, `areas/apw`, `msaw/engine`, `radar_widget` matching+safety, `stca_analyzer`) contra los checklists CR-1..8 ([doc 13](13_estandar_codificacion.md)).
- Los **HLR/LLR de las redes de seguridad** y sus SSR (checklists QR-1..8 y ED).
- Los **hallazgos de seguridad cerrados** (STCA-1..4, TRK-1, ROB-1) y su evidencia de regresión.

Resultado esperado: actas de revisión **firmadas por el revisor independiente**, que reemplazan las de
autoevaluación de los docs 12 y 20 en el alcance acordado.

## 4. Criterios de calificación del revisor

- Experiencia en aseguramiento de software CNS/ATM (DO-278A/ED-109A) o equivalente.
- No haber participado en el desarrollo del código/artefactos que revisa.
- Acceso al repositorio bajo baseline y a los planes/estándares.

## 5. Acta de acuerdo de independencia (plantilla — a completar con ANAC)

```
ACTA DE ACUERDO DE INDEPENDENCIA DE VERIFICACIÓN — RNC-006
Fecha: __________   Lugar/Modalidad: __________

Participantes:
- Por ANAC: ______________________  (rol) ______________
- Por el proyecto: _______________  (rol) ______________
- Revisor independiente designado: ______________________

Acuerdos:
1. Opción de independencia adoptada:  ☐ A   ☐ B (alcance: __________)   ☐ C   ☐ A+C
2. Alcance de la re-verificación independiente: ____________________________
3. Objetivos cubiertos:  ☐ V-1  ☐ V-2  ☐ V-3  ☐ Q-1  ☐ Q-2   Otros: __________
4. Calificación del revisor aceptada:  ☐ Sí  ☐ Con observaciones: __________
5. Plazo y entregables (actas firmadas): __________________________________
6. Cierre de RNC-006 condicionado a: ______________________________________

Firmas: ____________________   ____________________   ____________________
```

## 6. Cierre de RNC-006

RNC-006 se marcará **CERRADA** en el [SQAP §5.3](11_SQAP.md) cuando: (a) exista acta de acuerdo firmada
con ANAC sobre el arreglo; y (b) obren las actas de revisión **firmadas por el revisor independiente**
en el alcance acordado. Hasta entonces permanece **abierta (externa)**.

## 7. Registro de cambios

| Ver | Fecha | Cambio |
|-----|-------|--------|
| 0.1 | 2026-07-09 | Emisión inicial: objetivos con independencia, opciones de arreglo, alcance de re-verificación, plantilla de acta y criterio de cierre. |
