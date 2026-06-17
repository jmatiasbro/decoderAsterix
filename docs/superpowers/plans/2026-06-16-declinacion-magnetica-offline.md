# Declinación magnética offline (grilla + WMM + isógonas) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Que la app obtenga la declinación magnética por coordenada sin depender de `pygeomag` en runtime (grilla offline) y dibuje líneas isógonas toggleables en PPI + satélite, conservando el WMM exacto cuando esté disponible.

**Architecture:** Una grilla precalculada (JSON) se genera offline desde el WMM. Un loader Python puro la interpola (bilineal). `MagneticCompensator` aplica la cascada WMM → grilla → offset estático. Las isógonas se extraen de la grilla con marching squares, se guardan como GeoJSON y se cargan como capa `MAGVAR::ISOGONAS` del `map_manager`, que PPI y vista FIR pintan automáticamente.

**Tech Stack:** Python puro (stdlib `json`, `math`), `pygeomag` (solo en generación), PyQt6 (capa visual, ya integrada vía `VideoMapManager`).

**Convención de signo:** declinación en grados, **oeste negativo** (`pygeomag` `res.d`), consistente con `analysis/geo_math.calcular_rumbo_magnetico`.

**Entorno de tests:** intérprete nativo `C:\Users\Usuario\AppData\Local\Programs\Python\Python312\python.exe`. Para tests que tocan Qt: `QT_QPA_PLATFORM=offscreen`.

---

## File Structure

- Create: `player/geo/__init__.py` — paquete de utilidades geográficas.
- Create: `player/geo/isogonic.py` — marching squares → polilíneas por nivel.
- Create: `player/geo/declination_grid.py` — loader + interpolación bilineal de la grilla.
- Create: `tools/gen_declination_grid.py` — genera la grilla JSON y el GeoJSON de isógonas desde el WMM.
- Create (generado): `data/magnetic/declination_grid.json`
- Create (generado): `data/magnetic/isogonic_lines.geojson`
- Modify: `player/magnetic_compensator.py` — cascada de fuentes.
- Modify: `player/main_window.py` — acción de menú + `_toggle_isogonas`.
- Test: `tests/geo/test_isogonic.py`, `tests/geo/test_declination_grid.py`, `tests/geo/test_magnetic_cascade.py`, `tests/geo/test_isogonic_layer.py`.

---

## Task 1: Extracción de isógonas (marching squares)

**Files:**
- Create: `player/geo/__init__.py`
- Create: `player/geo/isogonic.py`
- Test: `tests/geo/test_isogonic.py`

- [ ] **Step 1: Crear el paquete**

Create `player/geo/__init__.py` con contenido vacío (un solo salto de línea).

- [ ] **Step 2: Write the failing test**

Create `tests/geo/test_isogonic.py`:

```python
from player.geo.isogonic import contour_lines


def _grid_value_lon(n_lat, n_lon, lat_min, lon_min, step):
    # value(i, j) = longitud del nodo -> isógonas verticales en lon = nivel
    return [[lon_min + j * step for j in range(n_lon)] for _ in range(n_lat)]


def test_contour_follows_requested_level():
    values = _grid_value_lon(4, 5, 0.0, 0.0, 1.0)
    lines = contour_lines(values, lat_min=0.0, lon_min=0.0, step=1.0, levels=[2.0])
    segs = lines[2.0]
    assert segs, "debe haber al menos un segmento en el nivel 2.0"
    for poly in segs:
        for (lat, lon) in poly:
            assert abs(lon - 2.0) < 1e-9
            assert 0.0 <= lat <= 3.0


def test_auto_levels_are_interior_integers():
    values = _grid_value_lon(3, 5, 0.0, 0.0, 1.0)  # rango lon 0..4
    lines = contour_lines(values, lat_min=0.0, lon_min=0.0, step=1.0)
    assert {1.0, 2.0, 3.0} <= set(lines.keys())
    assert 0.0 not in lines and 4.0 not in lines  # no niveles en los bordes


def test_empty_when_level_out_of_range():
    values = _grid_value_lon(3, 3, 0.0, 0.0, 1.0)  # lon 0..2
    lines = contour_lines(values, lat_min=0.0, lon_min=0.0, step=1.0, levels=[9.0])
    assert lines.get(9.0, []) == []
```

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest tests/geo/test_isogonic.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'player.geo.isogonic'`.

- [ ] **Step 4: Write minimal implementation**

Create `player/geo/isogonic.py`:

```python
"""Marching squares puro: convierte una grilla escalar (declinación) en
polilíneas por nivel. Sin dependencias externas.

`values[i][j]` corresponde al nodo (lat_min + i*step, lon_min + j*step).
Devuelve {nivel: [polilinea, ...]} con polilinea = [(lat, lon), ...].
Cada polilínea es un segmento de 2 puntos (sin unir): suficiente para
dibujar como cartografía.
"""
import math


def _auto_levels(values):
    flat = [v for row in values for v in row if v is not None]
    if not flat:
        return []
    lo, hi = min(flat), max(flat)
    return [float(n) for n in range(math.ceil(lo + 1e-9), math.floor(hi - 1e-9) + 1)]


def _interp(p1, v1, p2, v2, level):
    if v2 == v1:
        return p1
    t = (level - v1) / (v2 - v1)
    return (p1[0] + t * (p2[0] - p1[0]), p1[1] + t * (p2[1] - p1[1]))


def contour_lines(values, lat_min, lon_min, step, levels=None):
    n_lat = len(values)
    n_lon = len(values[0]) if n_lat else 0
    if levels is None:
        levels = _auto_levels(values)
    out = {float(lv): [] for lv in levels}
    for i in range(n_lat - 1):
        for j in range(n_lon - 1):
            # esquinas: TL, TR, BR, BL  (lat crece con i, lon crece con j)
            tl = (lat_min + i * step, lon_min + j * step)
            tr = (lat_min + i * step, lon_min + (j + 1) * step)
            br = (lat_min + (i + 1) * step, lon_min + (j + 1) * step)
            bl = (lat_min + (i + 1) * step, lon_min + j * step)
            vtl, vtr = values[i][j], values[i][j + 1]
            vbr, vbl = values[i + 1][j + 1], values[i + 1][j]
            if None in (vtl, vtr, vbr, vbl):
                continue
            edges = [(tl, vtl, tr, vtr), (tr, vtr, br, vbr),
                     (br, vbr, bl, vbl), (bl, vbl, tl, vtl)]
            for lv in levels:
                lv = float(lv)
                cross = []
                for (pa, va, pb, vb) in edges:
                    if (va <= lv < vb) or (vb <= lv < va):
                        cross.append(_interp(pa, va, pb, vb, lv))
                # 2 cruces -> un segmento; 4 cruces (silla) -> dos pares por orden
                for k in range(0, len(cross) - 1, 2):
                    out[lv].append([cross[k], cross[k + 1]])
    return out
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/geo/test_isogonic.py -v`
Expected: PASS (3 tests).

- [ ] **Step 6: Commit**

```bash
git add player/geo/__init__.py player/geo/isogonic.py tests/geo/test_isogonic.py
git commit -m "feat(magvar): marching squares para lineas isogonas"
```

---

## Task 2: Loader + interpolación bilineal de la grilla

**Files:**
- Create: `player/geo/declination_grid.py`
- Test: `tests/geo/test_declination_grid.py`

- [ ] **Step 1: Write the failing test**

Create `tests/geo/test_declination_grid.py`:

```python
import json
from player.geo import declination_grid as dg


def _grid():
    # value(i, j) = i + j sobre lat -1..1, lon -1..1, step 1
    return {"convention": "west-negative", "epoch": 2026.0,
            "lat_min": -1.0, "lat_max": 1.0, "lon_min": -1.0, "lon_max": 1.0,
            "step": 1.0, "n_lat": 3, "n_lon": 3,
            "values": [[r + c for c in range(3)] for r in range(3)]}


def test_interpolate_bilinear_center():
    g = _grid()
    # centro de la celda (0,0): esquinas 0,1,1,2 -> 1.0
    assert abs(dg.interpolate(g, -0.5, -0.5) - 1.0) < 1e-9


def test_interpolate_on_node():
    g = _grid()
    assert abs(dg.interpolate(g, 0.0, 1.0) - dg.G_NODE(g, 1, 2)) < 1e-9  # i=1,j=2 -> 3


def test_interpolate_clamps_outside_bbox():
    g = _grid()
    v = dg.interpolate(g, -50.0, -50.0)   # clamp a esquina (i0,j0) = 0
    assert abs(v - 0.0) < 1e-9


def test_declinacion_returns_none_when_file_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(dg, "DEFAULT_PATH", str(tmp_path / "nope.json"))
    dg._CACHE.clear()
    assert dg.declinacion(-34.6, -58.4) is None


def test_declinacion_reads_file(tmp_path, monkeypatch):
    p = tmp_path / "grid.json"
    p.write_text(json.dumps(_grid()), encoding="utf-8")
    monkeypatch.setattr(dg, "DEFAULT_PATH", str(p))
    dg._CACHE.clear()
    assert abs(dg.declinacion(-0.5, -0.5) - 1.0) < 1e-9
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/geo/test_declination_grid.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'player.geo.declination_grid'`.

- [ ] **Step 3: Write minimal implementation**

Create `player/geo/declination_grid.py`:

```python
"""Loader + interpolación bilineal de la grilla offline de declinación magnética.

Python puro (stdlib). Fuente de respaldo del WMM: ver player/magnetic_compensator.py.
"""
import json
import os

DEFAULT_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "data", "magnetic", "declination_grid.json")

_CACHE = {}   # path -> grid dict | None


def G_NODE(grid, i, j):
    return grid["values"][i][j]


def _clamp(v, lo, hi):
    return lo if v < lo else hi if v > hi else v


def interpolate(grid, lat, lon):
    """Declinación interpolada (bilineal). Clampa al bbox de la grilla."""
    step = grid["step"]
    lat = _clamp(lat, grid["lat_min"], grid["lat_max"])
    lon = _clamp(lon, grid["lon_min"], grid["lon_max"])
    fi = (lat - grid["lat_min"]) / step
    fj = (lon - grid["lon_min"]) / step
    i0 = min(int(fi), grid["n_lat"] - 2) if grid["n_lat"] > 1 else 0
    j0 = min(int(fj), grid["n_lon"] - 2) if grid["n_lon"] > 1 else 0
    di, dj = fi - i0, fj - j0
    v = grid["values"]
    v00, v01 = v[i0][j0], v[i0][j0 + 1]
    v10, v11 = v[i0 + 1][j0], v[i0 + 1][j0 + 1]
    top = v00 + (v01 - v00) * dj
    bot = v10 + (v11 - v10) * dj
    return top + (bot - top) * di


def load(path=None):
    path = path or DEFAULT_PATH
    if path in _CACHE:
        return _CACHE[path]
    grid = None
    try:
        with open(path, "r", encoding="utf-8") as f:
            grid = json.load(f)
    except (OSError, ValueError):
        grid = None
    _CACHE[path] = grid
    return grid


def declinacion(lat, lon):
    """Declinación en (lat, lon) o None si la grilla no está disponible."""
    if lat is None or lon is None:
        return None
    grid = load(DEFAULT_PATH)
    if not grid:
        return None
    return interpolate(grid, lat, lon)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/geo/test_declination_grid.py -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add player/geo/declination_grid.py tests/geo/test_declination_grid.py
git commit -m "feat(magvar): loader e interpolacion bilineal de la grilla"
```

---

## Task 3: Generador de artefactos (grilla JSON + GeoJSON de isógonas)

**Files:**
- Create: `tools/gen_declination_grid.py`
- Create (generado): `data/magnetic/declination_grid.json`
- Create (generado): `data/magnetic/isogonic_lines.geojson`

- [ ] **Step 1: Write the generator**

Create `tools/gen_declination_grid.py`:

```python
"""Genera la grilla offline de declinación magnética y la cartografía de isógonas
a partir del World Magnetic Model (pygeomag). Re-ejecutar para actualizar la época.

  python tools/gen_declination_grid.py
"""
import datetime
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from player.geo.isogonic import contour_lines  # noqa: E402

LAT_MIN, LAT_MAX = -56.0, -21.0
LON_MIN, LON_MAX = -76.0, -52.0
STEP = 1.0
OUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "data", "magnetic")


def _anio_decimal(fecha=None):
    fecha = fecha or datetime.date.today()
    ini = datetime.date(fecha.year, 1, 1).toordinal()
    fin = datetime.date(fecha.year + 1, 1, 1).toordinal()
    return round(fecha.year + (fecha.toordinal() - ini) / (fin - ini), 2)


def build_grid(geomag, epoch):
    n_lat = int(round((LAT_MAX - LAT_MIN) / STEP)) + 1
    n_lon = int(round((LON_MAX - LON_MIN) / STEP)) + 1
    values = []
    for i in range(n_lat):
        lat = LAT_MIN + i * STEP
        row = []
        for j in range(n_lon):
            lon = LON_MIN + j * STEP
            row.append(round(float(geomag.calculate(glat=lat, glon=lon, alt=0,
                                                     time=epoch).d), 3))
        values.append(row)
    return {"convention": "west-negative", "epoch": epoch,
            "lat_min": LAT_MIN, "lat_max": LAT_MAX,
            "lon_min": LON_MIN, "lon_max": LON_MAX,
            "step": STEP, "n_lat": n_lat, "n_lon": n_lon, "values": values}


def grid_to_geojson(grid):
    lines = contour_lines(grid["values"], grid["lat_min"], grid["lon_min"],
                          grid["step"])
    features = []
    for level in sorted(lines):
        segs = lines[level]
        for poly in segs:
            features.append({
                "type": "Feature",
                "properties": {"layer": "ISOGONAS", "name": f"{level:.0f}°"},
                "geometry": {"type": "LineString",
                             "coordinates": [[lon, lat] for (lat, lon) in poly]},
            })
        # una etiqueta por nivel, en el punto medio del segmento central
        if segs:
            mid = segs[len(segs) // 2]
            la, lo = mid[0]
            features.append({
                "type": "Feature",
                "properties": {"layer": "NOMBRES_WAYPOINTS", "type": "text",
                               "name": f"{level:.0f}°"},
                "geometry": {"type": "Point", "coordinates": [lo, la]},
            })
    return {"type": "FeatureCollection", "color": "#FF40FF", "features": features}


def main():
    from pygeomag import GeoMag
    os.makedirs(OUT_DIR, exist_ok=True)
    epoch = _anio_decimal()
    grid = build_grid(GeoMag(), epoch)
    with open(os.path.join(OUT_DIR, "declination_grid.json"), "w",
              encoding="utf-8") as f:
        json.dump(grid, f)
    with open(os.path.join(OUT_DIR, "isogonic_lines.geojson"), "w",
              encoding="utf-8") as f:
        json.dump(grid_to_geojson(grid), f)
    print(f"OK epoch={epoch} grid={grid['n_lat']}x{grid['n_lon']} "
          f"isogonas={sum(1 for x in grid_to_geojson(grid)['features'] if x['geometry']['type']=='LineString')}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run the generator**

Run: `python tools/gen_declination_grid.py`
Expected: imprime `OK epoch=20XX.X grid=36x25 isogonas=<N>` y crea los dos archivos en `data/magnetic/`.

- [ ] **Step 3: Verify the artifacts**

Run:
```bash
python -c "import json; g=json.load(open('data/magnetic/declination_grid.json')); print(g['n_lat'], g['n_lon'], len(g['values']), len(g['values'][0]))"
```
Expected: `36 25 36 25`.

Run:
```bash
python -c "import json; d=json.load(open('data/magnetic/isogonic_lines.geojson')); t=[f['geometry']['type'] for f in d['features']]; print('LineString' in t, 'Point' in t)"
```
Expected: `True True`.

- [ ] **Step 4: Sanity check del valor (cruza con WMM)**

Run:
```bash
python -c "from player.geo import declination_grid as dg; dg._CACHE.clear(); print(round(dg.declinacion(-34.6,-58.4),1))"
```
Expected: aproximadamente `-10.2` (Buenos Aires).

- [ ] **Step 5: Commit**

```bash
git add tools/gen_declination_grid.py data/magnetic/declination_grid.json data/magnetic/isogonic_lines.geojson
git commit -m "feat(magvar): generador y artefactos offline (grilla + isogonas)"
```

---

## Task 4: Cascada de fuentes en MagneticCompensator

**Files:**
- Modify: `player/magnetic_compensator.py`
- Test: `tests/geo/test_magnetic_cascade.py`

- [ ] **Step 1: Write the failing test**

Create `tests/geo/test_magnetic_cascade.py`:

```python
from player.magnetic_compensator import MagneticCompensator
from player.geo import declination_grid as dg


def test_grid_used_when_wmm_absent(monkeypatch):
    mc = MagneticCompensator(fallback_deg=-7.0)
    mc._geomag = None                       # simula WMM no disponible
    mc._cache.clear()
    monkeypatch.setattr(dg, "declinacion", lambda lat, lon: 5.0)
    assert mc.obtener_declinacion(-34.6, -58.4) == 5.0


def test_static_fallback_when_grid_absent(monkeypatch):
    mc = MagneticCompensator(fallback_deg=-7.0)
    mc._geomag = None
    mc._cache.clear()
    monkeypatch.setattr(dg, "declinacion", lambda lat, lon: None)
    assert mc.obtener_declinacion(-34.6, -58.4) == -7.0


def test_none_coords_return_fallback():
    mc = MagneticCompensator(fallback_deg=-7.0)
    assert mc.obtener_declinacion(None, None) == -7.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/geo/test_magnetic_cascade.py -v`
Expected: FAIL en `test_grid_used_when_wmm_absent` (hoy con `_geomag=None` devuelve `fallback_deg`, no `5.0`).

- [ ] **Step 3: Edit the implementation**

En `player/magnetic_compensator.py`, reemplazar el cuerpo de `obtener_declinacion` (líneas 40-61) por:

```python
    def obtener_declinacion(self, latitud, longitud, altitud_ft: float = 0.0) -> float:
        """Declinación en grados (oeste negativo). Cascada: WMM -> grilla -> estático."""
        if latitud is None or longitud is None:
            return self.fallback_deg

        clave = (round(latitud, 2), round(longitud, 2))  # celda ~1 km
        cached = self._cache.get(clave)
        if cached is not None:
            return cached

        dec = None
        # 1) WMM exacto (modelo local, sin red)
        if self._geomag is not None:
            try:
                alt_km = (altitud_ft or 0.0) * 0.0003048
                dec = float(self._geomag.calculate(
                    glat=float(latitud), glon=float(longitud),
                    alt=alt_km, time=_anio_decimal()).d)
            except Exception:
                dec = None
        # 2) Grilla offline
        if dec is None:
            from player.geo import declination_grid as _dg
            g = _dg.declinacion(latitud, longitud)
            dec = g if g is not None else self.fallback_deg  # 3) estático

        self._cache[clave] = dec
        return dec
```

Y actualizar el cómputo de `self.disponible` en `__init__` (línea 38) por:

```python
        self.disponible = _PYGEOMAG_OK
        if not self.disponible:
            from player.geo import declination_grid as _dg
            self.disponible = _dg.load() is not None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/geo/test_magnetic_cascade.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Regresión rápida del módulo**

Run: `pytest tests/geo -v`
Expected: PASS (todos).

- [ ] **Step 6: Commit**

```bash
git add player/magnetic_compensator.py tests/geo/test_magnetic_cascade.py
git commit -m "feat(magvar): cascada WMM -> grilla -> estatico en el compensador"
```

---

## Task 5: Capa visual de isógonas (toggle en menú, PPI + satélite)

**Files:**
- Modify: `player/main_window.py` (en `_rebuild_areas_menu`, tras el bloque MSA ~líneas 3702-3707; nuevo método junto a `_toggle_msa_sectores`)
- Test: `tests/geo/test_isogonic_layer.py`

- [ ] **Step 1: Write the failing test (carga del artefacto como capa)**

Create `tests/geo/test_isogonic_layer.py`:

```python
import os
import pytest

pytestmark = pytest.mark.skipif(
    not os.path.exists("data/magnetic/isogonic_lines.geojson"),
    reason="requiere el artefacto generado (Task 3)")


def test_geojson_loads_as_map_layer():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PyQt6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    from player.video_map_manager import VideoMapManager
    mm = VideoMapManager()
    mm.load_geojson("data/magnetic/isogonic_lines.geojson",
                    "MAGVAR::ISOGONAS", "TACTICO")
    assert "MAGVAR::ISOGONAS" in mm.layers
    segs = mm.layers["MAGVAR::ISOGONAS"].raw_segments
    kinds = {s[0] for s in segs}
    assert "M" in kinds and "L" in kinds   # polilíneas
    assert "T" in kinds                    # etiquetas de nivel
```

- [ ] **Step 2: Run test to verify it fails or passes**

Run: `QT_QPA_PLATFORM=offscreen pytest tests/geo/test_isogonic_layer.py -v`
Expected: PASS (el artefacto ya existe de Task 3 y `load_geojson` ya soporta el formato). Si falla por falta de `T`, revisar que `grid_to_geojson` emita los `Point type:"text"`.

- [ ] **Step 3: Agregar la acción de menú**

En `player/main_window.py`, dentro de `_rebuild_areas_menu`, justo después de la línea `self.act_msa_sectores.toggled.connect(self._toggle_msa_sectores)` (≈3707), agregar:

```python
        self.act_isogonas = self.menu_areas.addAction("Mostrar isógonas (declinación)")
        self.act_isogonas.setCheckable(True)
        self.act_isogonas.setChecked(getattr(self, '_isogonas_on', False))
        self.act_isogonas.toggled.connect(self._toggle_isogonas)
```

- [ ] **Step 4: Agregar el método toggle**

En `player/main_window.py`, inmediatamente después del método `_toggle_msa_sectores` (después de su `return`/`self.radar.update()`, ≈línea 3732), agregar:

```python
    def _toggle_isogonas(self, on):
        """Muestra/oculta las líneas isógonas (declinación magnética) en PPI y FIR."""
        import os
        self._isogonas_on = on
        mm = getattr(self.radar, 'map_manager', None)
        if mm is None:
            return
        name = "MAGVAR::ISOGONAS"
        if on:
            path = "data/magnetic/isogonic_lines.geojson"
            if not os.path.exists(path):
                print("[MAGVAR] Falta data/magnetic/isogonic_lines.geojson "
                      "(corré tools/gen_declination_grid.py)")
                return
            mm.load_geojson(path, name, "TACTICO")
            if name in mm.layers:
                mm.layers[name].color = "#FF40FF"
            if getattr(self.radar, 'proy', None) is not None:
                mm.reproject_all(self.radar.proy)
        else:
            mm.layers.pop(name, None)
        self.radar.update()
```

- [ ] **Step 5: Verify import sanity (sin abrir la GUI)**

Run: `QT_QPA_PLATFORM=offscreen python -c "import ast; ast.parse(open('player/main_window.py').read()); print('syntax ok')"`
Expected: `syntax ok`.

- [ ] **Step 6: Commit**

```bash
git add player/main_window.py tests/geo/test_isogonic_layer.py
git commit -m "feat(magvar): capa toggleable de isogonas en PPI + satelite"
```

---

## Task 6: Verificación final

- [ ] **Step 1: Suite completa de geo + firmap**

Run: `QT_QPA_PLATFORM=offscreen pytest tests/geo tests/firmap -q`
Expected: todos PASS.

- [ ] **Step 2: Confirmar cascada con WMM presente**

Run:
```bash
python -c "from player.magnetic_compensator import MagneticCompensator as M; mc=M(-7.0); print(round(mc.obtener_declinacion(-34.6,-58.4),1), mc.disponible)"
```
Expected: `-10.2 True` (usa WMM, el valor exacto; la grilla está como respaldo).

---

## Notas de integración

- PPI: `radar_widget._draw_map_layers` ya pinta toda capa `TACTICO` reproyectada; `MAGVAR::ISOGONAS` no empieza con `AREA::`, así que se dibuja como línea (sin relleno). ✓
- Satélite (FIR): `firmap/feed.build_maps` incluye toda capa visible del `map_manager`; `is_area` es `False` para `MAGVAR::ISOGONAS`, se dibuja como polilínea fina con etiquetas. ✓
- Color `#FF40FF` (magenta) elegido para no chocar con áreas (rojo/ámbar) ni aerovías (cian/otros).
