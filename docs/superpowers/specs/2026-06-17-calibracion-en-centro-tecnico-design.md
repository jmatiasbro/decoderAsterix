# Análisis y Calibración dentro del Centro Técnico ATSEP

Fecha: 2026-06-17
Estado: Aprobado (diseño)

## Objetivo

"Análisis y Calibración" deja de ser un diálogo independiente del menú
Configuración y pasa a ser una pestaña del Centro Técnico ATSEP. Único punto de
entrada: la pestaña.

## Contexto actual

- `player/calib_dialog.py`: `CalibrationDialog(QDialog)` (365 líneas). Construye su
  UI en `QVBoxLayout(self)`. Corre el LSQ de red (`fusion.calib_network`) en un
  `_SolverThread`, muestra propuestas por sensor (tabla editable), y escribe el
  bloque `registration` en `default-site-params/{sac}_{sic}.json`. Botones
  "Guardar" y "Desactivar" llaman `self.accept()` (cierran el diálogo) → el
  llamador conecta `accepted` a `_recargar_sensores_calib`.
- `player/main_window.py`: item de menú Configuración "Análisis y Calibración
  (Técnico)…" → `_abrir_calibracion()` (no-modal, gateado por rol técnico,
  referencia en `_calib_dialog`). Gateo por rol también en el cambio de rol
  (`act_calibracion.setEnabled`).
- `player/centro_tecnico/window.py`: `CentroTecnicoWindow(QMainWindow)` con
  `QTabWidget` (Estadísticas, PASS, Monitor ATSEP, Inspector, Cobertura).
  Recibe `sensores` del app vía `self.parent().sensores`. Solo rol técnico.

## Decisiones (brainstorming)

1. **Acceso**: quitar el item del menú Configuración. Único acceso = pestaña.
2. **Enfoque**: extraer un `CalibrationWidget(QWidget)` (no embeber el QDialog tal
   cual, porque sus botones llaman `self.accept()` y cerrarían la pestaña).
3. **PCAP/sensores**: la calibración conserva su propio selector de PCAP dentro de
   la pestaña; `sensores` viene del app vía el Centro Técnico.

## Arquitectura

### 1. `player/calib_dialog.py` — refactor a widget

- Renombrar/refactorizar `CalibrationDialog(QDialog)` → `CalibrationWidget(QWidget)`.
  Mismo contenido y layout (`QVBoxLayout(self)`), mismos métodos/lógica.
- Agregar señal `cambios_guardados = pyqtSignal()`.
- Reemplazar las dos llamadas `self.accept()` (Guardar / Desactivar) por
  `self.cambios_guardados.emit()` (ya no cierra nada; la pestaña permanece).
- `__init__(self, sensores, pcap_path="", parent=None)` se mantiene.
- El `_SolverThread` y la lógica de tabla/guardado no cambian.

### 2. `player/centro_tecnico/window.py` — nueva pestaña

- Importar `CalibrationWidget`.
- Construir `self.calib_tab = CalibrationWidget(sensores, pcap_path=<pcap del app>,
  parent=self)` y `self.tabs.addTab(self.calib_tab, "🛠 Calibración")`.
- `sensores`: `getattr(self.parent(), "sensores", {})` (patrón ya usado en la
  ventana). `pcap_path`: `getattr(self.parent(), "pcap_path", "")`.
- Conectar `self.calib_tab.cambios_guardados` a un handler que pida al app recargar
  sensores (equivalente al actual `_recargar_sensores_calib`). Se expone llamando
  `self.parent()._recargar_sensores_calib()` si existe.

### 3. `player/main_window.py` — quitar acceso de menú

- Eliminar la creación del item `act_calibracion` y su `_abrir_calibracion`.
- Eliminar la referencia a `act_calibracion` en el gateo por cambio de rol.
- Conservar `_recargar_sensores_calib` (lo usa ahora la pestaña vía la ventana).
- `CentroTecnicoWindow` ya recibe `parent=self`; no requiere parámetros nuevos
  (lee `sensores`/`pcap_path` del parent).

## Manejo de errores / degradación

- Sin sensores o sin PCAP válido: la pestaña muestra los mismos avisos que hoy
  (la lógica de validación del widget no cambia).
- El gateo por rol técnico lo cubre la apertura del Centro Técnico (ya restringida
  a `rol == "tecnico"`); se elimina el gateo redundante del item de menú.

## Testing

- El solver y la evaluación viven en `fusion/` (sin Qt) y ya están cubiertos; no
  cambian.
- El cambio es UI/wiring. Verificación:
  - `import` de los tres módulos sin error (`ast.parse` + import real).
  - Smoke: instanciar `CalibrationWidget(sensores={}, pcap_path="")` no lanza.
  - Smoke: `CentroTecnicoWindow` lista una pestaña cuyo texto contiene
    "Calibración".
- No se agregan tests Qt nuevos (el repo no testea UI interactiva).

## Secuencia de construcción

1. Refactor `calib_dialog.py` → `CalibrationWidget` + señal `cambios_guardados`.
2. Agregar la pestaña en `centro_tecnico/window.py` y cablear la señal.
3. Quitar el item de menú y `_abrir_calibracion` de `main_window.py`.
4. Verificación (imports + smoke).
