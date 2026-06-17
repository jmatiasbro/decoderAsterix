import json
from player.geo import declination_grid as dg


def _grid():
    # value(i, j) = i + j sobre lat -1..1, lon -1..1, step 1
    return {"convention": "west-negative", "epoch": 2026.0,
            "lat_min": -1.0, "lat_max": 1.0, "lon_min": -1.0, "lon_max": 1.0,
            "step": 1.0, "n_lat": 3, "n_lon": 3,
            "values": [[r + c for c in range(3)] for r in range(3)]}


def test_interpolate_bilinear_center():
    g = _grid()
    # centro de la celda (0,0): esquinas 0,1,1,2 -> 1.0
    assert abs(dg.interpolate(g, -0.5, -0.5) - 1.0) < 1e-9


def test_interpolate_on_node():
    g = _grid()
    assert abs(dg.interpolate(g, 0.0, 1.0) - dg.G_NODE(g, 1, 2)) < 1e-9  # i=1,j=2 -> 3


def test_interpolate_clamps_outside_bbox():
    g = _grid()
    v = dg.interpolate(g, -50.0, -50.0)   # clamp a esquina (i0,j0) = 0
    assert abs(v - 0.0) < 1e-9


def test_declinacion_returns_none_when_file_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(dg, "DEFAULT_PATH", str(tmp_path / "nope.json"))
    dg._CACHE.clear()
    assert dg.declinacion(-34.6, -58.4) is None


def test_declinacion_reads_file(tmp_path, monkeypatch):
    p = tmp_path / "grid.json"
    p.write_text(json.dumps(_grid()), encoding="utf-8")
    monkeypatch.setattr(dg, "DEFAULT_PATH", str(p))
    dg._CACHE.clear()
    assert abs(dg.declinacion(-0.5, -0.5) - 1.0) < 1e-9
