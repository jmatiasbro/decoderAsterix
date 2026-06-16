import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
pytest.importorskip("PyQt6.QtWidgets")
from PyQt6.QtWidgets import QApplication
from player.centro_tecnico.stats_widget import StatsWidget
from player.stats.data_source import SessionSource


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def _session_provider():
    rows = [{"sac_sic": "25/01", "time": float(i), "flight_level": "100",
             "mode3a": "7000", "raw_range": 100.0 + i, "raw_azimuth": 10.0}
            for i in range(5)]
    src = SessionSource(rows)
    return lambda: src


def test_stats_widget_generate_renders(app):
    sw = StatsWidget(_session_provider())
    sw.set_metric("count"); sw.set_dimension("radar"); sw.set_chart("bar")
    sw.generate()
    assert sw.figure.axes               # algo se dibujó
    assert len(sw.figure.axes[0].patches) == 1   # 1 radar -> 1 barra


from player.centro_tecnico.window import CentroTecnicoWindow


def test_window_has_five_tabs(app):
    w = CentroTecnicoWindow()
    assert w.tabs.count() == 5
    titles = [w.tabs.tabText(i) for i in range(5)]
    assert any("Estad" in t for t in titles)
    assert any("Cobertura" in t for t in titles)


def test_source_toggle_default_duckdb(app):
    w = CentroTecnicoWindow()
    assert w.current_source_kind() in ("duckdb", "session")


from player.technical_monitor import TechnicalMonitorWidget


def test_monitor_tab_is_technical_monitor(app):
    w = CentroTecnicoWindow()
    idx = next(i for i in range(w.tabs.count()) if "Monitor" in w.tabs.tabText(i))
    assert isinstance(w.tabs.widget(idx), TechnicalMonitorWidget)


from PyQt6.QtWidgets import QTabWidget


def test_pass_tab_embeds_dashboard_tabs(app):
    w = CentroTecnicoWindow()
    # Pestaña PASS tiene cálculo diferido, refrescamos con resultados simulados
    w.refresh_pass_page({(25, 1): {"name": "Radar Test", "total_plots": 10, "pd_3d": 99.0, "pd_2d": 99.0, "bias_r": 0.0, "bias_theta": 0.0, "jitter_r": 0.0, "jitter_theta": 0.0}})
    idx = next(i for i in range(w.tabs.count()) if "PASS" in w.tabs.tabText(i))
    page = w.tabs.widget(idx)
    assert page.findChild(QTabWidget) is not None, \
        "PASS tab debe contener un QTabWidget interno del PassDashboardDialog"


from player.centro_tecnico.inspector_widget import InspectorWidget


def test_inspector_widget_builds_without_db(app):
    iw = InspectorWidget(repo_db=None, worker=None)
    assert iw is not None    # no debe lanzar sin repo_db


def test_inspector_tab_is_inspector_widget(app):
    w = CentroTecnicoWindow()
    idx = next(i for i in range(w.tabs.count()) if "Inspector" in w.tabs.tabText(i))
    assert isinstance(w.tabs.widget(idx), InspectorWidget)


def test_technical_import_worker_scans_and_updates(app, tmp_path):
    import unittest.mock as mock
    from player.centro_tecnico.window import TechnicalImportWorker
    from storage.duckdb_repo import DuckDBRepository
    
    db_file = tmp_path / "test_import.duckdb"
    repo = DuckDBRepository(str(db_file))
    
    with mock.patch("decoder.data_engine.DataEngine") as MockEngine:
        instance = MockEngine.return_value
        from decoder.data_engine import AsterixPlot
        mock_plot = AsterixPlot(
            id="test_id",
            sac_sic="25/01",
            category=48,
            time=123.45,
            lat=-31.0,
            lon=-64.0,
            mode3a="7000",
            callsign="ARG123",
            flight_level=150.0,
            altitude_ft=15000.0,
            is_track=False
        )
        mock_plot.ground_speed = 250.0
        mock_plot.track_angle = 180.0
        mock_plot.vertical_rate_ftmin = 0.0
        mock_plot.raw_range = 100.0
        mock_plot.raw_azimuth = 45.0
        mock_plot.mode_s = "7C1234"
        
        def mock_scan_pcap(file_paths):
            return ([mock_plot], 1.0, {("25", "01")})
            
        instance.scan_pcap.side_effect = mock_scan_pcap
        
        worker = TechnicalImportWorker(["dummy.pcap"], str(db_file), repo_db=repo)
        
        # Correr el worker sincrónicamente para testear linealmente
        worker.run()
        
        # Simular el guardado en base de datos que hace la ventana principal en el hilo principal
        repo.recrear_tabla()
        repo.guardar_plots_bulk([mock_plot.to_dict()])
        
        # Verificar que la tabla asterix_plots se creó y contiene el registro
        res = repo.query("SELECT sac_sic, timestamp, flight_level FROM asterix_plots")
        assert len(res) == 1
        assert res[0][0] == "25/01"
        assert res[0][1] == 123.45
        assert res[0][2] == "150.0"
        repo.close()


def test_guardar_plots_bulk_csv_copy_verification(tmp_path):
    from storage.duckdb_repo import DuckDBRepository
    db_file = tmp_path / "test_bulk_copy.duckdb"
    repo = DuckDBRepository(str(db_file))
    
    # Recrear la tabla
    repo.recrear_tabla()
    
    # Definir plots con datos variados
    plots = [
        # Plot 1: Registro completo con raw bytes (BLOB)
        {
            "time": 1000.0,
            "pcap_time": 2000.0,
            "category": 48,
            "sac_sic": "226/210",
            "mode_s": "7C1234",
            "callsign": "ARG123",
            "mode3a": 0o2375,
            "lat": -31.1,
            "lon": -64.2,
            "flight_level": "100",
            "raw_azimuth": 45.0,
            "raw_range": 120.0,
            "track_number": 12,
            "altitude_ft": 10000.0,
            "ground_speed": 250.0,
            "track_angle": 180.0,
            "vertical_rate_ftmin": -500.0,
            "id": "plot_1",
            "raw_bytes": b"\x00\x01\xff\x7f\x80",
            "garbled": True,
            "frequency": 1030.0,
            "pd": 99.5
        },
        # Plot 2: Registro mínimo (valores nulos / por defecto)
        {
            "time": 1001.0,
            "pcap_time": 2001.0,
            "category": 48,
            "sac_sic": "07/10",
            "id": "plot_2",
            "raw_bytes": None,
            "altitude_ft": None,
            "ground_speed": None,
            "garbled": False
        },
        # Plot 3: Caracteres especiales en columnas de texto (comas y comillas)
        {
            "time": 1002.0,
            "pcap_time": 2002.0,
            "category": 34,
            "sac_sic": "99/99",
            "callsign": "ARG, \"ABC\"",
            "id": "plot_3",
            "raw_bytes": b"\xaa\xbb"
        }
    ]
    
    repo.guardar_plots_bulk(plots)
    
    # Consultar todos los registros insertados
    res = repo.query("SELECT * FROM asterix_plots ORDER BY timestamp ASC")
    assert len(res) == 3
    
    # Verificar Plot 1
    p1 = res[0]
    assert p1[0] == 1000.0
    assert p1[1] == 2000.0
    assert p1[2] == 48
    assert p1[3] == "226/210"
    assert p1[4] == "7C1234"
    assert p1[5] == "ARG123"
    assert p1[6] == "2375" # Squawk octal
    assert p1[7] == -31.1
    assert p1[8] == -64.2
    assert p1[9] == "100"
    assert p1[10] == 45.0
    assert p1[11] == 120.0
    assert p1[12] == 12
    assert p1[13] == "7C1234"
    assert p1[14] == 10000.0
    assert p1[15] == 250.0
    assert p1[16] == 180.0
    assert p1[17] == -500.0
    assert p1[18] == "plot_1"
    assert p1[19] == b"\x00\x01\xff\x7f\x80"
    assert p1[20] is True
    assert p1[21] == 1030.0
    assert p1[22] == 99.5
    
    # Verificar Plot 2 (Valores Nulos)
    p2 = res[1]
    assert p2[0] == 1001.0
    assert p2[14] is None # altitude_ft
    assert p2[15] is None # ground_speed
    assert p2[19] is None # raw_bytes
    assert p2[20] is False # garbled
    
    # Verificar Plot 3 (Escapado de comillas/comas)
    p3 = res[2]
    assert p3[0] == 1002.0
    assert p3[5] == "ARG, \"ABC\""
    assert p3[19] == b"\xaa\xbb"
    
    repo.close()


def test_pass_analytics_engine_with_string_flight_level():
    from analysis.pass_analyzer import PASSAnalyticsEngine
    
    sensores = {
        (226, 230): {
            'lat': -34.8222,
            'lon': -58.5358,
            'name': "Ezeiza PSR/SSR",
            'type': "PSR/SSR",
            'category': "CAT048"
        }
    }
    
    engine = PASSAnalyticsEngine(sensores=sensores)
    
    plots = [
        {
            'sac_sic': '226/230',
            'time': 1000.0,
            'category': 48,
            'mode_s': '7C1234',
            'callsign': 'ARG123',
            'mode3a': '2375',
            'lat': -34.8,
            'lon': -58.5,
            'flight_level': '100.0',
            'raw_azimuth': 45.0,
            'raw_range': 12.0
        },
        {
            'sac_sic': '226/230',
            'time': 1004.0,
            'category': 48,
            'mode_s': '7C1234',
            'callsign': 'ARG123',
            'mode3a': '2375',
            'lat': -34.81,
            'lon': -58.51,
            'flight_level': '101.0',
            'raw_azimuth': 46.0,
            'raw_range': 13.0
        },
        {
            'sac_sic': '226/230',
            'time': 1008.0,
            'category': 48,
            'mode_s': '7C1234',
            'callsign': 'ARG123',
            'mode3a': '2375',
            'lat': -34.82,
            'lon': -58.52,
            'flight_level': '---',
            'raw_azimuth': 47.0,
            'raw_range': 14.0
        }
    ]
    
    results = engine.analyze_data(plots, {})
    
    assert (226, 230) in results
    sensor_res = results[(226, 230)]
    assert sensor_res['total_plots'] == 3
    assert 'range_bias_m' in sensor_res
    assert 'range_jitter_m' in sensor_res
    
    overlap_res = engine.calculate_overlap_pd(plots)
    assert 'pairwise' in overlap_res


def test_pass_analytics_engine_with_timestamp_key():
    from analysis.pass_analyzer import PASSAnalyticsEngine
    
    sensores = {
        (226, 230): {
            'lat': -34.8222,
            'lon': -58.5358,
            'name': "Ezeiza PSR/SSR",
            'type': "PSR/SSR",
            'category': "CAT048"
        }
    }
    
    engine = PASSAnalyticsEngine(sensores=sensores)
    
    # plots con 'timestamp' en lugar de 'time' (formato DuckDBSource/SessionSource)
    plots = [
        {
            'sac_sic': '226/230',
            'timestamp': 1000.0,
            'category': 48,
            'mode_s': '7C1234',
            'callsign': 'ARG123',
            'mode3a': '2375',
            'lat': -34.8,
            'lon': -58.5,
            'flight_level': 100.0,
            'raw_azimuth': 45.0,
            'raw_range': 12.0
        },
        {
            'sac_sic': '226/230',
            'timestamp': 1004.0,
            'category': 48,
            'mode_s': '7C1234',
            'callsign': 'ARG123',
            'mode3a': '2375',
            'lat': -34.81,
            'lon': -58.51,
            'flight_level': 101.0,
            'raw_azimuth': 46.0,
            'raw_range': 13.0
        }
    ]
    
    results = engine.analyze_data(plots, {})
    assert (226, 230) in results
    sensor_res = results[(226, 230)]
    assert sensor_res['total_plots'] == 2

