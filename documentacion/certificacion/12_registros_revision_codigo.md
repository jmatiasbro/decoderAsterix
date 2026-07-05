# Registros de Revisión de Código — Módulos SWAL 2

**Sistema:** Decodificador ASTERIX + Display PPI ATC.
**Norma:** EUROCAE ED-109A / RTCA DO-278A — Verificación (revisión de código fuente).
**Versión:** 0.1. **Fecha:** 2026-07-05. **Estado:** PROPUESTO — no aprobado por ANAC.

> Cierra **RNC-008** (ausencia de registros de revisión de código para módulos SWAL 2).
> Alcance: las unidades de seguridad (redes de seguridad, ciclo de vida y correlación),
> las mismas sobre las que se mide cobertura de decisiones (ver [09_SVP.md](09_SVP.md) §4.4).

---

## 1. Alcance y método

Se revisan por inspección estructurada los módulos SWAL 2:

| Módulo | Función |
|--------|---------|
| `analysis/stca_analyzer.py` | Motor STCA (conflicto de separación). |
| `player/areas/apw.py` | Motor APW (proximidad/penetración de área). |
| `player/msaw/engine.py` | Motor MSAW (altitud mínima de seguridad). |
| `player/tracking/lifecycle.py` | Ciclo de vida de pista monoradar (determinista). |
| `fusion/correlator.py` | Correlación multi-radar (identidad de aeronave). |

### 1.1 Independencia

La revisión la realiza el mismo autor del código (**brecha declarada RNC-006**, pendiente de
acuerdo con ANAC). Mitigaciones: lista de comprobación objetiva (§2), cobertura de decisiones
≥ 80 % verificada, y registro trazable de hallazgos y disposición (§3).

## 2. Lista de comprobación (criterios)

| Id | Criterio |
|----|----------|
| CR-1 | **Agnóstico a Qt**: el motor es testeable headless (sin GUI). |
| CR-2 | **Determinismo**: sin `time.time()` en la lógica de decisión; temporización por ToD. |
| CR-3 | **Robustez de entrada**: validación/coerción de tipos; tolerante a campos ausentes. |
| CR-4 | **Trazabilidad**: el módulo traza a un HLR/requisito de la SRS y a la FHA. |
| CR-5 | **Verificación**: cobertura de decisiones adecuada y casos de borde probados. |
| CR-6 | **Manejo de errores**: los fallos no se descartan en silencio. |
| CR-7 | **Constantes**: los números mágicos están documentados o nombrados. |
| CR-8 | **Legibilidad/complejidad**: funciones acotadas, intención clara. |

Disposición de cada hallazgo: **Aceptado** (sin acción), **Aceptado con nota** (mejora futura
registrada), o **Corregido** (con referencia al commit).

---

## 3. Registros de revisión

### RR-01 — `analysis/stca_analyzer.py` (STCA)

- **Revisado:** commit de la baseline `v0.3.0`. **Cobertura:** 100 % (branch).
- **Verificación asociada:** `tests/stca/test_stca_engine.py` (27) + `test_stca_scenarios.py` (7).

| Criterio | Resultado |
|----------|-----------|
| CR-1 Agnóstico a Qt | ✅ Sin imports de Qt. |
| CR-2 Determinismo | ✅ Geometría pura; sin reloj de pared. |
| CR-3 Robustez | ✅ Filtros de banda FL, velocidad y `isdigit()` antes de convertir. |
| CR-4 Trazabilidad | ✅ REQ-SN-1 / HLR-STCA-01 / SSR-07 / FC-STCA-01. |
| CR-5 Verificación | ✅ 34 casos (unitarios + escenarios end-to-end). |
| CR-6 Errores | ✅ Sin except silenciosos. |
| CR-7 Constantes | ✅ Umbrales nombrados (`min_horizontal_nm`, `min_vertical_ft`, `fl_min/max`). |
| CR-8 Complejidad | ⚠️ Doble bucle O(N²) sobre pares (aceptable a densidad operativa). |

**Hallazgos:**
- **H-01 (STCA-1, ya registrado):** doble marco de coordenadas — VIOLATION con `lat_render`
  (haversine), PREDICTION con `x/y` suavizado. **Disposición: Aceptado con nota** — riesgo acotado
  (VIOLATION siempre dispara para conflicto real <10 NM, ver gap analysis y `test_stca_scenarios`);
  requisito SRS de marco único pendiente.

### RR-02 — `player/areas/apw.py` (APW)

- **Revisado:** `v0.3.0`. **Cobertura:** 85 % (branch). **Verificación:** `tests/areas/test_apw.py`, `test_integration.py`.

| Criterio | Resultado |
|----------|-----------|
| CR-1 Agnóstico a Qt | ✅ |
| CR-2 Determinismo | ✅ `ahora: datetime` proviene del caller (vigencia de área), no de la lógica de track. |
| CR-3 Robustez | ✅ Soporta track objeto o dict; valida/coerciona FL, lat/lon, vx/vy. |
| CR-4 Trazabilidad | ✅ REQ-SN-2 / FC-APW-01. |
| CR-5 Verificación | ✅ Penetración inmediata y predicción. |
| CR-6 Errores | ✅ `try/except` acotado a coerción de tipo (no traga lógica). |
| CR-7 Constantes | ✅ `lead_s=120` nombrado; `111120.0` m/° documentado. |
| CR-8 Complejidad | ⚠️ Predicción paso a paso 1 s hasta `limit_s` (≤120 iter) por track×área. |

**Hallazgos:**
- **H-02:** el bucle de predicción es O(`limit_s`) por track y área, acotado por el prefiltro de
  bounding box. **Disposición: Aceptado** — coste acotado y prefiltrado; sin impacto a densidad real.
- **H-03:** `predecir_posicion` usa aproximación de tierra plana (111120 m/°). **Disposición: Aceptado**
  — error despreciable en el horizonte de 120 s a velocidades típicas.

### RR-03 — `player/msaw/engine.py` (MSAW)

- **Revisado:** `v0.3.0`. **Cobertura:** 86 % (branch). **Verificación:** `tests/msaw/test_engine.py`, `test_suppression.py`.

| Criterio | Resultado |
|----------|-----------|
| CR-1 Agnóstico a Qt | ✅ |
| CR-2 Determinismo | ✅ |
| CR-3 Robustez | ✅ Reusa helpers de `apw.py` (DRY); valida tipos; categorías exentas. |
| CR-4 Trazabilidad | ✅ REQ-SN-3/4 / FC-MSAW. |
| CR-5 Verificación | ✅ Violación, predicción de descenso y supresión en aproximación. |
| CR-6 Errores | ✅ Coerción acotada. |
| CR-7 Constantes | ✅ `time_to_prediction` parametrizado. |
| CR-8 Complejidad | ✅ Clara; reutiliza el motor de predicción. |

**Hallazgos:**
- **H-04:** `alt_ft = FL*100` es una aproximación (presión ≈ QNH cerca de la TA); por debajo de la TA,
  con QNH distinto del estándar, la altitud real puede divergir. **Disposición: Aceptado con nota** —
  documentado en el módulo; mejora futura: derivar altitud con QNH bajo la TA (coherente con el toggle
  A/F de `decoder/altimetry.py`).
- **H-05 (cosmético):** en la alerta PREDICTED, el campo `alt_ft` reporta la altitud **actual**, no la
  proyectada; `msa_ft` y `eta_s` sí son del punto proyectado. **Disposición: Aceptado con nota** — no
  afecta la decisión de alerta; alinear el campo informado en una futura edición.

### RR-04 — `player/tracking/lifecycle.py` (ciclo de vida)

- **Revisado:** `v0.3.0`. **Cobertura:** 92 % (branch). **Verificación:** `tests/tracking/test_lifecycle.py`.

| Criterio | Resultado |
|----------|-----------|
| CR-1 Agnóstico a Qt | ✅ Explícitamente headless. |
| CR-2 Determinismo | ✅ Gobernado por ToD; `time.time()` vedado por diseño. |
| CR-3 Robustez | ✅ Conteo por tiempo transcurrido (robusto a saltos de ToD y fuera de orden). |
| CR-4 Trazabilidad | ✅ REQ-TRK-1 / FC-LIF-02. |
| CR-5 Verificación | ✅ Confirmación M-de-N, coasting y borrado. |
| CR-6 Errores | ✅ Sin except silenciosos. |
| CR-7 Constantes | ⚠️ Fallback de período `4.0 s` embebido (documentado). |
| CR-8 Complejidad | ✅ `__slots__`, funciones cortas, intención clara. |

**Hallazgos:**
- **H-06:** `identidad_codigo` para SSR usa el squawk como clave; dos aeronaves con el mismo Modo 3/A
  discreto en el mismo sensor colapsarían. **Disposición: Aceptado** — condición operativamente rara
  (código duplicado no asignado), acotada al ciclo monoradar; la fusión multi-radar usa Mode-S.

### RR-05 — `fusion/correlator.py` (correlación)

- **Revisado:** `v0.3.0`. **Cobertura:** 100 % (branch). **Verificación:** `tests/fusion_tests/test_correlator.py` (26).

| Criterio | Resultado |
|----------|-----------|
| CR-1 Agnóstico a Qt | ✅ |
| CR-2 Determinismo | ✅ `now_fn` inyectable (usa el reloj de simulación en el widget). |
| CR-3 Robustez | ✅ Identidades no contradictorias antes de fusionar; gate de distancia. |
| CR-4 Trazabilidad | ✅ REQ-FUS-1/2. |
| CR-5 Verificación | ✅ Claves de identidad, extrapolación y asociación aprendida. |
| CR-6 Errores | ✅ |
| CR-7 Constantes | ✅ Gates configurables (`gate_estricto_nm`, `gate_asociado_nm`, `assoc_ttl_s`). |
| CR-8 Complejidad | ✅ Política conservadora (preferir duplicado a fusión errónea). |

**Hallazgos:**
- Sin hallazgos. La política conservadora es la correcta para seguridad (una fusión errónea ocultaría
  tráfico/STCA; ver análisis en [09_SVP.md](09_SVP.md) §5.4, Hallazgo 2).

---

## 4. Resumen y disposición

| Registro | Módulo | Hallazgos | Abiertos |
|----------|--------|-----------|----------|
| RR-01 | STCA | H-01 (STCA-1) | Ligado a STCA-1 (SRS) |
| RR-02 | APW | H-02, H-03 | 0 (aceptados) |
| RR-03 | MSAW | H-04, H-05 | 0 (aceptados con nota) |
| RR-04 | Lifecycle | H-06 | 0 (aceptado) |
| RR-05 | Correlator | — | 0 |

Ningún hallazgo es de Clase A. Los hallazgos con nota (H-04, H-05) se listan como mejoras futuras;
H-01 queda ligado al cierre de STCA-1 vía requisito SRS.

## 5. Registro de cambios

| Ver | Fecha | Cambio |
|-----|-------|--------|
| 0.1 | 2026-07-05 | Emisión inicial: revisión de los 5 módulos SWAL 2. |
