# Ciclo de Vida de Pista Monoradar — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Motor headless determinista por ToD que confirma pistas monoradar con M-de-N (4 detecciones), las mantiene en coasting al faltar datos (flecha hacia abajo) y las borra a la 4ª falta, integrado y coloreado en el player.

**Architecture:** Un motor sin Qt (`player/tracking/lifecycle.py`) lleva el estado por código (identidad squawk/callsign/Mode-S), cuenta detecciones y faltas en **vueltas de antena** (`60/RPM`, índice = `floor(ToD/scan_period)`), y expone estado (TENTATIVE/CONFIRMED/COASTING/DELETED) + faltas. El player lo alimenta con cada plot cuando hay **un solo sensor activo**, lo envejece con un `tick(ToD)` y mapea estado→color (tentativa=categoría, confirmada=blanco) + flecha de coasting en `_draw_oaci_track`.

**Tech Stack:** Python 3.12, pytest (`tests/tracking/`, `--import-mode=importlib`). Sin Qt en el motor. ToD ASTERIX exclusivamente (nada de `time.time()`). Intérprete: `/c/Users/Usuario/AppData/Local/Programs/Python/Python312/python.exe`.

---

## File Structure

- `player/tracking/__init__.py` — **crear**: paquete vacío.
- `player/tracking/lifecycle.py` — **crear**: motor headless (identidad, estados, `MonoradarLifecycle`).
- `tests/tracking/__init__.py` — **crear** (vacío, por si importlib lo requiere).
- `tests/tracking/test_lifecycle.py` — **crear**: tests del motor.
- `player/radar_widget.py` — **modificar**: gateo monoradar, alimentación del motor, `tick`, color por estado y flecha de coasting.

Convenciones (verificadas): tests con `pytest` desde la raíz; `tests/pytest.ini` define `--import-mode=importlib`; plots de prueba con `types.SimpleNamespace`. 1 NM = 1852 m; los plots traen `x,y` en metros proyectados y `timestamp` = ToD ASTERIX.

---

## Task 1: Identidad de código

**Files:**
- Create: `player/tracking/__init__.py`
- Create: `player/tracking/lifecycle.py`
- Create: `tests/tracking/__init__.py`
- Test: `tests/tracking/test_lifecycle.py`

- [ ] **Step 1: Crear paquetes vacíos**

Crear `player/tracking/__init__.py` y `tests/tracking/__init__.py` ambos vacíos (0 bytes).

- [ ] **Step 2: Escribir el test de identidad**

Create `tests/tracking/test_lifecycle.py`:

```python
from types import SimpleNamespace as S

from player.tracking.lifecycle import identidad_codigo


def _plot(**kw):
    base = dict(timestamp=0.0, sac=1, sic=44, x=0.0, y=0.0,
                mode3a=None, mode_s=None, callsign=None, category=48)
    base.update(kw)
    return S(**base)


def test_squawk_es_la_clave():
    assert identidad_codigo(_plot(mode3a=0o1234)) == "1234"
    assert identidad_codigo(_plot(mode3a="2701")) == "2701"


def test_squawk_invalido_no_es_clave_sin_adsb():
    assert identidad_codigo(_plot(mode3a="0000", category=48)) is None
    assert identidad_codigo(_plot(mode3a="----", category=48)) is None


def test_adsb_usa_callsign_luego_mode_s():
    # ADS-B (cat21) sin squawk -> callsign primero
    assert identidad_codigo(_plot(category=21, mode3a=None, callsign="AAL123",
                                  mode_s="ABCDEF")) == "AAL123"
    # sin callsign -> dirección Mode S
    assert identidad_codigo(_plot(category=21, mode3a=None, callsign=None,
                                  mode_s="ABCDEF")) == "ABCDEF"


def test_psr_puro_sin_codigo_es_none():
    assert identidad_codigo(_plot(category=48, mode3a=None, mode_s=None,
                                  callsign=None)) is None
```

- [ ] **Step 3: Correr (debe fallar)**

Run: `"/c/Users/Usuario/AppData/Local/Programs/Python/Python312/python.exe" -m pytest tests/tracking/test_lifecycle.py -v`
Expected: FAIL con `ImportError: cannot import name 'identidad_codigo'`

- [ ] **Step 4: Implementar identidad en lifecycle.py**

Create `player/tracking/lifecycle.py`:

```python
"""Ciclo de vida de pista monoradar (confirmación M-de-N + coasting por vueltas).

Determinista por ToD ASTERIX: nada de time.time(). Headless (sin Qt).
"""
import math

NM_M = 1852.0

TENTATIVE = "TENTATIVE"
CONFIRMED = "CONFIRMED"
COASTING = "COASTING"
DELETED = "DELETED"


def _squawk(plot):
    m = getattr(plot, "mode3a", None)
    s = f"{m:04o}" if isinstance(m, int) else str(m or "").strip()
    if s and s not in ("----", "0000"):
        return s
    return None


def identidad_codigo(plot):
    """Clave de identidad del plot, o None.

    SSR/PSR-SSR → squawk (Modo 3/A). ADS-B (cat 21) sin squawk → callsign;
    si falta → dirección Mode S.
    """
    sq = _squawk(plot)
    if sq:
        return sq
    if getattr(plot, "category", None) == 21:
        cs = (getattr(plot, "callsign", None) or "").strip().upper()
        if cs:
            return cs
        ms = (getattr(plot, "mode_s", None) or "").strip().upper()
        if ms and ms != "----":
            return ms
    return None
```

- [ ] **Step 5: Correr (debe pasar)**

Run: `"/c/Users/Usuario/AppData/Local/Programs/Python/Python312/python.exe" -m pytest tests/tracking/test_lifecycle.py -v`
Expected: PASS (4 tests)

- [ ] **Step 6: Commit**

```bash
git add player/tracking/ tests/tracking/
git commit -m "feat(tracking): identidad de codigo (squawk/callsign/mode-s) del ciclo monoradar"
```

---

## Task 2: Confirmación M-de-N (4 detecciones en vueltas consecutivas)

**Files:**
- Modify: `player/tracking/lifecycle.py`
- Test: `tests/tracking/test_lifecycle.py`

- [ ] **Step 1: Agregar tests de confirmación**

Agregar a `tests/tracking/test_lifecycle.py`:

```python
from player.tracking.lifecycle import (MonoradarLifecycle, TENTATIVE,
                                        CONFIRMED)

# scan_period fijo de 4 s (RPM=15) para todas las pruebas de ciclo
def _lc():
    return MonoradarLifecycle(scan_period_fn=lambda sac, sic: 4.0)


def _p(tod, code="1234", x=0.0, y=0.0):
    return _plot(timestamp=tod, mode3a=code, x=x, y=y, category=48)


def test_cuatro_vueltas_confirman():
    lc = _lc()
    for i, tod in enumerate([0.0, 4.0, 8.0]):     # vueltas 0,1,2
        lc.procesar(_p(tod))
        assert lc.estado("1234") == TENTATIVE
    lc.procesar(_p(12.0))                          # vuelta 3 → 4ª detección
    assert lc.estado("1234") == CONFIRMED
    assert lc.faltas("1234") == 0


def test_tres_vueltas_siguen_tentativas():
    lc = _lc()
    for tod in [0.0, 4.0, 8.0]:
        lc.procesar(_p(tod))
    assert lc.estado("1234") == TENTATIVE


def test_pista_nueva_arranca_tentativa():
    lc = _lc()
    lc.procesar(_p(0.0))
    assert lc.estado("1234") == TENTATIVE
    assert lc.faltas("1234") == 0
```

- [ ] **Step 2: Correr (debe fallar)**

Run: `"/c/Users/Usuario/AppData/Local/Programs/Python/Python312/python.exe" -m pytest tests/tracking/test_lifecycle.py -k "vueltas or tentativa" -v`
Expected: FAIL con `ImportError: cannot import name 'MonoradarLifecycle'`

- [ ] **Step 3: Implementar el motor (confirmación) en lifecycle.py**

Agregar a `player/tracking/lifecycle.py`:

```python
class _Pista:
    __slots__ = ("codigo", "estado", "detecciones", "faltas",
                 "ultima_vuelta", "scan_period", "x", "y")

    def __init__(self, codigo, vuelta, scan_period, x, y):
        self.codigo = codigo
        self.estado = TENTATIVE
        self.detecciones = 1
        self.faltas = 0
        self.ultima_vuelta = vuelta
        self.scan_period = scan_period
        self.x = x
        self.y = y


class MonoradarLifecycle:
    """Confirma/mantiene/borra pistas monoradar por vueltas de antena.

    scan_period_fn(sac, sic) -> período de barrido en s (60/RPM).
    confirm_n: detecciones para confirmar. drop_misses: faltas para borrar.
    pair_nm: umbral para colapsar dos plots del mismo código en la misma vuelta.
    """

    def __init__(self, scan_period_fn, confirm_n=4, drop_misses=4, pair_nm=1.0):
        self._period_fn = scan_period_fn
        self.confirm_n = confirm_n
        self.drop_misses = drop_misses
        self.pair_m = pair_nm * NM_M
        self.pistas = {}

    def _periodo(self, plot):
        p = self._period_fn(getattr(plot, "sac", None), getattr(plot, "sic", None))
        return p if p and p > 0 else 4.0

    def procesar(self, plot):
        """Registra una detección. Devuelve el código tratado o None."""
        codigo = identidad_codigo(plot)
        if codigo is None:
            return None
        period = self._periodo(plot)
        vuelta = int(plot.timestamp // period)
        pista = self.pistas.get(codigo)
        if pista is None:
            self.pistas[codigo] = _Pista(codigo, vuelta, period, plot.x, plot.y)
            return codigo
        # vuelta nueva consecutiva (o posterior): cuenta como detección
        if vuelta > pista.ultima_vuelta:
            if pista.estado == CONFIRMED or pista.estado == COASTING:
                pista.estado = CONFIRMED        # recuperación
            else:
                # tentativa: si hubo hueco, reinicia la racha
                if vuelta > pista.ultima_vuelta + 1:
                    pista.detecciones = 0
                pista.detecciones += 1
            pista.faltas = 0
            pista.ultima_vuelta = vuelta
            pista.x, pista.y = plot.x, plot.y
        if pista.estado == TENTATIVE and pista.detecciones >= self.confirm_n:
            pista.estado = CONFIRMED
        return codigo

    def estado(self, codigo):
        p = self.pistas.get(codigo)
        return p.estado if p else None

    def faltas(self, codigo):
        p = self.pistas.get(codigo)
        return p.faltas if p else 0
```

- [ ] **Step 4: Correr (debe pasar)**

Run: `"/c/Users/Usuario/AppData/Local/Programs/Python/Python312/python.exe" -m pytest tests/tracking/test_lifecycle.py -v`
Expected: PASS (todos)

- [ ] **Step 5: Commit**

```bash
git add player/tracking/lifecycle.py tests/tracking/test_lifecycle.py
git commit -m "feat(tracking): confirmacion M-de-N (4 detecciones) por vueltas de antena"
```

---

## Task 3: Doble plot en la misma vuelta (<1 NM cuenta 2 / >1 NM no colapsa)

**Files:**
- Modify: `player/tracking/lifecycle.py`
- Test: `tests/tracking/test_lifecycle.py`

- [ ] **Step 1: Agregar tests del doble plot**

Agregar a `tests/tracking/test_lifecycle.py`:

```python
from player.tracking.lifecycle import DUPLICADO_LEJANO


def test_doble_plot_cercano_cuenta_dos():
    lc = _lc()
    # vuelta 0: dos plots <1 NM -> 2 detecciones
    lc.procesar(_p(0.0, x=0.0, y=0.0))
    lc.procesar(_p(0.5, x=500.0, y=0.0))          # mismo scan (0.5//4=0), 0.5 NM
    # vuelta 1: una detección -> total 3, sigue tentativa
    lc.procesar(_p(4.0, x=0.0, y=0.0))
    assert lc.estado("1234") == TENTATIVE
    # vuelta 2: cuarta detección -> confirma (2+1+1)
    lc.procesar(_p(8.0, x=0.0, y=0.0))
    assert lc.estado("1234") == CONFIRMED


def test_doble_plot_lejano_no_colapsa():
    lc = _lc()
    lc.procesar(_p(0.0, x=0.0, y=0.0))
    # mismo scan, >1 NM (3000 m ~ 1.6 NM): no suma, marca duplicado lejano
    ev = lc.procesar(_p(0.5, x=3000.0, y=0.0))
    assert ev == DUPLICADO_LEJANO
    # la detección de la pista no aumentó por el plot lejano
    assert lc.pistas["1234"].detecciones == 1
```

- [ ] **Step 2: Correr (debe fallar)**

Run: `"/c/Users/Usuario/AppData/Local/Programs/Python/Python312/python.exe" -m pytest tests/tracking/test_lifecycle.py -k doble -v`
Expected: FAIL con `ImportError: cannot import name 'DUPLICADO_LEJANO'`

- [ ] **Step 3: Implementar la rama de misma vuelta**

En `player/tracking/lifecycle.py`, agregar la constante (junto a los estados):

```python
DUPLICADO_LEJANO = "DUPLICADO_LEJANO"
```

Y en `procesar`, reemplazar el bloque `if vuelta > pista.ultima_vuelta:` por el manejo que incluye la **misma vuelta**:

```python
        if vuelta == pista.ultima_vuelta:
            # mismo scan: colapsar si está cerca, si no es duplicado lejano
            dist = math.hypot(plot.x - pista.x, plot.y - pista.y)
            if dist < self.pair_m:
                if pista.estado == TENTATIVE:
                    pista.detecciones += 1
                pista.x, pista.y = plot.x, plot.y
                if pista.estado == TENTATIVE and pista.detecciones >= self.confirm_n:
                    pista.estado = CONFIRMED
                return codigo
            return DUPLICADO_LEJANO
        if vuelta > pista.ultima_vuelta:
            if pista.estado == CONFIRMED or pista.estado == COASTING:
                pista.estado = CONFIRMED        # recuperación
            else:
                if vuelta > pista.ultima_vuelta + 1:
                    pista.detecciones = 0
                pista.detecciones += 1
            pista.faltas = 0
            pista.ultima_vuelta = vuelta
            pista.x, pista.y = plot.x, plot.y
        if pista.estado == TENTATIVE and pista.detecciones >= self.confirm_n:
            pista.estado = CONFIRMED
        return codigo
```

- [ ] **Step 4: Correr (debe pasar)**

Run: `"/c/Users/Usuario/AppData/Local/Programs/Python/Python312/python.exe" -m pytest tests/tracking/test_lifecycle.py -v`
Expected: PASS (todos)

- [ ] **Step 5: Commit**

```bash
git add player/tracking/lifecycle.py tests/tracking/test_lifecycle.py
git commit -m "feat(tracking): doble plot misma vuelta (<1NM cuenta 2, >1NM duplicado lejano)"
```

---

## Task 4: Coasting y borrado por faltas (`tick`)

**Files:**
- Modify: `player/tracking/lifecycle.py`
- Test: `tests/tracking/test_lifecycle.py`

- [ ] **Step 1: Agregar tests de coasting/borrado/recuperación**

Agregar a `tests/tracking/test_lifecycle.py`:

```python
from player.tracking.lifecycle import COASTING, DELETED


def _confirmada():
    lc = _lc()
    for tod in [0.0, 4.0, 8.0, 12.0]:             # confirma en vuelta 3
        lc.procesar(_p(tod))
    assert lc.estado("1234") == CONFIRMED
    return lc


def test_coasting_marca_faltas():
    lc = _confirmada()
    # sin datos: a ToD de la vuelta 4,5,6 (16,20,24 s) → faltas 1,2,3, sigue viva
    for v, tod in enumerate([16.0, 20.0, 24.0], start=1):
        lc.tick(tod)
        assert lc.estado("1234") == COASTING
        assert lc.faltas("1234") == v


def test_borra_en_la_cuarta_falta():
    lc = _confirmada()
    for tod in [16.0, 20.0, 24.0]:
        lc.tick(tod)
    eventos = lc.tick(28.0)                        # 4ª falta → DELETE
    assert ("1234", DELETED) in eventos
    assert lc.estado("1234") is None              # ya no está


def test_recuperacion_resetea_faltas():
    lc = _confirmada()
    lc.tick(16.0)                                 # falta 1 (COASTING)
    lc.tick(20.0)                                 # falta 2
    lc.procesar(_p(24.0))                         # vuelve dato en vuelta 6
    assert lc.estado("1234") == CONFIRMED
    assert lc.faltas("1234") == 0


def test_tentativa_que_falta_se_descarta():
    lc = _lc()
    lc.procesar(_p(0.0))                          # 1 detección, TENTATIVE
    lc.tick(8.0)                                  # pasó ≥1 vuelta sin confirmar
    assert lc.estado("1234") is None
```

- [ ] **Step 2: Correr (debe fallar)**

Run: `"/c/Users/Usuario/AppData/Local/Programs/Python/Python312/python.exe" -m pytest tests/tracking/test_lifecycle.py -k "coasting or cuarta or recupera or descarta" -v`
Expected: FAIL con `AttributeError: 'MonoradarLifecycle' object has no attribute 'tick'`

- [ ] **Step 3: Implementar `tick` en lifecycle.py**

Agregar a `MonoradarLifecycle`:

```python
    def tick(self, tod_actual):
        """Envejece faltas según el ToD actual. Devuelve [(codigo, evento)].

        Para cada pista, la vuelta actual = floor(tod/scan_period). Si hay vueltas
        sin dato: tentativa → se descarta; confirmada/coasting → COASTING y, al
        llegar a drop_misses, DELETE.
        """
        eventos = []
        for codigo in list(self.pistas.keys()):
            pista = self.pistas[codigo]
            vuelta_actual = int(tod_actual // pista.scan_period)
            faltantes = vuelta_actual - pista.ultima_vuelta
            if faltantes <= 0:
                continue
            if pista.estado == TENTATIVE:
                # sin confirmar y perdió una vuelta → descartar
                del self.pistas[codigo]
                eventos.append((codigo, DELETED))
                continue
            pista.faltas = faltantes
            if faltantes >= self.drop_misses:
                del self.pistas[codigo]
                eventos.append((codigo, DELETED))
            else:
                pista.estado = COASTING
                eventos.append((codigo, COASTING))
        return eventos
```

- [ ] **Step 4: Correr toda la suite del motor (debe pasar)**

Run: `"/c/Users/Usuario/AppData/Local/Programs/Python/Python312/python.exe" -m pytest tests/tracking/test_lifecycle.py -v`
Expected: PASS (todos)

- [ ] **Step 5: Commit**

```bash
git add player/tracking/lifecycle.py tests/tracking/test_lifecycle.py
git commit -m "feat(tracking): coasting y borrado por faltas (tick por vueltas)"
```

---

## Task 5: Integración en el player (gateo monoradar + alimentación + tick)

**Files:**
- Modify: `player/radar_widget.py`

- [ ] **Step 1: Inicializar el motor**

Buscar donde se inicializa `self.pending_tracks: Dict[str, RadarPlot] = {}` (~línea 801) y agregar debajo:

```python
        from player.tracking.lifecycle import MonoradarLifecycle
        self._mono_lifecycle = MonoradarLifecycle(
            scan_period_fn=lambda sac, sic: 60.0 / max(
                0.1, self.sensor_rpms.get((sac, sic), self.sweep_rpm) or self.sweep_rpm))
        self._mono_estado = {}     # codigo -> (estado, faltas), para el render
```

- [ ] **Step 2: Helper de gateo monoradar**

Agregar un método (junto a `get_all_areas`, por ejemplo):

```python
    def _es_monoradar(self) -> bool:
        """True si hay exactamente un sensor activo (un único SAC/SIC con tracks)."""
        sensores = {t.sac_sic for t in self.tracks.values()
                    if getattr(t, 'sac_sic', None)}
        sensores |= {t.sac_sic for t in self.pending_tracks.values()
                     if getattr(t, 'sac_sic', None)}
        return len(sensores) == 1
```

- [ ] **Step 3: Alimentar el motor al procesar cada plot**

En `on_new_plot_batch` (ahora) reemplazar:

```python
        for data in batch:
            self._process_plot_data(data)
        self._reconciliar_pistas()
        self._schedule_safety()
        self._request_repaint()
```

por:

```python
        for data in batch:
            self._process_plot_data(data)
        if self._es_monoradar():
            from types import SimpleNamespace as _S
            for data in batch:
                p = _S(timestamp=data.get('time', 0.0) or 0.0,
                       sac=data.get('sac'), sic=data.get('sic'),
                       x=data.get('x_meters') or 0.0, y=data.get('y_meters') or 0.0,
                       mode3a=data.get('mode3a'), mode_s=data.get('mode_s'),
                       callsign=data.get('callsign'), category=data.get('category'))
                self._mono_lifecycle.procesar(p)
        self._reconciliar_pistas()
        self._schedule_safety()
        self._request_repaint()
```

> Nota: `x_meters`/`y_meters` se setean en `_process_plot_data` (ver el bloque que asigna `plot['x_meters']`). Si faltan, el motor usa 0,0 (la distancia entre plots del mismo código seguirá siendo coherente para el caso típico).

- [ ] **Step 4: Tick por ToD en el timer**

En el bloque de 1 Hz de `_on_timer` (donde está `# 4. FASE 4: Contar plots...`), agregar antes de `self.evaluar_stca()`:

```python
                # Ciclo de vida monoradar: envejecer faltas por vueltas (ToD).
                if self._es_monoradar():
                    tod = getattr(self, '_last_tod', 0.0) or 0.0
                    for codigo, evento in self._mono_lifecycle.tick(tod):
                        self._mono_estado.pop(codigo, None)
                    self._mono_estado = {
                        c: (p.estado, p.faltas)
                        for c, p in self._mono_lifecycle.pistas.items()
                    }
```

- [ ] **Step 5: Verificar que importa y la suite no rompe**

Run: `"/c/Users/Usuario/AppData/Local/Programs/Python/Python312/python.exe" -c "import ast; ast.parse(open('player/radar_widget.py',encoding='utf-8').read()); print('ok')"`
Expected: `ok`

Run: `"/c/Users/Usuario/AppData/Local/Programs/Python/Python312/python.exe" -m pytest tests/tracking/ -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add player/radar_widget.py
git commit -m "feat(tracking): gateo monoradar + alimentacion del ciclo de vida en el player"
```

---

## Task 6: Render — color por estado + flecha de coasting

**Files:**
- Modify: `player/radar_widget.py` (`_draw_oaci_track` ~5249-5292 y helper nuevo)

- [ ] **Step 1: Mapear estado→color en `_draw_oaci_track`**

En `_draw_oaci_track`, dentro del bloque `else:` que elige color por tipo (la rama final, ~`if is_fused: ... else: plot_color = self._get_sensor_color(...)`), anteponer el estado monoradar. Reemplazar la línea inicial de ese `else:` (la que empieza con `if is_fused:`) por:

```python
                mono = None
                if getattr(self, '_es_monoradar', None) and self._es_monoradar():
                    from player.tracking.lifecycle import (identidad_codigo,
                                                           CONFIRMED, TENTATIVE, COASTING)
                    cod = identidad_codigo(plot)
                    mono = self._mono_estado.get(cod) if cod else None
                if mono is not None and mono[0] in (CONFIRMED, COASTING):
                    plot_color = QColor("#FFFFFF")   # confirmada/coasting = blanco
                elif mono is not None and mono[0] == TENTATIVE:
                    # tentativa: color por tipo/categoría (cae al esquema de abajo)
                    plot_color = self._color_por_tipo(is_fused, is_adsb, is_mlat,
                                                      is_psr, is_ssr, is_combined,
                                                      ssr_code, plot)
                elif is_fused:
                    plot_color = QColor("#FFFFFF")  # Blanco para fusionado/CAT62
                elif is_adsb:
                    plot_color = QColor("#FFFF00")  # Amarillo para ADS-B/CAT21
                elif is_mlat:
                    plot_color = QColor(255, 0, 255)  # Magenta para MLAT
                elif is_psr:
                    plot_color = QColor(204, 85, 0)  # Naranja oscuro para PSR
                elif is_ssr or is_combined:
                    has_valid_ssr = ssr_code and ssr_code not in ("----", "0000", "")
                    has_fl = plot.flight_level is not None
                    if plot.category in (1, 48) and (not has_valid_ssr or not has_fl):
                        plot_color = QColor(100, 200, 255)
                    else:
                        plot_color = COLOR_GREEN_NEON
                else:
                    plot_color = self._get_sensor_color(plot.sac, plot.sic)
```

- [ ] **Step 2: Extraer el helper `_color_por_tipo`**

Agregar el método (para reusar el esquema de color de tipo en estado tentativo):

```python
    def _color_por_tipo(self, is_fused, is_adsb, is_mlat, is_psr, is_ssr,
                        is_combined, ssr_code, plot):
        if is_fused:
            return QColor("#FFFFFF")
        if is_adsb:
            return QColor("#FFFF00")
        if is_mlat:
            return QColor(255, 0, 255)
        if is_psr:
            return QColor(204, 85, 0)
        if is_ssr or is_combined:
            has_valid_ssr = ssr_code and ssr_code not in ("----", "0000", "")
            has_fl = plot.flight_level is not None
            if plot.category in (1, 48) and (not has_valid_ssr or not has_fl):
                return QColor(100, 200, 255)
            return COLOR_GREEN_NEON
        return self._get_sensor_color(plot.sac, plot.sic)
```

- [ ] **Step 3: Dibujar la flecha de coasting**

En `_draw_oaci_track`, después de dibujar el símbolo del track (buscar donde termina el dibujo del símbolo principal, antes del `return` del método), agregar:

```python
            # Flecha de coasting (monoradar): faltó dato en ≥1 vuelta.
            if getattr(self, '_es_monoradar', None) and self._es_monoradar():
                from player.tracking.lifecycle import identidad_codigo
                cod = identidad_codigo(plot)
                est = self._mono_estado.get(cod) if cod else None
                if est is not None and est[1] >= 1:      # faltas >= 1
                    sp = self._world_to_screen(plot.x, plot.y)
                    if sp is not None:
                        painter.save()
                        painter.resetTransform()
                        pen = QPen(QColor("#FF5050"))
                        pen.setWidthF(2.0)
                        painter.setPen(pen)
                        bx, by = sp.x() + 10, sp.y() + 10
                        painter.drawLine(int(bx), int(by - 8), int(bx), int(by + 8))
                        painter.drawLine(int(bx - 5), int(by + 3), int(bx), int(by + 8))
                        painter.drawLine(int(bx + 5), int(by + 3), int(bx), int(by + 8))
                        painter.restore()
```

- [ ] **Step 4: Verificar sintaxis + suite**

Run: `"/c/Users/Usuario/AppData/Local/Programs/Python/Python312/python.exe" -c "import ast; ast.parse(open('player/radar_widget.py',encoding='utf-8').read()); print('ok')"`
Expected: `ok`

Run: `"/c/Users/Usuario/AppData/Local/Programs/Python/Python312/python.exe" -m pytest tests/tracking/ -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add player/radar_widget.py
git commit -m "feat(tracking): color por estado (tentativa=categoria, firme=blanco) + flecha de coasting"
```

---

## Task 7: Verificación manual (grabación monoradar)

**Files:** ninguno (verificación).

- [ ] **Step 1: Correr con una grabación monoradar**

Lanzar la app (`"/c/Users/Usuario/AppData/Local/Programs/Python/Python312/python.exe" main.py`), reproducir una captura **de un solo radar** y observar:
- Los primeros plots de un código aparecen con color de categoría (tentativos).
- Al 4º barrido con dato, la pista pasa a **blanco** (confirmada).
- Si falta el dato en una vuelta, aparece la **flecha hacia abajo**; al volver el dato, desaparece.
- Tras 4 vueltas sin dato, la pista se borra.

- [ ] **Step 2: Confirmar suite**

Run: `"/c/Users/Usuario/AppData/Local/Programs/Python/Python312/python.exe" -m pytest tests/tracking/ -q`
Expected: todos PASS.

---

## Notas de verificación contra el spec

- **Identidad (squawk/callsign/Mode-S):** Task 1. ✔
- **Confirmación 4/4 por vueltas consecutivas:** Task 2. ✔
- **Doble plot misma vuelta (<1NM cuenta 2 / >1NM no colapsa):** Task 3. ✔
- **Coasting + flecha + borrado a la 4ª falta + recuperación:** Task 4 (motor) + Task 6 (flecha). ✔
- **Período por RPM detectado:** Task 5 (`scan_period_fn` desde `sensor_rpms`). ✔
- **Determinismo ToD (sin time.time()):** el motor solo usa `plot.timestamp`/`tod`; Task 4/5. ✔
- **Color tentativa=categoría / confirmada=blanco:** Task 6. ✔
- **Gateo monoradar (no toca multisensor):** Task 5 (`_es_monoradar`). ✔
- **Tests headless con ToD sintético:** Tasks 1-4. ✔
```
