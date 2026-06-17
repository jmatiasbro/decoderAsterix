import pytest
from unittest.mock import MagicMock
from player.areas.model import Area, Vigencia

def test_get_all_areas_combines_db_and_user_areas(monkeypatch):
    from player import atm_db
    monkeypatch.setattr(atm_db, "available", lambda: True)
    
    db_area = Area("DB_AREA", "R", "poly", vertices=[(0, 0), (0, 1), (1, 1)])
    monkeypatch.setattr(atm_db, "restricted_airspaces", lambda: [db_area])
    
    # Test MainWindow.get_all_areas function
    from player.main_window import MainWindow
    win = MagicMock(spec=MainWindow)
    win.user_areas = [Area("USER_AREA", "P", "circle", center=(0, 0), radius_nm=5.0)]
    
    # Call the actual unbound method by passing the mock instance as 'self'
    result = MainWindow.get_all_areas(win)
    assert len(result) == 2
    assert result[0].name == "DB_AREA"
    assert result[1].name == "USER_AREA"

def test_radar_widget_get_all_areas(monkeypatch):
    from player import atm_db
    monkeypatch.setattr(atm_db, "available", lambda: True)
    
    db_area = Area("DB_AREA", "R", "poly", vertices=[(0, 0), (0, 1), (1, 1)])
    monkeypatch.setattr(atm_db, "restricted_airspaces", lambda: [db_area])
    
    # Test RadarWidget.get_all_areas function
    from player.radar_widget import RadarWidget
    radar = MagicMock(spec=RadarWidget)
    radar.user_areas = [Area("USER_AREA", "P", "circle", center=(0, 0), radius_nm=5.0)]
    
    result = RadarWidget.get_all_areas(radar)
    assert len(result) == 2
    assert result[0].name == "DB_AREA"
    assert result[1].name == "USER_AREA"


def test_radar_widget_evaluar_apw(monkeypatch):
    from player.radar_widget import RadarWidget
    
    radar = MagicMock(spec=RadarWidget)
    radar.tracks = {}
    radar.get_all_areas = MagicMock(return_value=[])
    radar.apw_habilitado = True
    radar.apw_dialog = MagicMock()
    
    # Call actual evaluar_apw via unbound call
    RadarWidget.evaluar_apw(radar)
    
    assert radar.apw_activos == []
    radar.apw_dialog.actualizar_alertas.assert_called_with([], radar)
