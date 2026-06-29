# Gap Analysis — DO-278A / ED-109A

**Versión:** 0.1 (borrador). **Fecha:** 2026-06-28. **SWAL de referencia:** 2 (núcleo, provisional).

> Estado por objetivo: ✅ Cumplido · ⚠️ Parcial · ❌ Ausente. La columna *Evidencia* apunta a lo que
> existe hoy en el repositorio. Los objetivos se agrupan por proceso DO-278A. La numeración es
> indicativa; al adquirir la norma debe alinearse con sus tablas A-1…A-9 oficiales.

---

## Resumen ejecutivo

| Proceso | Objetivos | ✅ | ⚠️ | ❌ | % cobertura aprox. |
|---------|-----------|----|----|----|--------------------|
| Planificación | 5 | 0 | 1 | 4 | 10% |
| Desarrollo (requisitos/diseño/código) | 6 | 1 | 3 | 2 | 35% |
| Verificación | 7 | 0 | 4 | 3 | 35% |
| Gestión de configuración (SCM) | 4 | 1 | 3 | 0 | 55% |
| Aseguramiento de calidad (SQA) | 3 | 0 | 0 | 3 | 0% |
| Enlace con autoridad | 2 | 0 | 1 | 1 | 15% |
| **Total** | **27** | **2** | **12** | **13** | **~30%** |

Conclusión: **no apto para auditoría de certificación hoy.** Base técnica sólida, pero la capa de
evidencia de proceso (planes, trazabilidad, SCM/SQA, análisis de seguridad) está mayormente ausente.

---

## 1. Proceso de Planificación

| Obj | Descripción | Estado | Evidencia / Brecha |
|-----|-------------|--------|--------------------|
| P-1 | PSAC definido y acordado con la autoridad | ⚠️ | [01_PSAC.md](01_PSAC.md) borrador; sin acuerdo ANAC |
| P-2 | SDP (plan de desarrollo) | ❌ | No existe |
| P-3 | SVP (plan de verificación) | ❌ | No existe |
| P-4 | SCMP + SQAP | ❌ | No existen |
| P-5 | Estándares de requisitos/diseño/código | ❌ | No formalizados; convenciones en CLAUDE.md |

## 2. Proceso de Desarrollo

| Obj | Descripción | Estado | Evidencia / Brecha |
|-----|-------------|--------|--------------------|
| D-1 | Requisitos de alto nivel (HLR) | ❌ | Sin SRS; requisitos implícitos en specs ASTERIX y código |
| D-2 | Requisitos de bajo nivel (LLR) | ❌ | No documentados |
| D-3 | Arquitectura de software | ⚠️ | CLAUDE.md, TECHNICAL.md, planes en `docs/superpowers/` — informal |
| D-4 | Código fuente conforme a estándares | ⚠️ | Código existe y compila; sin estándar de codificación verificado |
| D-5 | Trazabilidad requisitos↔diseño | ❌ | No existe (ver [04](04_matriz_trazabilidad.md)) |
| D-6 | Determinismo / reproducibilidad | ✅ | Ciclo de vida por ToD; `time.time()` vedado (`lifecycle.py`) |

## 3. Proceso de Verificación

| Obj | Descripción | Estado | Evidencia / Brecha |
|-----|-------------|--------|--------------------|
| V-1 | Revisión de requisitos | ❌ | Sin requisitos formales que revisar |
| V-2 | Revisión de diseño | ❌ | No registrada |
| V-3 | Revisión/análisis de código | ⚠️ | Revisiones ad-hoc; sin registro formal |
| V-4 | Pruebas basadas en requisitos | ⚠️ | `tests/` por subsistema; trazabilidad parcial iniciada ([04](04_matriz_trazabilidad.md)) |
| V-5 | Cobertura estructural acorde a SWAL | ⚠️ | CI con `pytest-cov` añadido (`.github/workflows/tests.yml`); falta fijar criterio/umbral por SWAL |
| V-6 | Pruebas de integración del sistema | ⚠️ | PCAP de referencia; CI ejecuta la suite; falta procedimiento formal y archivado de resultados |
| V-7 | Independencia de la verificación | ❌ | No establecida |

## 4. Gestión de Configuración (SCM)

| Obj | Descripción | Estado | Evidencia / Brecha |
|-----|-------------|--------|--------------------|
| C-1 | Identificación de la configuración | ⚠️ | Git presente; sin baseline ni versionado de release |
| C-2 | Control de cambios / problem reporting | ⚠️ | Commits convencionales; sin registro de problemas formal |
| C-3 | Integridad del árbol de fuentes | ⚠️ | `.gitignore` endurecido (binarios/cachés/crashes); falta purgar histórico ya versionado |
| C-4 | Control de entornos de build | ✅ | Runtime documentado (CLAUDE.md, run_linux.sh) |

## 5. Aseguramiento de Calidad (SQA)

| Obj | Descripción | Estado | Evidencia / Brecha |
|-----|-------------|--------|--------------------|
| Q-1 | Auditorías de proceso | ❌ | No existen |
| Q-2 | Auditorías de conformidad de productos | ❌ | No existen |
| Q-3 | Aseguramiento de transición del ciclo de vida | ❌ | No existe |

## 6. Enlace con la Autoridad

| Obj | Descripción | Estado | Evidencia / Brecha |
|-----|-------------|--------|--------------------|
| A-1 | Acuerdo del PSAC y puntos de revisión (SOI) | ⚠️ | PSAC borrador; sin coordinación ANAC |
| A-2 | Presentación del cierre (SAS/Accomplishment Summary) | ❌ | No existe |

## 7. Análisis de seguridad (transversal, exigido por marco ATM)

| Obj | Descripción | Estado | Evidencia / Brecha |
|-----|-------------|--------|--------------------|
| S-1 | FHA (Functional Hazard Assessment) | ❌ | No existe — bloquea confirmación de SWAL |
| S-2 | PSSA / SSA | ❌ | No existe |
| S-3 | Safety case / argumento de seguridad | ❌ | `safety_audit_dialog` audita tráfico, no es safety case de SW |

### Hallazgos de verificación abiertos

**STCA-1 — Doble marco de coordenadas en el motor STCA** (severidad: BAJA; estado: abierto).
`STCA_Engine.evaluar_conflictos` resuelve la **separación actual** con haversine sobre
`lat_render/lon_render` (posición cruda reportada) y la **predicción de CPA** con `x/y`. El caller
`radar_widget.evaluar_stca` alimenta `x/y` con la posición proyectada **suavizada alpha-beta**
([radar_widget.py:1827](../../player/radar_widget.py)), de un linaje distinto a `lat_render`. Además
hay un mismatch de prioridad de campo (`lat or lat_render` en la reproyección vs `lat_render or lat`
en el builder STCA).
- *Riesgo acotado:* la fase VIOLATION (crítica) usa la posición cruda → un conflicto real cercano
  (<10 NM) **siempre** dispara, sin depender de `x/y`. El efecto es una discontinuidad de precisión
  en el borde de los 10 NM (predicción adelantada/atrasada, posible falso positivo transitorio), no
  un conflicto omitido.
- *Acción de certificación:* el SRS debe incluir un requisito de que el caller suministre un **único
  marco de posición consistente** a ambas fases, o que el motor reproyecte `x/y` desde `lat_render`.
  Contrato actual fijado por tests en `tests/stca/test_stca_engine.py` (`test_contrato_*`).

## 8. Prioridades de cierre (top 5)

1. **FHA + confirmación de SWAL** (desbloquea todo el rigor aplicable).
2. **SRS + matriz de trazabilidad** (D-1, D-2, D-5, V-4).
3. **CI con `pytest` + cobertura** (V-5, V-6) y limpieza del árbol de fuentes (C-3).
4. **Planes faltantes** SDP/SVP/SCMP/SQAP (P-2…P-4).
5. **Registros de revisión y SQA** (V-1…V-3, Q-1…Q-3).
