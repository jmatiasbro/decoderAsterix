"""Tests de ProfileManager (REQ-ROL-1): CRUD de perfiles y validación de esquema."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import shutil
import pytest
pytest.importorskip("PyQt6.QtWidgets")
from PyQt6.QtWidgets import QApplication

from player.profile_manager import ProfileManager


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def manager(tmp_path):
    config_path = str(tmp_path / "config_profile.json")
    m = ProfileManager(profile_path=config_path)
    m.profiles_dir = str(tmp_path)
    return m


_PERFIL_BASE = {
    "nombre_usuario": "Matias_TWR",
    "aeropuerto_trabajo": "SACO",
    "coordenadas_centro": {"lat": -31.31, "lon": -64.21},
    "nivel_incumbencia": 95,
    "frecuencias_sector": ["118.5", "121.9", "122.5"],
    "mapas_visibles": [],
    "stca_habilitado": False,
}


class TestProfileCRUD:

    def test_guardar_y_leer(self, manager, tmp_path):
        manager.guardar_perfil("Matias_TWR", _PERFIL_BASE)
        path = tmp_path / "Matias_TWR.json"
        assert path.exists()
        data = manager.leer_perfil("Matias_TWR")
        assert data["nombre_usuario"] == "Matias_TWR"
        assert data["aeropuerto_trabajo"] == "SACO"
        assert data["stca_habilitado"] is False
        assert data["coordenadas_centro"]["lat"] == pytest.approx(-31.31)

    def test_eliminar_perfil(self, manager, tmp_path):
        manager.guardar_perfil("Delete_Me", _PERFIL_BASE | {"nombre_usuario": "Delete_Me"})
        assert (tmp_path / "Delete_Me.json").exists()
        manager.eliminar_perfil("Delete_Me")
        assert not (tmp_path / "Delete_Me.json").exists()

    def test_leer_perfil_inexistente_lanza_error(self, manager):
        with pytest.raises(FileNotFoundError):
            manager.leer_perfil("noexiste")

    def test_nombre_vacio_lanza_error(self, manager):
        with pytest.raises(ValueError):
            manager.guardar_perfil("", _PERFIL_BASE)


class TestProfileValidacion:

    def test_lat_invalida_lanza_error(self, manager):
        datos = _PERFIL_BASE | {"coordenadas_centro": {"lat": "not_a_float", "lon": -64.21}}
        with pytest.raises((ValueError, Exception)):
            manager.guardar_perfil("Bad_Lat", datos)

    def test_nivel_invalido_lanza_error(self, manager):
        datos = _PERFIL_BASE | {"nivel_incumbencia": "not_an_int"}
        with pytest.raises((ValueError, Exception)):
            manager.guardar_perfil("Bad_Nivel", datos)


class TestRadarWidgetPerfil:

    def test_configurar_vista_perfil(self, app):
        from player.radar_widget import RadarWidget
        radar = RadarWidget()
        radar.resize(800, 600)
        radar.configurar_vista_perfil(-31.31, -64.21)
        assert radar.proy.center_lat == pytest.approx(-31.31)
        assert radar.proy.center_lon == pytest.approx(-64.21)
        assert radar.zoom_factor > 0

    def test_stca_deshabilitado_limpia_alertas(self, app):
        from player.radar_widget import RadarWidget
        radar = RadarWidget()
        radar.stca_habilitado = False
        radar.tracks_en_alerta = {"track_A", "track_B"}
        radar.evaluar_stca()
        assert len(radar.tracks_en_alerta) == 0
        assert len(radar.conflictos_activos) == 0
