"""Verifica el linter del estándar SWAL 2 (tools/lint_swal2.py, doc 13 §7).

Cubre dos propiedades: (1) el árbol real es conforme; (2) el linter efectivamente
detecta cada prohibición dura (no es un no-op que siempre pasa).
"""
import importlib.util
import os

import pytest

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
_LINT = os.path.join(_REPO, "tools", "lint_swal2.py")


def _cargar_modulo():
    spec = importlib.util.spec_from_file_location("lint_swal2", _LINT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_arbol_real_conforme():
    """El código SWAL 2 vigente pasa el linter (regresión de conformidad)."""
    mod = _cargar_modulo()
    assert mod.main() == 0


def test_encuentra_modulos():
    mod = _cargar_modulo()
    archivos = mod._archivos_swal2()
    assert any(a.name == "lifecycle.py" for a in archivos)
    assert any(a.name == "correlator.py" for a in archivos)
    assert all("__pycache__" not in a.parts for a in archivos)


@pytest.mark.parametrize("codigo,regla", [
    ("t = time.time()\n", "EC-7"),
    ("import PyQt6\n", "EC-6"),
    ("from PyQt6.QtCore import Qt\n", "EC-6"),
    ("from foo import *\n", "EC-5"),
])
def test_detecta_violacion(codigo, regla):
    """Cada prohibición se dispara sobre código real (fuera de string/comentario)."""
    mod = _cargar_modulo()
    lineas = list(mod._lineas_de_codigo(codigo))
    disparo = any(
        patron.search(limpia)
        for rid, patron, _ in mod._REGLAS if rid == regla
        for _, _, limpia in lineas
    )
    assert disparo, f"{regla} no detectó: {codigo!r}"


@pytest.mark.parametrize("codigo", [
    'x = "menciona time.time() en un string"\n',
    '"""Docstring: nada de time.time() acá."""\n',
    "# comentario con import PyQt6 y from x import *\n",
    '"""\nDocstring multilínea\ncon time.time() adentro\n"""\n',
])
def test_ignora_strings_y_comentarios(codigo):
    """time.time()/imports dentro de strings o comentarios NO son violación."""
    mod = _cargar_modulo()
    for _, _, limpia in mod._lineas_de_codigo(codigo):
        for _, patron, _ in mod._REGLAS:
            assert not patron.search(limpia), f"falso positivo en: {codigo!r}"
