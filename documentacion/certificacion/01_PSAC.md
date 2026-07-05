# PSAC — Plan for Software Aspects of Certification/Approval

**Sistema:** Decodificador ASTERIX + Display PPI ATC.
**Norma de aseguramiento:** EUROCAE ED-109A / RTCA DO-278A.
**Versión:** 0.1 (borrador). **Fecha:** 2026-06-28. **Estado:** PROPUESTO — no aprobado por ANAC.

> El PSAC es el documento de entrada que se presenta a la autoridad. Declara *qué* se va a certificar,
> *con qué rigor* y *mediante qué planes y evidencia*. Esta versión refleja el estado real: muchos
> planes están **por elaborar** y se indican como tales.

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

- Funciones de **redes de seguridad (STCA/APW/MSAW)** y **presentación HMI usada para separación**:
  candidatas a **SWAL 2** (provisional, sujeto a FHA/PSSA).
- Funciones de **análisis/exportación post-operación**: **SWAL 4** o fuera de alcance de seguridad.

> La asignación es **provisional** hasta completar el análisis funcional de peligros (FHA). El PSAC
> se revisará tras la FHA.

## 4. Consideraciones del ciclo de vida del software

### 4.1 Procesos
Se adoptarán los procesos DO-278A: planificación, desarrollo, verificación, gestión de configuración (SCM),
aseguramiento de la calidad (SQA) y enlace con la autoridad.

### 4.2 Planes asociados (estado)
| Plan | Documento | Estado |
|------|-----------|--------|
| SDP — Plan de Desarrollo de Software | [08_SDP.md](08_SDP.md) | Borrador v0.1 |
| SVP — Plan de Verificación de Software | [09_SVP.md](09_SVP.md) | Borrador v0.1 |
| SCMP — Plan de Gestión de Configuración | [10_SCMP.md](10_SCMP.md) | Borrador v0.1 |
| SQAP — Plan de Aseguramiento de Calidad | [11_SQAP.md](11_SQAP.md) | Borrador v0.1 |
| Estándares (diseño/código) | [13_estandar_codificacion.md](13_estandar_codificacion.md) | Borrador v0.2 (linter en CI) |
| Estándares de requisitos | [14_estandar_requisitos.md](14_estandar_requisitos.md) | Borrador v0.1 |

### 4.3 Transición de datos del ciclo de vida
Se definirán los entregables (SRS, SDD, casos/resultados de prueba, registros de revisión) y sus
criterios de transición. Hoy **inexistentes en forma controlada**.

## 5. Datos del ciclo de vida del software (entregables)

| Dato | Existe hoy | Brecha |
|------|-----------|--------|
| Plan de aseguramiento (este PSAC) | Borrador | Aprobación ANAC |
| SRS — Especificación de Requisitos | ❌ | Redactar requisitos de alto y bajo nivel |
| SDD — Descripción de Diseño | [15_SDD.md](15_SDD.md) v0.3 (arquitectura + LLR de todas las capas; todo HLR con LLR) | Diagramas de estados/despliegue; LLR por categoría |
| Código fuente | ✅ | Bajo SCM con baseline |
| Casos y procedimientos de verificación | Parcial (`tests/`) | Cobertura y trazabilidad |
| Resultados de verificación | Parcial (ejecución local) | Reproducible en CI, archivado |
| Matriz de trazabilidad | Inicial ([04](04_matriz_trazabilidad.md)) | Completar bidireccional |
| Registros SCM/SQA | ❌ | Crear |

## 6. Cronograma y enlace con la autoridad
Se definirá en la [hoja de ruta](05_hoja_de_ruta.md). Puntos de contacto (SOI 1–4) a coordinar con ANAC.

## 7. Componentes COTS / SOUP
La extensión `asterix_decoder-0.7.4` (binario C de terceros) se gestionará como software de origen no
controlado (SOUP): identificación de versión, análisis de impacto, y estrategia de verificación de su
salida (los parsers propios ya envuelven y validan resultados — ver `native_asterix.py`).

## 8. Gestión de configuración (resumen)
Repositorio Git existente. **Brechas:** baseline formal, control de cambios, exclusión de artefactos
binarios/entornos del árbol de fuentes, etiquetado de releases certificables.

## 9. Aseguramiento de calidad (resumen)
**Brechas:** auditorías de proceso, revisiones independientes, criterios de aceptación documentados.

## 10. Verificación (estrategia propuesta)
- Revisión de requisitos y diseño.
- Pruebas basadas en requisitos sobre el núcleo (sin GUI, reproducibles por ToD).
- Cobertura estructural acorde al SWAL (a definir el criterio: sentencia / decisión).
- Análisis de la cadena de safety-nets con casos derivados de escenarios operacionales (PCAP de referencia).
- Integración Continua que ejecute `pytest tests/` y publique cobertura (**a implementar**).

## 11. Registro de cambios
| Ver | Fecha | Cambio |
|-----|-------|--------|
| 0.1 | 2026-06-28 | Creación del borrador inicial. |
