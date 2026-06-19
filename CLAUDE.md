# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 🎯 Directivas de comportamiento (CRÍTICO)
- **Sé extremadamente conciso** (responde en español). Cero palabrería, sin saludos ni explicaciones obvias. Ve directo al código o a la respuesta.
- **Eficiencia:** No generes archivos de resumen `.md` ni comentes el código en exceso salvo que se pida explícitamente.
- **Límites:** Si un bug persiste o un test falla tras 2 intentos, DETENTE. Explica el bloqueo brevemente y espera instrucciones.
- **Scope:** Modifica estricta y únicamente los archivos necesarios. No hagas refactors no solicitados.

## Qué es
Decodificador ASTERIX (EUROCONTROL) + display radar PPI en tiempo real para control de tránsito aéreo (PyQt6). Decodifica CAT 001/002/010/020/021/034/048/062, convierte coordenadas polares→WGS-84, y pinta tracks sobre cartografía satelital/vectorial con redes de seguridad (STCA/APW/MSAW), fusión multi-radar y vista EUROCONTROL ODS.

## Ejecutar / probar (Windows)
El `.venv` del repo se creó bajo WSL y **NO funciona** en Windows nativo. Usar el Python nativo:
```
C:\Users\Usuario\AppData\Local\Programs\Python\Python312\python.exe
```
Tiene PyQt6, pyproj, duckdb, scapy instalados (`requirements.txt` está incompleto respecto a lo realmente usado).

- **App:** `python main.py` — **entry point canónico** (`player/main_window.py`). `main_pyqt.py` es **legacy monolítico**: no refleja los cambios de UI; nunca lanzarlo para validar.
- **Smoke test sin GUI:** `QT_QPA_PLATFORM=offscreen` + `PYTHONUTF8=1` (evita `UnicodeEncodeError` con emojis en cp1252). Para lanzar la GUI real en este entorno usar `QT_QPA_PLATFORM=windows` (hay un xcb de WSL que rompe el arranque por defecto).
- **Compilar un archivo:** `python -m py_compile player/main_window.py` (chequeo rápido antes de dar por hecho un cambio).
- **Feed en vivo:** UDP, puerto por defecto **20000** (`PlaybackWorker`, un socket por puerto = multi-sensor). Stress test desde `C:\Users\Usuario\Desktop\stress_tester.py` (puerto **8600**, `baires.pcap` ~296k paquetes en la raíz; aguanta ~5000 PPS).

## Tests
```
python -m pytest tests/                         # toda la suite
python -m pytest tests/atm/test_atm_db.py       # un archivo
python -m pytest tests/atm/test_atm_db.py::test_airways_clasificacion_excluyente   # un test
```
`tests/pytest.ini` usa `--import-mode=importlib`; `tests/conftest.py` inyecta la raíz al `sys.path`. Tests organizados por subsistema: `tests/{atm,areas,msaw,ods,tracking,geo,stats,firmap,centro_tecnico}`. Muchos dependen de `data/atm/atm.duckdb` (se saltan si no está). Los `test_*.py` sueltos en la raíz son scripts ad-hoc, no la suite.

## Arquitectura (big picture)
Separación estricta **núcleo agnóstico a Qt** ↔ **UI PyQt6**:

- **`decoder/`** — decodificación pura, sin Qt. `data_engine.py` (`DataEngine`, `AsterixPlot`) hace el trabajo pesado de PCAP/stream; `asterix_router.py` enruta por categoría; `decoders/` los parsers; `native_asterix.py` envuelve la extensión C (`asterix_decoder-0.7.4`); `altimetry.py` deriva el Nivel de Transición y el toggle A/F desde la TA del perfil + QNH manual; `sensor_registry.py` gestiona SAC/SIC.
- **`player/`** — toda la UI. `main_window.py` (`MainWindow`: menús, HUD, dock lateral, roles); `radar_widget.py` es el lienzo PPI (render acelerado, matching/reconciliación de tracks, cadena de safety-nets); `playback_worker.py` (`QThread` que decodifica PCAP o escucha UDP y emite `new_plot_batch`); diálogos (`*_dialog.py`), `map_manager.py`/`atm_maps.py`/`atm_db.py` (cartografía), `profile_manager.py` (perfiles/roles).
- **Subpaquetes de `player/`:** `areas/` (espacios restringidos + motor APW), `msaw/` (MSAW: zonas poligonales, supresión en aproximación), `ods/` (simbología y paleta EUROCONTROL ODS), `tracking/` (`lifecycle.py`: ciclo de vida monoradar), `firmap/` (vista FIR satelital), `centro_tecnico/` (Centro Técnico ATSEP, solo rol técnico), `stats/`.
- **`analysis/`** — coverage, `exporters.py` (KMZ/CSV/Parquet), `pass_analyzer.py`, `mode_analyzer.py`, `geo_math.py`, `filters.py`.
- **`fusion/`** — correlación multi-radar y calibración (registración); herramienta exclusiva del rol técnico.
- **`data/atm/atm.duckdb`** — base ATM **read-only** vía `player/atm_db.py`: aeropuertos, aerovías, procedimientos (SID/STAR/IAP), fixes, espacios restringidos (R/P/D) y parámetros MSAW. El esquema/seed está en `data/atm/atm_schema_duckdb.sql` y `atm_data_duckdb.sql`.

### Flujo de datos
PCAP o UDP → `DataEngine` decodifica y proyecta → batches de dicts de plot (`new_plot_batch`) → `radar_widget` matchea/reconcilia contra tracks vivos → `_schedule_safety()` corre la cadena **STCA → APW → MSAW** coalescida a ~1 Hz (gateada solo por los flags `*_habilitado`, no por `modo_integrado`) → repintado por batch del PPI.

### Roles operativos
`profile_manager.get_rol()` → `"controlador"` o `"tecnico"`. `MainWindow._aplicar_rol()` aplica los defaults: el **controlador** trabaja en vivo (UDP, vista ODS limpia, sin playback, UI reducida); el **técnico** tiene acceso completo (playback PCAP, Centro Técnico ATSEP, calibración/fusión, exportación). Perfiles en `profiles/*.json` y `config/profile.json`.

### Ciclo de vida de tracks (determinista)
El ciclo de vida (`player/tracking/lifecycle.py`) se gobierna **exclusivamente por el ToD de ASTERIX**; `time.time()` está vedado en el motor de ciclo de vida para que el comportamiento sea reproducible en playback. El reloj de simulación avanza con cada plot procesado.

### Cartografía
El loader de mapas personalizados (`DxfLoaderThread`) sólo entiende **GeoJSON** con geometrías `LineString` y `Point` (coords `[lon, lat]`). El formato legacy `.map` (coordenadas DMS, `Circumference`/`Arc`/`Polyline`/`Polygon`) se convierte con `tools/map_to_geojson.py`. Las opciones de capas viven en el menú **Mapas**.

## Convenciones
- Comentarios y mensajes de UI en **español**; los commits siguen Conventional Commits con scope (ej. `fix(tracking): …`).
- Para ocultar/mostrar un widget dentro de un `QToolBar`, togglear la **acción** que devuelve `addWidget()` (`action.setVisible(...)`), no `widget.setVisible()` — este último no funciona dentro de toolbars en Qt.
