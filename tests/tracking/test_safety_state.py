"""Estado de redes de seguridad siempre disponible en la HMI (SSR-10 / HLR-HMI-05, SSA-A7).

`estado_redes_seguridad()` es la fuente única de verdad del indicador HMI siempre
visible: refleja los flags *_habilitado sin requerir acción del operador (abrir menú).
"""
import pytest

from tests.tracking.test_matching import app  # noqa: F401


@pytest.fixture
def w(app):
    from player.radar_widget import RadarWidget
    widget = RadarWidget()
    widget.projection_set = True
    return widget


def test_estado_por_defecto_todas_habilitadas(w):
    assert w.estado_redes_seguridad() == {"STCA": True, "APW": True, "MSAW": True}


def test_refleja_inhibicion_individual(w):
    w.stca_habilitado = False
    w.apw_habilitado = True
    w.msaw_habilitado = False
    assert w.estado_redes_seguridad() == {"STCA": False, "APW": True, "MSAW": False}


def test_claves_completas_las_tres_redes(w):
    assert set(w.estado_redes_seguridad()) == {"STCA", "APW", "MSAW"}


def test_valores_son_booleanos(w):
    # Un flag ausente/truthy se normaliza a bool (no propaga tipos raros al HUD).
    w.stca_habilitado = 1
    estado = w.estado_redes_seguridad()
    assert all(isinstance(v, bool) for v in estado.values())
