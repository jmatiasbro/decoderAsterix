"""REQ-AUD-1/2: Persistencia de eventos safety y exportación CSV de auditoría."""
import csv
import time
import pytest
from storage.duckdb_repo import DuckDBRepository
from analysis.exporters import PassExporter

# ── helpers ─────────────────────────────────────────────────────────────────

def _evento(repo, ts=50000.0, subsistema="STCA", transicion="ONSET",
            clave="('7C1234','7CABCD')", nivel="WARNING",
            origen="226/210", descripcion="Sep < 3 NM", sesion_id="S1"):
    repo.guardar_evento_safety(
        ts=ts, ts_wall=ts,
        subsistema=subsistema, transicion=transicion,
        clave=clave, nivel=nivel,
        origen=origen, descripcion=descripcion,
        sesion_id=sesion_id,
    )


@pytest.fixture
def repo(tmp_path):
    r = DuckDBRepository(str(tmp_path / "test.duckdb"))
    yield r
    r._stop_worker()


# ── REQ-AUD-1: persistencia asíncrona ───────────────────────────────────────

class TestGuardarEventoSafety:

    def test_evento_guardado_y_recuperado(self, repo):
        _evento(repo)
        repo.flush()
        rows = repo.query_safety_events()
        assert len(rows) == 1
        assert rows[0][2] == "STCA"          # subsistema
        assert rows[0][3] == "ONSET"         # transicion

    def test_multiples_eventos(self, repo):
        for i in range(5):
            _evento(repo, ts=50000.0 + i)
        repo.flush()
        rows = repo.query_safety_events()
        assert len(rows) == 5

    def test_filtro_por_subsistema(self, repo):
        _evento(repo, subsistema="STCA")
        _evento(repo, subsistema="APW",  clave="('TRK_1','AREA_R1','R')")
        _evento(repo, subsistema="MSAW", clave="('TRK_2','CBA_ELEV','T')")
        repo.flush()
        assert len(repo.query_safety_events(subsistema="STCA")) == 1
        assert len(repo.query_safety_events(subsistema="APW"))  == 1
        assert len(repo.query_safety_events(subsistema="MSAW")) == 1

    def test_filtro_por_sesion_id(self, repo):
        _evento(repo, sesion_id="S1")
        _evento(repo, sesion_id="S2")
        repo.flush()
        assert len(repo.query_safety_events(sesion_id="S1")) == 1
        assert len(repo.query_safety_events(sesion_id="S2")) == 1

    def test_filtro_ts_wall_rango(self, repo):
        _evento(repo, ts=1000.0)
        _evento(repo, ts=2000.0)
        _evento(repo, ts=3000.0)
        repo.flush()
        rows = repo.query_safety_events(ts_desde=1500.0, ts_hasta=2500.0)
        assert len(rows) == 1
        assert rows[0][0] == pytest.approx(2000.0)

    def test_onset_clear_persistidos(self, repo):
        _evento(repo, ts=100.0, transicion="ONSET")
        _evento(repo, ts=115.0, transicion="CLEAR")
        repo.flush()
        rows = repo.query_safety_events()
        transiciones = [r[3] for r in rows]
        assert "ONSET" in transiciones
        assert "CLEAR" in transiciones

    def test_clave_y_nivel_guardados(self, repo):
        _evento(repo, clave="('AA1111','BB2222')", nivel="ALERTA")
        repo.flush()
        rows = repo.query_safety_events()
        assert rows[0][4] == "('AA1111','BB2222')"
        assert rows[0][5] == "ALERTA"

    def test_sin_eventos_retorna_lista_vacia(self, repo):
        assert repo.query_safety_events() == []

    def test_flush_vacia_la_cola(self, repo):
        for _ in range(10):
            _evento(repo)
        repo.flush()
        # Si flush() retorna, la cola está drenada y la BD tiene los datos
        assert len(repo.query_safety_events()) == 10


# ── REQ-AUD-2: exportación CSV ───────────────────────────────────────────────

class TestExportSafetyEventsCSV:

    def test_csv_generado(self, repo, tmp_path):
        _evento(repo)
        repo.flush()
        exp = PassExporter(repo_db=repo)
        dest = str(tmp_path / "audit.csv")
        ok = exp.export_safety_events_csv(dest)
        assert ok
        assert (tmp_path / "audit.csv").exists()

    def test_csv_tiene_cabecera_correcta(self, repo, tmp_path):
        _evento(repo)
        repo.flush()
        exp = PassExporter(repo_db=repo)
        dest = str(tmp_path / "audit.csv")
        exp.export_safety_events_csv(dest)
        with open(dest, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            assert "subsistema" in reader.fieldnames
            assert "transicion" in reader.fieldnames
            assert "aeronave_1" in reader.fieldnames
            assert "duracion_s" in reader.fieldnames

    def test_csv_duracion_onset_clear(self, repo, tmp_path):
        clave = "('7C1234','7CABCD')"
        _evento(repo, ts=1000.0, transicion="ONSET", clave=clave)
        _evento(repo, ts=1015.0, transicion="CLEAR", clave=clave)
        repo.flush()
        exp = PassExporter(repo_db=repo)
        dest = str(tmp_path / "dur.csv")
        exp.export_safety_events_csv(dest)
        with open(dest, encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        onset_row = next(r for r in rows if r["transicion"] == "ONSET")
        assert onset_row["duracion_s"] == "15.0"

    def test_csv_onset_sin_clear_duracion_vacia(self, repo, tmp_path):
        _evento(repo, ts=1000.0, transicion="ONSET")
        repo.flush()
        exp = PassExporter(repo_db=repo)
        dest = str(tmp_path / "nodur.csv")
        exp.export_safety_events_csv(dest)
        with open(dest, encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        assert rows[0]["duracion_s"] == ""

    def test_csv_stca_aeronaves_extraidas(self, repo, tmp_path):
        _evento(repo, subsistema="STCA", clave="('7C1234','7CABCD')")
        repo.flush()
        exp = PassExporter(repo_db=repo)
        dest = str(tmp_path / "stca.csv")
        exp.export_safety_events_csv(dest)
        with open(dest, encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        assert rows[0]["aeronave_1"] == "7C1234"
        assert rows[0]["aeronave_2"] == "7CABCD"

    def test_csv_apw_aeronaves_extraidas(self, repo, tmp_path):
        _evento(repo, subsistema="APW", clave="('TRK_5','AREA_R1','R')")
        repo.flush()
        exp = PassExporter(repo_db=repo)
        dest = str(tmp_path / "apw.csv")
        exp.export_safety_events_csv(dest)
        with open(dest, encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        assert rows[0]["aeronave_1"] == "TRK_5"
        assert rows[0]["aeronave_2"] == "AREA_R1"

    def test_csv_vacio_retorna_false(self, repo, tmp_path):
        exp = PassExporter(repo_db=repo)
        dest = str(tmp_path / "empty.csv")
        ok = exp.export_safety_events_csv(dest)
        assert ok is False

    def test_csv_filtro_sesion_id(self, repo, tmp_path):
        _evento(repo, sesion_id="S1", ts=1.0)
        _evento(repo, sesion_id="S2", ts=2.0)
        repo.flush()
        exp = PassExporter(repo_db=repo)
        dest = str(tmp_path / "ses1.csv")
        exp.export_safety_events_csv(dest, sesion_id="S1")
        with open(dest, encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        assert len(rows) == 1
        assert rows[0]["sesion_id"] == "S1"
