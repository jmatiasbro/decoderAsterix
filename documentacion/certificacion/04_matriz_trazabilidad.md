# Matriz de Trazabilidad — Requisitos ↔ Diseño ↔ Código ↔ Verificación

**Versión:** 0.2 (parcial). **Fecha:** 2026-07-04.

> Trazabilidad bidireccional exigida por DO-278A (requisito → diseño → código → caso de prueba, y a la
> inversa). Esta versión es un **punto de partida**: aún **no existe un SRS**, por lo que los
> "requisitos" listados son **derivados** (reconstruidos a partir de las specs ASTERIX, el CONOPS
> implícito y la suite de tests existente). Deben formalizarse en un SRS antes de usarse como evidencia.

---

## 1. Convención de identificadores

- `REQ-<SUBSISTEMA>-<n>` — requisito derivado (provisional).
- Código: ruta de archivo del repositorio.
- Verificación: archivo bajo `tests/` o ❌ si no hay prueba automatizada.

## 2. Matriz

| Req (derivado) | Descripción | Diseño / Código | Verificación | Cobertura |
|----------------|-------------|-----------------|--------------|-----------|
| REQ-DEC-1 | Decodificar CAT 048 (target reports monoradar) | `decoder/decoders/cat048.py` | `tests/decoders/test_cat048_062.py` (26 casos) | ✅ |
| REQ-DEC-2 | Decodificar CAT 062 (system tracks) | `decoder/decoders/cat062.py`, `decoder/native_asterix.py` | `tests/decoders/test_cat048_062.py` (19 casos) | ✅ |
| REQ-DEC-3 | Decodificar CAT 021 (ADS-B) v2.4 y v0.26 | `decoder/decoders/cat021.py` | `tests/decoders/test_decoders_asterix.py` (14 casos) | ✅ |
| REQ-DEC-4 | Decodificar CAT 001/002/034 | `decoder/decoders/cat001.py`, `cat002.py`, `cat034.py` | `tests/decoders/test_decoders_asterix.py` (32 casos) | ✅ |
| REQ-DEC-5 | Gestión SAC/SIC de sensores | `decoder/sensor_registry.py` | `tests/decoders/test_sensor_registry.py` (11 casos) | ✅ |
| REQ-GEO-1 | Proyección polar→WGS-84 | `utils/geo.py` (`StereographicLocal`) | `tests/geo/test_stereographic.py` (11 casos) | ✅ |
| REQ-GEO-2 | Declinación magnética offline | `player/` (capa isogónica) | `tests/geo/test_isogonic*.py`, `test_magnetic_cascade.py` | ✅ |
| REQ-TRK-1 | Ciclo de vida monoradar determinista (ToD) | `player/tracking/lifecycle.py` | `tests/tracking/test_lifecycle.py` | ✅ |
| REQ-TRK-2 | Matching/reconciliación de tracks | `player/radar_widget.py` (`_process_plot_data`, pasos A–E) | `tests/tracking/test_matching.py` (31 casos) | ✅ |
| REQ-SN-1 | STCA — alerta de conflicto a corto plazo | `analysis/stca_analyzer.py` (`STCA_Engine`), cadena safety en `radar_widget` | `tests/stca/test_stca_engine.py` (27 casos) | ✅ |
| REQ-SN-2 | APW — alerta de penetración de área | `player/areas/` | `tests/areas/test_apw.py`, `test_integration.py` | ✅ |
| REQ-SN-3 | MSAW — alerta de altitud mínima de seguridad | `player/msaw/` | `tests/msaw/test_engine.py`, `test_suppression.py`, etc. | ✅ |
| REQ-SN-4 | Supresión MSAW en aproximación | `player/msaw/` | `tests/msaw/test_suppression.py` | ✅ |
| REQ-HMI-1 | Presentación PPI EUROCONTROL ODS | `radar_widget.py`, `player/ods/` | `tests/ods/test_symbology.py`, `test_palette.py`, `test_fdb.py` | ✅ |
| REQ-HMI-2 | Declutter / niveles de información | `player/ods/` | `tests/ods/test_declutter.py` | ✅ |
| REQ-HMI-3 | Estado de track (símbolo según calidad) | `player/ods/` | `tests/ods/test_track_state.py` | ✅ |
| REQ-HMI-4 | Vista FIR satelital | `player/firmap/` | `tests/firmap/` | ✅ |
| REQ-HMI-5 | Completitud de presentación (ningún track activo omitido) y fidelidad de etiqueta (callsign/Mode3A/FL) | `radar_widget.py` (`_draw_oaci_track`, `is_alive`) | `tests/tracking/test_hmi.py` (17 casos, HLR-HMI-01/02/03) | ✅ |
| REQ-HMI-6 | Estado de track por calidad (coasting / Mode-S / ADS-B) | `radar_widget.py` (`RadarPlot.is_coasting`), `player/ods/track_state.py` | `tests/tracking/test_track_state.py` (12 casos, HLR-HMI-04) | ✅ |
| REQ-HMI-7 | Watchdog de cadena de safety-nets (alerta si sin salida > 5 s) | `radar_widget.py` (`_check_safety_watchdog`, `_watchdog_timer`) | `tests/tracking/test_safety_watchdog.py` (5 casos, HLR-HMI-06) | ✅ |
| REQ-PERF-1 | Cotas de rendimiento del motor (latencia de lote, cadencia safety, 500 tracks) | `radar_widget.py`, `player/playback_worker.py` | `tests/tracking/test_perf.py` (6 casos, HLR-PERF-01/02/03) | ✅ |
| REQ-PERF-2 | Refresco PPI e ingesta sostenible (HLR-PERF-04/05) | `radar_widget.py` (cache de mapa de fondo), `player/playback_worker.py` | Manual: [09_SVP.md](09_SVP.md) §5.4 — banco de estrés UDP, 800 PPS verificados | ✅ (manual) |
| REQ-FUS-1 | Correlación multi-radar | `fusion/correlator.py` | `tests/fusion_tests/test_correlator.py` (26 casos) | ✅ |
| REQ-FUS-2 | Calibración/registración (solo rol técnico) | `fusion/correlator.py` | `tests/fusion_tests/test_correlator.py` (claves, extrapolación, asociación) | ✅ |
| REQ-ATM-1 | Base ATM read-only (aeropuertos/aerovías/fixes) | `player/atm_db.py`, `data/atm/` | `tests/atm/test_atm_db.py` | ✅ |
| REQ-ROL-1 | Roles operativos (controlador/técnico) | `player/profile_manager.py` | `tests/profiles/test_profile_manager.py` (8 casos) | ✅ |
| REQ-AUD-1 | Persistencia asíncrona de eventos safety | `storage/duckdb_repo.py` | `tests/storage_tests/test_safety_audit.py` (9 casos) | ✅ |
| REQ-AUD-2 | Exportación CSV de eventos para informe OACI | `analysis/exporters.py` (`PassExporter`) | `tests/storage_tests/test_safety_audit.py` (8 casos CSV) | ✅ |
| REQ-FDP-1 | Parser ADEXP / FDP | `decoder/adexp_parser.py`, `player/fdp/` | `tests/fdp/test_adexp_parser.py`, `test_dispatcher.py`, `test_worker.py` | ✅ |
| REQ-CT-1 | Centro Técnico ATSEP (solo rol técnico) | `player/centro_tecnico/` | `tests/centro_tecnico/` | ✅ |
| REQ-STAT-1 | Métricas / cobertura / estadísticas | `analysis/`, `player/stats/` | `tests/stats/` | ✅ |

## 3. Huecos de trazabilidad críticos (acción)

| Hueco | Riesgo | Acción |
|-------|--------|--------|
| ~~STCA sin test automatizado (REQ-SN-1)~~ | ✅ **Cerrado** | Banco `tests/stca/` (27 unitarios del motor + 7 escenarios end-to-end por el pipeline del widget) |
| ~~Decodificadores CAT sin tests (REQ-DEC-1/2/3/4)~~ | ✅ **Cerrado** | `tests/decoders/` (91 casos: 46 CAT001/002/021/034 + 45 CAT048/062) |
| ~~Matching/reconciliación sin test (REQ-TRK-2)~~ | ✅ **Cerrado** | `tests/tracking/test_matching.py` (31 casos, pasos A–E + CAT62) |
| ~~**Fusión sin test** (REQ-FUS-1/2)~~ | ✅ **Cerrado** | `tests/fusion_tests/test_correlator.py` (26 casos) |
| ~~HMI sin test de completitud/fidelidad/watchdog (HLR-HMI-01..06)~~ | ✅ **Cerrado** | `tests/tracking/test_hmi.py`, `test_track_state.py`, `test_safety_watchdog.py` (34 casos) |
| ~~Rendimiento sin verificación (HLR-PERF-01..05)~~ | ✅ **Cerrado** | `tests/tracking/test_perf.py` (6 casos) + verificación manual SVP §5.4 (800 PPS) |
| ~~Integración end-to-end PCAP sin test~~ | ✅ **Cerrado** | `tests/integration/test_pcap_e2e.py` (6 casos: decode→proyección→matching→safety sobre `cat_034_048.pcap`) |
| ~~Escenarios end-to-end STCA (hallazgo STCA-1)~~ | ✅ **Cerrado** | `tests/stca/test_stca_scenarios.py` (7 escenarios por el pipeline: VIOLATION, sep. vertical/horizontal, misma aeronave, estáticos, banda FL, inhibición). Documenta que un conflicto real <10 NM siempre dispara |
| **Scripts ad-hoc en raíz** | Media — no son la suite | Migrar lo válido a `tests/`, descartar el resto |

## 4. Cobertura agregada (estimación cualitativa)

- **Bien cubierto:** STCA, MSAW, APW, ODS/HMI, firmap, geo-declinación, ATM-DB, FDP/ADEXP, stats, centro técnico, ciclo de vida, decodificadores CAT001/002/021/034/048/062, matching A–E, correlación multi-radar, auditoría safety, completitud/fidelidad HMI + watchdog (HLR-HMI-01..06), rendimiento del motor + capacidad de ingesta verificada (HLR-PERF-01..05).
- **Sin cubrir:** purga de binarios del histórico git.

> Tras cerrar STCA, la prioridad #1 de verificación restante son los **decodificadores ASTERIX por
> categoría** (núcleo SWAL 2 sin tests) y el **matching/reconciliación de tracks**.
