# Protocolo de Validación de Supuestos de Seguridad con EANA (H-AS-1..6)

**Sistema:** Decodificador ASTERIX + Display PPI ATC.
**Norma:** RTCA DO-278A / EUROCAE ED-109A; base de análisis [FHA (doc 06)](06_FHA.md).
**Versión:** 0.1. **Fecha:** 2026-07-09. **Estado:** PROPUESTO — a coordinar con EANA/explotador.

> Cierra las acciones **FHA-A1** y **SSA-A5** (objetivos **S-2/S-3** del gap analysis): la clasificación
> SWAL y el argumento de seguridad se apoyan en **seis supuestos operacionales (H-AS-1..6)** que **no**
> puede verificar el proyecto por sí solo — dependen del entorno operativo (EANA/explotador). Este
> protocolo define qué validar, con qué evidencia y cómo registrarlo en acta.
>
> **Criticidad:** si un supuesto **no** se valida, la clasificación afectada **debe re-evaluarse al alza**
> ([FHA §1.3](06_FHA.md)); por eso la validación es condición del safety case.

---

## 1. Supuestos a validar y evidencia requerida

| ID | Supuesto (FHA §1.3) | Mitiga / sostiene | Evidencia que EANA/explotador debe aportar | Efecto si NO se cumple |
|----|---------------------|-------------------|--------------------------------------------|------------------------|
| **H-AS-1** | Existe un controlador ATC humano en el lazo en todo momento | SWAL de la HMI de separación | CONOPS / MATS: el sistema es **apoyo a la decisión**, no autónomo; dotación de controladores por posición | Reclasificar separación HMI a SWAL 2 o superior |
| **H-AS-2** | La separación primaria se realiza por procedimientos PANS-ATM (Doc 4444), no exclusivamente por este sistema | FC-STCA/HMI/TRK como *respaldo* | Procedimientos ATS que definan el medio primario de separación; rol de este sistema como vigilancia/respaldo | Reclasificar como medio primario; **escalar SWAL** |
| **H-AS-3** | Las aeronaves del sector disponen de ACAS/TCAS como salvaguarda autónoma | Atenúa FC-STCA-01 (falso negativo) | Normativa de porte (RAAC/OACI Anexo 6) + perfil de equipamiento del tránsito del sector | Sube severidad de FC-STCA-01 |
| **H-AS-4** | El sistema no emite resoluciones de conflicto automáticas ni controla actuadores | Límite del alcance de seguridad | Confirmación operacional de que no se usa como automatización ni lazo de control | Si se añade automatización → **FHA nueva completa** |
| **H-AS-5** | Las aeronaves IFR en aproximación/crucero cuentan con GPWS/EGPWS | Atenúa FC-MSAW-01 (CFIT) | Normativa de porte GPWS/EGPWS + perfil de la flota IFR del área | Sube severidad de FC-MSAW-01 (Peligroso sin GPWS) |
| **H-AS-6** | La organización explotadora define procedimientos para pérdida o degradación del sistema | Atenúa FC-HMI-01 y FC-DEC-01 | Procedimientos de contingencia por pérdida/degradación de la vigilancia (fallback a otros sensores/procedimientos) | Sube severidad de FC-HMI-01/DEC-01 |

## 2. Método de validación

1. **Preparación:** enviar a EANA/explotador la FHA (doc 06) y esta tabla; solicitar la documentación
   operacional de referencia por supuesto (§1).
2. **Sesión de validación** (taller conjunto proyecto ↔ EANA, con participación ANAC si corresponde):
   revisar supuesto por supuesto contra la evidencia aportada.
3. **Dictamen por supuesto:** `VALIDADO` / `VALIDADO CON CONDICIONES` / `NO VALIDADO`, con referencia
   documental y, si aplica, la condición/limitación operacional.
4. **Impacto:** para cada supuesto `NO VALIDADO` o condicional, evaluar el impacto en la FHA/SWAL
   ([FHA §1.3](06_FHA.md)) y abrir la acción de re-clasificación correspondiente.
5. **Registro:** consolidar en el **acta** (§3); actualizar S-2/S-3 en el gap analysis y cerrar SSA-A5 /
   FHA-A1 si todos los supuestos quedan validados (o validados con condiciones aceptadas).

## 3. Acta de validación (plantilla — a completar con EANA)

```
ACTA DE VALIDACIÓN DE SUPUESTOS DE SEGURIDAD (H-AS-1..6) — FHA-A1 / SSA-A5
Fecha: __________   Modalidad: __________
Participantes:  Por EANA/explotador: __________   Por el proyecto: __________   Por ANAC: __________

| Supuesto | Dictamen | Evidencia (doc/ref) | Condición / limitación | Impacto FHA/SWAL |
|----------|----------|---------------------|------------------------|------------------|
| H-AS-1   | ☐ Validado ☐ Cond. ☐ No | ____________________ | ______________________ | ________________ |
| H-AS-2   | ☐ Validado ☐ Cond. ☐ No | ____________________ | ______________________ | ________________ |
| H-AS-3   | ☐ Validado ☐ Cond. ☐ No | ____________________ | ______________________ | ________________ |
| H-AS-4   | ☐ Validado ☐ Cond. ☐ No | ____________________ | ______________________ | ________________ |
| H-AS-5   | ☐ Validado ☐ Cond. ☐ No | ____________________ | ______________________ | ________________ |
| H-AS-6   | ☐ Validado ☐ Cond. ☐ No | ____________________ | ______________________ | ________________ |

Conclusión:  ☐ Todos validados (habilita el safety case)  ☐ Con acciones de re-clasificación: ______
Firmas: ____________________   ____________________   ____________________
```

## 4. Cierre de S-2/S-3

Al obrar el acta con todos los supuestos **validados** (o validados con condiciones aceptadas por ANAC):
- Se marcan **SSA-A5** ([doc 16 §8](16_PSSA_SSA.md)) y **FHA-A1** ([doc 06](06_FHA.md)) como cerradas.
- Se actualizan **S-2/S-3** ⚠️→✅ en el [gap analysis](03_gap_analysis_DO-278A.md).
- El **safety case** ([doc 16 §7](16_PSSA_SSA.md)) queda habilitado (validación de premisas externas completa).

## 5. Registro de cambios

| Ver | Fecha | Cambio |
|-----|-------|--------|
| 0.1 | 2026-07-09 | Emisión inicial: supuestos H-AS-1..6 con evidencia requerida y efecto si no se cumplen, método de validación, plantilla de acta y criterio de cierre de S-2/S-3. |
