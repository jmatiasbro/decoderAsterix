# SDP — Software Development Plan

**Sistema:** Decodificador ASTERIX + Display PPI ATC.
**Norma:** EUROCAE ED-109A / RTCA DO-278A — Sección 4 (Planificación) y Sección 5 (Desarrollo).
**Versión:** 0.1 (borrador). **Fecha:** 2026-07-03. **Estado:** PROPUESTO — no aprobado por ANAC.

---

## 1. Propósito y alcance

Este plan describe los procesos, estándares y herramientas empleados para desarrollar el software
del sistema dentro del marco de aseguramiento DO-278A. Debe leerse junto con el
[PSAC](01_PSAC.md), la [Clasificación SWAL](02_clasificacion_SWAL.md) y la [SRS](07_SRS.md).

El alcance de desarrollo cubre los módulos identificados en el PSAC §1.2. La extensión
`asterix_decoder-0.7.4` se trata como SOUP y queda fuera del proceso de desarrollo propio.

---

## 2. Entorno de desarrollo

### 2.1 Plataforma de referencia

| Elemento | Valor |
|---|---|
| Sistema operativo | Windows 11 Home Single Language 10.0.26200 |
| Intérprete Python | CPython 3.12 en `C:\Users\Usuario\AppData\Local\Programs\Python\Python312\python.exe` |
| Entorno virtual | NO usar el `.venv` del repositorio (creado bajo WSL, roto en Windows nativo) |
| PyQt6 | 6.x instalado en el Python nativo |
| DuckDB | ≥ 0.9 (requerido por `ON CONFLICT DO UPDATE`) |

> **Brechas actuales:** No existe `requirements.txt` completo ni lockfile de dependencias. El
> entorno de desarrollo es único (la máquina del desarrollador); no hay entorno reproducible
> declarado. Para certificación se deberá proveer un entorno sellado (conda-lock o pip-tools).

### 2.2 Herramientas

| Herramienta | Versión | Uso | Estado DO-278A |
|---|---|---|---|
| Python 3.12 | CPython 3.12.x | Lenguaje de implementación | SOUP — a cualificar |
| PyQt6 | 6.x | UI/señales Qt | SOUP — fuera de alcance de seguridad |
| DuckDB | ≥ 0.9 | Persistencia | SOUP — fuera de alcance de seguridad |
| pytest | ≥ 7 | Ejecución de tests | Herramienta de verificación — ver SVP |
| Git | ≥ 2.40 | Gestión de configuración | Ver SCMP |
| pyproj | ≥ 3 | Proyección geodésica | SOUP — envuelto en `geo_math.py` |
| scapy | ≥ 2 | Lectura PCAP | SOUP — fuera de alcance de seguridad |

### 2.3 IDE y entorno de prueba sin GUI

```
# Pruebas sin interfaz gráfica (headless):
set QT_QPA_PLATFORM=offscreen
set PYTHONUTF8=1
python -m pytest tests/

# Verificación de sintaxis de un módulo:
python -m py_compile player/main_window.py
```

---

## 3. Estándares de desarrollo

### 3.1 Estructura de módulos

La separación arquitectónica **núcleo sin Qt ↔ UI PyQt6** es un estándar de diseño obligatorio:

- `decoder/` y `fusion/` y `analysis/` y `storage/`: sin imports de PyQt6 — testeables en aislamiento.
- `player/`: toda la UI; los tests de player requieren QApplication.
- Toda función con impacto en seguridad (STCA/APW/MSAW/tracking) se implementa en módulos sin Qt.

### 3.2 Estándares de codificación

| Regla | Detalle |
|---|---|
| Idioma de comentarios y UI | Español |
| Commits | Conventional Commits con scope: `tipo(scope): mensaje` |
| Comentarios de código | Solo cuando el WHY es no obvio; no comentarios de WHAT |
| `time.time()` en el motor | VEDADO en el ciclo de vida de tracks; usar `SimulationTime.time()` |
| Formato de archivos | UTF-8; `PYTHONUTF8=1` en ejecución para evitar errores cp1252 |

### 3.3 Convenciones de visibilidad en QToolBar

Para ocultar/mostrar widgets dentro de un `QToolBar`, togglear la **acción** devuelta por
`addWidget()` — `action.setVisible(...)` — no `widget.setVisible()` (este último no funciona
dentro de toolbars en Qt).

### 3.4 Reloj de simulación

`player/tracking/lifecycle.py` y todos los módulos de ciclo de vida deben usar
`SimulationTime.time()` (tiempo del ToD ASTERIX). El uso de `time.time()` en el motor de ciclo
de vida es un defecto detectado por la suite de verificación.

---

## 4. Proceso de desarrollo

### 4.1 Ramas (branching)

```
main            ← baseline certificable; solo Fast-Forward desde feature/
feature/<name>  ← ramas de trabajo
hotfix/<name>   ← correcciones sobre baseline
```

Convención de merge: Pull Request revisado, tests pasando, sin conflictos. El merge directo a
`main` sin PR está prohibido (a reforzar con reglas de rama cuando se tenga servidor CI).

### 4.2 Ciclo por elemento de software

1. **Requisito** — identificar el HLR en la [SRS](07_SRS.md) que motiva el cambio.
2. **Diseño** — actualizar comentarios de diseño o el SDD si el cambio afecta la arquitectura.
3. **Implementación** — código en la rama feature.
4. **Verificación** — escribir o actualizar el test asociado al HLR; todos los tests deben pasar.
5. **Revisión** — revisar el diff contra los criterios de §3.
6. **Merge** — con mensaje de commit que referencie el HLR: `fix(tracking): HLR-TRK-02 ...`.
7. **Trazabilidad** — actualizar la [Matriz de Trazabilidad](04_matriz_trazabilidad.md) si aplica.

### 4.3 Tratamiento de defectos

Los defectos detectados durante verificación se documentan con:
- Identificador (número de issue Git o referencia al test que falla).
- HLR afectado.
- Descripción del fallo y condición de entrada que lo reproduce.
- Verificación de cierre: re-ejecución del test que acredita la corrección.

> **Brecha actual:** No existe sistema de seguimiento de defectos formal. Se usa el historial
> de commits y los mensajes `fix(…)` como trazabilidad de correcciones.

---

## 5. Módulos y SWAL asociado

| Módulo | SWAL | Rigor de desarrollo |
|---|---|---|
| `player/tracking/lifecycle.py` | 2 | Revisión de código + cobertura de decisiones |
| `player/radar_widget.py` (matching A–E) | 2 | Revisión de código + cobertura de decisiones |
| `player/areas/` (APW) | 2 | Revisión + tests de geometría |
| `player/msaw/` (MSAW) | 2 | Revisión + tests de geometría y altitud |
| `decoder/` (parsers CAT*) | 3 | Tests basados en requisitos |
| `fusion/` (correlación) | 3 | Tests basados en requisitos |
| `storage/` (persistencia) | 4 | Tests de integración |
| `player/fdp/` (FDP/ADEXP) | 4 | Tests funcionales |
| `analysis/`, `player/firmap/`, etc. | 4 / fuera de alcance | Buenas prácticas |

---

## 6. Manejo de SOUP

La extensión `asterix_decoder-0.7.4` (binario C) se gestiona como SOUP:

| Acción | Estado |
|---|---|
| Identificación de versión y origen | ✅ — versión fija en el nombre del paquete |
| Análisis de funciones usadas | Parcial — `native_asterix.py` envuelve todas las llamadas |
| Estrategia de verificación de salida | Parcial — los parsers propios re-validan el resultado |
| Congelamiento de versión | ❌ — debe fijarse en el lockfile de dependencias |

---

## 7. Criterios de listo para verificación

Un módulo está listo para la fase de verificación cuando:
- Compila sin errores (`python -m py_compile <módulo>`).
- Los tests asociados pasan al 100 % (`pytest tests/<subsistema>/`).
- El código está mergeado en `main` y etiquetado en el baseline SCM.
- Los HLR cubiertos están trazados en la Matriz de Trazabilidad.

---

## 8. Brechas abiertas respecto a DO-278A

| Brecha | Impacto | Acción requerida |
|---|---|---|
| Sin `requirements.txt` completo ni lockfile | SWAL 2–3: reproducibilidad | Generar con pip-tools o conda-lock |
| Sin entorno de CI | Todos | Configurar pipeline (GitHub Actions / GitLab CI) |
| Sin cobertura de código medida | SWAL 2 (cobertura de decisiones) | Integrar `pytest-cov`; fijar umbral ≥ 80 % decisiones en SWAL 2 |
| Artefactos binarios en el repo (`.pcap`, `.duckdb`) | SCM / trazabilidad | Mover a almacenamiento externo con hash verificable |
| Sin revisiones de código documentadas | SWAL 2 | Implementar Pull Request con checklist de revisión |

---

## 9. Registro de cambios

| Ver | Fecha | Cambio |
|-----|-------|--------|
| 0.1 | 2026-07-03 | Creación del borrador inicial. |
