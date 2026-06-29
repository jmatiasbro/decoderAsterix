# Hoja de Ruta de Certificación

**Versión:** 0.1 (borrador). **Fecha:** 2026-06-28.

> Ordena el cierre de brecha en fases. Las estimaciones de esfuerzo son **órdenes de magnitud** para
> dimensionar la viabilidad, no compromisos. Asumen SWAL 2 (núcleo) provisional; la FHA puede mover
> el alcance al alza.

---

## Fase 0 — Decisión de viabilidad (previa)

| Tarea | Salida | Esfuerzo |
|-------|--------|----------|
| Adquirir DO-278A/ED-109A y ED-153 | Tablas de objetivos oficiales | Bajo |
| Definir CONOPS (rol primario vs. respaldo de safety-nets) | Documento CONOPS | Bajo-Medio |
| Reunión preliminar con ANAC | Acuerdo de marco aplicable y SWAL esperado | Bajo |
| **Hito:** decisión Go/No-Go de certificación | Acta | — |

## Fase 1 — Análisis de seguridad y planificación (desbloqueante)

| Tarea | Salida | Esfuerzo |
|-------|--------|----------|
| FHA a nivel sistema (con EANA/explotador) | Lista de peligros y severidades | Medio-Alto |
| PSSA → confirmar SWAL por función | Asignación SWAL definitiva | Medio |
| Actualizar PSAC y clasificación SWAL | [01](01_PSAC.md), [02](02_clasificacion_SWAL.md) v1.0 | Bajo |
| Redactar SDP, SVP, SCMP, SQAP + estándares | Planes aprobados | Alto |
| **Hito:** SOI-1 con ANAC (revisión de planificación) | Aceptación de planes | — |

## Fase 2 — Requisitos y trazabilidad

| Tarea | Salida | Esfuerzo |
|-------|--------|----------|
| Redactar SRS (HLR) a partir de specs ASTERIX + CONOPS | SRS | Alto |
| Derivar LLR y formalizar SDD | SDD | Alto |
| Completar matriz de trazabilidad bidireccional | [04](04_matriz_trazabilidad.md) v1.0 | Medio |
| Revisiones de requisitos y diseño (con registro) | Actas de revisión | Medio |
| **Hito:** SOI-2 (revisión de desarrollo) | — | — |

## Fase 3 — Verificación e infraestructura

| Tarea | Salida | Esfuerzo |
|-------|--------|----------|
| CI: ejecutar `pytest tests/` + cobertura en cada cambio | Pipeline + reportes | Medio |
| Limpiar árbol de fuentes (sacar `.venv`, `.pcap`, `.duckdb`, logs) | Repo bajo baseline | Bajo-Medio |
| Bancos de prueba faltantes: **STCA**, decodificadores CAT, matching, fusión | Casos + resultados | Alto |
| Migrar/descartar scripts `test_*.py` de la raíz | Suite única en `tests/` | Bajo-Medio |
| Cobertura estructural al criterio del SWAL | Reporte de cobertura | Medio-Alto |
| **Hito:** SOI-3 (revisión de verificación) | — | — |

## Fase 4 — Configuración, calidad y cierre

| Tarea | Salida | Esfuerzo |
|-------|--------|----------|
| Baseline formal, control de cambios, etiquetado de release | Registros SCM | Medio |
| Auditorías SQA de proceso y producto | Registros SQA | Medio |
| Gestión COTS/SOUP de `asterix_decoder-0.7.4` | Análisis de impacto | Bajo-Medio |
| Safety case / argumento de seguridad consolidado | Safety case | Medio-Alto |
| Software Accomplishment Summary (SAS) | SAS | Medio |
| **Hito:** SOI-4 (cierre) y presentación final a ANAC | Dossier completo | — |

## Camino crítico

```
Fase 0 ─► FHA/PSSA (Fase 1) ─► SRS+Trazabilidad (Fase 2) ─► Verificación STCA/decoders (Fase 3) ─► Cierre (Fase 4)
            │                        │                              │
       confirma SWAL          define qué probar              cierra los huecos de seguridad
```

Los dos cuellos de botella reales: **(a)** la FHA, que condiciona todo el rigor; y **(b)** la
verificación de **STCA y decodificadores ASTERIX**, hoy sin pruebas automatizadas pese a ser núcleo
de seguridad.

## Quick wins (ejecutables ya, alto valor / bajo costo)

1. CI con `pytest tests/` + cobertura (visibilidad inmediata del estado real).
2. Limpieza del árbol de fuentes y `.gitignore` (integridad de configuración, C-3).
3. `requirements.txt` completo + lockfile de dependencias.
4. Banco de pruebas STCA con escenarios PCAP de referencia (cierra el hueco de mayor riesgo).
5. Consolidar/eliminar los scripts `test_*.py` de la raíz hacia `tests/`.
