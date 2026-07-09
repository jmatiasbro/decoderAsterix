# Plan: Motor FDP + Parser ADEXP (EUROCONTROL SPEC-107 Ed. 3.3)

**Branch objetivo:** `feature/fdp-adexp`  
**Referencia normativa:** `documentacion/035904_Markdown_6a2db688d822e.md`

---

## Arquitectura objetivo

```
FdpWorker (QThread TCP)          ← nuevo: player/fdp/worker.py
    └─→ AdexpLexer               ← nuevo: decoder/adexp_parser.py
         └─→ FdpDispatcher       ← nuevo: player/fdp/dispatcher.py
              └─→ fdp.duckdb     ← nuevo: data/fdp/fdp.duckdb (escribible, separado de atm.duckdb)
              └─→ señal Qt       → MainWindow (opcional, Fase E)
```

Separación estricta igual que el resto del proyecto: `decoder/` sin Qt, `player/` con Qt.

---

## Fase A — Schema DuckDB (fdp.duckdb)

**Archivo:** `data/fdp/fdp_schema.sql` + script de inicialización `tools/init_fdp_db.py`

Tabla principal:

```sql
CREATE TABLE IF NOT EXISTS flight_plans (
    arcid        TEXT PRIMARY KEY,
    adep         TEXT,
    ades         TEXT,
    aircraft_type TEXT,
    wtc          TEXT,          -- Wake Turbulence Category (L/M/H/J)
    requested_fl TEXT,
    route        TEXT,
    eobt         TEXT,          -- Estimated Off-Block Time (HHMM)
    cop          TEXT,          -- Coordination Point
    status       TEXT DEFAULT 'ACTIVE',  -- ACTIVE | CANCELLED | CLOSED
    raw_msg      TEXT,          -- trama original para auditoría
    created_at   TIMESTAMP DEFAULT current_timestamp,
    updated_at   TIMESTAMP DEFAULT current_timestamp
);

CREATE TABLE IF NOT EXISTS fdp_log (
    id           INTEGER PRIMARY KEY,
    ts           TIMESTAMP DEFAULT current_timestamp,
    msg_type     TEXT,
    arcid        TEXT,
    raw          TEXT
);
```

**Criterio de completitud:** `python tools/init_fdp_db.py` crea `data/fdp/fdp.duckdb` sin errores.

---

## Fase B — AdexpLexer (parser regex)

**Archivo:** `decoder/adexp_parser.py`

### Diseño

1. **Pre-proceso de campos lista**: extraer y descartar (o preservar aparte) bloques `-BEGIN X ... -END X` antes de parsear con regex, para evitar que los keywords internos contaminen el resultado.
2. **Regex principal** (con `re.DOTALL`):

```python
REGEX_ADEXP = re.compile(
    r"-([A-Z0-9]+)[ \t\r\n]+(.*?)(?=[ \t\r\n]-[A-Z0-9]+[ \t\r\n]|$)",
    re.DOTALL
)
```

3. **Extracción de EQPT**: `B738/M-SDE1FGHIRWXY` → `aircraft_type=B738`, `wtc=M`
4. **Campos a extraer** para los 4 tipos de mensaje:
   - `TITLE`, `ARCID`, `ADEP`, `ADES`, `RFL`, `ROUTE`, `EOBT`, `EQPT`, `COP`, `ARCTYP`

### Contrato de `parsear_trama(msg: str) -> dict`

- Entrada: trama ADEXP cruda (puede tener `\r\n` o `\n`)
- Salida: dict con claves en mayúsculas, valores limpios (sin saltos de línea internos)
- Listas (`-BEGIN/-END`): guardadas como string crudo en clave `_LIST_<nombre>`

**Criterio de completitud:** tests en `tests/fdp/test_adexp_parser.py` con tramas FPL, CHG, CNL, EST reales (incluyendo rutas con guiones tipo `DCT LAMDO-M301`).

---

## Fase C — FdpDispatcher

**Archivo:** `player/fdp/dispatcher.py`

### Métodos

| Método | Mensaje ADEXP | Operación DB |
|---|---|---|
| `_upsert_flight_plan(data)` | FPL, EST | INSERT OR REPLACE en `flight_plans` |
| `_update_flight_plan(data)` | CHG | UPDATE dinámico solo de los campos presentes |
| `_cancel_flight_plan(arcid)` | CNL | UPDATE status='CANCELLED' |
| `_log(msg_type, arcid, raw)` | siempre | INSERT en `fdp_log` |

### CHG dinámico (crítico)

El CHG puede traer solo 1-2 campos. Construir el SET dinámicamente:

```python
CAMPO_A_COLUMNA = {'RFL': 'requested_fl', 'ROUTE': 'route', 'ADES': 'ades', ...}
updates = {CAMPO_A_COLUMNA[k]: v for k, v in data.items() if k in CAMPO_A_COLUMNA}
# + siempre updated_at=current_timestamp
```

**Criterio de completitud:** test de integración `tests/fdp/test_dispatcher.py` con DuckDB en memoria (`:memory:`).

---

## Fase D — FdpWorker (QThread TCP)

**Archivo:** `player/fdp/worker.py`

### Requisitos

- `QThread` independiente de `PlaybackWorker` (no mezclar UDP ASTERIX con TCP FDP)
- Reconexión automática con backoff (la FD_LAN puede tirar la conexión)
- Buffer de recepción: los mensajes ADEXP pueden llegar en múltiples `recv()` o varios en uno
- Delimitador de mensaje: según AFTN/AMHS, los mensajes ADEXP terminan en `\x03` (ETX) o línea en blanco doble — confirmar con el entorno real
- Señales Qt:
  - `mensaje_procesado = pyqtSignal(str, str)` — (tipo, arcid) para UI opcional
  - `error_conexion = pyqtSignal(str)`

### Parámetros configurables (perfil)

```json
"fdp": {
    "enabled": false,
    "host": "192.168.1.100",
    "port": 4000
}
```

**Criterio de completitud:** worker arranca, conecta, parsea un mensaje hardcodeado en loopback y persiste en DuckDB.

---

## Fase E — Integración en MainWindow (mínima)

**Archivo:** `player/main_window.py`

- Instanciar `FdpWorker` si `perfil["fdp"]["enabled"]` es `True`
- Menú **Herramientas → FDP** con:
  - Toggle activar/desactivar
  - Indicador de conexión (semáforo en HUD, igual que el estado de red ASTERIX)
- (Opcional) Panel de lista de vuelos activos como dock, solo rol `tecnico`

**Criterio de completitud:** toggle FDP visible, worker arranca/para sin crashear la app.

---

## Orden de implementación recomendado

```
A (schema) → B (parser, con tests) → C (dispatcher, con tests) → D (worker TCP) → E (UI mínima)
```

Fases A–C son puramente Python puro / DuckDB, sin Qt → se pueden testear sin arrancar la GUI.

---

## Riesgos y decisiones pendientes

| Riesgo | Mitigación |
|---|---|
| Delimitador de fin de mensaje en TCP desconocido | Confirmar con el FDS/entorno; implementar modo "línea en blanco doble" como default |
| Versión DuckDB instalada (necesita ≥0.9 para ON CONFLICT) | `python -c "import duckdb; print(duckdb.__version__)"` antes de Fase C |
| Tramas con campos lista complejos (RTEPTS con 50+ waypoints) | Para MVP: guardar ruta como TEXT crudo; parseo de waypoints es Fase F futura |
| FD_LAN no disponible en desarrollo | Mock TCP server con `socketserver` para tests de integración |

---

*Generado: 2026-06-25*
