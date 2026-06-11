# Plan de Trabajo — Configuración Radar

Hoja de ruta para extender el sistema con una "Radar Treatment Configuration"
(estilo Indra): ajuste de registración, slant-range, zonas de filtro de reflexión
y zonas de exclusión de procesamiento, con UI técnica y modo en vivo.

Estado base: la **calibración de registración** (Adjustment) ya está construida
(Fases 1–6 de fusión): núcleo `Correlator`, colector, solver, LSQ de red,
aplicación opt-in por sensor y panel "Análisis y Calibración" (rol técnico).

## Mapeo pantalla de referencia → proyecto

| Sección | Estado |
|---|---|
| **Adjustment** (Manual/Automatic, Azimuth/Range) | ✅ Construido = bloque `registration`. Falta toggle Manual/Automatic y modo *Automatic en vivo*. |
| **Slant-range Correction** | ⚠️ Lo calcula el colector; el pipeline en vivo NO lo aplica (usa rho directo). |
| **Reflects** (zonas 1–5 filtro de reflexión) | ⚠️ Hay detección automática (`is_reflection`, radar_widget.py:2615) pero NO por zonas. |
| **Rho-Theta filter** (zonas 1–4, no procesa/no muestra) | ❌ No existe — crear. |
| **PSR/SSR/MET/CMB/TEST** | ⚠️ Parcial (tipos de sensor); falta filtrar por tipo de detección. |

**Clave técnica:** todo se aplica por plot en `decoder/data_engine.py::_record_to_plot`,
donde ya hay rho/θ por sensor → funciona en vivo sin re-escaneo (igual que la registración).

## Modelo de datos propuesto (`default-site-params/{sac}_{sic}.json`)

```json
"treatment": {
  "psr": true, "ssr": true, "met": true, "cmb": true, "test": false,
  "adjustment": { "mode": "manual|automatic",
                  "azimuth_offset_deg": 0.0, "range_offset_nm": 0.0 },
  "slant_range_correction": true,
  "reflection_zones": [
    { "enabled": true, "rho_min": 0, "rho_max": 0, "az_min": 0, "az_max": 0 }
  ],
  "exclusion_zones": [
    { "enabled": true, "rho_min": 0, "rho_max": 0, "az_min": 0, "az_max": 0 }
  ]
}
```
Nota: `adjustment` unifica/reemplaza el actual bloque `registration`.

## Fases (cada una con commit)

- **A — Modelo de datos `treatment`** por radar. `cargar_sensores` lo carga. No cambia comportamiento.
- **B — Zonas de exclusión (Rho-Theta filter)** ← arrancar acá. En `_record_to_plot`, si el
  plot cae en una zona de exclusión del sensor → `return None` (no procesa ni muestra). En vivo, inmediato.
- **C — Slant-range correction.** Toggle por sensor: rho oblicuo→tierra con la altitud antes de proyectar.
- **D — Filtro de reflexión por zonas.** Scopear la detección de reflejos existente a `reflection_zones`.
- **E — Adjustment Manual/Automatic + calibración en vivo (Fase 7).** Unificar `registration`;
  modo Automatic = acumulador en vivo / LSQ. Aplicación en caliente (mutar dict de sensores → efecto inmediato).
- **F — Enables por tipo de detección (PSR/SSR/MET/CMB/TEST).** Filtrar por TYP de CAT048.
- **G — UI unificada "Configuración Radar".** Layout de la imagen: lista de
  estaciones + panel por radar (enables, Adjustment manual/auto + az/range, slant, grillas de zonas).
  Reusa el panel de calibración existente. Estilo de la app, gateado a rol técnico.

## Orden recomendado
A → B → C → (G parcial: UI de zonas + slant + adjustment) → D → E → F.
Arrancar por **A+B** da algo útil y de bajo riesgo enseguida (no-procesamiento por zona)
y deja la base de datos lista para el resto.

## Referencias de código
- Aplicación por plot: `decoder/data_engine.py::_record_to_plot` (registración ya aplicada acá).
- Carga de config por sensor: `utils/geo.py::cargar_sensores`.
- Detección de reflejos: `player/radar_widget.py` (~2615, `is_reflection`/`has_reflection`).
- Panel de calibración (Adjustment): `player/calib_dialog.py`. Núcleo: `fusion/`.
- Rol técnico: `player/profile_manager.py::get_rol`.
