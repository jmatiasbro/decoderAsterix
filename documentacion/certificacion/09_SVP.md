# SVP — Software Verification Plan

**Sistema:** Decodificador ASTERIX + Display PPI ATC.
**Norma:** EUROCAE ED-109A / RTCA DO-278A — Sección 6 (Verificación).
**Versión:** 0.1 (borrador). **Fecha:** 2026-07-03. **Estado:** PROPUESTO — no aprobado por ANAC.

---

## 1. Propósito y alcance

Este plan describe los métodos, niveles, criterios de cobertura y responsabilidades para verificar
que el software satisface los requisitos de la [SRS](07_SRS.md) con el rigor correspondiente al
SWAL asignado en [02_clasificacion_SWAL.md](02_clasificacion_SWAL.md).

La verificación de software en DO-278A incluye: revisión de requisitos y diseño, pruebas basadas
en requisitos, análisis de cobertura estructural y análisis de compatibilidad de herramientas.

---

## 2. Métodos de verificación

DO-278A reconoce tres métodos complementarios:

| Método | Uso en este proyecto |
|---|---|
| **Revisión** | Inspección de requisitos (SRS), diseño (SDD/CLAUDE.md), código y resultados de prueba |
| **Análisis** | Análisis de flujo de datos, control de tiempo, peor caso de ejecución (WCA) para SWAL 2 |
| **Prueba** | Suite `pytest` estructurada; pruebas de integración headless; smoke test en vivo |

---

## 3. Organización de la suite de verificación

### 3.1 Estructura de directorios

```
tests/
├── pytest.ini               ← addopts: --import-mode=importlib; pythonpath: ..
├── conftest.py              ← inyecta la raíz al sys.path
├── atm/                     ← tests de aerovías, aeropuertos, DB ATM
├── areas/                   ← tests APW (modelo + store) — HLR-APW-*
├── msaw/                    ← tests MSAW — HLR-MSAW-*
├── tracking/                ← tests matching/lifecycle — HLR-TRK-*
├── geo/                     ← tests proyección geodésica — HLR-GEO-*
├── stats/                   ← tests estadísticas
├── firmap/                  ← tests vista FIR
├── ods/                     ← tests simbología ODS
├── centro_tecnico/          ← tests Centro Técnico ATSEP
├── fdp/                     ← tests FDP/ADEXP — parser, dispatcher, worker
├── fusion_tests/            ← tests correlación multi-radar — HLR-FUS-*
├── storage_tests/           ← tests persistencia + auditoría — HLR-AUD-*
└── <raíz>/                  ← tests de decodificadores CAT* — HLR-DEC-*
```

> **Nota de importlib:** Los subdirectorios `fusion_tests/` y `storage_tests/` llevan sufijo
> `_tests` para evitar colisión de namespace con los paquetes `fusion/` y `storage/` del proyecto
> bajo `--import-mode=importlib`.

### 3.2 Estado actual de la suite

| Subsistema | Tests | HLR cubiertos | Estado |
|---|---|---|---|
| Decodificadores CAT* | ~60 | HLR-DEC-01..08 | ✅ |
| Proyección geodésica | ~15 | HLR-GEO-01..05 | ✅ |
| Tracking / matching | ~41 | HLR-TRK-01..08 | ✅ |
| Áreas / APW | ~20 | HLR-APW-01..04 | ✅ |
| MSAW | ~15 | HLR-MSAW-01..05 | ✅ |
| Fusión multi-radar | ~26 | HLR-FUS-01..02 | ✅ |
| Persistencia / Auditoría | ~17 | HLR-AUD-01..02 | ✅ |
| FDP / ADEXP | 32 | — (operacional) | ✅ |
| HMI (completitud / fidelidad / estado / watchdog) | 34 | HLR-HMI-01..06 | ✅ |
| Rendimiento del motor | 6 | HLR-PERF-01..03 | ✅ |
| Integración end-to-end PCAP | 6 | REQ-DEC/GEO/TRK + safety | ✅ |
| STCA escenarios end-to-end | 7 | REQ-SN-1 / HLR-STCA-01 (STCA-1) | ✅ |
| Navegación / zoom PPI | 6 | — (HMI) | ✅ |
| Varios (ATM, ODS, FIR, stats) | ~248 | — | ✅ |
| **Total** | **533** | | |

### 3.3 Brechas de cobertura abiertas

| HLR | Descripción | Tipo de test requerido |
|---|---|---|
| HLR-HMI-01..03 | Completitud de labels, simbología ODS, watchdog | Integración con QApplication offscreen |
| HLR-HMI-04 | Watchdog de pantalla negra | Implementación + test |
| HLR-PERF-01..05 | Latencia de batch, throughput, tiempo de ciclo safety | Benchmark (pytest-benchmark) |
| HLR-SSR-01..11 | Requisitos de seguridad derivados de la FHA | Parcialmente cubiertos por tests de safety nets |

---

## 4. Ejecución de la suite

### 4.1 Comando canónico

```
set QT_QPA_PLATFORM=offscreen
set PYTHONUTF8=1
C:\...\Python312\python.exe -m pytest tests/ -v --tb=short
```

### 4.2 Ejecución selectiva por subsistema

```
python -m pytest tests/tracking/          # ciclo de vida y matching
python -m pytest tests/areas/ tests/msaw/ # safety nets APW y MSAW
python -m pytest tests/fusion_tests/      # fusión multi-radar
python -m pytest tests/storage_tests/     # persistencia y auditoría
python -m pytest tests/fdp/               # FDP/ADEXP
```

### 4.3 Test de un caso específico

```
python -m pytest tests/tracking/test_matching.py::TestModoNoIntegrado -v
```

### 4.4 Cobertura de decisiones (branch) — módulos SWAL 2

Para SWAL 2 se mide cobertura de **decisiones** (branch) sobre las unidades de seguridad:
redes de seguridad (STCA/APW/MSAW), ciclo de vida de tracks y correlación multi-radar.
Los módulos de presentación/render (`*/render.py`) se excluyen (no contienen lógica de
decisión de seguridad). Configuración en [`.coveragerc`](../../.coveragerc).

**Comando canónico:**

```
python -m pytest tests/ \
    --cov=player/tracking --cov=player/areas --cov=player/msaw \
    --cov=analysis/stca_analyzer --cov=fusion/correlator \
    --cov-config=.coveragerc \
    --cov-branch --cov-report=term --cov-report=html:coverage/htmlcov
```

**Línea base medida (2026-07-05, 526 tests):**

| Módulo | Cobertura (branch) |
|---|---|
| `analysis/stca_analyzer.py` (STCA) | 100 % |
| `fusion/correlator.py` (correlación) | 100 % |
| `player/tracking/lifecycle.py` (ciclo de vida) | 92 % |
| `player/msaw/model.py` | 90 % |
| `player/areas/model.py` | 87 % |
| `player/msaw/engine.py` | 86 % |
| `player/areas/apw.py` | 85 % |
| `player/msaw/data.py`, `player/areas/store.py` | 85 % / 97 % |
| **TOTAL núcleo SWAL 2** | **88.5 %** |

Objetivo propuesto para SWAL 2: **≥ 80 %** (a acordar con ANAC) — **alcanzado**. La medición
se automatiza en Integración Continua ([`.github/workflows/ci.yml`](../../.github/workflows/ci.yml))
en cada *push*/PR, con `--cov-fail-under=80` y publicación del reporte HTML como artefacto.

---

## 5. Niveles de prueba

### 5.1 Prueba unitaria

Verifica módulos individuales en aislamiento, sin dependencias de Qt ni de red.

- Alcance: `decoder/`, `player/tracking/lifecycle.py`, `player/areas/model.py`,
  `player/msaw/model.py`, `decoder/adexp_parser.py`, `player/fdp/dispatcher.py`.
- Fixtures: datos mínimos construidos en el test; mocks solo donde sea imposible
  usar el objeto real sin efectos secundarios.
- Criterio: 100 % de tests pasan; los errores se documentan y cierran antes del merge.

### 5.2 Prueba de integración

Verifica la interacción entre módulos (p. ej., `DataEngine` + `DuckDBRepository`,
`FdpWorker` + `FdpDispatcher` + DuckDB en memoria).

- Alcance: `tests/storage_tests/`, `tests/fdp/test_worker.py`, `tests/fusion_tests/`.
- Entorno: headless, sin GUI; DuckDB en `tmp_path` (pytest fixture) o `:memory:`.
- Criterio: comportamiento de interfaz conforme a los HLR que cubren la interacción.

### 5.3 Prueba del sistema (smoke test)

Verifica que la aplicación arranca, procesa un PCAP real y no produce errores fatales.

- Script: `test_app_ok.py` en la raíz (arranque con `QT_QPA_PLATFORM=offscreen`).
- PCAP de referencia: `baires.pcap` (~296 k paquetes, ~5000 PPS).
- Criterio: sin `SystemExit` no controlado, sin `RuntimeError` no capturado.

### 5.4 Prueba de rendimiento

Verifica que la cadena de procesamiento cumple las cotas de latencia declaradas en HLR-PERF-*.

**Cobertura automática (pytest, `tests/tracking/test_perf.py`):**
- HLR-PERF-01: latencia de lote de 200 plots < 200 ms.
- HLR-PERF-02: cadencia de safety chain configurable (0.5–2 Hz).
- HLR-PERF-03: creación de 500 tracks < 2 s; reconciliación de 500 tracks < 500 ms.

**Cobertura manual (banco de estrés UDP, `HLR-PERF-04/05`):**

Instrumentación: variable de entorno `DECODE_PERF=1` (umbral `DECODE_PERF_MS`), que
registra en consola cada callback del hilo de UI que supere el umbral, con nº de tracks.

Inyector: `stress_tester.py` reproduce `baires.pcap` (multi-sensor: radares SSR/PSR +
ADS-B) a una tasa de PPS configurable contra el puerto UDP 8600.

- **HLR-PERF-04 — refresco del PPI:** el repintado está capado a 15 FPS (`_request_repaint`,
  `_repaint_min_dt = 1/15`). El presupuesto por frame es 66 ms. Criterio: `paintEvent < 66 ms`
  con la carga operativa nominal (playback multi-sensor de `baires.pcap` a tiempo real).
- **HLR-PERF-05 — capacidad de ingesta:** tasa de PPS sostenible sin degradar la
  interactividad de la HMI (los menús responden). Se determina empíricamente por rampa.

#### 5.4.1 Resultados de la rampa de estrés (fecha: _______, operador: _______)

| PPS objetivo | Interactividad (menús) | Presentación | Veredicto |
|---|---|---|---|
| 500  | Fluida | Correcta | ✅ Sostenible |
| 800  | Fluida, menús operativos | Duplicados (ver Hallazgo 2) | ⚠️ Límite |
| 1000 | Degradada | Tracks se atrasan y saltan (backlog) | ❌ |
| 2500 | No responde | — | ❌ |

**Tasa sostenible verificada (interactividad):** **800 PPS** (inyección de un único stream
UDP, `baires.pcap` multi-sensor, replay en loop). Muy por encima de la carga operativa real
(un radar SSR ≈ 50–200 PPS; agregado multi-sensor, cientos).

**Hallazgo 1 — costo de render (RESUELTO).** El `paintEvent` costaba ~40–43 ms **independiente
del nº de tracks**: lo dominaba el redibujo vectorial del mapa de fondo (cartografía +
coberturas + anillos). Se implementó cache del mapa de fondo a `QPixmap` (regenerado solo al
cambiar zoom/pan/tamaño/capas). Además se corrigió: emisión única de `sensor_detected` por
sensor, límite de drenaje UDP por ciclo, `deque` para el búfer de plots y throttle del `print`
de RPM en el hilo de UI. Tras estos cambios la interactividad es fluida hasta 800 PPS.

**Hallazgo 2 — duplicados bajo estrés (ARTEFACTO DEL BANCO, no defecto).** A ≥800 PPS con el
inyector sintético aparecen tracks duplicados (el mismo avión, sin fusionar entre sensores).
Causa raíz: la fusión multi-radar (`fusion/correlator.py::son_misma_aeronave`) decide identidad
por co-ubicación **extrapolada a un tiempo de referencia común** y por asociación squawk↔Mode-S
**aprendida en el tiempo**. El banco de estrés comprime el tiempo ~10×, reproduce el PCAP en
loop e inyecta todos los sensores en un solo stream a velocidad no realista; bajo esas
condiciones la extrapolación temporal y el aprendizaje de asociación no operan como en régimen
real y las representaciones quedan sin fusionar.

*Verificación de aislamiento:* en **playback a 1× no hay duplicados** — la fusión opera
correctamente en condiciones operativas. El defecto NO se reproduce en régimen real.

*Decisión de diseño (crítica para seguridad):* **NO se relajan los gates de fusión** para
suprimir estos duplicados. Aflojar el umbral para fusionar representaciones dispersas
arriesgaría fusionar dos aeronaves realmente distintas en operación real, **ocultando un
conflicto STCA entre ellas**. La política conservadora (preferir un duplicado visible antes que
una fusión errónea) es la correcta para un sistema de seguridad: un duplicado es visible y
diagnosticable; una fusión indebida esconde tráfico. Traza a HLR-TRK/HLR-FUS y a la FHA.

- Herramienta futura para 01–03: migrar a `pytest-benchmark` para históricos de regresión.
- Mejora futura para elevar el techo >800 PPS: mover matching/decodificación fuera del hilo de
  UI o aplicar load-shedding bajo sobrecarga; ver [08_SDP.md](08_SDP.md). No requerido para la
  capacidad operativa nominal.

---

## 6. Trazabilidad de verificación

Cada test debe trazar a uno o más HLR de la SRS. La convención es:

```python
# En el docstring o comentario del test:
# HLR-TRK-08: modo_integrado=False no fusiona cross-sensor
def test_proximidad_sensor_diferente_no_fusiona(self, w_no_int):
    ...
```

La [Matriz de Trazabilidad](04_matriz_trazabilidad.md) mantiene la relación HLR ↔ test.
Los HLR sin test asociado se marcan como **brecha** y bloquean la aprobación de SOI-2.

---

## 7. Revisión de código

Para módulos SWAL 2, la revisión de código es un paso obligatorio antes del merge:

### 7.1 Checklist mínimo de revisión

- [ ] El cambio está motivado por un HLR identificado.
- [ ] No se usa `time.time()` en el motor de ciclo de vida (detecta HLR-TRK-01).
- [ ] No se usan `widget.setVisible()` en toolbars (ver CLAUDE.md).
- [ ] Los tests asociados pasan al 100 % y están en el commit.
- [ ] No se introducen imports de PyQt6 en módulos de `decoder/`, `fusion/`, `analysis/`.
- [ ] La Matriz de Trazabilidad está actualizada.

> **Brecha:** La revisión es hoy informal (no hay checklist formal ni registro de revisión). Para
> SWAL 2 se requiere evidencia de revisión independiente documentada.

---

## 8. Verificación de herramientas

Las herramientas de verificación (pytest, pytest-cov) son SOUP. Se documentan:

| Herramienta | Versión | Función | Calificación |
|---|---|---|---|
| pytest | ≥ 7 | Ejecución y reporte de tests | No calificada — resultado verificado manualmente |
| pytest-cov | pendiente | Cobertura estructural | No calificada — resultado a auditar |

Para SWAL 2, si los resultados de cobertura se usan como crédito de verificación, se requiere
justificación de adecuación de la herramienta (Tool Qualification Consideration — DO-278A §12.4).

---

## 9. Criterios de aprobación de verificación (SOI-2)

| Criterio | Estado actual |
|---|---|
| 100 % de tests pasan | ✅ (526/526) |
| Trazabilidad HLR ↔ test completa para SWAL 2 | ✅ HLR-HMI/PERF cubiertos (PERF-04/05 por verificación manual) |
| Cobertura de decisiones ≥ objetivo en módulos SWAL 2 | ❌ No medida (RNC-007: falta CI + `pytest-cov`) |
| Registros de revisión de código para módulos SWAL 2 | ❌ No existen |
| Resultados de verificación archivados y reproducibles | ❌ Solo ejecución local |

---

## 10. Registro de cambios

| Ver | Fecha | Cambio |
|-----|-------|--------|
| 0.1 | 2026-07-03 | Creación del borrador inicial. |
