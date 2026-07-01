"""REQ-GEO-1: StereographicLocal — proyección polar/WGS-84 ↔ cartesianas."""
import math
import pytest
from utils.geo import StereographicLocal

NM = 1852.0
CENTER_LAT, CENTER_LON = -31.31, -64.21   # Córdoba ACC


@pytest.fixture
def proy():
    return StereographicLocal(CENTER_LAT, CENTER_LON)


class TestRoundtripLatLon:

    def test_centro_mapea_a_cero(self, proy):
        x, y = proy.latlon_to_xy(CENTER_LAT, CENTER_LON)
        assert x == pytest.approx(0.0, abs=1.0)
        assert y == pytest.approx(0.0, abs=1.0)

    def test_roundtrip_norte(self, proy):
        lat, lon = CENTER_LAT + 1.0, CENTER_LON
        x, y = proy.latlon_to_xy(lat, lon)
        lat2, lon2 = proy.xy_to_latlon(x, y)
        assert lat2 == pytest.approx(lat, abs=1e-5)
        assert lon2 == pytest.approx(lon, abs=1e-5)

    def test_roundtrip_suroeste(self, proy):
        lat, lon = -34.82, -58.54   # Buenos Aires
        x, y = proy.latlon_to_xy(lat, lon)
        lat2, lon2 = proy.xy_to_latlon(x, y)
        assert lat2 == pytest.approx(lat, abs=1e-4)
        assert lon2 == pytest.approx(lon, abs=1e-4)

    def test_punto_norte_tiene_y_positivo(self, proy):
        x, y = proy.latlon_to_xy(CENTER_LAT + 1.0, CENTER_LON)
        assert y > 0

    def test_punto_este_tiene_x_positivo(self, proy):
        x, y = proy.latlon_to_xy(CENTER_LAT, CENTER_LON + 1.0)
        assert x > 0

    def test_distancia_preservada_50nm(self, proy):
        # 50 NM al norte
        x1, y1 = proy.latlon_to_xy(CENTER_LAT, CENTER_LON)
        x2, y2 = proy.latlon_to_xy(CENTER_LAT + 0.8327, CENTER_LON)  # ~50 NM
        dist = math.hypot(x2 - x1, y2 - y1)
        assert dist == pytest.approx(50 * NM, rel=0.01)


class TestSinCentro:

    def test_sin_centro_retorna_cero(self):
        p = StereographicLocal()
        x, y = p.latlon_to_xy(-31.31, -64.21)
        assert x == 0.0 and y == 0.0

    def test_set_center_activa_proyeccion(self):
        p = StereographicLocal()
        p.set_center(-31.31, -64.21)
        x, y = p.latlon_to_xy(-31.31, -64.21)
        assert x == pytest.approx(0.0, abs=1.0)
        assert y == pytest.approx(0.0, abs=1.0)

    def test_build_proj_sin_centro_lanza(self):
        p = StereographicLocal()
        with pytest.raises(ValueError):
            p._build_proj()


class TestRhoTheta:

    def test_rho_theta_to_xy_norte(self, proy):
        # 60 NM al Norte (0°) → x≈0, y≈111120 m
        x, y = proy.rho_theta_to_xy(60.0, 0.0)
        assert x == pytest.approx(0.0, abs=500)
        assert y == pytest.approx(60 * NM, rel=0.01)

    def test_rho_theta_to_xy_este(self, proy):
        x, y = proy.rho_theta_to_xy(60.0, 90.0)
        assert x > 0
        assert y == pytest.approx(0.0, abs=500)

    def test_rho_theta_to_wgs84_consistente_con_latlon_to_xy(self, proy):
        lat, lon = proy.rho_theta_to_wgs84(50.0, 45.0)
        x1, y1 = proy.latlon_to_xy(lat, lon)
        x2, y2 = proy.rho_theta_to_xy(50.0, 45.0)
        assert x1 == pytest.approx(x2, abs=10)
        assert y1 == pytest.approx(y2, abs=10)
