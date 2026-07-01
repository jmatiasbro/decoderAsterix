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

1. ✅ **Banco de pruebas STCA** (`tests/stca/`, 27 casos) — cierra el hueco de mayor riesgo (REQ-SN-1).
   Pendiente: escenarios PCAP end-to-end y resolución del hallazgo STCA-1.
2. ✅ **Banco de pruebas decodificadores ASTERIX** (`tests/decoders/`, 91 casos: CAT001/002/021/034/048/062) — REQ-DEC-1 a REQ-DEC-4 cerrados.
3. ✅ **CI con `pytest tests/` + cobertura** (`.github/workflows/tests.yml`) — V-5/V-6.
4. ⚠️ **`.gitignore` endurecido** (`.pcap`, `.S4RD`, `.kmz`, `.sqlite`, cachés, crashes) — C-3.
   Pendiente: purgar del histórico los binarios ya versionados.
5. ✅ **`requirements.txt` completo + `requirements-lock.txt`** (PyQt6, duckdb, scapy, dpkt, numpy, matplotlib, pyproj, fpdf2, pygeomag, Pillow — versiones exactas fijadas).
6. ⚠️ **Consolidar/eliminar scripts `test_*.py` de la raíz** — `test_profile.py` migrado a `tests/profiles/` (8 casos, REQ-ROL-1 ✅). Los 22 restantes son legacy; pendiente confirmación de borrado.
7. ✅ **Matching de tracks** (`tests/tracking/test_matching.py`, 31 casos, pasos A–E + CAT62) — REQ-TRK-2 cerrado.
8. ✅ **Sensor registry** (`tests/decoders/test_sensor_registry.py`, 11 casos) — REQ-DEC-5 cerrado.
9. ✅ **Proyección estereográfica** (`tests/geo/test_stereographic.py`, 11 casos) — REQ-GEO-1 cerrado.
10. ✅ **Correlación multi-radar** (`tests/fusion_tests/test_correlator.py`, 26 casos) — REQ-FUS-1/2 cerrados.
11. ✅ **Auditoría safety** (`tests/storage_tests/test_safety_audit.py`, 17 casos: 9 persistencia + 8 CSV) — REQ-AUD-1/2 cerrados. **Suite total: 447 tests / 0 fallos.**

### Triage de tests (resuelto)
- ✅ **3 tests preexistentes en rojo** corregidos (eran expectativas desactualizadas, no regresiones):
  `tests/msaw/test_render.py` (etiqueta correcta = número + apóstrofe, p. ej. `"2500'"`) y
  `tests/centro_tecnico/test_window.py` (6 pestañas, no 5). **Baseline verde: 251 pasan / 0 fallan.**
