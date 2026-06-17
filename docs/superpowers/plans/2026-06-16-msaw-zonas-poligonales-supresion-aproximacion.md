# MSAW Zonas Poligonales + Supresión en Aproximación — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Agregar al MSAW zonas poligonales de altitud mínima (SACO) con cascada sobre el modelo circular existente, e inhibir la alerta cuando una aeronave está establecida en el corredor de aproximación/salida dentro de su envelope vertical.

**Architecture:** Los datos (polígonos MSA, perfiles APM, waypoints) se cargan en `data/atm/atm.duckdb` y se leen vía `player/atm_db.py`. El modelo (`player/msaw/model.py`, sin Qt) gana `MsaPolygon`, `ApmCorridor`, `ProfileCorridor` y `SuppressionSet`. El motor (`engine.py`) usa una cascada `msa_lookup` (polígonos→círculos) y consulta `SuppressionSet` antes de emitir alertas. `radar_widget.py` arma ambos conjuntos perezosamente.

**Tech Stack:** Python 3.12, DuckDB, pytest (`tests/msaw/`, `--import-mode=importlib`). Sin Qt en model/engine. Reusa `haversine_nm` y `point_in_poly` de `player/areas/model.py`.

---

## File Structure

- `data/atm/msaw_profiles_schema-1.sql` — **crear**: DDL de las 6 tablas nuevas (contenido provisto como adjunto en la conversación).
- `data/atm/msaw_profiles_data.sql` — **crear**: INSERTs (contenido provisto como adjunto).
- `tools/load_msaw_profiles.py` — **crear**: carga idempotente de ambos SQL en `atm.duckdb`.
- `player/atm_db.py` — **modificar**: agregar `dms_to_dd`, `minimums_zones()`, `apm_corridors()`, `profile_corridors()`, `profile_parameters()`.
- `player/msaw/model.py` — **modificar**: helpers de geometría (`enu_nm`, `cross_along_nm`), `MsaPolygon`, `ApmCorridor`, `ProfileCorridor`, `SuppressionSet`.
- `player/msaw/engine.py` — **modificar**: `msa_lookup()` (cascada) + parámetro `suppression`.
- `player/radar_widget.py` — **modificar**: `evaluar_msaw()` arma polígonos + supresión.
- `tests/msaw/test_geometry.py` — **crear**.
- `tests/msaw/test_polygons.py` — **crear**.
- `tests/msaw/test_suppression.py` — **crear**.
- `tests/msaw/test_engine.py` — **modificar**: tests de cascada + supresión.
- `tests/msaw/test_profiles_db.py` — **crear**: lectura desde DB (skip si no hay DB).

Notas de convención (verificadas en el repo):
- Tests corren con `pytest` desde la raíz; `tests/pytest.ini` define `--import-mode=importlib`.
- Tracks en tests se simulan con `types.SimpleNamespace`.
- Tests que dependen de la DB usan `pytestmark = pytest.mark.skipif(not atm_db.available(), ...)`.
- `python` en este entorno: `/c/Users/Usuario/AppData/Local/Programs/Python/Python312/python.exe` (la `.venv` del proyecto está rota). Usar ese intérprete para correr pytest.

---

## Task 0: Cargar datos en atm.duckdb

**Files:**
- Create: `data/atm/msaw_profiles_schema-1.sql`
- Create: `data/atm/msaw_profiles_data.sql`
- Create: `tools/load_msaw_profiles.py`

- [ ] **Step 1: Escribir los dos archivos SQL**

Escribir `data/atm/msaw_profiles_schema-1.sql` con el contenido íntegro del adjunto `msaw_profiles_schema-1.sql` de la conversación (DDL de `minimums_zones_kernel`, `minimums_zones_vertices`, `profile_parameters`, `profiles_kernel`, `profile_points`, `apm_profiles_kernel` y las 3 vistas).

Escribir `data/atm/msaw_profiles_data.sql` con el contenido íntegro del adjunto `msaw_profiles_data.sql` (los INSERT de las 6 tablas: 10 zonas, 97 vértices, 1 fila de parámetros, 8 perfiles, 21 puntos, 128 APM).

> Las vistas del schema usan `CREATE OR REPLACE VIEW`. DuckDB las soporta. Si alguna vista falla por tipos, el loader las ignora (ver Step 2): lo único imprescindible son las 6 tablas base.

- [ ] **Step 2: Escribir el loader idempotente**

Create `tools/load_msaw_profiles.py`:

```python
"""Carga (idempotente) las tablas MSAW de zonas/perfiles en atm.duckdb.

Uso:
    python tools/load_msaw_profiles.py
"""
import os
import sys

import duckdb

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DB_PATH = os.path.join(ROOT, "data", "atm", "atm.duckdb")
SCHEMA_SQL = os.path.join(ROOT, "data", "atm", "msaw_profiles_schema-1.sql")
DATA_SQL = os.path.join(ROOT, "data", "atm", "msaw_profiles_data.sql")

TABLES = [
    "minimums_zones_vertices",
    "minimums_zones_kernel",
    "profile_points",
    "profiles_kernel",
    "profile_parameters",
    "apm_profiles_kernel",
]


def _exec_statements(con, sql_text):
    """Ejecuta sentencias separadas por ';', tolerando fallos de vistas."""
    for stmt in sql_text.split(";"):
        s = stmt.strip()
        if not s:
            continue
        try:
            con.execute(s)
        except Exception as e:
            if "VIEW" in s.upper():
                print(f"[WARN] vista omitida: {e}")
            else:
                raise


def main():
    if not os.path.exists(DB_PATH):
        sys.exit(f"No existe la DB: {DB_PATH}")
    schema = open(SCHEMA_SQL, encoding="utf-8").read()
    data = open(DATA_SQL, encoding="utf-8").read()
    con = duckdb.connect(DB_PATH, read_only=False)
    try:
        _exec_statements(con, schema)            # CREATE TABLE IF NOT EXISTS
        for t in TABLES:                          # idempotencia: limpiar antes
            con.execute(f"DELETE FROM {t}")
        _exec_statements(con, data)               # INSERT
        for t in TABLES:
            n = con.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
            print(f"{t}: {n} filas")
    finally:
        con.close()


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Ejecutar el loader**

Run: `"/c/Users/Usuario/AppData/Local/Programs/Python/Python312/python.exe" tools/load_msaw_profiles.py`
Expected (salida):
```
minimums_zones_vertices: 97 filas
minimums_zones_kernel: 10 filas
profile_points: 21 filas
profiles_kernel: 8 filas
profile_parameters: 1 filas
apm_profiles_kernel: 128 filas
```

- [ ] **Step 4: Commit**

```bash
git add data/atm/msaw_profiles_schema-1.sql data/atm/msaw_profiles_data.sql tools/load_msaw_profiles.py
git commit -m "feat(msaw): cargar tablas de zonas poligonales y perfiles en atm.duckdb"
```

---

## Task 1: Readers en atm_db.py

**Files:**
- Modify: `player/atm_db.py`
- Test: `tests/msaw/test_profiles_db.py`

- [ ] **Step 1: Escribir el test de lectura**

Create `tests/msaw/test_profiles_db.py`:

```python
import pytest

from player import atm_db

pytestmark = pytest.mark.skipif(not atm_db.available(),
                                reason="atm.duckdb no disponible")


def test_dms_to_dd_lat_lon():
    assert atm_db.dms_to_dd("311836S") == pytest.approx(-31.31, abs=0.01)
    assert atm_db.dms_to_dd("0641230W") == pytest.approx(-64.208, abs=0.01)
    assert atm_db.dms_to_dd("bad") is None


def test_minimums_zones():
    zs = {z["identifier"]: z for z in atm_db.minimums_zones()}
    # 10 zonas en los datos; las que tienen >=3 vértices válidos forman polígono
    assert "80E" in zs
    z = zs["80E"]
    assert z["msa_ft"] == 8000          # 80 -> x100
    assert len(z["coords"]) >= 4
    assert all(isinstance(c, tuple) and len(c) == 2 for c in z["coords"])


def test_apm_corridors_saco():
    cs = atm_db.apm_corridors("SACO")
    runways = {c["runway"] for c in cs}
    assert {"01", "05", "19", "23"} <= runways
    c = next(c for c in cs if c["runway"] == "01")
    assert c["near"] and c["far"]
    assert c["half_wide_nm"] == 1.0
    assert c["lower_slope"] == 2.5 and c["upper_slope"] == 4.8
    assert c["thr_elev_ft"] == 1604


def test_profile_corridors_saco():
    ps = {p["profile"]: p for p in atm_db.profile_corridors("SACO")}
    assert "RWY01A" in ps
    p = ps["RWY01A"]
    assert p["kind"] == "A"
    assert len(p["points"]) == 3
    lat, lon, min_ft, dlat, az = p["points"][0]
    assert min_ft == 4500              # altitude 45 -> x100


def test_profile_parameters():
    pr = atm_db.profile_parameters()
    assert pr["tol_heading"] == 18
    assert pr["tol_altitude_ft"] == 300     # 3 -> x100
    assert pr["tol_distance_nm"] == 0.5
    assert pr["entorno_aerodrome_nm"] == 3
```

- [ ] **Step 2: Correr el test (debe fallar)**

Run: `"/c/Users/Usuario/AppData/Local/Programs/Python/Python312/python.exe" -m pytest tests/msaw/test_profiles_db.py -v`
Expected: FAIL con `AttributeError: module 'player.atm_db' has no attribute 'dms_to_dd'`

- [ ] **Step 3: Implementar los readers en atm_db.py**

Agregar al final de `player/atm_db.py`:

```python
# ── MSAW: zonas poligonales y perfiles de aproximación ──────────────────────

def dms_to_dd(dms):
    """DMS del FDP ('311836S' / '0641230W') -> decimal degrees, o None."""
    if not dms or not isinstance(dms, str):
        return None
    dms = dms.strip()
    if not dms:
        return None
    hemi = dms[-1].upper()
    nums = dms[:-1]
    try:
        if len(nums) == 6:        # DDMMSS (lat)
            d, m, s = int(nums[0:2]), int(nums[2:4]), int(nums[4:6])
        elif len(nums) == 7:      # DDDMMSS (lon)
            d, m, s = int(nums[0:3]), int(nums[3:5]), int(nums[5:7])
        else:
            return None
        dd = d + m / 60 + s / 3600
        return round(-dd if hemi in ("S", "W") else dd, 6)
    except (ValueError, TypeError):
        return None


def _dms_dot_to_dd(s):
    """Variante con segundos decimales: '312228.69S' / '0641226.21W'."""
    if not s or not isinstance(s, str):
        return None
    s = s.strip()
    if not s:
        return None
    hemi = s[-1].upper()
    body = s[:-1]
    # separar grados según largo de la parte entera
    intpart = body.split(".")[0]
    try:
        if len(intpart) == 6:         # DDMMSS(.ss) lat
            d, m = int(intpart[0:2]), int(intpart[2:4])
            sec = float(body[4:])
        elif len(intpart) == 7:       # DDDMMSS(.ss) lon
            d, m = int(intpart[0:3]), int(intpart[3:5])
            sec = float(body[5:])
        else:
            return dms_to_dd(s)
        dd = d + m / 60 + sec / 3600
        return round(-dd if hemi in ("S", "W") else dd, 6)
    except (ValueError, TypeError):
        return None


def minimums_zones():
    """[{identifier, msa_ft, coords:[(lat,lon)...]}] (msa en ft = altitude*100)."""
    if not available():
        return []
    try:
        rows = _con().execute("""
            SELECT TRIM(mzk.identifier) AS ident, mzk.altitude,
                   mzv.sequence_number, mzv.latitude_image, mzv.longitude_image
            FROM minimums_zones_kernel mzk
            JOIN minimums_zones_vertices mzv
              ON mzk.identifier = mzv.zone_identifier
            ORDER BY ident, mzv.sequence_number
        """).fetchall()
    except Exception:
        return []
    out = {}
    for ident, alt, _seq, lat_i, lon_i in rows:
        lat, lon = dms_to_dd(lat_i), dms_to_dd(lon_i)
        if lat is None or lon is None:
            continue
        z = out.setdefault(ident, {"identifier": ident,
                                   "msa_ft": int(float(alt) * 100), "coords": []})
        z["coords"].append((lat, lon))
    return [z for z in out.values() if len(z["coords"]) >= 3]


def apm_corridors(airport=None):
    """Corredores APM con near/far no nulos. Distancias en NM, slopes en °."""
    if not available():
        return []
    where = f"WHERE TRIM(ap.airport_id) = '{airport}'" if airport else ""
    try:
        rows = _con().execute(f"""
            SELECT TRIM(ap.airport_id), TRIM(ap.runway_id),
                   ap.min_distance, ap.max_distance, ap.half_wide,
                   ap.lower_slope, ap.upper_slope, ap.glide_slope,
                   ap.near_latitude, ap.near_longitude,
                   ap.far_latitude, ap.far_longitude,
                   ak.place_altitude
            FROM apm_profiles_kernel ap
            JOIN airports_kernel ak ON ap.airport_id = ak.identifier_name
            {where}
            ORDER BY ap.airport_id, ap.runway_id
        """).fetchall()
    except Exception:
        return []
    out = []
    for (apid, rwy, mind, maxd, hw, lo, up, gl,
         nlat, nlon, flat, flon, elev) in rows:
        if not (nlat and nlon and flat and flon):
            continue
        near = (_dms_dot_to_dd(nlat), _dms_dot_to_dd(nlon))
        far = (_dms_dot_to_dd(flat), _dms_dot_to_dd(flon))
        if None in near or None in far:
            continue
        out.append({
            "airport": apid, "runway": rwy,
            "near": near, "far": far,
            "min_dist": float(mind), "max_dist": float(maxd),
            "half_wide_nm": float(hw),
            "lower_slope": float(lo), "upper_slope": float(up),
            "glide_slope": float(gl) if gl is not None else None,
            "thr_elev_ft": int(elev or 0),
        })
    return out


def profile_corridors(airport=None):
    """[{profile, airport, runway, kind, points:[(lat,lon,min_ft,dlat,az)...]}]."""
    if not available():
        return []
    where = f"WHERE TRIM(pk.airport) = '{airport}'" if airport else ""
    try:
        rows = _con().execute(f"""
            SELECT TRIM(pk.name), TRIM(pk.airport), TRIM(pk.runway), TRIM(pk.kind),
                   pp.seq_num, pp.latitude, pp.longitude,
                   pp.altitude, pp.distance_lateral, pp.azimut
            FROM profiles_kernel pk
            JOIN profile_points pp ON pk.name = pp.perfil_id
            {where}
            ORDER BY pk.name, pp.seq_num
        """).fetchall()
    except Exception:
        return []
    out = {}
    for name, apid, rwy, kind, _seq, lat_i, lon_i, alt, dlat, az in rows:
        lat, lon = dms_to_dd(lat_i), dms_to_dd(lon_i)
        if lat is None or lon is None:
            continue
        p = out.setdefault(name, {"profile": name, "airport": apid,
                                  "runway": rwy, "kind": kind, "points": []})
        p["points"].append((lat, lon, int(float(alt) * 100),
                            float(dlat or 0.5), int(az or 0)))
    return [p for p in out.values() if len(p["points"]) >= 2]


def profile_parameters():
    """Tolerancias globales de perfiles (escalas aplicadas)."""
    default = {"tol_heading": 18, "tol_altitude_ft": 300,
               "tol_distance_nm": 0.5, "entorno_aerodrome_nm": 3}
    if not available():
        return default
    try:
        row = _con().execute(
            "SELECT tol_heading, tol_altitude, tol_distance, entorno_aerodrome "
            "FROM profile_parameters LIMIT 1").fetchone()
    except Exception:
        return default
    if not row:
        return default
    return {
        "tol_heading": int(row[0] or 18),
        "tol_altitude_ft": int(float(row[1] or 3) * 100),
        "tol_distance_nm": float(row[2] or 0.5),
        "entorno_aerodrome_nm": float(row[3] or 3),
    }
```

- [ ] **Step 4: Correr el test (debe pasar)**

Run: `"/c/Users/Usuario/AppData/Local/Programs/Python/Python312/python.exe" -m pytest tests/msaw/test_profiles_db.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add player/atm_db.py tests/msaw/test_profiles_db.py
git commit -m "feat(msaw): readers de zonas poligonales y perfiles desde atm.duckdb"
```

---

## Task 2: Geometría + MsaPolygon

**Files:**
- Modify: `player/msaw/model.py`
- Test: `tests/msaw/test_geometry.py`, `tests/msaw/test_polygons.py`

- [ ] **Step 1: Escribir los tests de geometría**

Create `tests/msaw/test_geometry.py`:

```python
import math

from player.msaw.model import enu_nm, cross_along_nm


def test_enu_nm_norte_este():
    # 1 minuto de lat ~ 1 NM al norte
    x, y = enu_nm(0.0, 0.0, 1.0 / 60, 0.0)
    assert abs(y - 1.0) < 0.02
    assert abs(x) < 0.001


def test_cross_along_sobre_eje():
    # segmento de (0,0) a (0, 0.1) (hacia el este); punto sobre el eje a mitad
    cross, along = cross_along_nm(0.0, 0.05, 0.0, 0.0, 0.0, 0.1)
    assert abs(cross) < 0.05
    assert along > 0


def test_cross_lateral():
    # punto desplazado al norte del eje este-oeste -> cross != 0
    cross, along = cross_along_nm(0.02, 0.05, 0.0, 0.0, 0.0, 0.1)
    assert abs(cross) > 0.5
```

Create `tests/msaw/test_polygons.py`:

```python
from player.msaw.model import MsaPolygon

# Cuadrado ~ (0,0)-(0,1)-(1,1)-(1,0) en lat/lon
SQUARE = [(0.0, 0.0), (0.0, 1.0), (1.0, 1.0), (1.0, 0.0)]


def test_dentro():
    p = MsaPolygon("Z", 5000, SQUARE)
    assert p.contiene(0.5, 0.5) is True
    assert p.msa_en(0.5, 0.5) == 5000


def test_fuera():
    p = MsaPolygon("Z", 5000, SQUARE)
    assert p.contiene(2.0, 2.0) is False
    assert p.msa_en(2.0, 2.0) is None


def test_pocos_vertices_no_contiene():
    p = MsaPolygon("Z", 5000, [(0.0, 0.0), (1.0, 1.0)])
    assert p.contiene(0.5, 0.5) is False
```

- [ ] **Step 2: Correr (debe fallar)**

Run: `"/c/Users/Usuario/AppData/Local/Programs/Python/Python312/python.exe" -m pytest tests/msaw/test_geometry.py tests/msaw/test_polygons.py -v`
Expected: FAIL con `ImportError: cannot import name 'enu_nm'`

- [ ] **Step 3: Implementar geometría + MsaPolygon en model.py**

Agregar a `player/msaw/model.py` (después de los imports y de `in_arc`):

```python
from player.areas.model import point_in_poly

NM_PER_DEG = 60.0
FT_PER_NM = 6076.12


def enu_nm(lat0, lon0, lat, lon):
    """Desplazamiento local (este, norte) en NM desde (lat0,lon0)."""
    dy = (lat - lat0) * NM_PER_DEG
    dx = (lon - lon0) * NM_PER_DEG * math.cos(math.radians(lat0))
    return dx, dy


def cross_along_nm(lat, lon, lat1, lon1, lat2, lon2):
    """(cross, along) en NM del punto respecto del segmento (1)->(2).

    cross = distancia perpendicular (>=0); along = proyección sobre el eje
    medida desde el extremo (1) (puede ser <0 o > largo del segmento).
    """
    px, py = enu_nm(lat1, lon1, lat, lon)
    sx, sy = enu_nm(lat1, lon1, lat2, lon2)
    seg = math.hypot(sx, sy)
    if seg < 1e-9:
        return math.hypot(px, py), 0.0
    ux, uy = sx / seg, sy / seg
    along = px * ux + py * uy
    cross = abs(px * (-uy) + py * ux)
    return cross, along


@dataclass
class MsaPolygon:
    identifier: str
    msa_ft: int
    coords: list                  # [(lat,lon)...]

    def contiene(self, lat, lon) -> bool:
        return point_in_poly(lat, lon, self.coords)

    def msa_en(self, lat, lon):
        return self.msa_ft if self.contiene(lat, lon) else None
```

- [ ] **Step 4: Correr (debe pasar)**

Run: `"/c/Users/Usuario/AppData/Local/Programs/Python/Python312/python.exe" -m pytest tests/msaw/test_geometry.py tests/msaw/test_polygons.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add player/msaw/model.py tests/msaw/test_geometry.py tests/msaw/test_polygons.py
git commit -m "feat(msaw): MsaPolygon y helpers de geometria cross/along-track"
```

---

## Task 3: Corredores de supresión

**Files:**
- Modify: `player/msaw/model.py`
- Test: `tests/msaw/test_suppression.py`

- [ ] **Step 1: Escribir los tests de supresión**

Create `tests/msaw/test_suppression.py`:

```python
from player.msaw.model import ApmCorridor, ProfileCorridor, SuppressionSet

# Corredor sintético: eje sur->norte de (0,0) [umbral, elev 0] a (0.2,0) [far].
# 0.2° lat ~ 12 NM. half_wide 1 NM, slopes 2.5/4.8°, min/max 3..12 NM.
APM = ApmCorridor(airport="T", runway="01", near=(0.0, 0.0), far=(0.2, 0.0),
                  half_wide_nm=1.0, min_dist=3.0, max_dist=12.0,
                  lower_slope=2.5, upper_slope=4.8, glide_slope=3.0,
                  thr_elev_ft=0)


def _alt_a(d_nm, slope_deg):
    import math
    return d_nm * 6076.12 * math.tan(math.radians(slope_deg))


def test_apm_en_corredor_y_envelope_suprime():
    # ~6 NM along (0.1° lat), sobre el eje, alt entre lower y upper
    d = 6.0
    lat = d / 60.0
    alt = _alt_a(d, 3.0)            # glide nominal, dentro de [2.5, 4.8]
    assert APM.en_corredor(lat, 0.0) is True
    assert APM.en_envelope(lat, 0.0, alt) is True


def test_apm_fuera_lateral_no_suprime():
    lat = 6.0 / 60.0
    # 2 NM al este -> fuera de half_wide=1
    lon = 2.0 / (60.0 * 1.0)
    assert APM.en_corredor(lat, lon) is False


def test_apm_fuera_de_banda_distancia():
    # 1 NM along (< min_dist 3)
    lat = 1.0 / 60.0
    alt = _alt_a(1.0, 3.0)
    assert APM.en_corredor(lat, 0.0) is False


def test_apm_demasiado_bajo_fuera_de_envelope():
    d = 6.0
    lat = d / 60.0
    alt = _alt_a(d, 1.0)           # 1° < lower 2.5 -> demasiado bajo
    assert APM.en_corredor(lat, 0.0) is True
    assert APM.en_envelope(lat, 0.0, alt) is False


def test_suppression_set_apm():
    ss = SuppressionSet(apm=[APM], profiles=[],
                        params={"tol_altitude_ft": 300})
    d = 6.0
    lat = d / 60.0
    assert ss.suprime(lat, 0.0, _alt_a(d, 3.0)) is True
    assert ss.suprime(lat, 0.0, _alt_a(d, 1.0)) is False     # bajo envelope
    assert ss.suprime(2.0, 2.0, 5000) is False               # lejos


def test_profile_corridor_envelope():
    # 2 puntos: umbral (0,0) min 2000 ft, lejano (0.1,0) min 4000 ft
    pc = ProfileCorridor(profile="P", kind="A",
                         points=[(0.0, 0.0, 2000, 0.5, 0),
                                 (0.1, 0.0, 4000, 0.5, 0)])
    # a mitad de camino (0.05 lat) el perfil interpola ~3000 ft
    assert pc.en_corredor(0.05, 0.0) is True
    # aeronave a 3100 (>= 3000 - tol) suprime; a 2000 (< 3000 - 300) no
    assert pc.en_envelope(0.05, 0.0, 3100, tol_ft=300) is True
    assert pc.en_envelope(0.05, 0.0, 2000, tol_ft=300) is False
```

- [ ] **Step 2: Correr (debe fallar)**

Run: `"/c/Users/Usuario/AppData/Local/Programs/Python/Python312/python.exe" -m pytest tests/msaw/test_suppression.py -v`
Expected: FAIL con `ImportError: cannot import name 'ApmCorridor'`

- [ ] **Step 3: Implementar los corredores en model.py**

Agregar a `player/msaw/model.py`:

```python
@dataclass
class ApmCorridor:
    airport: str
    runway: str
    near: tuple                   # (lat,lon) umbral
    far: tuple                    # (lat,lon) punto lejano
    half_wide_nm: float
    min_dist: float
    max_dist: float
    lower_slope: float            # grados
    upper_slope: float            # grados
    glide_slope: float
    thr_elev_ft: int

    def _cross_along(self, lat, lon):
        return cross_along_nm(lat, lon, self.near[0], self.near[1],
                              self.far[0], self.far[1])

    def en_corredor(self, lat, lon) -> bool:
        cross, along = self._cross_along(lat, lon)
        return (cross <= self.half_wide_nm
                and self.min_dist <= along <= self.max_dist)

    def en_envelope(self, lat, lon, alt_ft) -> bool:
        _cross, along = self._cross_along(lat, lon)
        if along <= 0:
            return False
        ft = along * FT_PER_NM
        alt_lo = self.thr_elev_ft + ft * math.tan(math.radians(self.lower_slope))
        alt_hi = self.thr_elev_ft + ft * math.tan(math.radians(self.upper_slope))
        return alt_lo <= alt_ft <= alt_hi


@dataclass
class ProfileCorridor:
    profile: str
    kind: str                     # 'A' | 'D'
    points: list                  # [(lat,lon,min_ft,dlat_nm,az)...] por seq

    def _nearest_segment(self, lat, lon):
        """(idx, cross, along, min_interp) del tramo más cercano."""
        best = None
        for i in range(len(self.points) - 1):
            la1, lo1, m1, dl1, _ = self.points[i]
            la2, lo2, m2, _dl2, _ = self.points[i + 1]
            cross, along = cross_along_nm(lat, lon, la1, lo1, la2, lo2)
            seg = haversine_nm(la1, lo1, la2, lo2)
            t = max(0.0, min(1.0, along / seg)) if seg > 1e-9 else 0.0
            min_interp = m1 + (m2 - m1) * t
            cand = (i, cross, along, min_interp, dl1)
            if best is None or cross < best[1]:
                best = cand
        return best

    def en_corredor(self, lat, lon) -> bool:
        b = self._nearest_segment(lat, lon)
        if b is None:
            return False
        _i, cross, _along, _m, dlat = b
        return cross <= dlat

    def en_envelope(self, lat, lon, alt_ft, tol_ft=300) -> bool:
        b = self._nearest_segment(lat, lon)
        if b is None:
            return False
        _i, _cross, _along, min_interp, _dlat = b
        # suprime si la aeronave sigue el perfil de mínimos (no muy por debajo)
        return alt_ft >= (min_interp - tol_ft)


@dataclass
class SuppressionSet:
    apm: list = field(default_factory=list)        # [ApmCorridor]
    profiles: list = field(default_factory=list)   # [ProfileCorridor]
    params: dict = field(default_factory=dict)

    def suprime(self, lat, lon, alt_ft) -> bool:
        for c in self.apm:
            if c.en_corredor(lat, lon) and c.en_envelope(lat, lon, alt_ft):
                return True
        tol = self.params.get("tol_altitude_ft", 300)
        for p in self.profiles:
            if p.en_corredor(lat, lon) and p.en_envelope(lat, lon, alt_ft, tol):
                return True
        return False
```

- [ ] **Step 4: Correr (debe pasar)**

Run: `"/c/Users/Usuario/AppData/Local/Programs/Python/Python312/python.exe" -m pytest tests/msaw/test_suppression.py -v`
Expected: PASS (7 tests)

- [ ] **Step 5: Commit**

```bash
git add player/msaw/model.py tests/msaw/test_suppression.py
git commit -m "feat(msaw): corredores APM/perfil y SuppressionSet con envelope vertical"
```

---

## Task 4: Cascada MSA + supresión en el motor

**Files:**
- Modify: `player/msaw/engine.py`
- Test: `tests/msaw/test_engine.py`

- [ ] **Step 1: Agregar tests de cascada y supresión a test_engine.py**

Agregar a `tests/msaw/test_engine.py` (al final; reutiliza `_trk`, `_zona`, `S`):

```python
from player.msaw.model import MsaPolygon, ApmCorridor, SuppressionSet


def test_cascada_poligono_tiene_prioridad():
    # Polígono alrededor del origen con MSA 9000; el círculo daría 4100 al este.
    poly = MsaPolygon("SACO", 9000,
                      [(-0.05, -0.05), (-0.05, 0.05), (0.05, 0.05), (0.05, -0.05)])
    # FL080 = 8000 < 9000 (polígono) -> VIOLATION con msa del polígono
    al = evaluar_msaw([_trk(lat=0.0, lon=0.01, flight_level=80)], [poly, _zona()])
    assert len(al) == 1 and al[0].msa_ft == 9000


def test_cascada_cae_a_circulo_fuera_del_poligono():
    poly = MsaPolygon("P", 9000,
                      [(0.40, 0.40), (0.40, 0.45), (0.45, 0.45), (0.45, 0.40)])
    # punto fuera del polígono pero dentro del círculo (sector este 4100)
    al = evaluar_msaw([_trk(lat=0.0, lon=0.05, flight_level=30)], [poly, _zona()])
    assert len(al) == 1 and al[0].msa_ft == 4100


def test_supresion_inhibe_violacion():
    # Corredor sur->norte; track a ~6NM, sobre el eje, en envelope, FL010.
    import math
    apm = ApmCorridor("T", "01", near=(0.0, 0.0), far=(0.2, 0.0),
                      half_wide_nm=1.0, min_dist=3.0, max_dist=12.0,
                      lower_slope=2.5, upper_slope=4.8, glide_slope=3.0,
                      thr_elev_ft=0)
    ss = SuppressionSet(apm=[apm], profiles=[], params={"tol_altitude_ft": 300})
    d = 6.0
    lat = d / 60.0
    alt = d * 6076.12 * math.tan(math.radians(3.0))
    fl = alt / 100.0
    poly = MsaPolygon("T", 9000,
                      [(-1.0, -1.0), (-1.0, 1.0), (1.0, 1.0), (1.0, -1.0)])
    sin_sup = evaluar_msaw([_trk(lat=lat, lon=0.0, flight_level=fl)], [poly])
    assert len(sin_sup) == 1                      # sin supresión: alerta
    con_sup = evaluar_msaw([_trk(lat=lat, lon=0.0, flight_level=fl)], [poly],
                           suppression=ss)
    assert con_sup == []                          # suprimida
```

- [ ] **Step 2: Correr (debe fallar)**

Run: `"/c/Users/Usuario/AppData/Local/Programs/Python/Python312/python.exe" -m pytest tests/msaw/test_engine.py -v`
Expected: FAIL (`test_supresion_inhibe_violacion` por `TypeError: unexpected keyword 'suppression'`; cascada por msa incorrecta).

- [ ] **Step 3: Implementar la cascada y la supresión en engine.py**

En `player/msaw/engine.py`, agregar el helper antes de `evaluar_msaw`:

```python
def msa_lookup(zones, lat, lon):
    """MSA aplicable en el punto. Polígonos primero, luego círculos.

    `zones` es una lista que puede mezclar MsaPolygon (tienen `.identifier`) y
    MsaZone (tienen `.icao`). Devuelve (msa_ft, ident) o (None, None).
    """
    polys = [z for z in zones if hasattr(z, "identifier")]
    circles = [z for z in zones if not hasattr(z, "identifier")]
    for z in polys:
        msa = z.msa_en(lat, lon)
        if msa is not None:
            return msa, z.identifier
    for z in circles:
        msa = z.msa_en(lat, lon)
        if msa is not None:
            return msa, z.icao
    return None, None
```

Modificar la firma y el cuerpo de `evaluar_msaw`:

```python
def evaluar_msaw(tracks, zones, params: MsawParams = None, exentos=None,
                 suppression=None):
```

Reemplazar el bloque `for z in zones:` (desde `for z in zones:` hasta el final del lazo de tracks) por:

```python
        msa, ident = msa_lookup(zones, lat, lon)
        if msa is None:                            # fuera de toda zona
            continue

        if suppression is not None and suppression.suprime(lat, lon, alt_ft):
            continue

        # 1. Violación inmediata
        if alt_ft < msa:
            alertas.append(AlertaMSAW(track_id, ident, 'VIOLATION',
                                      int(msa), int(alt_ft), 0.0))
            continue

        # 2. Predicción de descenso (sólo si desciende)
        if vrate is not None and vrate < 0:
            for t in range(1, look + 1):
                alt_t = alt_ft + vrate * (t / 60.0)
                if vx is not None and vy is not None:
                    lat_t, lon_t = predecir_posicion(lat, lon, vx, vy, t)
                else:
                    lat_t, lon_t = lat, lon
                if suppression is not None and suppression.suprime(lat_t, lon_t, alt_t):
                    continue
                msa_t, ident_t = msa_lookup(zones, lat_t, lon_t)
                if msa_t is None:
                    msa_t, ident_t = msa, ident
                if alt_t < msa_t:
                    alertas.append(AlertaMSAW(track_id, ident_t, 'PREDICTED',
                                              int(msa_t), int(alt_ft), float(t)))
                    break
```

> Nota: se reemplaza el doble `break` previo (que salía del `for z in zones`) por `continue` sobre el lazo de tracks, ya que ahora hay una sola MSA por punto.

- [ ] **Step 4: Correr toda la suite del motor (debe pasar)**

Run: `"/c/Users/Usuario/AppData/Local/Programs/Python/Python312/python.exe" -m pytest tests/msaw/test_engine.py -v`
Expected: PASS (todos los tests previos + los 3 nuevos)

- [ ] **Step 5: Commit**

```bash
git add player/msaw/engine.py tests/msaw/test_engine.py
git commit -m "feat(msaw): cascada poligono->circulo y supresion en aproximacion en el motor"
```

---

## Task 5: Wiring en radar_widget.py

**Files:**
- Modify: `player/radar_widget.py` (`evaluar_msaw`, ~líneas 2398-2426)

- [ ] **Step 1: Leer el método actual**

Run: `"/c/Users/Usuario/AppData/Local/Programs/Python/Python312/python.exe" -c "pass"` (no-op; abrir el archivo y localizar `def evaluar_msaw` ~2398).

- [ ] **Step 2: Inicializar atributos de supresión**

Buscar dónde se inicializa `self._msaw_zones = None` y `self._msaw_params = None` (en `__init__` o setup del widget) y agregar al lado:

```python
        self._msaw_suppression = None
```

Si no existe esa inicialización explícita, agregar dentro de `evaluar_msaw` el guard `getattr(self, '_msaw_suppression', None)` (ver Step 3, que ya lo contempla con `getattr`).

- [ ] **Step 3: Reescribir el cuerpo de carga perezosa en evaluar_msaw**

Reemplazar el bloque:

```python
            from player.msaw.engine import evaluar_msaw as _engine
            if self._msaw_zones is None:
                from player.msaw import data as _md
                self._msaw_zones = _md.msa_zones()
            if self._msaw_params is None:
                from player import atm_db
                self._msaw_params = atm_db.msaw_params()
            if not self._msaw_zones:
                self.msaw_activos = []
                return
```

por:

```python
            from player.msaw.engine import evaluar_msaw as _engine
            from player import atm_db
            if self._msaw_zones is None:
                from player.msaw import data as _md
                from player.msaw.model import MsaPolygon
                circulos = _md.msa_zones()
                poligonos = [MsaPolygon(z["identifier"], z["msa_ft"], z["coords"])
                             for z in atm_db.minimums_zones()]
                self._msaw_zones = poligonos + circulos
            if self._msaw_params is None:
                self._msaw_params = atm_db.msaw_params()
            if getattr(self, '_msaw_suppression', None) is None:
                from player.msaw.model import (ApmCorridor, ProfileCorridor,
                                               SuppressionSet)
                apm = [ApmCorridor(
                            airport=c["airport"], runway=c["runway"],
                            near=c["near"], far=c["far"],
                            half_wide_nm=c["half_wide_nm"],
                            min_dist=c["min_dist"], max_dist=c["max_dist"],
                            lower_slope=c["lower_slope"], upper_slope=c["upper_slope"],
                            glide_slope=c["glide_slope"], thr_elev_ft=c["thr_elev_ft"])
                       for c in atm_db.apm_corridors()]
                profs = [ProfileCorridor(profile=p["profile"], kind=p["kind"],
                                         points=p["points"])
                         for p in atm_db.profile_corridors()]
                self._msaw_suppression = SuppressionSet(
                    apm=apm, profiles=profs, params=atm_db.profile_parameters())
            if not self._msaw_zones:
                self.msaw_activos = []
                return
```

- [ ] **Step 4: Pasar la supresión al motor**

Reemplazar:

```python
            self.msaw_activos = _engine(self.tracks.values(), self._msaw_zones,
                                        self._msaw_params, self.msaw_exentos)
```

por:

```python
            self.msaw_activos = _engine(self.tracks.values(), self._msaw_zones,
                                        self._msaw_params, self.msaw_exentos,
                                        suppression=self._msaw_suppression)
```

- [ ] **Step 5: Verificar que el módulo importa sin errores**

Run: `"/c/Users/Usuario/AppData/Local/Programs/Python/Python312/python.exe" -c "import ast; ast.parse(open('player/radar_widget.py',encoding='utf-8').read()); print('ok')"`
Expected: `ok`

- [ ] **Step 6: Correr toda la suite MSAW**

Run: `"/c/Users/Usuario/AppData/Local/Programs/Python/Python312/python.exe" -m pytest tests/msaw/ -v`
Expected: PASS (toda la carpeta)

- [ ] **Step 7: Commit**

```bash
git add player/radar_widget.py
git commit -m "feat(msaw): wiring de zonas poligonales y supresion en aproximacion en radar_widget"
```

---

## Task 6: Verificación manual (humo)

**Files:** ninguno (verificación).

- [ ] **Step 1: Smoke de readers + supresión contra la DB real**

Run:
```bash
"/c/Users/Usuario/AppData/Local/Programs/Python/Python312/python.exe" - <<'PY'
from player import atm_db
from player.msaw.model import ApmCorridor, SuppressionSet
import math
print("polígonos:", len(atm_db.minimums_zones()))
cs = atm_db.apm_corridors("SACO")
print("APM SACO:", [(c["runway"], c["near"], round(c["thr_elev_ft"])) for c in cs])
c = next(c for c in cs if c["runway"] == "01")
apm = ApmCorridor(airport=c["airport"], runway=c["runway"], near=c["near"],
                  far=c["far"], half_wide_nm=c["half_wide_nm"],
                  min_dist=c["min_dist"], max_dist=c["max_dist"],
                  lower_slope=c["lower_slope"], upper_slope=c["upper_slope"],
                  glide_slope=c["glide_slope"], thr_elev_ft=c["thr_elev_ft"])
# punto a mitad del corredor 01
mid = ((c["near"][0]+c["far"][0])/2, (c["near"][1]+c["far"][1])/2)
print("en_corredor(mid):", apm.en_corredor(*mid))
PY
```
Expected: `polígonos:` > 0; `APM SACO:` lista con 4 pistas y near coords no nulos; `en_corredor(mid): True`.

- [ ] **Step 2: (Opcional) Verificación visual en la app**

Si se desea, lanzar la app y observar que con tráfico de aproximación SACO no se dispara MSAW en final, mientras un track desplazado lateralmente sí. Referencia de arranque: memoria del proyecto (`env_python_runtime`).

- [ ] **Step 3: Confirmar suite completa**

Run: `"/c/Users/Usuario/AppData/Local/Programs/Python/Python312/python.exe" -m pytest tests/msaw/ -q`
Expected: todos PASS.

---

## Notas de verificación contra el spec

- **Zonas poligonales**: Task 1 (reader) + Task 2 (`MsaPolygon`) + Task 4 (cascada). ✔
- **Cascada polígono→círculo (SACO polígonos, resto círculos)**: `msa_lookup` Task 4. ✔
- **Corredor APM + profile_points**: Task 1 (readers) + Task 3 (`ApmCorridor`, `ProfileCorridor`). ✔
- **Supresión solo dentro del envelope**: `en_envelope` en Task 3; integrada en Task 4. ✔
- **Escala ×100** (minimums_zones, profile_points, tol_altitude): aplicada en readers Task 1. ✔
- **Degradación sin tablas**: readers devuelven `[]`/defaults; engine y wiring toleran vacío (Task 1, Task 5). ✔
- **Render (Fase 2)**: fuera de alcance, no hay tarea. ✔ (coincide con spec).
```
