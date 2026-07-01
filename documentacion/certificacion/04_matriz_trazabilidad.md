# Matriz de Trazabilidad — Requisitos ↔ Diseño ↔ Código ↔ Verificación

**Versión:** 0.1 (inicial/parcial). **Fecha:** 2026-06-28.

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
| REQ-DEC-5 | Gestión SAC/SIC de sensores | `decoder/sensor_registry.py` | ❌ (scripts `test_sac_sic.py` raíz) | ⚠️ Ad-hoc |
| REQ-GEO-1 | Proyección polar→WGS-84 | `projection.py`, `geo_utils.py` | `tests/geo/` | ⚠️ Indirecta |
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
| REQ-FUS-1 | Correlación multi-radar | `fusion/` | ❌ (`diag_fusion.py` ad-hoc) | ❌ Ausente |
| REQ-FUS-2 | Calibración/registración (solo rol técnico) | `fusion/` | ❌ | ❌ Ausente |
| REQ-ATM-1 | Base ATM read-only (aeropuertos/aerovías/fixes) | `player/atm_db.py`, `data/atm/` | `tests/atm/test_atm_db.py` | ✅ |
| REQ-ROL-1 | Roles operativos (controlador/técnico) | `player/profile_manager.py` | `tests/profiles/test_profile_manager.py` (8 casos) | ✅ |
| REQ-AUD-1 | Persistencia asíncrona de eventos safety | `storage/`, `safety_audit_dialog` | ❌ | ❌ Ausente |
| REQ-AUD-2 | Exportación CSV de eventos para informe OACI | `safety_audit_dialog`, `exporters.py` | ❌ | ❌ Ausente |
| REQ-FDP-1 | Parser ADEXP / FDP | `decoder/adexp_parser.py`, `player/fdp/` | `tests/fdp/test_adexp_parser.py`, `test_dispatcher.py`, `test_worker.py` | ✅ |
| REQ-CT-1 | Centro Técnico ATSEP (solo rol técnico) | `player/centro_tecnico/` | `tests/centro_tecnico/` | ✅ |
| REQ-STAT-1 | Métricas / cobertura / estadísticas | `analysis/`, `player/stats/` | `tests/stats/` | ✅ |

## 3. Huecos de trazabilidad críticos (acción)

| Hueco | Riesgo | Acción |
|-------|--------|--------|
| ~~STCA sin test automatizado (REQ-SN-1)~~ | ✅ **Cerrado** | Banco `tests/stca/` (27 casos). Pendiente: escenarios PCAP end-to-end y hallazgo STCA-1 |
| ~~Decodificadores CAT sin tests (REQ-DEC-1/2/3/4)~~ | ✅ **Cerrado** | `tests/decoders/` (91 casos: 46 CAT001/002/021/034 + 45 CAT048/062) |
| ~~Matching/reconciliación sin test (REQ-TRK-2)~~ | ✅ **Cerrado** | `tests/tracking/test_matching.py` (31 casos, pasos A–E + CAT62) |
| **Fusión sin test** (REQ-FUS-1/2) | Media (solo técnico) | Tests de correlación con pares de sensores |
| **Scripts ad-hoc en raíz** | Media — no son la suite | Migrar lo válido a `tests/`, descartar el resto |

## 4. Cobertura agregada (estimación cualitativa)

- **Bien cubierto:** STCA, MSAW, APW, ODS/HMI, firmap, geo-declinación, ATM-DB, FDP/ADEXP, stats, centro técnico, ciclo de vida.
- **Mal cubierto / sin cubrir:** decodificadores ASTERIX por categoría, matching de tracks, fusión, auditoría safety.

> Tras cerrar STCA, la prioridad #1 de verificación restante son los **decodificadores ASTERIX por
> categoría** (núcleo SWAL 2 sin tests) y el **matching/reconciliación de tracks**.
