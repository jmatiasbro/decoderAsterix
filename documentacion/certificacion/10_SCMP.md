# SCMP — Software Configuration Management Plan

**Sistema:** Decodificador ASTERIX + Display PPI ATC.
**Norma:** EUROCAE ED-109A / RTCA DO-278A — Sección 7 (Gestión de Configuración de Software).
**Versión:** 0.1 (borrador). **Fecha:** 2026-07-03. **Estado:** PROPUESTO — no aprobado por ANAC.

---

## 1. Propósito y alcance

Este plan define cómo se identifican, controlan, archivan y auditan los elementos de configuración
del software (SCI — Software Configuration Items) a lo largo del ciclo de vida, de modo que en
todo momento sea posible reproducir exactamente el estado del software en un punto dado.

El SCM cubre: código fuente, datos de ciclo de vida (planes, SRS, SDD, resultados de test),
herramientas de construcción, y las dependencias de terceros (SOUP).

---

## 2. Herramienta SCM

**Git** (versión ≥ 2.40) es la herramienta SCM del proyecto. El repositorio es local con
historial completo; la copia remota (cuando exista) es el espejo de respaldo y punto de
integración de ramas.

### 2.1 Ramas

| Rama | Propósito | Restricción |
|---|---|---|
| `main` | Baseline certificable | Solo merge via PR; no push directo |
| `feature/<nombre>` | Desarrollo de nueva función | Tiempo de vida corto; merge a `main` tras verificación |
| `hotfix/<nombre>` | Corrección urgente sobre baseline | Revisión obligatoria; merge a `main` con evidencia de test |

### 2.2 Convención de commits

```
tipo(scope): descripción en español

Tipos válidos: feat | fix | test | docs | refactor | perf | chore
Scope: decoder | tracking | areas | msaw | stca | fusion | storage | fdp | ui | cert

Co-Authored-By: <nombre>
```

Ejemplo: `fix(tracking): HLR-TRK-02 — timeout de track usa ToD ASTERIX`

---

## 3. Elementos de configuración (SCI)

### 3.1 Código fuente

| Directorio | Descripción | SWAL |
|---|---|---|
| `decoder/` | Parsers ASTERIX, DataEngine, router | 3 |
| `player/tracking/` | Ciclo de vida de tracks | 2 |
| `player/areas/` | Motor APW | 2 |
| `player/msaw/` | Motor MSAW | 2 |
| `player/radar_widget.py` | Matching/reconciliación (pasos A–E), cadena safety | 2 |
| `player/fdp/` | FDP/ADEXP — parser, dispatcher, worker | 4 |
| `fusion/` | Correlación multi-radar | 3 |
| `storage/` | Persistencia DuckDB | 4 |
| `player/main_window.py` | Ventana principal, HUD, roles | 4 |

### 3.2 Datos de ciclo de vida

| Elemento | Ubicación | Bajo SCM |
|---|---|---|
| Planes (PSAC, SDP, SVP, SCMP, SQAP) | `documentacion/certificacion/` | ✅ Git |
| SRS, FHA | `documentacion/certificacion/` | ✅ Git |
| Matriz de trazabilidad | `documentacion/certificacion/04_matriz_trazabilidad.md` | ✅ Git |
| Tests | `tests/` | ✅ Git |
| Resultados de tests | No archivados | ❌ Brecha — ver §7 |
| Registros de revisión | No formalizados | ❌ Brecha |

### 3.3 Exclusiones explícitas del SCM

Los siguientes elementos NO se versionan en Git (ignorados por `.gitignore`):

| Elemento | Razón |
|---|---|
| `*.pcap` | Binarios de captura; deben distribuirse por canal externo con hash SHA-256 |
| `*.duckdb`, `*.duckdb.wal` | Bases de datos generadas; se recrean desde el schema |
| `.venv/` | Entorno virtual WSL; no portable ni reproducible |
| `__pycache__/`, `*.pyc` | Artefactos generados |
| `.pcap` de referencia (`baires.pcap`) | Ver §4 |

---

## 4. Gestión de datos de referencia (PCAP)

El archivo `baires.pcap` (~296 k paquetes) se usa en el smoke test y los tests de rendimiento.
Al no estar en Git, su gestión es:

| Acción | Estado |
|---|---|
| Hash SHA-256 del archivo de referencia documentado | ❌ Pendiente |
| Procedimiento de obtención/distribución para el equipo | ❌ Pendiente |
| Verificación del hash antes de ejecutar tests de sistema | ❌ Pendiente |

> **Acción requerida:** Calcular `sha256sum baires.pcap`, registrar el hash en un archivo
> `tests/data/checksums.txt` versionado, y verificarlo en el script de CI.

---

## 5. Baseline y etiquetado de releases

### 5.1 Definición de baseline

Un baseline es un snapshot inmutable del software listo para revisión o entrega. Se crea con
una etiqueta Git anotada:

```
git tag -a v<mayor>.<menor>.<parche> -m "Baseline SOI-<n>: <descripción>"
```

Convención de versiones: `MAYOR.MENOR.PARCHE` donde:
- MAYOR: cambio de alcance o de SWAL.
- MENOR: nueva función o cobertura de requisito.
- PARCHE: corrección de defecto.

### 5.2 Baseline para SOI-1

El baseline de entrada a la primera revisión con ANAC (SOI-1) debe incluir:
- Todos los planes aprobados internamente (PSAC, SDP, SVP, SCMP, SQAP).
- La FHA y la SRS en estado borrador consolidado.
- La suite de tests pasando al 100 %.
- El gap analysis actualizado.

### 5.3 Baseline actual

| Etiqueta | Commit | Estado |
|---|---|---|
| (ninguno) | `main` en desarrollo | Pre-SOI-1 |

> **Acción requerida:** Crear la etiqueta `v0.1.0-soi1` al completar los planes y aprobarlos
> internamente.

---

## 6. Control de cambios

### 6.1 Proceso para cambios en módulos SWAL 2

1. **Solicitud de cambio**: descripción, HLR afectado, análisis de impacto.
2. **Implementación**: en rama `feature/` o `hotfix/`.
3. **Verificación**: tests pasan; revisión de código documentada.
4. **Aprobación**: revisor independiente (o el mismo desarrollador con registro formal mientras
   el equipo sea unipersonal — declarar la limitación en el SQAP).
5. **Merge**: a `main` con mensaje de commit que incluya referencia al HLR y al defecto (si aplica).
6. **Actualización de baseline**: nueva etiqueta si el cambio modifica un entregable de ciclo de vida.

### 6.2 Cambios de emergencia (hotfix)

Se permiten en `hotfix/` directamente sobre `main` solo si:
- El defecto afecta la operación en vivo del sistema.
- Se documenta un registro de análisis de impacto antes del merge.
- Los tests se ejecutan y pasan en `hotfix/` antes del merge.

---

## 7. Archivo de resultados de verificación

Para que los resultados de verificación sean evidencia de DO-278A, deben ser:

- **Reproducibles**: ejecutar `pytest tests/` con el mismo entorno produce el mismo resultado.
- **Archivados**: el reporte de pytest debe guardarse con referencia al commit/baseline.
- **Firmados**: asociados a una persona y fecha.

### 7.1 Procedimiento propuesto (a implementar)

```
# Generar reporte archivable:
python -m pytest tests/ --tb=short --html=resultados/pytest_<FECHA>_<COMMIT>.html \
    --self-contained-html

# Guardar junto con el hash del commit:
git rev-parse HEAD >> resultados/pytest_<FECHA>_<COMMIT>.html
```

> **Brecha crítica:** Hoy los resultados de tests solo existen en la consola local. No hay
> archivo de resultados asociado a ningún baseline. Esto bloquea la demostración de conformidad
> ante la autoridad.

---

## 8. Gestión de dependencias (SOUP)

| Dependencia | Versión fijada | Lockfile | Acción |
|---|---|---|---|
| Python 3.12 | Sí (path explícito en CLAUDE.md) | No | Documentar versión exacta |
| PyQt6 | No | No | Fijar en requirements.txt |
| DuckDB | ≥ 0.9 | No | Fijar versión exacta |
| pyproj | ≥ 3 | No | Fijar versión exacta |
| pytest | ≥ 7 | No | Fijar versión exacta |
| asterix_decoder-0.7.4 | Sí (nombre del paquete) | No | Documentar origen y hash |

> **Acción requerida:** Generar `requirements.lock` con `pip freeze > requirements.lock` en el
> entorno de referencia y commitear junto con el baseline SOI-1.

---

## 9. Auditoría SCM

El SQAP ([11_SQAP.md](11_SQAP.md)) planifica auditorías periódicas del proceso SCM que verifican:
- Que los cambios en módulos SWAL 2 siguen el proceso de §6.1.
- Que el `.gitignore` excluye correctamente artefactos generados.
- Que no hay commits directos a `main` sin PR (cuando se disponga de protección de rama).
- Que los baselines están etiquetados y los resultados de verificación archivados.

---

## 10. Brechas abiertas respecto a DO-278A

| Brecha | Severidad | Acción |
|---|---|---|
| Sin resultados de verificación archivados | Alta | Implementar reporte HTML + archivo en baseline |
| Sin lockfile de dependencias | Alta | `pip freeze` en entorno de referencia |
| Sin hash de `baires.pcap` | Media | `sha256sum` + `tests/data/checksums.txt` |
| Sin etiquetas de baseline | Media | `git tag v0.1.0-soi1` al completar SOI-1 |
| Sin protección de rama `main` | Media | Configurar en servidor Git cuando esté disponible |
| Sin registros de revisión formales | Media | Implementar checklist de PR |

---

## 11. Registro de cambios

| Ver | Fecha | Cambio |
|-----|-------|--------|
| 0.1 | 2026-07-03 | Creación del borrador inicial. |
