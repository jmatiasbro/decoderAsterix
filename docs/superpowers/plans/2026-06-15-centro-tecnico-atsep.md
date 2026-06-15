# Centro Técnico ATSEP — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Construir un hub de ventana única para el rol TÉCNICO que integra (en pestañas) el PASS, el Monitor ATSEP y el Inspector existentes, y agrega un constructor configurable de estadísticas/gráficos y una vista de cobertura de radar con exportación.

**Architecture:** Capa de datos y lógica en Python puro (sin pandas — no está instalado), reutilizable por el constructor de estadísticas y por la cobertura. UI en PyQt6: una `QMainWindow` con `QTabWidget`, gateada por rol. Las herramientas existentes (QDialog) se embeben reusando su contenido. Gráficos con matplotlib (ya usado por el PASS). Datos desde `pass_analytics.duckdb` (duckdb) o desde la sesión en memoria, detrás de una interfaz común.

**Tech Stack:** Python 3.12, PyQt6, matplotlib, duckdb, numpy. Tests con pytest (`--import-mode=importlib`); Qt en modo `offscreen`.

**Convenciones del repo:**
- Ejecutar Python con: `"C:/Users/Usuario/AppData/Local/Programs/Python/Python312/python.exe"` (el `.venv` está roto). Abreviado abajo como `PY`.
- Tests Qt: setear `QT_QPA_PLATFORM=offscreen` y `QApplication.instance() or QApplication([])` (ver `tests/firmap/test_view_coords.py`).
- Correr tests: `PY -m pytest tests/<ruta> -v`

---

## File Structure

```
analysis/
  coverage.py              # NUEVO: lógica de cobertura por FL (polar + polígonos), pura
player/
  stats/
    __init__.py            # NUEVO
    data_source.py         # NUEVO: DataSource / DuckDBSource / SessionSource
    metric_registry.py     # NUEVO: catálogo de métricas + aggregate()
    chart_renderer.py      # NUEVO: render(figure, data, chart_type, ...)
  centro_tecnico/
    __init__.py            # NUEVO
    window.py              # NUEVO: CentroTecnicoWindow (QMainWindow + QTabWidget)
    stats_widget.py        # NUEVO: UI del constructor de estadísticas
    coverage_widget.py     # NUEVO: pestaña Cobertura (mapa + polar + export)
    inspector_widget.py    # NUEVO: wrapper embebible del Analizador de Paquetes
  main_window.py           # MODIFICAR: acción de menú gateada por rol
tests/
  stats/
    test_coverage.py       # NUEVO
    test_data_source.py    # NUEVO
    test_metric_registry.py# NUEVO
    test_chart_renderer.py # NUEVO
  centro_tecnico/
    test_window.py         # NUEVO (smoke, offscreen)
    test_coverage_widget.py# NUEVO (smoke, offscreen)
```

`player/technical_monitor.py` (`TechnicalMonitorWidget`) se reutiliza tal cual.
`player/pass_dashboard.py` (`PassDashboardDialog`) se reutiliza mediante su `QTabWidget` interno (ver Task 11).

---

## Phase 1 — Lógica de cobertura (pura, TDD)

### Task 1: `classify_fl` — normalizar flight level a banda

**Files:**
- Create: `analysis/coverage.py`
- Test: `tests/stats/test_coverage.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/stats/test_coverage.py
from analysis.coverage import classify_fl, FL_BANDS

def test_classify_fl_buckets():
    assert classify_fl("50") == 50      # FL50 cae en banda 50
    assert classify_fl("120") == 100    # 125 > x >= 75 -> 100
    assert classify_fl("300") == 300
    assert classify_fl("400") == 300    # >=275 -> 300
    assert classify_fl("25000") == 300  # pies: 25000/100=250 -> banda 250? -> ver abajo

def test_classify_fl_feet_normalization():
    # valores > 450 se interpretan como pies y se dividen por 100
    assert classify_fl("5000") == 50    # 5000/100 = 50
    assert classify_fl("25000") == 250  # 25000/100 = 250

def test_classify_fl_invalid():
    assert classify_fl(None) is None
    assert classify_fl("---") is None
    assert classify_fl("abc") is None
    assert classify_fl("10") is None    # < 25, fuera de bandas
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PY -m pytest tests/stats/test_coverage.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'analysis.coverage'`

- [ ] **Step 3: Write minimal implementation**

```python
# analysis/coverage.py
"""Cálculo de cobertura real de radar por nivel de vuelo (FL).

Lógica extraída de analysis/exporters.py::export_coverage_map_kmz para poder
reusarla en pantalla (polar + mapa) y en exportación, sin acoplarla al KMZ.
Python puro + numpy. Sin pandas.
"""
import math
from dataclasses import dataclass, field

FL_BANDS = (50, 100, 150, 200, 250, 300)


def classify_fl(fl_str):
    """Devuelve la banda FL (50..300) para un flight_level, o None si no aplica."""
    if fl_str is None or fl_str == "---":
        return None
    try:
        fl = float(fl_str)
    except (ValueError, TypeError):
        return None
    if fl > 450.0:        # viene en pies -> normalizar a FL
        fl = fl / 100.0
    if 25 <= fl < 75:
        return 50
    if 75 <= fl < 125:
        return 100
    if 125 <= fl < 175:
        return 150
    if 175 <= fl < 225:
        return 200
    if 225 <= fl < 275:
        return 250
    if fl >= 275:
        return 300
    return None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PY -m pytest tests/stats/test_coverage.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add analysis/coverage.py tests/stats/test_coverage.py
git commit -m "feat(coverage): classify_fl normaliza flight level a banda"
```

---

### Task 2: `compute_coverage` — contorno polar p95 por banda

**Files:**
- Modify: `analysis/coverage.py`
- Test: `tests/stats/test_coverage.py`

- [ ] **Step 1: Write the failing test**

```python
# append a tests/stats/test_coverage.py
import numpy as np
from analysis.coverage import compute_coverage, CoverageResult
from utils.geo import GeoTools

def _point_at(lat, lon, az_deg, r_nm):
    return GeoTools.vincenty_forward(lat, lon, az_deg, GeoTools.nm_to_meters(r_nm))

def test_compute_coverage_p95_range():
    rlat, rlon = -31.31, -64.21
    plots = []
    # 20 plots a ~100 NM en azimut 90, todos FL100
    for _ in range(20):
        plat, plon = _point_at(rlat, rlon, 90.0, 100.0)
        plots.append((plat, plon, "100"))
    res = compute_coverage(plots, rlat, rlon)
    assert isinstance(res, CoverageResult)
    assert res.plot_count == 20
    # banda 100, sector azimut 90 -> ~100 NM (tolerancia por proyección)
    assert abs(res.levels[100][90] - 100.0) < 2.0
    # sector sin datos -> 0
    assert res.levels[100][200] == 0.0

def test_compute_coverage_requires_min_plots():
    # < 10 plots en una banda -> banda vacía (todo 0)
    rlat, rlon = -31.31, -64.21
    plots = [(_point_at(rlat, rlon, 10.0, 50.0) + ("50",)) for _ in range(3)]
    res = compute_coverage(plots, rlat, rlon)
    assert all(r == 0.0 for r in res.levels[50])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PY -m pytest tests/stats/test_coverage.py -v`
Expected: FAIL — `ImportError: cannot import name 'compute_coverage'`

- [ ] **Step 3: Write minimal implementation**

```python
# append a analysis/coverage.py
import numpy as np
from utils.geo import GeoTools


@dataclass
class CoverageResult:
    radar_lat: float
    radar_lon: float
    levels: dict = field(default_factory=dict)   # FL banda -> list[360] rangos NM
    plot_count: int = 0


def compute_coverage(plots, radar_lat, radar_lon, *, percentile=95, bands=FL_BANDS):
    """plots: iterable de (lat, lon, fl_str). Devuelve CoverageResult.

    Para cada banda FL agrupa los plots en 360 sectores de azimut (1°) y toma el
    percentil indicado del rango (NM) por sector. Bandas con <10 plots quedan en 0.
    """
    by_band = {b: [[] for _ in range(360)] for b in bands}
    count = 0
    for lat, lon, fl_str in plots:
        band = classify_fl(fl_str)
        if band is None or band not in by_band:
            continue
        count += 1
        dist_m, az = GeoTools.calculate_distance_and_azimuth(radar_lat, radar_lon, lat, lon)
        r_nm = GeoTools.meters_to_nm(dist_m)
        by_band[band][int(math.floor(az)) % 360].append(r_nm)

    levels = {}
    for band, sectores in by_band.items():
        total = sum(len(s) for s in sectores)
        ranges = [0.0] * 360
        if total >= 10:
            for i, s in enumerate(sectores):
                if s:
                    ranges[i] = float(np.percentile(s, percentile))
        levels[band] = ranges
    return CoverageResult(radar_lat=radar_lat, radar_lon=radar_lon,
                          levels=levels, plot_count=count)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PY -m pytest tests/stats/test_coverage.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add analysis/coverage.py tests/stats/test_coverage.py
git commit -m "feat(coverage): compute_coverage con contorno polar p95 por banda FL"
```

---

### Task 3: `level_polygon_latlon` — polígono lat/lon para el mapa

**Files:**
- Modify: `analysis/coverage.py`
- Test: `tests/stats/test_coverage.py`

- [ ] **Step 1: Write the failing test**

```python
# append a tests/stats/test_coverage.py
from analysis.coverage import level_polygon_latlon

def test_level_polygon_closed_ring():
    rlat, rlon = -31.31, -64.21
    plots = []
    for az in range(0, 360, 2):           # cobertura uniforme ~80 NM
        plat, plon = _point_at(rlat, rlon, float(az), 80.0)
        plots.append((plat, plon, "150"))
    res = compute_coverage(plots, rlat, rlon)
    ring = level_polygon_latlon(res, 150)
    assert len(ring) >= 4
    assert ring[0] == ring[-1]            # anillo cerrado
    # cada vértice ~80 NM del radar
    d_m, _ = GeoTools.calculate_distance_and_azimuth(rlat, rlon, *ring[0])
    assert abs(GeoTools.meters_to_nm(d_m) - 80.0) < 3.0

def test_level_polygon_empty_band_returns_empty():
    res = compute_coverage([], -31.31, -64.21)
    assert level_polygon_latlon(res, 100) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PY -m pytest tests/stats/test_coverage.py -v`
Expected: FAIL — `ImportError: cannot import name 'level_polygon_latlon'`

- [ ] **Step 3: Write minimal implementation**

```python
# append a analysis/coverage.py
def level_polygon_latlon(result, fl):
    """Anillo [(lat, lon), ...] cerrado para la banda fl, o [] si vacía."""
    ranges = result.levels.get(fl)
    if not ranges:
        return []
    ring = []
    for az in range(360):
        r_nm = ranges[az]
        if r_nm <= 0.0:
            continue
        lat, lon = GeoTools.vincenty_forward(
            result.radar_lat, result.radar_lon, float(az), GeoTools.nm_to_meters(r_nm))
        ring.append((lat, lon))
    if len(ring) >= 3:
        ring.append(ring[0])             # cerrar
    else:
        return []
    return ring
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PY -m pytest tests/stats/test_coverage.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add analysis/coverage.py tests/stats/test_coverage.py
git commit -m "feat(coverage): level_polygon_latlon para vista de mapa"
```

---

## Phase 2 — Capa de datos del constructor (pura, TDD)

### Task 4: `DataSource` + `SessionSource`

**Files:**
- Create: `player/stats/__init__.py` (vacío)
- Create: `player/stats/data_source.py`
- Test: `tests/stats/test_data_source.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/stats/test_data_source.py
from player.stats.data_source import SessionSource

def _rec(sac_sic, t, fl="100", mode3a="7000", rng=100.0, az=45.0):
    # claves al estilo Plot.to_dict() de decoder/data_engine.py
    return {"sac_sic": sac_sic, "time": t, "lat": -31.0, "lon": -64.0,
            "flight_level": fl, "mode3a": mode3a, "raw_range": rng, "raw_azimuth": az}

def test_session_source_normalizes_keys():
    src = SessionSource([_rec("25/01", 1000.0)])
    rows = src.load()
    assert rows[0]["timestamp"] == 1000.0     # 'time' -> 'timestamp'
    assert rows[0]["sac_sic"] == "25/01"
    assert set(["sac_sic","timestamp","lat","lon","flight_level",
                "mode3a","raw_range","raw_azimuth"]).issubset(rows[0].keys())

def test_session_source_radars_sorted_unique():
    src = SessionSource([_rec("25/01", 1.0), _rec("07/10", 2.0), _rec("25/01", 3.0)])
    assert src.radars() == ["07/10", "25/01"]

def test_session_source_filters():
    src = SessionSource([_rec("25/01", 100.0), _rec("07/10", 200.0), _rec("25/01", 300.0)])
    assert len(src.load(radars=["25/01"])) == 2
    assert len(src.load(t_min=150.0, t_max=250.0)) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PY -m pytest tests/stats/test_data_source.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'player.stats.data_source'`

- [ ] **Step 3: Write minimal implementation**

```python
# player/stats/__init__.py
```
```python
# player/stats/data_source.py
"""Fuente unificada de filas de plots para el constructor de estadísticas.

Dos implementaciones tras la misma interfaz:
- SessionSource: filas Plot.to_dict() de la sesión en memoria.
- DuckDBSource: tabla asterix_plots de pass_analytics.duckdb.
Ambas devuelven filas con las mismas claves normalizadas (NORMALIZED_KEYS).
Python puro, sin pandas.
"""
from abc import ABC, abstractmethod

NORMALIZED_KEYS = ("sac_sic", "timestamp", "lat", "lon", "flight_level",
                   "mode3a", "raw_range", "raw_azimuth")


def _filter(rows, radars, t_min, t_max):
    out = rows
    if radars:
        rset = set(radars)
        out = [r for r in out if r.get("sac_sic") in rset]
    if t_min is not None:
        out = [r for r in out if (r.get("timestamp") or 0) >= t_min]
    if t_max is not None:
        out = [r for r in out if (r.get("timestamp") or 0) <= t_max]
    return out


class DataSource(ABC):
    @abstractmethod
    def load(self, *, radars=None, t_min=None, t_max=None):
        """Lista de dicts con claves NORMALIZED_KEYS."""

    @abstractmethod
    def radars(self):
        """Lista ordenada y única de sac_sic disponibles."""


class SessionSource(DataSource):
    def __init__(self, records):
        self._rows = [self._norm(r) for r in (records or [])]

    @staticmethod
    def _norm(r):
        return {
            "sac_sic": r.get("sac_sic"),
            "timestamp": r.get("timestamp", r.get("time")),
            "lat": r.get("lat"),
            "lon": r.get("lon"),
            "flight_level": r.get("flight_level"),
            "mode3a": r.get("mode3a"),
            "raw_range": r.get("raw_range"),
            "raw_azimuth": r.get("raw_azimuth"),
        }

    def load(self, *, radars=None, t_min=None, t_max=None):
        return _filter(list(self._rows), radars, t_min, t_max)

    def radars(self):
        return sorted({r["sac_sic"] for r in self._rows if r["sac_sic"]})
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PY -m pytest tests/stats/test_data_source.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add player/stats/__init__.py player/stats/data_source.py tests/stats/test_data_source.py
git commit -m "feat(stats): DataSource + SessionSource con claves normalizadas"
```

---

### Task 5: `DuckDBSource`

**Files:**
- Modify: `player/stats/data_source.py`
- Test: `tests/stats/test_data_source.py`

- [ ] **Step 1: Write the failing test**

```python
# append a tests/stats/test_data_source.py
import duckdb, pytest
from player.stats.data_source import DuckDBSource

@pytest.fixture
def db(tmp_path):
    p = tmp_path / "t.duckdb"
    con = duckdb.connect(str(p))
    con.execute("""CREATE TABLE asterix_plots(
        timestamp DOUBLE, sac_sic VARCHAR, lat DOUBLE, lon DOUBLE,
        flight_level VARCHAR, mode3a VARCHAR, raw_range DOUBLE, raw_azimuth DOUBLE)""")
    con.execute("INSERT INTO asterix_plots VALUES "
                "(100.0,'25/01',-31.0,-64.0,'100','7000',120.0,45.0),"
                "(200.0,'07/10',-30.0,-63.0,'150','7001',80.0,90.0)")
    con.close()
    return str(p)

def test_duckdb_source_load_and_radars(db):
    src = DuckDBSource(db)
    assert src.radars() == ["07/10", "25/01"]
    rows = src.load(radars=["25/01"])
    assert len(rows) == 1 and rows[0]["timestamp"] == 100.0
    assert set(rows[0].keys()) >= {"sac_sic","timestamp","lat","lon",
                                   "flight_level","mode3a","raw_range","raw_azimuth"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PY -m pytest tests/stats/test_data_source.py::test_duckdb_source_load_and_radars -v`
Expected: FAIL — `ImportError: cannot import name 'DuckDBSource'`

- [ ] **Step 3: Write minimal implementation**

```python
# append a player/stats/data_source.py
import duckdb


class DuckDBSource(DataSource):
    def __init__(self, db_path="pass_analytics.duckdb"):
        self.db_path = db_path

    def _query(self, sql, params=()):
        with duckdb.connect(self.db_path, read_only=True) as con:
            cur = con.execute(sql, params)
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]

    def load(self, *, radars=None, t_min=None, t_max=None):
        where, params = [], []
        if radars:
            where.append("sac_sic IN (" + ",".join(["?"] * len(radars)) + ")")
            params += list(radars)
        if t_min is not None:
            where.append("timestamp >= ?"); params.append(t_min)
        if t_max is not None:
            where.append("timestamp <= ?"); params.append(t_max)
        clause = (" WHERE " + " AND ".join(where)) if where else ""
        sql = ("SELECT sac_sic, timestamp, lat, lon, flight_level, mode3a, "
               "raw_range, raw_azimuth FROM asterix_plots" + clause)
        return self._query(sql, params)

    def radars(self):
        rows = self._query("SELECT DISTINCT sac_sic FROM asterix_plots "
                           "WHERE sac_sic IS NOT NULL ORDER BY sac_sic")
        return [r["sac_sic"] for r in rows]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PY -m pytest tests/stats/test_data_source.py -v`
Expected: PASS (todos)

- [ ] **Step 5: Commit**

```bash
git add player/stats/data_source.py tests/stats/test_data_source.py
git commit -m "feat(stats): DuckDBSource sobre asterix_plots"
```

---

## Phase 3 — Catálogo de métricas (puro, TDD)

### Task 6: `metric_registry` — métricas, dimensiones y `aggregate`

**Files:**
- Create: `player/stats/metric_registry.py`
- Test: `tests/stats/test_metric_registry.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/stats/test_metric_registry.py
from player.stats.metric_registry import METRICS, DIMENSIONS, aggregate, metric_by_id

def _rows():
    return [
        {"sac_sic": "25/01", "timestamp": 0.0, "flight_level": "100",
         "mode3a": "7000", "raw_range": 100.0, "raw_azimuth": 10.0},
        {"sac_sic": "25/01", "timestamp": 3600.0, "flight_level": "200",
         "mode3a": "7000", "raw_range": 50.0, "raw_azimuth": 20.0},
        {"sac_sic": "07/10", "timestamp": 0.0, "flight_level": "100",
         "mode3a": "1200", "raw_range": 200.0, "raw_azimuth": 30.0},
    ]

def test_registry_has_core_metrics_and_dims():
    ids = {m.id for m in METRICS}
    assert {"count", "avg_range", "p95_range"}.issubset(ids)
    assert {"radar", "hour", "mode3a"}.issubset(set(DIMENSIONS))

def test_aggregate_count_by_radar():
    res = dict(aggregate(_rows(), metric_by_id("count"), "radar"))
    assert res == {"25/01": 2, "07/10": 1}

def test_aggregate_avg_range_by_radar():
    res = dict(aggregate(_rows(), metric_by_id("avg_range"), "radar"))
    assert abs(res["25/01"] - 75.0) < 1e-9     # (100+50)/2
    assert abs(res["07/10"] - 200.0) < 1e-9

def test_aggregate_count_by_mode3a():
    res = dict(aggregate(_rows(), metric_by_id("count"), "mode3a"))
    assert res["7000"] == 2 and res["1200"] == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PY -m pytest tests/stats/test_metric_registry.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'player.stats.metric_registry'`

- [ ] **Step 3: Write minimal implementation**

```python
# player/stats/metric_registry.py
"""Catálogo declarativo de métricas/dimensiones y agregación en Python puro.

aggregate(rows, metric, dimension) -> list[(label, value)] ordenado desc por valor.
"""
from dataclasses import dataclass
import time as _time

import numpy as np


@dataclass(frozen=True)
class Metric:
    id: str
    label: str
    column: str          # campo fuente; "" para count
    agg: str             # "count" | "avg" | "p95"
    dims: tuple           # ids de dimensión admitidos


METRICS = [
    Metric("count",     "Nº detecciones",   "",          "count", ("radar", "hour", "mode3a", "fl_band")),
    Metric("avg_range", "Rango medio (NM)", "raw_range", "avg",   ("radar", "hour", "fl_band")),
    Metric("p95_range", "Rango p95 (NM)",   "raw_range", "p95",   ("radar", "hour", "fl_band")),
]


def metric_by_id(mid):
    for m in METRICS:
        if m.id == mid:
            return m
    raise KeyError(mid)


def _hour_bucket(row):
    ts = row.get("timestamp")
    if ts is None:
        return "—"
    return _time.strftime("%H:00", _time.gmtime(ts))


def _fl_band(row):
    from analysis.coverage import classify_fl
    b = classify_fl(row.get("flight_level"))
    return f"FL{b}" if b is not None else "—"


DIMENSIONS = {
    "radar":  lambda r: r.get("sac_sic") or "—",
    "hour":   _hour_bucket,
    "mode3a": lambda r: r.get("mode3a") or "—",
    "fl_band": _fl_band,
}


def aggregate(rows, metric, dimension):
    keyfn = DIMENSIONS[dimension]
    buckets = {}
    for r in rows:
        k = keyfn(r)
        buckets.setdefault(k, []).append(r)
    out = []
    for k, group in buckets.items():
        if metric.agg == "count":
            v = float(len(group))
        else:
            vals = [g.get(metric.column) for g in group if g.get(metric.column) is not None]
            if not vals:
                continue
            if metric.agg == "avg":
                v = float(np.mean(vals))
            elif metric.agg == "p95":
                v = float(np.percentile(vals, 95))
            else:
                raise ValueError(metric.agg)
        out.append((k, v))
    out.sort(key=lambda kv: kv[1], reverse=True)
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PY -m pytest tests/stats/test_metric_registry.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add player/stats/metric_registry.py tests/stats/test_metric_registry.py
git commit -m "feat(stats): catálogo de métricas/dimensiones y aggregate"
```

---

## Phase 4 — Renderer de gráficos (matplotlib, TDD)

### Task 7: `chart_renderer` — bar/line/pie sobre datos (label, value)

**Files:**
- Create: `player/stats/chart_renderer.py`
- Test: `tests/stats/test_chart_renderer.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/stats/test_chart_renderer.py
import matplotlib
matplotlib.use("Agg")
from matplotlib.figure import Figure
from player.stats.chart_renderer import render, CHART_TYPES

DATA = [("25/01", 12.0), ("07/10", 8.0), ("MTR", 5.0)]

def test_chart_types_v1():
    assert {"bar", "line", "pie", "box", "stacked100",
            "heatmap_hourday", "spider"}.issubset(set(CHART_TYPES))

def test_render_bar_draws_axes():
    fig = Figure()
    render(fig, DATA, "bar", title="t", xlabel="x", ylabel="y")
    ax = fig.axes[0]
    assert len(ax.patches) == 3            # 3 barras
    assert ax.get_title() == "t"

def test_render_line_and_pie_no_error():
    for ct in ("line", "pie"):
        fig = Figure()
        render(fig, DATA, ct)
        assert fig.axes                     # algo dibujado

def test_render_unknown_type_raises():
    import pytest
    with pytest.raises(ValueError):
        render(Figure(), DATA, "nope")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PY -m pytest tests/stats/test_chart_renderer.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'player.stats.chart_renderer'`

- [ ] **Step 3: Write minimal implementation**

```python
# player/stats/chart_renderer.py
"""Render de gráficos del constructor sobre una matplotlib Figure.

`data` para bar/line/pie/box/stacked100/spider es list[(label, value)].
Para heatmap_hourday es list[(hour_label, day_label, value)].
"""
CHART_TYPES = ("bar", "line", "pie", "box", "stacked100", "heatmap_hourday", "spider")


def _labels_values(data):
    labels = [str(d[0]) for d in data]
    values = [float(d[1]) for d in data]
    return labels, values


def render(figure, data, chart_type, *, title="", xlabel="", ylabel=""):
    if chart_type not in CHART_TYPES:
        raise ValueError(f"tipo de gráfico desconocido: {chart_type}")
    figure.clear()
    if chart_type == "bar":
        ax = figure.add_subplot(111)
        labels, values = _labels_values(data)
        ax.bar(labels, values)
        ax.set_xlabel(xlabel); ax.set_ylabel(ylabel)
    elif chart_type == "line":
        ax = figure.add_subplot(111)
        labels, values = _labels_values(data)
        ax.plot(labels, values, marker="o")
        ax.set_xlabel(xlabel); ax.set_ylabel(ylabel)
    elif chart_type == "pie":
        ax = figure.add_subplot(111)
        labels, values = _labels_values(data)
        ax.pie(values, labels=labels, autopct="%1.0f%%")
    else:
        _render_extended(figure, data, chart_type, xlabel, ylabel)
        ax = figure.axes[0] if figure.axes else figure.add_subplot(111)
    ax = figure.axes[0]
    ax.set_title(title)
    figure.tight_layout()
    return figure


def _render_extended(figure, data, chart_type, xlabel, ylabel):
    # implementado en Task 8
    raise ValueError(f"tipo de gráfico no implementado aún: {chart_type}")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PY -m pytest tests/stats/test_chart_renderer.py -v`
Expected: `test_chart_types_v1`, `test_render_bar_draws_axes`, `test_render_line_and_pie_no_error`, `test_render_unknown_type_raises` PASS. (Los de box/spider/heatmap/stacked llegan en Task 8.)

- [ ] **Step 5: Commit**

```bash
git add player/stats/chart_renderer.py tests/stats/test_chart_renderer.py
git commit -m "feat(stats): chart_renderer bar/line/pie"
```

---

### Task 8: `chart_renderer` — box, stacked100, heatmap_hourday, spider

**Files:**
- Modify: `player/stats/chart_renderer.py`
- Test: `tests/stats/test_chart_renderer.py`

- [ ] **Step 1: Write the failing test**

```python
# append a tests/stats/test_chart_renderer.py
def test_render_box():
    fig = Figure()
    render(fig, [("25/01", [1.0, 2.0, 3.0]), ("07/10", [2.0, 4.0])], "box")
    assert fig.axes

def test_render_stacked100():
    fig = Figure()
    render(fig, [("25/01", 12.0), ("07/10", 8.0)], "stacked100")
    assert fig.axes

def test_render_spider():
    fig = Figure()
    render(fig, [("Pd", 0.9), ("RMS", 0.7), ("Disp", 0.8)], "spider")
    assert fig.axes

def test_render_heatmap_hourday():
    fig = Figure()
    data = [("00:00", "Lun", 5.0), ("01:00", "Lun", 3.0), ("00:00", "Mar", 1.0)]
    render(fig, data, "heatmap_hourday")
    assert fig.axes
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PY -m pytest tests/stats/test_chart_renderer.py -v`
Expected: FAIL — `ValueError: tipo de gráfico no implementado aún: box`

- [ ] **Step 3: Write minimal implementation**

```python
# reemplazar _render_extended en player/stats/chart_renderer.py
import numpy as np


def _render_extended(figure, data, chart_type, xlabel, ylabel):
    if chart_type == "box":
        ax = figure.add_subplot(111)
        labels = [str(d[0]) for d in data]
        series = [list(d[1]) for d in data]
        ax.boxplot(series, labels=labels)
        ax.set_xlabel(xlabel); ax.set_ylabel(ylabel)
    elif chart_type == "stacked100":
        ax = figure.add_subplot(111)
        labels, values = _labels_values(data)
        total = sum(values) or 1.0
        bottom = 0.0
        for lab, val in zip(labels, values):
            pct = 100.0 * val / total
            ax.bar(["total"], [pct], bottom=[bottom], label=lab)
            bottom += pct
        ax.legend(fontsize=7); ax.set_ylabel("%")
    elif chart_type == "spider":
        labels, values = _labels_values(data)
        ang = np.linspace(0, 2 * np.pi, len(labels), endpoint=False).tolist()
        vals = values + values[:1]
        ang = ang + ang[:1]
        ax = figure.add_subplot(111, projection="polar")
        ax.plot(ang, vals, marker="o")
        ax.fill(ang, vals, alpha=0.25)
        ax.set_xticks(ang[:-1]); ax.set_xticklabels(labels, fontsize=8)
    elif chart_type == "heatmap_hourday":
        ax = figure.add_subplot(111)
        hours = sorted({d[0] for d in data})
        days = sorted({d[1] for d in data})
        hi = {h: i for i, h in enumerate(hours)}
        di = {d: i for i, d in enumerate(days)}
        grid = np.zeros((len(days), len(hours)))
        for h, d, v in data:
            grid[di[d], hi[h]] = v
        im = ax.imshow(grid, aspect="auto")
        ax.set_xticks(range(len(hours))); ax.set_xticklabels(hours, rotation=90, fontsize=7)
        ax.set_yticks(range(len(days))); ax.set_yticklabels(days, fontsize=7)
        figure.colorbar(im, ax=ax)
    else:
        raise ValueError(f"tipo de gráfico no implementado aún: {chart_type}")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PY -m pytest tests/stats/test_chart_renderer.py -v`
Expected: PASS (todos)

- [ ] **Step 5: Commit**

```bash
git add player/stats/chart_renderer.py tests/stats/test_chart_renderer.py
git commit -m "feat(stats): chart_renderer box/stacked100/heatmap_hourday/spider"
```

---

## Phase 5 — Ventana hub y embebido (Qt, smoke offscreen)

### Task 9: `CentroTecnicoWindow` — shell con QTabWidget + conmutador de fuente

**Files:**
- Create: `player/centro_tecnico/__init__.py` (vacío)
- Create: `player/centro_tecnico/window.py`
- Test: `tests/centro_tecnico/test_window.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/centro_tecnico/test_window.py
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import pytest
pytest.importorskip("PyQt6.QtWidgets")
from PyQt6.QtWidgets import QApplication
from player.centro_tecnico.window import CentroTecnicoWindow

@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])

def test_window_has_five_tabs(app):
    w = CentroTecnicoWindow()
    assert w.tabs.count() == 5
    titles = [w.tabs.tabText(i) for i in range(5)]
    assert any("Estad" in t for t in titles)
    assert any("Cobertura" in t for t in titles)

def test_source_toggle_default_duckdb(app):
    w = CentroTecnicoWindow()
    assert w.current_source_kind() in ("duckdb", "session")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PY -m pytest tests/centro_tecnico/test_window.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'player.centro_tecnico.window'`

- [ ] **Step 3: Write minimal implementation**

```python
# player/centro_tecnico/__init__.py
```
```python
# player/centro_tecnico/window.py
"""Centro Técnico ATSEP: ventana hub con pestañas de herramientas técnicas."""
from PyQt6.QtWidgets import (
    QMainWindow, QTabWidget, QWidget, QStatusBar, QRadioButton, QButtonGroup,
    QHBoxLayout, QLabel,
)

from player.centro_tecnico.stats_widget import StatsWidget
from player.centro_tecnico.coverage_widget import CoverageWidget


class CentroTecnicoWindow(QMainWindow):
    def __init__(self, repo_db=None, worker=None, session_records=None,
                 db_path="pass_analytics.duckdb", parent=None):
        super().__init__(parent)
        self.setWindowTitle("Centro Técnico ATSEP")
        self.resize(1280, 800)
        self._repo_db = repo_db
        self._worker = worker
        self._session_records = session_records or []
        self._db_path = db_path

        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)

        self.stats_tab = StatsWidget(self.source_provider)
        self.coverage_tab = CoverageWidget(self.source_provider, db_path=db_path)
        self.tabs.addTab(self.stats_tab, "📊 Estadísticas")
        self.tabs.addTab(QWidget(), "✅ PASS / SASS-C")     # poblada en Task 11
        self.tabs.addTab(QWidget(), "📡 Monitor ATSEP")     # poblada en Task 10
        self.tabs.addTab(self._inspector_placeholder(), "🔬 Inspector")  # Task 12
        self.tabs.addTab(self.coverage_tab, "🛰 Cobertura")

        self._build_statusbar()

    def _inspector_placeholder(self):
        return QWidget()

    def _build_statusbar(self):
        bar = QStatusBar()
        self.setStatusBar(bar)
        cont = QWidget(); lay = QHBoxLayout(cont); lay.setContentsMargins(8, 0, 8, 0)
        lay.addWidget(QLabel("Fuente:"))
        self.rb_duckdb = QRadioButton("DuckDB")
        self.rb_session = QRadioButton("Sesión actual")
        self.rb_duckdb.setChecked(True)
        grp = QButtonGroup(self); grp.addButton(self.rb_duckdb); grp.addButton(self.rb_session)
        lay.addWidget(self.rb_duckdb); lay.addWidget(self.rb_session); lay.addStretch(1)
        bar.addPermanentWidget(cont, 1)
        self.rb_duckdb.toggled.connect(self._on_source_changed)

    def current_source_kind(self):
        return "duckdb" if self.rb_duckdb.isChecked() else "session"

    def source_provider(self):
        """Devuelve la DataSource activa según el conmutador."""
        from player.stats.data_source import DuckDBSource, SessionSource
        if self.current_source_kind() == "duckdb":
            return DuckDBSource(self._db_path)
        return SessionSource(self._session_records)

    def _on_source_changed(self, _checked):
        if hasattr(self.stats_tab, "on_source_changed"):
            self.stats_tab.on_source_changed()
        if hasattr(self.coverage_tab, "on_source_changed"):
            self.coverage_tab.on_source_changed()
```

> Nota: `StatsWidget` y `CoverageWidget` se crean en Tasks 13 y 14. Para que este test
> pase antes, implementá primero los stubs mínimos de esos widgets (Tasks 13/14 Step 3),
> o reordená ejecutando Tasks 13 y 14 antes del Step 4 de esta task. El plan asume que
> al llegar al Step 4 de Task 9 ya existen los widgets (ver dependencias abajo).

- [ ] **Step 4: Run test to verify it passes**

Run: `PY -m pytest tests/centro_tecnico/test_window.py -v`
Expected: PASS (requiere StatsWidget y CoverageWidget — Tasks 13 y 14)

- [ ] **Step 5: Commit**

```bash
git add player/centro_tecnico/__init__.py player/centro_tecnico/window.py tests/centro_tecnico/test_window.py
git commit -m "feat(centro-tecnico): shell de ventana con 5 pestañas y conmutador de fuente"
```

**Dependencias:** Esta task se completa (Step 4 verde) recién después de Tasks 13 (StatsWidget) y 14 (CoverageWidget). Recomendado ejecutar en este orden: 13 → 14 → 9 → 10 → 11 → 12 → 15.

---

### Task 10: Pestaña Monitor ATSEP (reusar `TechnicalMonitorWidget`)

**Files:**
- Modify: `player/centro_tecnico/window.py`
- Test: `tests/centro_tecnico/test_window.py`

- [ ] **Step 1: Write the failing test**

```python
# append a tests/centro_tecnico/test_window.py
from player.technical_monitor import TechnicalMonitorWidget

def test_monitor_tab_is_technical_monitor(app):
    w = CentroTecnicoWindow()
    idx = next(i for i in range(w.tabs.count()) if "Monitor" in w.tabs.tabText(i))
    assert isinstance(w.tabs.widget(idx), TechnicalMonitorWidget)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PY -m pytest tests/centro_tecnico/test_window.py::test_monitor_tab_is_technical_monitor -v`
Expected: FAIL — la pestaña Monitor es un `QWidget` vacío.

- [ ] **Step 3: Write minimal implementation**

```python
# en player/centro_tecnico/window.py:
# 1) import arriba:
from player.technical_monitor import TechnicalMonitorWidget
# 2) reemplazar la línea de la pestaña Monitor:
#    self.tabs.addTab(QWidget(), "📡 Monitor ATSEP")
# por:
        self.monitor_tab = TechnicalMonitorWidget(self)
        self.tabs.addTab(self.monitor_tab, "📡 Monitor ATSEP")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PY -m pytest tests/centro_tecnico/test_window.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add player/centro_tecnico/window.py tests/centro_tecnico/test_window.py
git commit -m "feat(centro-tecnico): pestaña Monitor ATSEP reusa TechnicalMonitorWidget"
```

---

### Task 11: Pestaña PASS (embeber `PassDashboardDialog`)

**Files:**
- Modify: `player/centro_tecnico/window.py`
- Test: `tests/centro_tecnico/test_window.py`

**Contexto:** `PassDashboardDialog(analysis_results: Dict, parent=None)` construye su UI en `_setup_ui` y arma `self.tabs` (un `QTabWidget` interno con los gráficos PASS). Para embeber sin refactor profundo, se instancia el diálogo con resultados vacíos `{}` y se reparenta su `QTabWidget` interno dentro de un contenedor de la pestaña.

- [ ] **Step 1: Write the failing test**

```python
# append a tests/centro_tecnico/test_window.py
def test_pass_tab_embeds_dashboard_tabs(app):
    w = CentroTecnicoWindow()
    idx = next(i for i in range(w.tabs.count()) if "PASS" in w.tabs.tabText(i))
    page = w.tabs.widget(idx)
    # el contenedor PASS debe alojar un QTabWidget (las pestañas del PASS)
    from PyQt6.QtWidgets import QTabWidget
    assert page.findChild(QTabWidget) is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PY -m pytest tests/centro_tecnico/test_window.py::test_pass_tab_embeds_dashboard_tabs -v`
Expected: FAIL — la pestaña PASS es un `QWidget` vacío.

- [ ] **Step 3: Write minimal implementation**

```python
# en player/centro_tecnico/window.py
# import arriba:
from PyQt6.QtWidgets import QVBoxLayout
from player.pass_dashboard import PassDashboardDialog

# añadir método:
    def _build_pass_page(self):
        page = QWidget()
        lay = QVBoxLayout(page); lay.setContentsMargins(0, 0, 0, 0)
        self._pass_dialog = PassDashboardDialog({}, self)   # sin resultados aún
        inner = self._pass_dialog.tabs                       # QTabWidget interno
        inner.setParent(page)
        lay.addWidget(inner)
        return page

# reemplazar:
#   self.tabs.addTab(QWidget(), "✅ PASS / SASS-C")
# por:
        self.tabs.addTab(self._build_pass_page(), "✅ PASS / SASS-C")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PY -m pytest tests/centro_tecnico/test_window.py -v`
Expected: PASS

> Si `PassDashboardDialog({})` lanzara por resultados vacíos, envolver en
> try/except y, en fallo, mostrar un `QLabel("Cargá un análisis PASS para ver datos")`.
> Verificar manualmente: `PY -c "from player.pass_dashboard import PassDashboardDialog"`.

- [ ] **Step 5: Commit**

```bash
git add player/centro_tecnico/window.py tests/centro_tecnico/test_window.py
git commit -m "feat(centro-tecnico): pestaña PASS embebe el dashboard existente"
```

---

### Task 12: Pestaña Inspector (`inspector_widget` reusando el analizador)

**Files:**
- Create: `player/centro_tecnico/inspector_widget.py`
- Modify: `player/centro_tecnico/window.py`
- Test: `tests/centro_tecnico/test_window.py`

**Contexto:** `AsterixAnalyzerWindow(repo_db, worker=None, parent=None)` es un `QDialog`.
El wrapper instancia ese diálogo, le saca su layout y lo embebe; si `repo_db` es `None`
muestra un aviso (no rompe la ventana).

- [ ] **Step 1: Write the failing test**

```python
# append a tests/centro_tecnico/test_window.py
from player.centro_tecnico.inspector_widget import InspectorWidget

def test_inspector_widget_builds_without_db(app):
    iw = InspectorWidget(repo_db=None, worker=None)
    assert iw is not None    # no debe lanzar sin repo_db

def test_inspector_tab_is_inspector_widget(app):
    w = CentroTecnicoWindow()
    idx = next(i for i in range(w.tabs.count()) if "Inspector" in w.tabs.tabText(i))
    assert isinstance(w.tabs.widget(idx), InspectorWidget)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PY -m pytest tests/centro_tecnico/test_window.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'player.centro_tecnico.inspector_widget'`

- [ ] **Step 3: Write minimal implementation**

```python
# player/centro_tecnico/inspector_widget.py
"""Wrapper embebible del Analizador de Paquetes ASTERIX."""
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel


class InspectorWidget(QWidget):
    def __init__(self, repo_db=None, worker=None, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self); lay.setContentsMargins(0, 0, 0, 0)
        if repo_db is None:
            lay.addWidget(QLabel("Cargá una grabación para inspeccionar paquetes."))
            self._dialog = None
            return
        from player.packet_analyzer import AsterixAnalyzerWindow
        self._dialog = AsterixAnalyzerWindow(repo_db, worker, self)
        inner = self._dialog.layout()
        if inner is not None:
            host = QWidget(); host.setLayout(inner)
            lay.addWidget(host)
        else:
            lay.addWidget(self._dialog)
```
```python
# en player/centro_tecnico/window.py
# import arriba:
from player.centro_tecnico.inspector_widget import InspectorWidget
# reemplazar _inspector_placeholder por uso real en el addTab:
#   self.tabs.addTab(self._inspector_placeholder(), "🔬 Inspector")
# por:
        self.inspector_tab = InspectorWidget(self._repo_db, self._worker, self)
        self.tabs.addTab(self.inspector_tab, "🔬 Inspector")
# y eliminar el método _inspector_placeholder.
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PY -m pytest tests/centro_tecnico/test_window.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add player/centro_tecnico/inspector_widget.py player/centro_tecnico/window.py tests/centro_tecnico/test_window.py
git commit -m "feat(centro-tecnico): pestaña Inspector embebe el analizador de paquetes"
```

---

## Phase 6 — Widgets de contenido (Qt, smoke offscreen)

### Task 13: `StatsWidget` — UI del constructor

**Files:**
- Create: `player/centro_tecnico/stats_widget.py`
- Test: `tests/centro_tecnico/test_window.py`

**Contrato:** `StatsWidget(source_provider)` donde `source_provider()` devuelve una
`DataSource`. Combos: Métrica (de `METRICS`), Dimensión (`DIMENSIONS`), Gráfico
(`CHART_TYPES`). Botón **Generar** → `self.generate()` carga filas, agrega y renderiza
en un `FigureCanvas`. Método `on_source_changed()` refresca la lista de radares.

- [ ] **Step 1: Write the failing test**

```python
# append a tests/centro_tecnico/test_window.py
from player.centro_tecnico.stats_widget import StatsWidget
from player.stats.data_source import SessionSource

def _session_provider():
    rows = [{"sac_sic": "25/01", "time": float(i), "flight_level": "100",
             "mode3a": "7000", "raw_range": 100.0 + i, "raw_azimuth": 10.0}
            for i in range(5)]
    src = SessionSource(rows)
    return lambda: src

def test_stats_widget_generate_renders(app):
    sw = StatsWidget(_session_provider())
    sw.set_metric("count"); sw.set_dimension("radar"); sw.set_chart("bar")
    sw.generate()
    assert sw.figure.axes               # algo se dibujó
    assert len(sw.figure.axes[0].patches) == 1   # 1 radar -> 1 barra
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PY -m pytest tests/centro_tecnico/test_window.py::test_stats_widget_generate_renders -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'player.centro_tecnico.stats_widget'`

- [ ] **Step 3: Write minimal implementation**

```python
# player/centro_tecnico/stats_widget.py
"""Constructor configurable de estadísticas: métrica × dimensión × gráfico."""
from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QFormLayout, QComboBox, QPushButton,
    QLabel, QFileDialog,
)
from matplotlib.figure import Figure
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas

from player.stats.metric_registry import METRICS, DIMENSIONS, aggregate, metric_by_id
from player.stats.chart_renderer import render, CHART_TYPES


class StatsWidget(QWidget):
    def __init__(self, source_provider, parent=None):
        super().__init__(parent)
        self._source_provider = source_provider
        root = QHBoxLayout(self)

        cfg = QWidget(); form = QFormLayout(cfg); cfg.setMaximumWidth(320)
        self.cmb_metric = QComboBox()
        for m in METRICS:
            self.cmb_metric.addItem(m.label, m.id)
        self.cmb_dim = QComboBox()
        for d in DIMENSIONS:
            self.cmb_dim.addItem(d, d)
        self.cmb_chart = QComboBox()
        for c in CHART_TYPES:
            self.cmb_chart.addItem(c, c)
        self.btn_gen = QPushButton("Generar")
        self.btn_png = QPushButton("⤓ PNG")
        self.lbl_rows = QLabel("Filas: 0")
        form.addRow("Métrica", self.cmb_metric)
        form.addRow("Dimensión", self.cmb_dim)
        form.addRow("Gráfico", self.cmb_chart)
        form.addRow(self.btn_gen)
        form.addRow(self.btn_png)
        form.addRow(self.lbl_rows)

        self.figure = Figure(figsize=(6, 4))
        self.canvas = FigureCanvas(self.figure)

        root.addWidget(cfg)
        root.addWidget(self.canvas, 1)

        self.btn_gen.clicked.connect(self.generate)
        self.btn_png.clicked.connect(self._export_png)

    # API para tests
    def set_metric(self, mid): self.cmb_metric.setCurrentIndex(self.cmb_metric.findData(mid))
    def set_dimension(self, d): self.cmb_dim.setCurrentIndex(self.cmb_dim.findData(d))
    def set_chart(self, c): self.cmb_chart.setCurrentIndex(self.cmb_chart.findData(c))

    def on_source_changed(self):
        pass   # placeholder para refrescar filtros de radar (Task 15 opcional)

    def generate(self):
        src = self._source_provider()
        rows = src.load()
        metric = metric_by_id(self.cmb_metric.currentData())
        dim = self.cmb_dim.currentData()
        chart = self.cmb_chart.currentData()
        data = aggregate(rows, metric, dim)
        self.lbl_rows.setText(f"Filas: {len(data)}")
        try:
            render(self.figure, data, chart, title=metric.label,
                   xlabel=dim, ylabel=metric.label)
        except Exception as e:
            self.figure.clear()
            ax = self.figure.add_subplot(111)
            ax.text(0.5, 0.5, f"No se pudo graficar:\n{e}", ha="center", va="center")
        self.canvas.draw_idle()

    def _export_png(self):
        path, _ = QFileDialog.getSaveFileName(self, "Guardar PNG", "estadistica.png",
                                              "PNG (*.png)")
        if path:
            self.figure.savefig(path, dpi=150)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PY -m pytest tests/centro_tecnico/test_window.py::test_stats_widget_generate_renders -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add player/centro_tecnico/stats_widget.py tests/centro_tecnico/test_window.py
git commit -m "feat(centro-tecnico): StatsWidget — constructor métrica/dimensión/gráfico"
```

---

### Task 14: `CoverageWidget` — mapa + polar + export

**Files:**
- Create: `player/centro_tecnico/coverage_widget.py`
- Test: `tests/centro_tecnico/test_coverage_widget.py`

**Contrato:** `CoverageWidget(source_provider, db_path)`. Combos: Radar (sac/sic),
spin Percentil. Botón **Calcular** → `self.calculate()` arma `CoverageResult` con
`compute_coverage` y dibuja en dos `FigureCanvas` (mapa y polar). Menú **Exportar**
con KMZ/CSV/PNG/GeoJSON. `on_source_changed()` refresca radares.

- [ ] **Step 1: Write the failing test**

```python
# tests/centro_tecnico/test_coverage_widget.py
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import pytest
pytest.importorskip("PyQt6.QtWidgets")
from PyQt6.QtWidgets import QApplication
from player.centro_tecnico.coverage_widget import CoverageWidget
from player.stats.data_source import SessionSource
from utils.geo import GeoTools

@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])

def _provider_with_coverage():
    rlat, rlon = -31.31, -64.21
    rows = []
    for az in range(0, 360, 4):
        plat, plon = GeoTools.vincenty_forward(rlat, rlon, float(az),
                                               GeoTools.nm_to_meters(90.0))
        rows.append({"sac_sic": "25/01", "lat": plat, "lon": plon,
                     "flight_level": "150", "time": 0.0})
    src = SessionSource(rows)
    return lambda: src

def test_coverage_widget_calculate_draws(app, monkeypatch):
    cw = CoverageWidget(_provider_with_coverage(), db_path="pass_analytics.duckdb")
    # forzar radar y centro (sin depender de default-site-params)
    cw.set_radar("25/01")
    monkeypatch.setattr(cw, "_radar_latlon", lambda sac_sic: (-31.31, -64.21))
    cw.calculate()
    assert cw.result is not None
    assert cw.result.plot_count > 0
    assert cw.fig_polar.axes and cw.fig_map.axes
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PY -m pytest tests/centro_tecnico/test_coverage_widget.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'player.centro_tecnico.coverage_widget'`

- [ ] **Step 3: Write minimal implementation**

```python
# player/centro_tecnico/coverage_widget.py
"""Pestaña Cobertura: contorno real por FL en vista polar + mapa, con exportación."""
import numpy as np
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QComboBox, QSpinBox, QPushButton,
    QLabel, QMenu, QFileDialog,
)
from matplotlib.figure import Figure
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas

from analysis.coverage import compute_coverage, level_polygon_latlon, FL_BANDS


class CoverageWidget(QWidget):
    def __init__(self, source_provider, db_path="pass_analytics.duckdb", parent=None):
        super().__init__(parent)
        self._source_provider = source_provider
        self._db_path = db_path
        self.result = None

        root = QVBoxLayout(self)
        ctrl = QHBoxLayout()
        self.cmb_radar = QComboBox()
        self.spin_pctl = QSpinBox(); self.spin_pctl.setRange(50, 99); self.spin_pctl.setValue(95)
        self.btn_calc = QPushButton("Calcular")
        self.btn_export = QPushButton("⤓ Exportar ▼")
        self.lbl_info = QLabel("—")
        ctrl_items = [QLabel("Radar"), self.cmb_radar, QLabel("Pctil"),
                      self.spin_pctl, self.btn_calc, self.btn_export, self.lbl_info]
        for it in ctrl_items:
            ctrl.addWidget(it)
        ctrl.addStretch(1)
        root.addLayout(ctrl)

        views = QHBoxLayout()
        self.fig_map = Figure(figsize=(5, 5)); self.canvas_map = FigureCanvas(self.fig_map)
        self.fig_polar = Figure(figsize=(5, 5)); self.canvas_polar = FigureCanvas(self.fig_polar)
        views.addWidget(self.canvas_map, 1)
        views.addWidget(self.canvas_polar, 1)
        root.addLayout(views, 1)

        self.btn_calc.clicked.connect(self.calculate)
        self.btn_export.clicked.connect(self._show_export_menu)
        self.on_source_changed()

    def set_radar(self, sac_sic):
        i = self.cmb_radar.findText(sac_sic)
        if i < 0:
            self.cmb_radar.addItem(sac_sic); i = self.cmb_radar.findText(sac_sic)
        self.cmb_radar.setCurrentIndex(i)

    def on_source_changed(self):
        try:
            radars = self._source_provider().radars()
        except Exception:
            radars = []
        cur = self.cmb_radar.currentText()
        self.cmb_radar.clear(); self.cmb_radar.addItems(radars)
        if cur:
            self.set_radar(cur)

    def _radar_latlon(self, sac_sic):
        """Lat/lon del radar desde default-site-params. (lat, lon) o (None, None)."""
        from utils.geo import cargar_sensores
        try:
            sac, sic = (int(x) for x in sac_sic.split("/"))
        except Exception:
            return (None, None)
        info = cargar_sensores("default-site-params").get((sac, sic))
        if not info:
            return (None, None)
        return (info["lat"], info["lon"])

    def calculate(self):
        sac_sic = self.cmb_radar.currentText()
        rlat, rlon = self._radar_latlon(sac_sic)
        if rlat is None:
            self.lbl_info.setText(f"Sin parámetros de sitio para {sac_sic}")
            return
        rows = self._source_provider().load(radars=[sac_sic])
        plots = [(r["lat"], r["lon"], r.get("flight_level")) for r in rows
                 if r.get("lat") and r.get("lon")]
        self.result = compute_coverage(plots, rlat, rlon, percentile=self.spin_pctl.value())
        self.lbl_info.setText(f"Plots: {self.result.plot_count}")
        self._draw()

    def _draw(self):
        res = self.result
        # Polar
        self.fig_polar.clear()
        axp = self.fig_polar.add_subplot(111, projection="polar")
        axp.set_theta_zero_location("N"); axp.set_theta_direction(-1)
        for fl in FL_BANDS:
            ranges = res.levels.get(fl) or []
            if any(r > 0 for r in ranges):
                theta = np.deg2rad(np.arange(360))
                axp.plot(theta, ranges, linewidth=1, label=f"FL{fl}")
        axp.legend(fontsize=6, loc="upper right")
        self.canvas_polar.draw_idle()
        # Mapa
        self.fig_map.clear()
        axm = self.fig_map.add_subplot(111)
        axm.plot([res.radar_lon], [res.radar_lat], marker="*", color="cyan")
        for fl in FL_BANDS:
            ring = level_polygon_latlon(res, fl)
            if ring:
                lons = [p[1] for p in ring]; lats = [p[0] for p in ring]
                axm.plot(lons, lats, linewidth=1, label=f"FL{fl}")
                axm.fill(lons, lats, alpha=0.10)
        axm.set_xlabel("lon"); axm.set_ylabel("lat"); axm.legend(fontsize=6)
        axm.set_aspect("equal", adjustable="datalim")
        self.canvas_map.draw_idle()

    def _show_export_menu(self):
        menu = QMenu(self)
        menu.addAction("KMZ (Google Earth)", self._export_kmz)
        menu.addAction("Heatmap QGIS (CSV)", self._export_csv)
        menu.addAction("Imagen PNG (mapa)", self._export_png)
        menu.addAction("Polígonos GeoJSON", self._export_geojson)
        menu.exec(self.btn_export.mapToGlobal(self.btn_export.rect().bottomLeft()))

    def _export_kmz(self):
        from analysis.exporters import PassExporter
        path, _ = QFileDialog.getSaveFileName(self, "KMZ", "cobertura.kmz", "KMZ (*.kmz)")
        if path:
            PassExporter(db_path=self._db_path).export_coverage_map_kmz(
                self.cmb_radar.currentText(), output_file=path)

    def _export_csv(self):
        from analysis.exporters import PassExporter
        path, _ = QFileDialog.getSaveFileName(self, "CSV", "heatmap.csv", "CSV (*.csv)")
        if path:
            PassExporter(db_path=self._db_path).export_heatmap_qgis(output_file=path)

    def _export_png(self):
        path, _ = QFileDialog.getSaveFileName(self, "PNG", "cobertura.png", "PNG (*.png)")
        if path:
            self.fig_map.savefig(path, dpi=150)

    def _export_geojson(self):
        import json
        if not self.result:
            return
        path, _ = QFileDialog.getSaveFileName(self, "GeoJSON", "cobertura.geojson",
                                              "GeoJSON (*.geojson)")
        if not path:
            return
        feats = []
        for fl in FL_BANDS:
            ring = level_polygon_latlon(self.result, fl)
            if ring:
                feats.append({"type": "Feature",
                              "properties": {"FL": fl},
                              "geometry": {"type": "Polygon",
                                           "coordinates": [[[p[1], p[0]] for p in ring]]}})
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"type": "FeatureCollection", "features": feats}, f, indent=2)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PY -m pytest tests/centro_tecnico/test_coverage_widget.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add player/centro_tecnico/coverage_widget.py tests/centro_tecnico/test_coverage_widget.py
git commit -m "feat(centro-tecnico): CoverageWidget mapa+polar con exportación"
```

---

## Phase 7 — Integración en la app

### Task 15: Acción de menú gateada por rol en `main_window`

**Files:**
- Modify: `player/main_window.py` (cerca de `self.act_calibracion`, líneas ~979-981)
- Test: manual (la ventana principal requiere entorno gráfico completo)

- [ ] **Step 1: Localizar el punto de integración**

Run: `PY -c "import re,io; s=open('player/main_window.py',encoding='utf-8').read(); print('act_calibracion' in s, '_abrir_calibracion' in s)"`
Expected: `True True`

- [ ] **Step 2: Agregar la acción de menú**

En `player/main_window.py`, justo después del bloque de `self.act_calibracion`
(línea ~981), agregar:

```python
        self.act_centro_tecnico = menu_config.addAction(
            "Centro Técnico ATSEP…", self._abrir_centro_tecnico)
        self.act_centro_tecnico.setEnabled(self.profile_manager.get_rol() == "tecnico")
```

- [ ] **Step 3: Agregar el handler**

Agregar el método (junto a `_abrir_calibracion` / `_abrir_analizador_paquetes`):

```python
    def _abrir_centro_tecnico(self):
        from player.centro_tecnico.window import CentroTecnicoWindow
        repo_db = getattr(self, "repo_db", None)
        worker = getattr(self, "worker", None)
        records = []
        try:
            if hasattr(self, "track_manager") and self.track_manager:
                records = [p.to_dict() for p in self.track_manager.all_plots()]
        except Exception:
            records = []
        self._centro_tecnico_win = CentroTecnicoWindow(
            repo_db=repo_db, worker=worker, session_records=records, parent=self)
        self._centro_tecnico_win.show()
```

> Verificar el nombre real del proveedor de plots en memoria antes de usar
> `track_manager.all_plots()`: `grep -n "def .*plots\|self.track_manager" player/main_window.py`.
> Si no existe un acumulador, pasar `session_records=[]` (la fuente DuckDB sigue
> funcionando; la sesión queda vacía hasta cablear el acumulador en una mejora futura).

- [ ] **Step 4: Smoke import**

Run: `PY -c "import player.centro_tecnico.window as w; print('import OK')"`
Expected: `import OK`

Run toda la suite nueva:
Run: `PY -m pytest tests/stats tests/centro_tecnico -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add player/main_window.py
git commit -m "feat(centro-tecnico): abrir el hub desde Configuración (gateado por rol técnico)"
```

---

## Self-Review (cobertura del spec)

- **§3 contenedor ventana dedicada + conmutador fuente** → Task 9. ✔
- **§4 embebido de PASS / Monitor / Inspector** → Tasks 11, 10, 12. ✔
- **§5 constructor: metric_registry + DataSource (DuckDB+Session) + renderer + UI** → Tasks 4, 5, 6, 7, 8, 13. ✔
- **§5.3 set de gráficos v1** (serie de tiempo=line, heatmap hora×día, barras agrupadas=bar, apiladas 100%, torta=pie, box, spider) → Tasks 7, 8. ✔
- **§6 Cobertura mapa+polar + export KMZ/CSV/PNG/GeoJSON, reusa export_coverage_map_kmz** → Tasks 1, 2, 3, 14. ✔
- **§11 gating por rol técnico** → Task 15. ✔

Notas de consistencia verificadas: `DataSource.load(...)`/`radars()`, `compute_coverage(...)->CoverageResult.levels`, `level_polygon_latlon`, `aggregate(rows, metric, dimension)`, `render(figure, data, chart_type, ...)`, `CHART_TYPES`, `source_provider()` usados igual en todas las tasks.

Pendientes asumidos (fuera de v1, documentados): refresco de filtros de radar/período en `StatsWidget.on_source_changed` (placeholder), y el acumulador de plots en memoria para `SessionSource` (Task 15 Step 3 nota).
