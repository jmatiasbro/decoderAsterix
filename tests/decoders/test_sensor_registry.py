"""REQ-DEC-5: SensorRegistry — carga de parámetros SAC/SIC desde JSON."""
import json
import pytest
from decoder.sensor_registry import SensorRegistry


def _escribir_sensor(tmp_path, sac, sic, lat, lon, nombre="Radar Test"):
    d = tmp_path / f"{sac}_{sic}.json"
    d.write_text(json.dumps({
        "name": nombre,
        "location": {"latitude": lat, "longitude": lon}
    }), encoding="utf-8")
    return d


class TestSensorRegistryCarga:

    def test_carga_json_desde_directorio(self, tmp_path):
        _escribir_sensor(tmp_path, 226, 210, -31.31, -64.21)
        reg = SensorRegistry(str(tmp_path))
        assert "226_210" in reg.sensors

    def test_carga_multiples_sensores(self, tmp_path):
        _escribir_sensor(tmp_path, 226, 210, -31.31, -64.21)
        _escribir_sensor(tmp_path, 226, 211, -34.82, -58.53)
        reg = SensorRegistry(str(tmp_path))
        assert len(reg.sensors) == 2

    def test_directorio_inexistente_no_falla(self, tmp_path):
        reg = SensorRegistry(str(tmp_path / "noexiste"))
        assert reg.sensors == {}

    def test_json_malformado_no_lanza(self, tmp_path):
        (tmp_path / "99_99.json").write_text("no es json", encoding="utf-8")
        reg = SensorRegistry(str(tmp_path))
        assert "99_99" not in reg.sensors

    def test_ignora_archivos_no_json(self, tmp_path):
        _escribir_sensor(tmp_path, 226, 210, -31.31, -64.21)
        (tmp_path / "readme.txt").write_text("nada")
        reg = SensorRegistry(str(tmp_path))
        assert len(reg.sensors) == 1


class TestSensorRegistryBusqueda:

    @pytest.fixture
    def reg(self, tmp_path):
        _escribir_sensor(tmp_path, 226, 210, -31.31, -64.21, "Cordoba")
        _escribir_sensor(tmp_path, 226, 211, -34.82, -58.53, "Ezeiza")
        return SensorRegistry(str(tmp_path))

    def test_get_coordenadas_sensor_existente(self, reg):
        lat, lon = reg.get_sensor_coordinates(226, 210)
        assert lat == pytest.approx(-31.31)
        assert lon == pytest.approx(-64.21)

    def test_get_coordenadas_sensor_segundo(self, reg):
        lat, lon = reg.get_sensor_coordinates(226, 211)
        assert lat == pytest.approx(-34.82)
        assert lon == pytest.approx(-58.53)

    def test_sensor_inexistente_retorna_none(self, reg):
        lat, lon = reg.get_sensor_coordinates(1, 1)
        assert lat is None and lon is None

    def test_sac_sic_string_se_convierte(self, reg):
        lat, lon = reg.get_sensor_coordinates("226", "210")
        assert lat == pytest.approx(-31.31)

    def test_sac_sic_invalido_retorna_none(self, reg):
        lat, lon = reg.get_sensor_coordinates(None, None)
        assert lat is None and lon is None

    def test_sac_sic_no_numerico_retorna_none(self, reg):
        lat, lon = reg.get_sensor_coordinates("abc", "xyz")
        assert lat is None and lon is None
