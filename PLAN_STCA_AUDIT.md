# Plan: Persistencia de Eventos Safety + Módulo de Auditoría OACI

**Branch objetivo:** `feature/safety-audit`  
**Módulos afectados:** `storage/duckdb_repo.py`, `player/radar_widget.py`, nuevo `player/safety_audit_dialog.py`

---

## Contexto y punto de enganche

El sistema ya tiene todo el trabajo duro hecho:

- `_publicar_eventos_safety(subsistema, eventos)` en `radar_widget.py:2505` **ya detecta transiciones ONSET** (claves que aparecen en `actuales - prev`). Solo falta detectar también las CLEAR y escribir ambas a DuckDB.
- `SimulationTime.time()` es el reloj correcto — coherente con el ToD de ASTERIX, reproducible en playback.
- `DuckDBRepository` ya tiene el patrón de cola asíncrona (`cola_insercion` + hilo worker) — se extiende sin tocar la lógica de `asterix_plots`.

---

## Fase A — Tabla `safety_events` en DuckDBRepository

**Archivo:** `storage/duckdb_repo.py`

### 1. Agregar la tabla al schema inicial

En `_inicializar_esquema()`, agregar después de `asterix_plots`:

```python
self.conn.execute('''
    CREATE TABLE IF NOT EXISTS safety_events (
        id          INTEGER PRIMARY KEY,
        ts          DOUBLE NOT NULL,        -- SimulationTime.time() (ToD ASTERIX)
        ts_wall     DOUBLE NOT NULL,        -- time.time() (para correlación con logs)
        subsistema  VARCHAR NOT NULL,       -- 'STCA' | 'APW' | 'MSAW'
        transicion  VARCHAR NOT NULL,       -- 'ONSET' | 'CLEAR'
        clave       VARCHAR NOT NULL,       -- clave estable del evento (track1__track2 o track__zona)
        nivel       VARCHAR,               -- 'CRITICAL' | 'WARNING'
        origen      VARCHAR,               -- origen descriptivo
        descripcion VARCHAR,               -- texto completo del evento
        sesion_id   VARCHAR                -- identificador de la sesión (pcap filename o 'LIVE')
    )
''')
self.conn.execute(
    "CREATE SEQUENCE IF NOT EXISTS safety_events_seq START 1"
)
```

> **Nota:** No se hace DROP en `safety_events` (a diferencia de `asterix_plots`) — los eventos históricos se acumulan entre sesiones.

### 2. Método `guardar_evento_safety()`

```python
def guardar_evento_safety(self, ts: float, ts_wall: float, subsistema: str,
                           transicion: str, clave: str, nivel: str,
                           origen: str, descripcion: str, sesion_id: str = ""):
    """No bloqueante: encola el evento para escritura asíncrona."""
    if self._running:
        self.cola_insercion.put({
            "_type": "safety_event",
            "ts": ts, "ts_wall": ts_wall,
            "subsistema": subsistema, "transicion": transicion,
            "clave": clave, "nivel": nivel, "origen": origen,
            "descripcion": descripcion, "sesion_id": sesion_id
        })
```

### 3. Extender `_procesar_lotes()` para despachar eventos safety

En el loop del worker, distinguir por `_type`:

```python
if isinstance(item, dict) and item.get("_type") == "safety_event":
    conn.execute("""
        INSERT INTO safety_events
            (id, ts, ts_wall, subsistema, transicion, clave,
             nivel, origen, descripcion, sesion_id)
        VALUES (nextval('safety_events_seq'), ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, [item["ts"], item["ts_wall"], item["subsistema"], item["transicion"],
          item["clave"], item["nivel"], item["origen"],
          item["descripcion"], item["sesion_id"]])
```

**Criterio de completitud:** Tras una sesión de playback, `SELECT COUNT(*) FROM safety_events` devuelve > 0 y los timestamps son coherentes con el PCAP.

---

## Fase B — Hook en `_publicar_eventos_safety()`

**Archivo:** `player/radar_widget.py:2505`

Extender el método para detectar **ONSET** y **CLEAR** y escribir a DuckDB:

```python
def _publicar_eventos_safety(self, subsistema: str, eventos: dict):
    bus = getattr(self, 'system_bus', None)
    repo = getattr(self, '_repo_db', None)  # DuckDBRepository inyectado desde MainWindow

    prev = self._safety_eventos_prev.get(subsistema, set())
    actuales = set(eventos)

    import time as _time
    ts_sim  = SimulationTime.time()
    ts_wall = _time.time()
    sesion  = getattr(self, '_sesion_id', 'LIVE')

    # ONSET: claves que aparecen ahora y no estaban antes
    for clave in actuales - prev:
        nivel, origen, desc = eventos[clave]
        if bus:
            bus.inyectar(nivel, origen, desc)
        if repo:
            repo.guardar_evento_safety(
                ts_sim, ts_wall, subsistema, 'ONSET',
                str(clave), nivel, origen, desc, sesion)

    # CLEAR: claves que desaparecen
    if repo:
        for clave in prev - actuales:
            nivel, origen, desc = self._safety_eventos_prev_data \
                                    .get(subsistema, {}).get(clave, ("INFO", subsistema, ""))
            repo.guardar_evento_safety(
                ts_sim, ts_wall, subsistema, 'CLEAR',
                str(clave), nivel, origen, desc, sesion)

    # Guardar datos completos del ciclo anterior para el CLEAR
    if not hasattr(self, '_safety_eventos_prev_data'):
        self._safety_eventos_prev_data = {}
    self._safety_eventos_prev_data[subsistema] = {k: v for k, v in eventos.items()}

    self._safety_eventos_prev[subsistema] = actuales
```

### Inyección de `_repo_db` y `_sesion_id`

En `MainWindow`, cuando se conecta el worker al radar_widget:

```python
# Al arrancar una sesión PCAP o en vivo:
self.radar_widget._repo_db = worker.repo_db          # ya existe en el worker
self.radar_widget._sesion_id = Path(pcap_path).name  # o 'LIVE'
```

**Criterio de completitud:** Eventos ONSET y CLEAR aparecen en la tabla con timestamps correctos; VIOLATION y PREDICTION de STCA se diferencian en `nivel`/`descripcion`.

---

## Fase C — Diálogo de Auditoría

**Archivo nuevo:** `player/safety_audit_dialog.py`

### Funcionalidad

Ventana modal (rol `tecnico`) con tres secciones:

```
┌─────────────────────────────────────────────────────────┐
│  Filtros: [Subsistema ▼] [Sesión ▼] [Desde HH:MM] [Hasta HH:MM] [Buscar]
├─────────────────────────────────────────────────────────┤
│  Tabla: ts | subsistema | transición | descripción | duración
│  (ordenada por ts, resalta VIOLATION en rojo, PREDICTION en amarillo)
├─────────────────────────────────────────────────────────┤
│  [Ir al instante en Reproductor]  [Exportar CSV]  [Cerrar]
└─────────────────────────────────────────────────────────┘
```

### Query base

```sql
SELECT
    ts,
    subsistema,
    transicion,
    nivel,
    descripcion,
    sesion_id,
    -- Duración: segundos hasta el CLEAR correspondiente (o NULL si sigue activo)
    LEAD(ts) FILTER (WHERE transicion = 'CLEAR')
        OVER (PARTITION BY subsistema, clave ORDER BY ts) - ts AS duracion_s
FROM safety_events
WHERE subsistema = ? AND sesion_id = ?
  AND ts BETWEEN ? AND ?
ORDER BY ts DESC
```

### Señal para seek en reproductor

```python
seek_to_ts = pyqtSignal(float)   # emite ts de la fila seleccionada → MainWindow.seek_to()
```

En `MainWindow`:
```python
self.audit_dialog.seek_to_ts.connect(self._seek_playback_to)
```

**Criterio de completitud:** Seleccionar una fila y hacer clic en "Ir al instante" posiciona el slider del reproductor en el momento del evento y reactiva los safety-nets.

---

## Fase D — Exportación para Informe OACI

**Archivo:** `analysis/exporters.py` (método adicional)

```python
def export_safety_events_csv(self, output_path: str, sesion_id: str = None) -> bool:
    """
    Exporta safety_events a CSV con columnas legibles para informe OACI/ATSEP.
    Columnas: fecha_hora_utc, subsistema, aeronave_1, aeronave_2, tipo_alerta,
              duracion_s, dist_horizontal_nm (extraída de descripcion).
    """
```

Accesible desde **Exportar → Eventos de Seguridad (CSV)** en el menú principal (solo rol `tecnico`).

**Criterio de completitud:** CSV abre en Excel con columnas legibles y timestamps en formato ISO 8601 UTC.

---

## Orden de implementación

```
A (schema + guardar_evento_safety) → B (hook _publicar_eventos_safety) → C (diálogo) → D (exportación)
```

Fases A y B no tocan Qt — se pueden probar con un test de integración que corre un PCAP headless y verifica `SELECT COUNT(*) FROM safety_events WHERE transicion='ONSET'`.

---

## Archivos a modificar / crear

| Archivo | Tipo de cambio |
|---|---|
| `storage/duckdb_repo.py` | Agregar tabla + método (Fase A) |
| `player/radar_widget.py` | Extender `_publicar_eventos_safety` (Fase B) |
| `player/main_window.py` | Inyectar `_repo_db` + `_sesion_id`; conectar señal seek; menú Auditoría |
| `player/safety_audit_dialog.py` | Nuevo (Fase C) |
| `analysis/exporters.py` | Nuevo método (Fase D) |
| `tests/tracking/test_safety_persistence.py` | Test de integración headless |

---

## Decisiones y riesgos

| Punto | Decisión |
|---|---|
| `safety_events` NO se borra entre sesiones | Permite comparar incidentes históricos. Limpiar manualmente o con botón en el diálogo. |
| El `_repo_db` puede ser `None` (sesión sin DuckDB) | Fase B ya guarda con `if repo:` — sin crash |
| Duraciones correctas solo si la sesión completa está en la BD | En sesiones cortadas, `duracion_s` queda NULL — aceptable para auditoría |
| STCA en modo multi-sensor desactivado | Los eventos se registran como CLEAR masivo — queda trazabilidad de cuándo se desactivó |

---

*Generado: 2026-06-25*
