# Clasificación SWAL — Software Assurance Level

**Norma:** EUROCAE ED-109A / RTCA DO-278A. **Versión:** 0.2 (borrador). **Fecha:** 2026-07-01.
**Estado:** PROVISIONAL — el FHA ([06_FHA.md](06_FHA.md) v0.1) escala matching/lifecycle a SWAL 2. Requiere validación con EANA y confirmación por PSSA.

> El SWAL (1 = más crítico … 4 = menos) se asigna según la **severidad del efecto de un fallo del
> software** en la seguridad operacional ATM, derivada del análisis de peligros del sistema. Sin FHA
> formal, esta clasificación es un **punto de partida razonado**, no una asignación definitiva.

---

## 1. Método

1. Identificar las **funciones** del software y su rol operacional.
2. Estimar la **severidad** del peor efecto creíble de un mal funcionamiento (datos erróneos o pérdida de función).
3. Considerar **mitigaciones externas** (procedimientos ATC, redundancia, juicio del controlador, otros sistemas).
4. Asignar SWAL provisional. La severidad se mapea a SWAL según las tablas de ED-109A/Doc 9859.

### Escala de severidad (referencia OACI Doc 9859 / ED-153)
| Severidad | Efecto | Tendencia SWAL |
|-----------|--------|----------------|
| Catastrófico | Accidente | SWAL 1 |
| Peligroso (Hazardous) | Gran reducción de márgenes de seguridad | SWAL 2 |
| Mayor (Major) | Reducción significativa | SWAL 3 |
| Menor (Minor) | Molestia operacional | SWAL 4 |
| Sin efecto | — | Fuera de alcance |

## 2. Inventario funcional y clasificación provisional

| Función | Módulo | Efecto de fallo (peor caso creíble) | Mitigación externa | Severidad | **SWAL prov.** |
|---------|--------|--------------------------------------|--------------------|-----------|----------------|
| Decodificación ASTERIX | `decoder/`, `decoders/` | Posición/identidad de track errónea sin aviso → decisión ATC sobre dato falso | Cotejo con otros sensores; plausibilidad | Peligroso | **2** |
| Proyección polar→WGS-84 | `projection.py`, `geo_*` | Track desplazado → separación mal evaluada | Juicio del controlador; otros sensores | Peligroso | **2** |
| Presentación PPI / ODS | `radar_widget.py`, `player/ods` | Símbolo/etiqueta engañosa usada para separación | Procedimientos; relectura | Peligroso/Mayor | **2** |
| STCA (conflicto a corto plazo) | cadena safety | Falla en alertar conflicto real, o alerta falsa que distrae | STCA es *red de respaldo*, no separación primaria | Mayor | **3** |
| APW (penetración de área) | `player/areas` | No alertar penetración de área restringida | Procedimientos; coordinación | Mayor | **3** |
| MSAW (alerta de altitud mínima) | `player/msaw` | No alertar proximidad al terreno | Red de respaldo; reglas de vuelo | Mayor | **3** |
| Ciclo de vida de tracks | `player/tracking/lifecycle.py` | Track fantasma / **caído prematuramente** (FC-LIF-02) | Determinista; testeado | **Peligroso** (caída silenciosa) | **2** ⬆️ |
| Matching/reconciliación de tracks | `player/radar_widget.py` | Fusión errónea de dos aeronaves (FC-TRK-01) | H-AS-3, TCAS | **Peligroso** (aeronave desaparece) | **2** ⬆️ |
| Fusión multi-radar / calibración | `fusion/` | Correlación errónea → doble track o salto | Solo rol técnico; no operacional en vivo | Mayor | **3** |
| Análisis / exportación post-operación | `analysis/`, `exporters.py` | Informe incorrecto (no afecta tiempo real) | Revisión humana del informe | Menor | **4** |
| Auditoría de eventos safety | `storage/`, `safety_audit_dialog` | Registro incompleto para informe OACI | No afecta separación en vivo | Menor | **4** |

## 3. SWAL gobernante propuesto

El nivel más exigente entre las funciones operacionales en tiempo real determina el rigor del núcleo
común (decodificación, proyección, presentación):

> **SWAL 2 (provisional)** para el núcleo operacional (decodificación, proyección, presentación HMI).
> **SWAL 3** para las redes de seguridad como funciones de respaldo.
> **SWAL 4 / fuera de alcance** para análisis y auditoría post-operación.

### Justificación de la rebaja de STCA/APW/MSAW a SWAL 3
Las redes de seguridad son, por diseño, **última barrera de respaldo** y no el medio primario de
separación (que recae en el controlador con procedimientos PANS-ATM). Por ello el efecto de un fallo
es típicamente *Mayor* y no *Peligroso* — **siempre que** la documentación operacional y la HMI dejen
explícito que son de respaldo. Si el CONOPS las posiciona como medio primario, escalan a SWAL 2.

## 4. Supuestos y dependencias
- Existe un controlador humano en el lazo con procedimientos PANS-ATM vigentes.
- El sistema no emite resoluciones de conflicto automáticas ni controla actuadores.
- La presentación es de **vigilancia/asistencia**, no un sistema de separación automatizada.

> Si cualquiera de estos supuestos no se cumple, **toda la clasificación debe re-evaluarse al alza**.

## 5. Confirmación requerida (acciones)
1. Ejecutar **FHA** (Functional Hazard Assessment) a nivel sistema con EANA/explotador.
2. Ejecutar **PSSA** para asignar/confirmar SWAL y derivar requisitos de seguridad.
3. Validar el CONOPS (rol primario vs. respaldo de las redes de seguridad).
4. Revisar este documento y el PSAC con los resultados.

## 6. Registro de cambios
| Ver | Fecha | Cambio |
|-----|-------|--------|
| 0.1 | 2026-06-28 | Clasificación provisional inicial basada en juicio de ingeniería. |
| 0.2 | 2026-07-01 | Revisión post-FHA: matching/reconciliación y ciclo de vida (caída prematura) escalados a SWAL 2. |
