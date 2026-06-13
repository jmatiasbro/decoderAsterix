# PPI EUROCONTROL ODS Refactor — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactorizar la consola PPI (`player/radar_widget.py`) para que la **vista controlador** cumpla las convenciones EUROCONTROL ODS (ED-128 / ICAO Doc 4444), sin depender de datos de plan de vuelo.

**Architecture:** Se extrae la lógica de presentación a un paquete nuevo `player/ods/` con funciones **puras y testeables** (clasificación de estado de track, paleta, simbología, FDB, declutter, rosa de rumbos). `radar_widget.py` pasa a **delegar** en esos módulos en sus puntos de dibujo ya existentes (`_draw_oaci_track`, `_draw_cat62_plot`, `_build_plot_label_lines`). La vista técnica conserva su estética actual (barrido, color por SAC/SIC); solo la vista controlador adopta ODS.

**Tech Stack:** Python 3.12, PyQt6 (`QPainter`), pytest. Sin datos de plan de vuelo (se omiten campos CFL/XFL/PEL; el nivel es FL actual + tendencia).

**Restricción de scope (CLAUDE.md):** modificar solo lo necesario; no refactorizar la vista técnica ni el pipeline de decodificación.

**Notas de entorno (memoria del proyecto):**
- Python nativo: `C:\Users\Usuario\AppData\Local\Programs\Python\Python312\python.exe` (la `.venv` está rota por WSL).
- Tests GUI: `QT_QPA_PLATFORM=offscreen`.
- En esta máquina no hay GPU en headless → el radar cae a `QWidget` (no afecta estos tests).

A lo largo del plan: `PY="C:\Users\Usuario\AppData\Local\Programs\Python\Python312\python.exe"`.

---

## File Structure

**Nuevos (lógica pura + tests):**
- `player/ods/__init__.py` — paquete.
- `player/ods/track_state.py` — clasifica un plot en estado ODS (PSR/SSR/COMBINED/ADSB/SYSTEM_TRACK/COASTING).
- `player/ods/palette.py` — paleta ODS + color por estado de track e intensidad por capa.
- `player/ods/symbology.py` — símbolo por estado (forma, tamaño px constante) y `draw_symbol()`.
- `player/ods/fdb.py` — construcción de líneas del Full/Limited Data Block (sin plan de vuelo).
- `player/ods/declutter.py` — relajación de colisiones de etiquetas (extraída y testeada).
- `player/ods/compass.py` — ticks de rosa de rumbos + leyenda de alcance.
- `tests/ods/test_track_state.py`, `test_palette.py`, `test_symbology.py`, `test_fdb.py`, `test_declutter.py`, `test_compass.py`.

**Modificados (integración):**
- `player/radar_widget.py`
  - `_draw_oaci_track` (def ~4720) — símbolo + color ODS.
  - `_draw_cat62_plot` (def ~5081) — símbolo system-track ODS.
  - `_build_plot_label_lines` (def ~4204) — delega en `ods/fdb.py`.
  - `_get_sensor_color` (def ~911) — en vista controlador usa color por estado.
  - Bloque declutter (~3446-3484) — delega en `ods/declutter.py`.
  - `paintEvent` (~3131 sweep, ~3175 plots) — rosa de rumbos, leyenda de alcance, intensidad por capa, sweep off por defecto en controlador.
- `player/main_window.py` — wiring de toggles ODS (intensidad por capa, mostrar rosa).

---

## Convención de tests

Todos los módulos nuevos son **pure-Python sin Qt** salvo `symbology.py`/`compass.py` (que reciben un `QPainter` solo en su función `draw_*`; la lógica de specs es pura y se testea sin Qt). Ejecutar:

```
$PY -m pytest tests/ods/ -v
```

Si `pytest` no está: `$PY -m pip install pytest`.

---

## Phase 0 — Scaffolding

### Task 0: Crear el paquete `player/ods/` y carpeta de tests

**Files:**
- Create: `player/ods/__init__.py`
- Create: `tests/ods/__init__.py`

- [ ] **Step 1: Crear el paquete**

`player/ods/__init__.py`:
```python
"""Presentación EUROCONTROL ODS para el PPI (símbolos, paleta, FDB, declutter).

Lógica pura y testeable que `radar_widget.py` consume en sus puntos de dibujo.
Solo aplica a la vista controlador; la vista técnica conserva su estética.
"""
```

`tests/ods/__init__.py`:
```python
```

- [ ] **Step 2: Verificar import**

Run: `$PY -c "import player.ods; print('ok')"`
Expected: `ok`

- [ ] **Step 3: Commit**

```bash
git add player/ods/__init__.py tests/ods/__init__.py
git commit -m "chore(ods): scaffold paquete de presentacion ODS"
```

---

## Phase 1 — Clasificación de estado de track

El símbolo ODS depende del **origen/calidad** del track, no de la categoría ASTERIX.

### Task 1: `track_state.py`

**Files:**
- Create: `player/ods/track_state.py`
- Test: `tests/ods/test_track_state.py`

- [ ] **Step 1: Escribir el test que falla**

`tests/ods/test_track_state.py`:
```python
from player.ods.track_state import classify, PSR_ONLY, SSR, COMBINED, ADSB, SYSTEM_TRACK, COASTING


class P:
    """Stub mínimo con los atributos que lee classify()."""
    def __init__(self, category=48, mode3a=None, mode_s=None, det_type=None):
        self.category = category
        self.mode3a = mode3a
        self.mode_s = mode_s
        self.raw_dict = {"det_type": det_type} if det_type is not None else {}


def test_cat62_es_system_track():
    assert classify(P(category=62), is_coasting=False) == SYSTEM_TRACK

def test_cat21_es_adsb():
    assert classify(P(category=21, mode_s="ABCDEF"), is_coasting=False) == ADSB

def test_cat48_sin_codigo_es_psr():
    assert classify(P(category=48), is_coasting=False) == PSR_ONLY

def test_cat48_con_squawk_es_ssr():
    assert classify(P(category=48, mode3a="7000"), is_coasting=False) == SSR

def test_cat48_combinado_por_det_type():
    # TYP=3 (SSR+PSR) en I048/020
    assert classify(P(category=48, mode3a="7000", det_type=3), is_coasting=False) == COMBINED

def test_coasting_tiene_prioridad():
    assert classify(P(category=62), is_coasting=True) == COASTING
```

- [ ] **Step 2: Correr y verificar que falla**

Run: `$PY -m pytest tests/ods/test_track_state.py -v`
Expected: FAIL `ModuleNotFoundError: player.ods.track_state`

- [ ] **Step 3: Implementar**

`player/ods/track_state.py`:
```python
"""Clasificación de un plot/track en su estado de presentación ODS.

El símbolo se elige por origen/calidad de la información, no por categoría ASTERIX.
`is_coasting` lo decide el llamador (depende del tiempo de simulación vs. scan rate).
"""

PSR_ONLY = "PSR_ONLY"        # primario no correlado
SSR = "SSR"                  # secundario / Mode-S correlado
COMBINED = "COMBINED"        # PSR + SSR
ADSB = "ADSB"                # ADS-B (CAT021)
SYSTEM_TRACK = "SYSTEM_TRACK"  # track de sistema (CAT062 / tracker)
COASTING = "COASTING"        # track sin actualización reciente


def _det_type(plot):
    """TYP de I048/020 si está disponible (0..7); None si no."""
    rd = getattr(plot, "raw_dict", None) or {}
    t = rd.get("det_type")
    if t is None and isinstance(rd.get("extra_data"), dict):
        t = rd["extra_data"].get("det_type")
    return t


def _tiene_squawk(plot):
    m = getattr(plot, "mode3a", None)
    if m is None:
        return False
    s = f"{m:04o}" if isinstance(m, int) else str(m).strip()
    return s not in ("", "----", "0000")


def classify(plot, is_coasting: bool) -> str:
    if is_coasting:
        return COASTING
    cat = getattr(plot, "category", None)
    if cat == 62:
        return SYSTEM_TRACK
    if cat == 21:
        return ADSB
    # CAT048 / CAT001: distinguir por detección
    typ = _det_type(plot)
    if typ in (3, 6, 7):  # combinaciones PSR+SSR en I048/020
        return COMBINED
    if typ == 1:          # PSR only
        return PSR_ONLY
    # Sin det_type fiable: inferir por presencia de código/dirección
    if _tiene_squawk(plot) or getattr(plot, "mode_s", None):
        return SSR
    return PSR_ONLY
```

- [ ] **Step 4: Correr y verificar PASS**

Run: `$PY -m pytest tests/ods/test_track_state.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
git add player/ods/track_state.py tests/ods/test_track_state.py
git commit -m "feat(ods): clasificacion de estado de track ODS"
```

---

## Phase 2 — Paleta ODS

Base casi monocroma + estado por calidad de track; color reservado para alertas; intensidad por capa.

### Task 2: `palette.py`

**Files:**
- Create: `player/ods/palette.py`
- Test: `tests/ods/test_palette.py`

- [ ] **Step 1: Test que falla**

`tests/ods/test_palette.py`:
```python
from player.ods import palette as P
from player.ods.track_state import PSR_ONLY, SSR, COMBINED, ADSB, SYSTEM_TRACK, COASTING


def test_fondo_es_gris_neutro_oscuro():
    # Gris neutro (R≈G≈B), oscuro pero no negro puro
    r, g, b = P.BG
    assert max(r, g, b) <= 30 and abs(r - g) <= 6 and abs(g - b) <= 6

def test_cada_estado_tiene_color():
    for st in (PSR_ONLY, SSR, COMBINED, ADSB, SYSTEM_TRACK, COASTING):
        assert st in P.STATE_RGB
        assert len(P.STATE_RGB[st]) == 3

def test_seleccionado_es_mas_brillante_que_normal():
    base = P.state_rgb(SYSTEM_TRACK, selected=False)
    sel = P.state_rgb(SYSTEM_TRACK, selected=True)
    assert sum(sel) > sum(base)

def test_alpha_por_intensidad_clampa():
    assert P.layer_alpha("labels", 0.0) == 0
    assert P.layer_alpha("labels", 1.0) == 255
    assert 0 <= P.layer_alpha("labels", 0.5) <= 255

def test_alerta_stca_es_rojo_dominante():
    r, g, b = P.ALERT_STCA
    assert r > 180 and g < 120 and b < 120
```

- [ ] **Step 2: Correr y verificar que falla**

Run: `$PY -m pytest tests/ods/test_palette.py -v`
Expected: FAIL `ModuleNotFoundError`

- [ ] **Step 3: Implementar**

`player/ods/palette.py`:
```python
"""Paleta EUROCONTROL ODS para la vista controlador.

Principios (ED-128 / ISO 9241): fondo gris neutro oscuro, datos normales de baja
saturación casi monocromos, color saturado reservado a alertas, intensidad por
capa ajustable por el controlador.
"""
from .track_state import PSR_ONLY, SSR, COMBINED, ADSB, SYSTEM_TRACK, COASTING

# Fondo gris neutro (no azul-negro). RGB.
BG = (18, 18, 18)

# Color por estado de track (RGB), baja saturación.
STATE_RGB = {
    SYSTEM_TRACK: (208, 216, 208),  # blanco-verdoso: track confirmado
    COMBINED:     (200, 208, 200),
    SSR:          (150, 200, 160),  # verde apagado: secundario correlado
    ADSB:         (150, 190, 210),  # cian apagado: ADS-B
    PSR_ONLY:     (140, 150, 140),  # gris-verde tenue: primario no correlado
    COASTING:     (120, 110, 90),   # ámbar muy apagado: sin actualización
}

# Colores reservados de alerta (saturados).
ALERT_STCA = (230, 60, 60)    # rojo
ALERT_MSAW = (235, 170, 40)   # ámbar
SELECTED = (255, 255, 255)    # blanco puro para el track seleccionado

# Intensidad por capa (0..1) por defecto; el controlador la ajusta.
LAYER_DEFAULT = {
    "map": 0.35, "rings": 0.30, "labels": 0.90, "history": 0.55,
    "symbols": 1.0, "compass": 0.45,
}


def _clamp(v, lo, hi):
    return lo if v < lo else hi if v > hi else v


def state_rgb(state: str, selected: bool = False):
    if selected:
        return SELECTED
    return STATE_RGB.get(state, STATE_RGB[PSR_ONLY])


def layer_alpha(layer: str, intensity: float) -> int:
    """Alpha 0..255 a partir de la intensidad 0..1 de la capa."""
    return int(round(_clamp(intensity, 0.0, 1.0) * 255))
```

- [ ] **Step 4: PASS**

Run: `$PY -m pytest tests/ods/test_palette.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add player/ods/palette.py tests/ods/test_palette.py
git commit -m "feat(ods): paleta ODS por estado e intensidad por capa"
```

---

## Phase 3 — Simbología (tamaño en píxeles constante)

### Task 3: `symbology.py` — specs puras

**Files:**
- Create: `player/ods/symbology.py`
- Test: `tests/ods/test_symbology.py`

- [ ] **Step 1: Test que falla**

`tests/ods/test_symbology.py`:
```python
from player.ods import symbology as S
from player.ods.track_state import PSR_ONLY, SSR, COMBINED, ADSB, SYSTEM_TRACK, COASTING


def test_cada_estado_tiene_spec():
    for st in (PSR_ONLY, SSR, COMBINED, ADSB, SYSTEM_TRACK, COASTING):
        spec = S.symbol_spec(st)
        assert spec.shape in S.SHAPES
        assert spec.size_px > 0

def test_psr_y_ssr_tienen_formas_distintas():
    assert S.symbol_spec(PSR_ONLY).shape != S.symbol_spec(SSR).shape

def test_coasting_es_punteado():
    assert S.symbol_spec(COASTING).dashed is True

def test_system_track_no_es_punteado():
    assert S.symbol_spec(SYSTEM_TRACK).dashed is False

def test_tamano_constante_no_depende_de_zoom():
    # symbol_spec no recibe zoom: el tamaño es en px de pantalla
    import inspect
    assert "zoom" not in inspect.signature(S.symbol_spec).parameters
```

- [ ] **Step 2: Falla**

Run: `$PY -m pytest tests/ods/test_symbology.py -v`
Expected: FAIL `ModuleNotFoundError`

- [ ] **Step 3: Implementar specs + draw**

`player/ods/symbology.py`:
```python
"""Simbología de posición ODS. El tamaño es en PÍXELES de pantalla (constante,
no escala con el zoom); el centroide del símbolo es la posición exacta del track.
"""
from dataclasses import dataclass
from .track_state import PSR_ONLY, SSR, COMBINED, ADSB, SYSTEM_TRACK, COASTING

SHAPES = {"plus", "square", "diamond", "filled_square", "track", "x"}


@dataclass(frozen=True)
class SymbolSpec:
    shape: str
    size_px: float
    dashed: bool = False
    pen_px: float = 1.4


_SPECS = {
    PSR_ONLY:     SymbolSpec("plus", 5.0),
    SSR:          SymbolSpec("square", 5.0),
    COMBINED:     SymbolSpec("filled_square", 5.0),
    ADSB:         SymbolSpec("diamond", 5.5),
    SYSTEM_TRACK: SymbolSpec("track", 5.0, pen_px=1.6),
    COASTING:     SymbolSpec("square", 5.0, dashed=True),
}


def symbol_spec(state: str) -> SymbolSpec:
    return _SPECS.get(state, _SPECS[PSR_ONLY])


def draw_symbol(painter, spec: SymbolSpec, x_px: float, y_px: float, qcolor):
    """Dibuja el símbolo en coordenadas de PANTALLA (sin scale activo).

    El llamador debe haber restaurado la transformación a píxeles (identity);
    ver integración en radar_widget (_draw_oaci_track).
    """
    from PyQt6.QtCore import QPointF, Qt
    from PyQt6.QtGui import QPen, QBrush
    s = spec.size_px
    pen = QPen(qcolor)
    pen.setWidthF(spec.pen_px)
    if spec.dashed:
        pen.setStyle(Qt.PenStyle.DashLine)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    c = QPointF(x_px, y_px)
    sh = spec.shape
    if sh == "plus":
        painter.drawLine(QPointF(x_px - s, y_px), QPointF(x_px + s, y_px))
        painter.drawLine(QPointF(x_px, y_px - s), QPointF(x_px, y_px + s))
    elif sh == "x":
        painter.drawLine(QPointF(x_px - s, y_px - s), QPointF(x_px + s, y_px + s))
        painter.drawLine(QPointF(x_px - s, y_px + s), QPointF(x_px + s, y_px - s))
    elif sh in ("square", "filled_square"):
        if sh == "filled_square":
            painter.setBrush(QBrush(qcolor))
        painter.drawRect(int(x_px - s), int(y_px - s), int(2 * s), int(2 * s))
    elif sh == "diamond":
        painter.drawPolygon(QPointF(x_px, y_px - s), QPointF(x_px + s, y_px),
                            QPointF(x_px, y_px + s), QPointF(x_px - s, y_px))
    elif sh == "track":
        # cuadrado + punto central (track de sistema)
        painter.drawRect(int(x_px - s), int(y_px - s), int(2 * s), int(2 * s))
        painter.setBrush(QBrush(qcolor))
        painter.drawEllipse(c, 1.2, 1.2)
```

- [ ] **Step 4: PASS**

Run: `$PY -m pytest tests/ods/test_symbology.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Smoke de dibujo (offscreen)**

Run:
```
QT_QPA_PLATFORM=offscreen $PY -c "from PyQt6.QtGui import QImage,QPainter,QColor; from player.ods import symbology as S; from player.ods.track_state import SSR; img=QImage(40,40,QImage.Format.Format_ARGB32); img.fill(0); p=QPainter(img); S.draw_symbol(p,S.symbol_spec(SSR),20,20,QColor(150,200,160)); p.end(); print('drawn', img.pixelColor(20,15).alpha()>0 or img.pixelColor(15,20).alpha()>0)"
```
Expected: `drawn True`

- [ ] **Step 6: Commit**

```bash
git add player/ods/symbology.py tests/ods/test_symbology.py
git commit -m "feat(ods): simbologia por estado, tamano px constante"
```

---

## Phase 4 — Full/Limited Data Block (sin plan de vuelo)

### Task 4: `fdb.py`

**Files:**
- Create: `player/ods/fdb.py`
- Test: `tests/ods/test_fdb.py`

- [ ] **Step 1: Test que falla**

`tests/ods/test_fdb.py`:
```python
from player.ods import fdb


class P:
    def __init__(self, callsign="", mode3a=None, fl=None, gs=None, vrate=None):
        self.callsign = callsign
        self.mode3a = mode3a
        self.flight_level = fl
        self.ground_speed = gs
        self.vertical_rate_ftmin = vrate


def test_level_con_tendencia_subiendo():
    assert fdb.format_level(330, 800) == "FL330↑"

def test_level_con_tendencia_bajando():
    assert fdb.format_level(330, -800) == "FL330↓"

def test_level_nivelado():
    assert fdb.format_level(330, 50) == "FL330="

def test_fdb_tres_lineas_track_correlado():
    p = P(callsign="IBE123", mode3a="2345", fl=330, gs=420, vrate=0)
    lines = fdb.build_lines(p, full=True)
    assert lines[0] == "IBE123"
    assert lines[1] == "FL330="
    assert lines[2] == "420"

def test_ldb_sin_callsign_usa_squawk():
    p = P(callsign="", mode3a="2345", fl=330)
    lines = fdb.build_lines(p, full=False)
    assert lines[0] == "2345"
```

- [ ] **Step 2: Falla**

Run: `$PY -m pytest tests/ods/test_fdb.py -v`
Expected: FAIL `ModuleNotFoundError`

- [ ] **Step 3: Implementar**

`player/ods/fdb.py`:
```python
"""Construcción del Data Block ODS (FDB/LDB). Sin datos de plan de vuelo:
el nivel es FL actual + flecha de tendencia (no hay CFL/XFL).
"""
ARROW_UP = "↑"     # ↑
ARROW_DOWN = "↓"   # ↓
ARROW_LEVEL = "="
VRATE_THRESHOLD = 100.0  # ft/min para considerar climb/descent


def format_level(fl, vrate_ftmin) -> str:
    if fl is None:
        return ""
    try:
        fl_i = int(round(float(fl)))
    except (TypeError, ValueError):
        return ""
    arrow = ARROW_LEVEL
    if vrate_ftmin is not None:
        if vrate_ftmin > VRATE_THRESHOLD:
            arrow = ARROW_UP
        elif vrate_ftmin < -VRATE_THRESHOLD:
            arrow = ARROW_DOWN
    return f"FL{fl_i:03d}{arrow}"


def _squawk(plot) -> str:
    m = getattr(plot, "mode3a", None)
    if m is None:
        return ""
    s = f"{m:04o}" if isinstance(m, int) else str(m).strip()
    return "" if s in ("", "----", "0000") else s


def build_lines(plot, full: bool = True):
    """Devuelve líneas del data block.

    L1: callsign (o squawk si no hay). L2: FL+tendencia. L3 (solo FDB): GS.
    """
    callsign = (getattr(plot, "callsign", "") or "").strip()
    squawk = _squawk(plot)
    l1 = callsign or squawk
    lines = []
    if l1:
        lines.append(l1)
    lvl = format_level(getattr(plot, "flight_level", None),
                       getattr(plot, "vertical_rate_ftmin", None))
    if lvl:
        lines.append(lvl)
    if full:
        gs = getattr(plot, "ground_speed", None)
        if gs is not None:
            try:
                lines.append(f"{int(round(float(gs)))}")
            except (TypeError, ValueError):
                pass
    return lines
```

- [ ] **Step 4: PASS**

Run: `$PY -m pytest tests/ods/test_fdb.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add player/ods/fdb.py tests/ods/test_fdb.py
git commit -m "feat(ods): data block FDB/LDB sin plan de vuelo"
```

---

## Phase 5 — Declutter (extracción + test)

El algoritmo de repulsión ya existe inline en `radar_widget.py` (~3446-3484). Se extrae a función pura.

### Task 5: `declutter.py`

**Files:**
- Create: `player/ods/declutter.py`
- Test: `tests/ods/test_declutter.py`

- [ ] **Step 1: Test que falla**

`tests/ods/test_declutter.py`:
```python
from player.ods.declutter import resolve_shifts


def test_dos_etiquetas_encimadas_se_separan():
    centers = {"a": (100.0, 100.0, 40.0), "b": (105.0, 102.0, 40.0)}
    shifts = resolve_shifts(centers, min_dist=50.0, passes=2)
    ax, ay = centers["a"][0] + shifts["a"][0], centers["a"][1] + shifts["a"][1]
    bx, by = centers["b"][0] + shifts["b"][0], centers["b"][1] + shifts["b"][1]
    d = ((ax - bx) ** 2 + (ay - by) ** 2) ** 0.5
    assert d > 5.0  # se separaron respecto al original (≈5.4)

def test_etiquetas_lejanas_no_se_mueven():
    centers = {"a": (0.0, 0.0, 40.0), "b": (500.0, 500.0, 40.0)}
    shifts = resolve_shifts(centers, min_dist=50.0, passes=2)
    assert shifts["a"] == [0.0, 0.0] and shifts["b"] == [0.0, 0.0]
```

- [ ] **Step 2: Falla**

Run: `$PY -m pytest tests/ods/test_declutter.py -v`
Expected: FAIL `ModuleNotFoundError`

- [ ] **Step 3: Implementar (lógica idéntica a la inline existente)**

`player/ods/declutter.py`:
```python
"""Relajación de colisiones de etiquetas (anti-solape) por repulsión de fuerzas.
Extraído de radar_widget._draw... para poder testearlo sin Qt.
"""
import math


def resolve_shifts(centers: dict, min_dist: float = 50.0, passes: int = 2) -> dict:
    """centers: {id: (cx, cy, ancho)} en píxeles. Devuelve {id: [dx, dy]}."""
    shifts = {tid: [0.0, 0.0] for tid in centers}
    ids = list(centers.keys())
    for _ in range(passes):
        for i in range(len(ids)):
            t1 = ids[i]
            c1x, c1y, _w1 = centers[t1]
            for j in range(i + 1, len(ids)):
                t2 = ids[j]
                c2x, c2y, _w2 = centers[t2]
                dx = (c1x + shifts[t1][0]) - (c2x + shifts[t2][0])
                dy = (c1y + shifts[t1][1]) - (c2y + shifts[t2][1])
                dist = math.sqrt(dx * dx + dy * dy)
                if dist < min_dist:
                    if dist < 1.0:
                        dist = 1.0
                    angle = math.atan2(dy, dx)
                    force = (min_dist - dist) * 0.5
                    rx, ry = force * math.cos(angle), force * math.sin(angle)
                    shifts[t1][0] += rx
                    shifts[t1][1] += ry
                    shifts[t2][0] -= rx
                    shifts[t2][1] -= ry
    return shifts
```

- [ ] **Step 4: PASS**

Run: `$PY -m pytest tests/ods/test_declutter.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add player/ods/declutter.py tests/ods/test_declutter.py
git commit -m "feat(ods): extraer declutter de etiquetas a funcion pura"
```

---

## Phase 6 — Integración de simbología, color y FDB en el renderer

> A partir de aquí se edita `player/radar_widget.py`. **Antes de cada edición, leer el bloque actual de la función nombrada** (las líneas se dieron como referencia y pueden haberse corrido).

### Task 6.1: `_build_plot_label_lines` delega en `ods/fdb.py` (solo controlador)

**Files:**
- Modify: `player/radar_widget.py` (`_build_plot_label_lines`, def ~4204)

- [ ] **Step 1: Inyectar la rama ODS al inicio de la función**

Leer la función y, justo después de la línea `es_ctrl = getattr(self, 'vista_controlador', False)`, insertar:
```python
        # ODS: en vista controlador el data block sigue el formato FDB/LDB estándar.
        if es_ctrl and getattr(self, 'ods_enabled', True):
            from player.ods import fdb as _fdb
            plot.vertical_rate_ftmin = self._estimar_vrate(plot)  # reusa estimación existente
            return _fdb.build_lines(plot, full=True)
```

- [ ] **Step 2: Extraer la estimación de vertical rate a un helper reutilizable**

En la misma función ya existe el cálculo de `rate_of_climb` (~4256-4283). Extraerlo a un método nuevo `_estimar_vrate(self, plot) -> float | None` (mover el bloque tal cual, devolviendo el valor) y reemplazar el cálculo inline por `rate_of_climb = self._estimar_vrate(plot)`.

Agregar el método (al lado de `_build_plot_label_lines`):
```python
    def _estimar_vrate(self, plot):
        """ft/min: usa vertical_rate del mensaje, o lo estima del historial de FL."""
        rate = None
        if plot.raw_dict:
            rate = plot.raw_dict.get('vertical_rate_ftmin')
            if rate is None and 'extra_data' in plot.raw_dict:
                rate = plot.raw_dict['extra_data'].get('vertical_rate_ftmin')
        if rate is not None:
            return rate
        if plot.id in self.history and plot.flight_level is not None:
            hist = list(self.history[plot.id])
            curr_fl, curr_time = plot.flight_level, plot.timestamp
            past_pt = None
            for pt in reversed(hist):
                if pt.timestamp > 0 and pt.fl and pt.timestamp < curr_time - 2.0:
                    past_pt = pt
                    if pt.timestamp < curr_time - 5.0:
                        break
            if past_pt is not None:
                try:
                    if past_pt.fl.startswith("FL"):
                        past_fl = float(past_pt.fl[2:])
                        dt = curr_time - past_pt.timestamp
                        if dt > 0:
                            return ((curr_fl - past_fl) * 100.0 / dt) * 60.0
                except Exception:
                    pass
        return 0.0
```

- [ ] **Step 3: Smoke (offscreen) — la vista controlador devuelve FDB**

Run:
```
QT_QPA_PLATFORM=offscreen $PY -c "
from PyQt6.QtWidgets import QApplication; app=QApplication([])
from player.radar_widget import RadarWidget, RadarPlot
w=RadarWidget(); w.vista_controlador=True; w.ods_enabled=True
import time
p=RadarPlot(x=0,y=0,timestamp=0,mode3a='2345',callsign='IBE123',flight_level=330,is_track=True,mode_s=None,category=62,sac=1,sic=1)
print(w._build_plot_label_lines(p))
"
```
Expected: lista tipo `['IBE123', 'FL330=', ...]` (la firma exacta de `RadarPlot.__init__` puede requerir kwargs; ver `RadarPlot` def ~312/328 y ajustar el stub).

- [ ] **Step 4: Correr la suite ODS**

Run: `$PY -m pytest tests/ods/ -v`
Expected: PASS (todos)

- [ ] **Step 5: Commit**

```bash
git add player/radar_widget.py
git commit -m "feat(ods): data block FDB en vista controlador"
```

### Task 6.2: símbolo + color ODS en `_draw_oaci_track`

**Files:**
- Modify: `player/radar_widget.py` (`_draw_oaci_track`, def ~4720; `_draw_cat62_plot`, def ~5081)

- [ ] **Step 1: Helper de coasting**

Agregar método `_is_coasting(self, plot) -> bool` (al lado de `_draw_oaci_track`). Usar la edad del track vs. scan time (lógica equivalente a la de la estela, ~3199-3202):
```python
    def _is_coasting(self, plot):
        try:
            rpm = self.sensor_rpms.get((plot.sac, plot.sic), self.sweep_rpm)
            scan = 60.0 / rpm if rpm > 0 else 5.0
            edad = SimulationTime.time() - plot.timestamp
            return edad > 1.5 * scan
        except Exception:
            return False
```

- [ ] **Step 2: Insertar render ODS al inicio de `_draw_oaci_track`**

Leer `_draw_oaci_track`. Justo después de obtener las coords de pantalla del símbolo (buscar el `self._world_to_screen(...)` o equivalente al comienzo), insertar la rama ODS que dibuja el símbolo en píxeles y retorna temprano de la parte de símbolo (manteniendo el resto: etiqueta, leader, vector):
```python
        if getattr(self, 'vista_controlador', False) and getattr(self, 'ods_enabled', True):
            from player.ods import track_state as _ts, symbology as _sym, palette as _pal
            from PyQt6.QtGui import QColor
            sp = self._world_to_screen(plot.x, plot.y)
            if sp is not None:
                estado = _ts.classify(plot, self._is_coasting(plot))
                seleccionado = (getattr(self, '_focused_track_id', None) == plot.id)
                rgb = _pal.state_rgb(estado, selected=seleccionado)
                spec = _sym.symbol_spec(estado)
                painter.save()
                painter.resetTransform()  # dibujar en px de pantalla, tamaño constante
                _sym.draw_symbol(painter, spec, sp.x(), sp.y(),
                                 QColor(rgb[0], rgb[1], rgb[2]))
                painter.restore()
                self._draw_track_label_ods(painter, plot, sp, QColor(rgb[0], rgb[1], rgb[2]))
                return
```

- [ ] **Step 3: Etiqueta ODS con leader line**

Agregar `_draw_track_label_ods(self, painter, plot, sp, qcolor)` que: arma las líneas con `_build_plot_label_lines` (ya devuelve FDB), aplica el shift de `self._label_shifts_cache.get(plot.id, [0,0])`, dibuja una **leader line** del símbolo a la etiqueta y el texto, en píxeles (`painter.resetTransform()`), con alpha de capa `labels`:
```python
    def _draw_track_label_ods(self, painter, plot, sp, qcolor):
        from PyQt6.QtGui import QColor, QPen, QFont
        from PyQt6.QtCore import QPointF, Qt
        lines = self._build_plot_label_lines(plot)
        if not lines:
            return
        shift = self._label_shifts_cache.get(plot.id, [0.0, 0.0]) if hasattr(self, '_label_shifts_cache') else [0.0, 0.0]
        lx, ly = sp.x() + 14 + shift[0], sp.y() - 14 + shift[1]
        painter.save()
        painter.resetTransform()
        intens = getattr(self, 'ods_layer_intensity', {})
        from player.ods import palette as _pal
        a = _pal.layer_alpha("labels", intens.get("labels", _pal.LAYER_DEFAULT["labels"]))
        col = QColor(qcolor); col.setAlpha(a)
        pen = QPen(col); pen.setWidthF(1.0)
        painter.setPen(pen)
        painter.drawLine(QPointF(sp.x(), sp.y()), QPointF(lx, ly))  # leader line
        painter.setFont(QFont("Consolas", 8))
        fm = painter.fontMetrics()
        for i, ln in enumerate(lines):
            painter.drawText(QPointF(lx, ly + i * (fm.height() - 1)), str(ln))
        painter.restore()
```

- [ ] **Step 4: `_draw_cat62_plot` usa símbolo SYSTEM_TRACK**

En `_draw_cat62_plot`, al inicio, agregar la misma rama ODS (estado forzado `SYSTEM_TRACK` vía `_ts.classify`, que ya devuelve SYSTEM_TRACK para CAT62) y `return` tras dibujar símbolo+label, igual que en 6.2 Step 2. Reusar `_draw_track_label_ods`.

- [ ] **Step 5: Smoke render (offscreen, no crash + pinta algo)**

Run:
```
QT_QPA_PLATFORM=offscreen $PY -c "
from PyQt6.QtWidgets import QApplication; app=QApplication([])
from player.radar_widget import RadarWidget
w=RadarWidget(); w.vista_controlador=True; w.ods_enabled=True; w.resize(400,400)
img=w.grab().toImage()
print('rendered', img.width(), img.height())
"
```
Expected: `rendered 400 400` (sin excepción).

- [ ] **Step 6: Commit**

```bash
git add player/radar_widget.py
git commit -m "feat(ods): simbolo/color/leader-line ODS en tracks (vista controlador)"
```

### Task 6.3: color por estado en `_get_sensor_color` (solo controlador)

**Files:**
- Modify: `player/radar_widget.py` (`_get_sensor_color`, def ~911)

- [ ] **Step 1: Cortocircuito ODS**

Leer `_get_sensor_color`. Insertar al comienzo:
```python
        # En vista controlador ODS el color es por estado de track, no por sensor.
        # (Las estelas/labels llaman a este método; se mantiene SAC/SIC en vista técnica.)
        # No-op aquí: el color de símbolo lo decide _draw_oaci_track; este método
        # solo afecta estelas. Se atenúan a gris neutro en controlador.
        if getattr(self, 'vista_controlador', False) and getattr(self, 'ods_enabled', True):
            from PyQt6.QtGui import QColor
            return QColor(150, 158, 150)
```

- [ ] **Step 2: Smoke (no crash)**

Run: `$PY -m pytest tests/ods/ -v` (regresión de módulos) → PASS.
Visual: ver checkpoint en Task 10.

- [ ] **Step 3: Commit**

```bash
git add player/radar_widget.py
git commit -m "feat(ods): estelas en gris neutro en vista controlador"
```

### Task 6.4: usar `ods/declutter.py` en el bloque de relajación

**Files:**
- Modify: `player/radar_widget.py` (~3446-3484)

- [ ] **Step 1: Reemplazar el doble for inline por la función pura**

Leer el bloque de "Relajación iterativa de colisiones" (~3446-3482). Sustituir el cuerpo (las 2 pasadas) por:
```python
                from player.ods.declutter import resolve_shifts
                _centers = {tid: (cx, cy, w) for tid, (cx, cy, w) in default_centers.items()}
                _res = resolve_shifts(_centers, min_dist=50.0, passes=2)
                for tid, (dx, dy) in _res.items():
                    label_shifts[tid][0] += dx
                    label_shifts[tid][1] += dy
```

- [ ] **Step 2: Smoke render (offscreen)**

Run: el mismo comando `w.grab()` de Task 6.2 Step 5 → `rendered 400 400`.

- [ ] **Step 3: Commit**

```bash
git add player/radar_widget.py
git commit -m "refactor(ods): declutter via funcion pura testeada"
```

---

## Phase 7 — Rosa de rumbos + leyenda de alcance

### Task 7.1: `compass.py` — geometría pura

**Files:**
- Create: `player/ods/compass.py`
- Test: `tests/ods/test_compass.py`

- [ ] **Step 1: Test que falla**

`tests/ods/test_compass.py`:
```python
from player.ods import compass


def test_ticks_cada_10_grados():
    ticks = compass.bearing_ticks()
    assert len(ticks) == 36

def test_mayores_cada_30_grados_rotulados():
    ticks = {t.deg: t for t in compass.bearing_ticks()}
    assert ticks[0].major and ticks[0].label == "360"
    assert ticks[30].major and ticks[30].label == "030"
    assert not ticks[10].major and ticks[10].label == ""

def test_range_marks_devuelve_nm_y_radio_px():
    marks = compass.range_marks(radius_px=300.0, range_nm=60.0, step_nm=20.0)
    assert marks[0] == (20.0, 100.0)
    assert marks[-1][0] <= 60.0
```

- [ ] **Step 2: Falla**

Run: `$PY -m pytest tests/ods/test_compass.py -v`
Expected: FAIL `ModuleNotFoundError`

- [ ] **Step 3: Implementar**

`player/ods/compass.py`:
```python
"""Geometría de la rosa de rumbos y marcas de alcance (ODS). Pura."""
from dataclasses import dataclass


@dataclass(frozen=True)
class BearingTick:
    deg: int
    major: bool
    label: str


def bearing_ticks(major_every: int = 30, minor_every: int = 10):
    ticks = []
    for d in range(0, 360, minor_every):
        major = (d % major_every == 0)
        label = ""
        if major:
            label = "360" if d == 0 else f"{d:03d}"
        ticks.append(BearingTick(d, major, label))
    return ticks


def range_marks(radius_px: float, range_nm: float, step_nm: float):
    """Devuelve [(nm, radio_px), ...] para cada anillo hasta range_nm."""
    out = []
    nm = step_nm
    while nm <= range_nm + 1e-6:
        out.append((nm, radius_px * (nm / range_nm)))
        nm += step_nm
    return out
```

- [ ] **Step 4: PASS**

Run: `$PY -m pytest tests/ods/test_compass.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add player/ods/compass.py tests/ods/test_compass.py
git commit -m "feat(ods): geometria de rosa de rumbos y marcas de alcance"
```

### Task 7.2: dibujar la rosa + leyenda en el `paintEvent` (controlador)

**Files:**
- Modify: `player/radar_widget.py` (`paintEvent`; agregar `_draw_compass_rose`)

- [ ] **Step 1: Método de dibujo**

Agregar:
```python
    def _draw_compass_rose(self, painter):
        """Rosa de rumbos en el borde + leyenda de alcance, en px de pantalla."""
        from PyQt6.QtGui import QColor, QPen, QFont
        from PyQt6.QtCore import QPointF, Qt
        import math as _m
        from player.ods import compass as _c, palette as _pal
        w, h = self.width(), self.height()
        cx, cy = w / 2.0 + self.pan_x, h / 2.0 + self.pan_y
        radius = min(w, h) * 0.46
        intens = getattr(self, 'ods_layer_intensity', {})
        a = _pal.layer_alpha("compass", intens.get("compass", _pal.LAYER_DEFAULT["compass"]))
        col = QColor(200, 208, 200, a)
        painter.save()
        painter.resetTransform()
        painter.setPen(QPen(col, 1.0))
        painter.setFont(QFont("Consolas", 7))
        for t in _c.bearing_ticks():
            ang = _m.radians(t.deg)  # 0=Norte, horario
            sin_a, cos_a = _m.sin(ang), -_m.cos(ang)
            inner = radius - (10 if t.major else 5)
            painter.drawLine(QPointF(cx + sin_a * inner, cy + cos_a * inner),
                             QPointF(cx + sin_a * radius, cy + cos_a * radius))
            if t.major:
                lr = radius + 10
                painter.drawText(QPointF(cx + sin_a * lr - 8, cy + cos_a * lr + 4), t.label)
        painter.restore()
```

- [ ] **Step 2: Llamarlo al final del render, solo en controlador**

Leer el final del `try` del `paintEvent` (antes de `painter.restore()` global / `painter.end()`). Insertar:
```python
            if getattr(self, 'vista_controlador', False) and getattr(self, 'ods_enabled', True):
                self._draw_compass_rose(painter)
```

- [ ] **Step 3: Smoke render**

Run: comando `w.grab()` de Task 6.2 Step 5 → `rendered 400 400`.

- [ ] **Step 4: Commit**

```bash
git add player/radar_widget.py
git commit -m "feat(ods): rosa de rumbos y leyenda de alcance en vista controlador"
```

---

## Phase 8 — Intensidad por capa + barrido off por defecto (controlador)

### Task 8.1: estado de intensidad y default de sweep

**Files:**
- Modify: `player/radar_widget.py` (`__init__`, ~687; sweep gating ~3131)

- [ ] **Step 1: Inicializar config ODS en `__init__`**

Tras `self.vista_controlador = False` (línea ~747), agregar:
```python
        # --- Config ODS (vista controlador) ---
        from player.ods import palette as _pal
        self.ods_enabled = True
        self.ods_layer_intensity = dict(_pal.LAYER_DEFAULT)
```

- [ ] **Step 2: Barrido off por defecto en controlador**

El gating ya es `if (not self.vista_controlador) and self.sweep_visible and self.sweep_enabled` (~3131). Asegurar además que al activar la vista controlador se apague el sweep. Buscar el setter de `vista_controlador` (o donde se asigna); si no hay setter, crear `set_vista_controlador(self, on)`:
```python
    def set_vista_controlador(self, on: bool):
        self.vista_controlador = bool(on)
        if on:
            self.sweep_enabled = False
            self.sweep_visible = False
        self.update()
```
y reemplazar las asignaciones directas `self.vista_controlador = ...` en `main_window.py` por `self.radar.set_vista_controlador(...)`.

- [ ] **Step 3: Setter de intensidad**

```python
    def set_ods_layer_intensity(self, layer: str, value: float):
        self.ods_layer_intensity[layer] = max(0.0, min(1.0, value))
        self.update()
```

- [ ] **Step 4: Smoke**

Run:
```
QT_QPA_PLATFORM=offscreen $PY -c "
from PyQt6.QtWidgets import QApplication; app=QApplication([])
from player.radar_widget import RadarWidget
w=RadarWidget(); w.set_vista_controlador(True)
print('sweep off?', not w.sweep_enabled, 'intens labels', w.ods_layer_intensity['labels'])
"
```
Expected: `sweep off? True intens labels 0.9`

- [ ] **Step 5: Commit**

```bash
git add player/radar_widget.py player/main_window.py
git commit -m "feat(ods): intensidad por capa y barrido off en vista controlador"
```

### Task 8.2: aplicar intensidad de mapa/rings/history

**Files:**
- Modify: `player/radar_widget.py` (`_draw_video_maps` ~2775; estela ~3219-3265; rings)

- [ ] **Step 1: Multiplicar alpha de capas por su intensidad (solo controlador)**

En cada capa, cuando `vista_controlador and ods_enabled`, escalar el alpha del color por `self.ods_layer_intensity[layer]`. Patrón a aplicar en mapa (`map`), anillos (`rings`) e historial (`history`):
```python
            if getattr(self, 'vista_controlador', False) and getattr(self, 'ods_enabled', True):
                from player.ods import palette as _pal
                _f = self.ods_layer_intensity.get("map", _pal.LAYER_DEFAULT["map"])
                color.setAlphaF(min(1.0, color.alphaF() * (0.3 + _f)))
```
(ajustar la clave `"map"`/`"rings"`/`"history"` por capa).

- [ ] **Step 2: Smoke render** → `rendered 400 400`.

- [ ] **Step 3: Commit**

```bash
git add player/radar_widget.py
git commit -m "feat(ods): intensidad ajustable de mapa/anillos/historial"
```

---

## Phase 9 — Presentación estándar de STCA

### Task 9: halo + parpadeo + color reservado para conflictos

**Files:**
- Modify: `player/radar_widget.py` (bloque de líneas de conflicto ~3519-3522+)

- [ ] **Step 1: Leer el bloque de `conflictos_activos`** y, para cada par en conflicto, en vista controlador: dibujar un **halo** alrededor de ambos símbolos con `ALERT_STCA`, la línea de conexión en rojo, y parpadeo por reloj de simulación:
```python
            if getattr(self, 'vista_controlador', False) and getattr(self, 'ods_enabled', True):
                from player.ods import palette as _pal
                from PyQt6.QtGui import QColor, QPen
                from PyQt6.QtCore import QPointF
                import math as _m
                blink = (int(SimulationTime.time() * 2) % 2 == 0)
                if blink:
                    rcol = QColor(*_pal.ALERT_STCA)
                    for t1_id, t2_id, estado, tiempo in getattr(self, 'conflictos_activos', []):
                        for tid in (t1_id, t2_id):
                            t = self.tracks.get(tid) or self.pending_tracks.get(tid)
                            if not t:
                                continue
                            sp = self._world_to_screen(t.x, t.y)
                            if sp is None:
                                continue
                            painter.save(); painter.resetTransform()
                            painter.setPen(QPen(rcol, 1.5)); painter.setBrush(0)
                            painter.drawEllipse(sp, 12.0, 12.0)
                            painter.restore()
```

- [ ] **Step 2: Smoke render** → `rendered 400 400`.

- [ ] **Step 3: Commit**

```bash
git add player/radar_widget.py
git commit -m "feat(ods): presentacion STCA estandar (halo+parpadeo+rojo)"
```

---

## Phase 10 — Wiring de UI y verificación visual

### Task 10.1: controles ODS en `main_window.py`

**Files:**
- Modify: `player/main_window.py`

- [ ] **Step 1: Sliders de intensidad por capa + toggle "Rosa de rumbos"** en el panel de la vista controlador, cableados a `self.radar.set_ods_layer_intensity(layer, v/100)` y a `self.radar.ods_enabled`. Seguir el patrón de toggles existente del menú "Modo" (ver commits recientes de toggles tácticos).

- [ ] **Step 2: Smoke import**

Run: `QT_QPA_PLATFORM=offscreen $PY -c "import main; from PyQt6.QtWidgets import QApplication; main.configurar_aceleracion(); QApplication([]); from player import gpu; gpu.detectar_gpu(); from player.main_window import MainWindow; MainWindow(); print('ok')"`
Expected: `ok`

- [ ] **Step 3: Commit**

```bash
git add player/main_window.py
git commit -m "feat(ods): controles de intensidad/rosa en panel controlador"
```

### Task 10.2: Verificación visual manual (REQUERIDA)

> Sub-skill: `superpowers:verification-before-completion`. Esto NO se puede afirmar sin verlo.

- [ ] **Step 1:** Lanzar la app real (no headless) según `env_python_runtime`, cargar un archivo con tráfico CAT048/021/062, activar **vista controlador**.
- [ ] **Step 2:** Confirmar checklist ODS:
  - [ ] Fondo gris neutro; sin barrido rotante.
  - [ ] Símbolos por estado (PSR `+`, SSR `□`, combinado relleno, ADS-B `◇`, system-track con punto, coasting punteado), **tamaño constante** al hacer zoom.
  - [ ] FDB de 3 líneas con flecha de tendencia; leader line visible; etiquetas sin solaparse.
  - [ ] Rosa de rumbos rotulada cada 30°; leyenda de alcance.
  - [ ] Sliders de intensidad por capa cambian brillo de mapa/etiquetas/historial.
  - [ ] STCA: halo rojo parpadeante en ambos tracks.
  - [ ] Vista técnica intacta (barrido + color por SAC/SIC).
- [ ] **Step 3:** Capturar screenshots antes/después para el PR.

### Task 10.3: Suite completa + cierre

- [ ] **Step 1:** `$PY -m pytest tests/ods/ -v` → todo PASS.
- [ ] **Step 2:** Sub-skill `superpowers:finishing-a-development-branch` para decidir merge/PR.

---

## Self-Review (cobertura del spec)

- Símbología por estado de track (no categoría): Tasks 1, 3, 6.2, 6.4 ✓
- Paleta ODS / color por estado / fondo neutro: Tasks 2, 6.2, 6.3 ✓
- FDB sin plan de vuelo + tendencia + leader line: Tasks 4, 6.1, 6.2 ✓
- Declutter testeado: Tasks 5, 6.4 ✓
- Rosa de rumbos + leyenda de alcance: Tasks 7.1, 7.2 ✓
- Intensidad por capa + sweep off (controlador): Task 8 ✓
- STCA estándar: Task 9 ✓
- Wiring UI + verificación visual: Task 10 ✓
- Vista técnica preservada (gating `vista_controlador`/`ods_enabled` en cada cambio) ✓

**Pendiente por diseño (fuera de scope, sin plan de vuelo):** CFL/XFL/PEL, ownership por sector, transferencia entre sectores. Cuando ingrese plan de vuelo: extender `fdb.build_lines` (L2 con CFL) y `palette.state_rgb` (color por estado de control).
