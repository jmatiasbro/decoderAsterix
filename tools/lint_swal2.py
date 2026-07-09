#!/usr/bin/env python3
"""Linter del estándar de codificación SWAL 2 (doc 13 §7).

Control mecánico de regresión de las prohibiciones duras del estándar sobre los
módulos de seguridad. NO reemplaza la revisión de código (checklist CR-1..8): solo
automatiza las reglas verificables por análisis léxico.

Reglas verificadas (13_estandar_codificacion.md §6):
  EC-6 [SWAL2] — el núcleo de seguridad no importa PyQt6 (headless).
  EC-7 [SWAL2] — `time.time()` VEDADO en motores de decisión / ciclo de vida.
  EC-5        — sin `import *` en los módulos SWAL 2.

Uso:  python tools/lint_swal2.py
Salida: código 0 si conforme; 1 si hay violaciones (lista a stderr). Apto para CI.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

# Raíz del repo = padre de tools/
_ROOT = Path(__file__).resolve().parent.parent

# Módulos/paths SWAL 2 según el estándar §1. Los directorios se expanden a *.py.
_SWAL2_PATHS = [
    "analysis/stca_analyzer.py",
    "player/tracking/lifecycle.py",
    "fusion/correlator.py",
    "player/areas",
    "player/msaw",
]

# (id_regla, patrón, descripción). Se ignoran comentarios y docstrings triviales
# solo parcialmente: el patrón se evalúa por línea excluyendo comentarios.
_REGLAS = [
    ("EC-7", re.compile(r"\btime\.time\s*\("),
     "time.time() vedado en módulos SWAL 2 (usar SimulationTime/ToD)"),
    ("EC-6", re.compile(r"^\s*(from\s+PyQt6|import\s+PyQt6)\b"),
     "import de PyQt6 prohibido en el núcleo SWAL 2 (headless)"),
    ("EC-5", re.compile(r"^\s*from\s+\S+\s+import\s+\*"),
     "import * prohibido en código de producción"),
]


def _archivos_swal2() -> list[Path]:
    archivos: list[Path] = []
    for rel in _SWAL2_PATHS:
        p = _ROOT / rel
        if p.is_dir():
            archivos.extend(sorted(p.rglob("*.py")))
        elif p.is_file():
            archivos.append(p)
    # Excluir __pycache__ por si acaso
    return [a for a in archivos if "__pycache__" not in a.parts]


_TRIPLES = ('"""', "'''")


def _lineas_de_codigo(texto: str):
    """Genera (nº, línea_original, línea_sin_strings/comentarios).

    Neutraliza el contenido de strings (incl. docstrings triple-quote multilínea)
    y comentarios `#`, para no producir falsos positivos: p. ej. `time.time()`
    mencionado en un docstring no es una llamada. Solo importa que las palabras
    clave detectables (imports, llamadas) queden fuera de literales.
    """
    triple_activo = None  # comilla triple abierta que cruza líneas
    for n, linea in enumerate(texto.splitlines(), start=1):
        limpia: list[str] = []
        i = 0
        en_comilla = None  # comilla simple/doble de una línea
        while i < len(linea):
            resto = linea[i:]
            if triple_activo:
                fin = resto.find(triple_activo)
                if fin == -1:
                    i = len(linea)
                else:
                    i += fin + 3
                    triple_activo = None
                continue
            if en_comilla:
                if linea[i] == en_comilla and linea[i - 1] != "\\":
                    en_comilla = None
                i += 1
                continue
            if resto[:3] in _TRIPLES:
                # ¿se cierra en la misma línea?
                cierre = linea.find(resto[:3], i + 3)
                if cierre == -1:
                    triple_activo = resto[:3]
                    i = len(linea)
                else:
                    i = cierre + 3
                continue
            ch = linea[i]
            if ch == "#":
                break
            if ch in ("'", '"'):
                en_comilla = ch
                i += 1
                continue
            limpia.append(ch)
            i += 1
        yield n, linea, "".join(limpia)


def main() -> int:
    archivos = _archivos_swal2()
    if not archivos:
        print("lint_swal2: no se encontraron módulos SWAL 2 (¿ruta incorrecta?)",
              file=sys.stderr)
        return 1

    violaciones: list[str] = []
    for archivo in archivos:
        try:
            texto = archivo.read_text(encoding="utf-8")
        except OSError as exc:
            violaciones.append(f"{archivo}: no se pudo leer ({exc})")
            continue
        rel = archivo.relative_to(_ROOT).as_posix()
        for n, linea_cruda, linea in _lineas_de_codigo(texto):
            for rid, patron, desc in _REGLAS:
                if patron.search(linea):
                    violaciones.append(f"{rel}:{n} [{rid}] {desc}\n    → {linea_cruda.strip()}")

    if violaciones:
        print(f"lint_swal2: {len(violaciones)} violación(es) del estándar SWAL 2:\n",
              file=sys.stderr)
        for v in violaciones:
            print("  " + v, file=sys.stderr)
        return 1

    print(f"lint_swal2: OK — {len(archivos)} módulos SWAL 2 conformes "
          f"(EC-5/EC-6/EC-7).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
