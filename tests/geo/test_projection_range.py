"""Rechazo de centro de proyección fuera de rango (SSR-03 / HLR-GEO-03, SSA-A3).

La proyección estereográfica no debe construirse con un centro geográficamente
implausible: en vez de generar posiciones silenciosamente corruptas, rechaza el
centro con ValueError para que el caller lo trate como no inicializado.
"""
import pytest

from utils.geo import StereographicLocal


def test_centro_valido_construye():
    p = StereographicLocal(-31.3, -64.2)
    x, y = p.latlon_to_xy(-31.3, -64.2)
    assert abs(x) < 1.0 and abs(y) < 1.0     # el centro proyecta a ~(0,0)


@pytest.mark.parametrize("lat,lon", [
    (120.0, -64.2),     # lat > 90
    (-91.0, 0.0),       # lat < -90
    (-31.3, 200.0),     # lon > 180
    (-31.3, -181.0),    # lon < -180
])
def test_centro_fuera_de_rango_rechazado(lat, lon):
    with pytest.raises(ValueError, match="fuera de rango"):
        StereographicLocal(lat, lon)


def test_set_center_fuera_de_rango_rechazado():
    p = StereographicLocal(-31.3, -64.2)      # arranca válido
    with pytest.raises(ValueError, match="fuera de rango"):
        p.set_center(999.0, 999.0)


def test_centro_no_numerico_rechazado():
    with pytest.raises(ValueError, match="no numérico"):
        StereographicLocal("abc", -64.2)
