# Estándar de Codificación y Diseño — Software SWAL 2

**Sistema:** Decodificador ASTERIX + Display PPI ATC.
**Norma:** EUROCAE ED-109A / RTCA DO-278A — objetivo de estándares (P-5) y código conforme (D-4).
**Versión:** 0.1. **Fecha:** 2026-07-05. **Estado:** PROPUESTO — no aprobado por ANAC.

> Formaliza las reglas contra las cuales se verifica el código (parte código/diseño de la brecha P-5
> «Estándares» del [gap analysis](03_gap_analysis_DO-278A.md); la parte de **requisitos** está en el
> [doc 14](14_estandar_requisitos.md)). Cada regla es **verificable**: por herramienta
> (linter) o por el checklist de [revisión de código](12_registros_revision_codigo.md) (CR-1..8).
> Expande el resumen del [SDP §3](08_SDP.md).

---

## 1. Propósito y alcance

Este estándar aplica a **todo el código Python** del sistema, con rigor reforzado sobre los
**módulos SWAL 2** (redes de seguridad, ciclo de vida y correlación): `analysis/stca_analyzer.py`,
`player/areas/`, `player/msaw/`, `player/tracking/lifecycle.py`, `fusion/correlator.py`.

Reglas marcadas **[SWAL2]** son obligatorias en esos módulos y auditadas en cada revisión;
las demás son recomendadas en todo el árbol.

## 2. Estándar base

- **Lenguaje:** Python 3.12. **Base de estilo:** PEP 8, con las desviaciones de §3.
- **Codificación de archivos:** UTF-8; ejecución con `PYTHONUTF8=1` (evita `UnicodeEncodeError` cp1252).
- **Herramienta de verificación mecánica recomendada:** `ruff`/`flake8` (subconjunto de reglas de §7).

## 3. Reglas de codificación (EC)

| Id | Regla | Verificación |
|----|-------|--------------|
| EC-1 | **Idioma:** comentarios, docstrings y textos de UI en **español**. | Revisión |
| EC-2 | **Comentarios del WHY, no del WHAT:** comentar solo lo no obvio (decisión, invariante, referencia normativa); no narrar lo que el código ya dice. | Revisión |
| EC-3 | **Nomenclatura:** `snake_case` para funciones/variables, `PascalCase` para clases, `MAYÚSCULAS` para constantes de módulo. Nombres del dominio (track, plot, squawk, FL). | Linter + revisión |
| EC-4 | **Longitud de línea:** ≤ 100 columnas (guía; no rígida en tablas/URLs). | Linter |
| EC-5 | **Sin imports no usados ni `import *`** en módulos de producción. | Linter |
| EC-6 **[SWAL2]** | **Núcleo agnóstico a Qt:** los módulos SWAL 2 no importan PyQt6; son ejecutables headless. | Linter (prohibir `PyQt6` en esos paths) + revisión (CR-1) |
| EC-7 **[SWAL2]** | **Determinismo temporal:** en los motores de decisión y ciclo de vida se usa `SimulationTime.time()` / ToD ASTERIX; **`time.time()` está VEDADO**. `time.monotonic()` de pared solo se permite en watchdogs de la UI, no en la lógica de decisión. | Linter (prohibir `time.time(` en `lifecycle.py`) + revisión (CR-2) |
| EC-8 **[SWAL2]** | **Validación de entradas:** todo campo externo (plot/track) se valida o coerciona (tipo, None, rango) antes de usarlo en aritmética o comparación. | Revisión (CR-3) |
| EC-9 **[SWAL2]** | **Sin descarte silencioso:** un `except` que descarta datos operativos debe **loguear/contabilizar** (observabilidad); prohibido `except: pass` que oculte pérdida de un plot/track. El alcance del `except` debe ser el mínimo necesario. | Revisión (CR-6); ver ROB-1 |
| EC-10 | **Manejo de errores explícito:** capturar excepciones concretas cuando se conocen; el `except Exception` amplio se justifica en comentario y no debe tragar errores de programación. | Revisión |
| EC-11 **[SWAL2]** | **Constantes nombradas:** umbrales de seguridad (separación, banda FL, tiempos) son constantes con nombre o parámetros, no literales embebidos sin explicar. | Revisión (CR-7) |
| EC-12 | **Complejidad acotada:** funciones de propósito único; complejidad ciclomática objetivo ≤ 15. Extraer helpers cuando crezca. | Linter (opcional) + revisión (CR-8) |
| EC-13 **[SWAL2]** | **Trazabilidad:** cada módulo SWAL 2 referencia en su docstring el/los HLR o FC que implementa. | Revisión (CR-4) |
| EC-14 | **Estado mutable global:** evitar; el estado de decisión vive en objetos inyectables (p. ej. `now_fn`, `SimulationTime`) para reproducibilidad y test. | Revisión |
| EC-15 | **Recursos y memoria:** usar `__slots__` en clases de alta cardinalidad (tracks); búferes acotados (`deque(maxlen=...)`) en rutas de alta frecuencia. | Revisión |

## 4. Estándar de diseño (ED)

| Id | Regla |
|----|-------|
| ED-1 | **Separación núcleo ↔ UI:** `decoder/`, `fusion/`, `analysis/`, `storage/` sin Qt; `player/` concentra la UI. Toda función de seguridad se implementa en el núcleo sin Qt. |
| ED-2 | **Cadena de seguridad coalescida:** STCA → APW → MSAW se evalúa a ~1 Hz; el repintado es independiente (throttle) para no acoplar seguridad y render. |
| ED-3 | **Fusión conservadora:** ante duda de identidad, **no fusionar** (preferir duplicado visible a fusión errónea que oculte tráfico/STCA). |
| ED-4 | **Cartografía:** geometrías en GeoJSON (`LineString`/`Point`, `[lon, lat]`); el formato legacy `.map` se convierte con `tools/map_to_geojson.py`. |
| ED-5 | **Visibilidad en QToolBar:** togglear la **acción** de `addWidget()` (`action.setVisible`), no `widget.setVisible()`. |

## 5. Convenciones de configuración de la gestión (SCM)

- **Commits:** Conventional Commits con scope — `tipo(scope): mensaje` (p. ej. `fix(tracking): …`).
- **Baselines:** etiquetas anotadas `vMAJOR.MINOR.PATCH[-hito]`.

## 6. Prohibiciones (resumen duro)

1. `time.time()` en motores de decisión/ciclo de vida **[SWAL2]** (EC-7).
2. `except: pass` o `except Exception: return` que **descarte datos operativos sin traza** (EC-9).
3. Imports de PyQt6 en módulos del núcleo SWAL 2 (EC-6).
4. Literales de umbral de seguridad sin nombrar (EC-11).
5. `import *` en código de producción (EC-5).

## 7. Verificación del estándar

| Mecanismo | Alcance |
|-----------|---------|
| **Revisión de código** ([doc 12](12_registros_revision_codigo.md)) | Checklist CR-1..8 mapea a EC/ED; obligatoria por baseline en módulos SWAL 2. |
| **Linter del estándar** (`tools/lint_swal2.py`) | Prohibiciones duras EC-5/EC-6/EC-7 sobre los paths SWAL 2 (§1); ignora strings/comentarios. **Automatizado en CI** (`.github/workflows/tests.yml`, step «Linter del estándar SWAL 2»): falla el pipeline ante `time.time(`, `import PyQt6` o `import *` en el núcleo. Auto-verificado por `tests/tools/test_lint_swal2.py`. |
| **Linter de estilo** (`ruff`/`flake8`) | EC-3/EC-4 (nomenclatura, longitud de línea). Recomendado; no bloqueante aún. |
| **Suite de tests** | EC-7/8/9 quedan además cubiertas por tests (`test_lifecycle`, `test_plot_descarte`, escenarios STCA). |

## 8. Registro de desviaciones

Las desviaciones aprobadas se listan aquí con justificación y fecha. Ninguna al momento de emisión.

| Id | Regla | Módulo | Justificación | Estado |
|----|-------|--------|---------------|--------|
| — | — | — | — | — |

## 9. Registro de cambios

| Ver | Fecha | Cambio |
|-----|-------|--------|
| 0.1 | 2026-07-05 | Emisión inicial: reglas EC-1..15, ED-1..5, verificación y prohibiciones. |
| 0.2 | 2026-07-05 | Linter del estándar (`tools/lint_swal2.py`) automatizado en CI (EC-5/6/7); §7 actualizada. Cierra D-4. |
