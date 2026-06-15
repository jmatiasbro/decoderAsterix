from analysis.coverage import classify_fl, FL_BANDS

def test_classify_fl_buckets():
    assert classify_fl("50") == 50      # FL50 cae en banda 50
    assert classify_fl("120") == 100    # 125 > x >= 75 -> 100
    assert classify_fl("300") == 300
    assert classify_fl("400") == 300    # >=275 -> 300
    assert classify_fl("25000") == 250  # pies: 25000/100=250 -> banda 250

def test_classify_fl_feet_normalization():
    # valores > 450 se interpretan como pies y se dividen por 100
    assert classify_fl("5000") == 50    # 5000/100 = 50
    assert classify_fl("25000") == 250  # 25000/100 = 250

def test_classify_fl_invalid():
    assert classify_fl(None) is None
    assert classify_fl("---") is None
    assert classify_fl("abc") is None
    assert classify_fl("10") is None    # < 25, fuera de bandas

import numpy as np
from analysis.coverage import compute_coverage, CoverageResult
from utils.geo import GeoTools

def _point_at(lat, lon, az_deg, r_nm):
    return GeoTools.vincenty_forward(lat, lon, az_deg, GeoTools.nm_to_meters(r_nm))

def test_compute_coverage_p95_range():
    rlat, rlon = -31.31, -64.21
    plots = []
    # 20 plots a ~100 NM en azimut 90, todos FL100
    for _ in range(20):
        plat, plon = _point_at(rlat, rlon, 90.0, 100.0)
        plots.append((plat, plon, "100"))
    res = compute_coverage(plots, rlat, rlon)
    assert isinstance(res, CoverageResult)
    assert res.plot_count == 20
    # banda 100, sector azimut 90 -> ~100 NM (tolerancia por proyección)
    assert abs(res.levels[100][90] - 100.0) < 2.0
    # sector sin datos -> 0
    assert res.levels[100][200] == 0.0

def test_compute_coverage_requires_min_plots():
    # < 10 plots en una banda -> banda vacía (todo 0)
    rlat, rlon = -31.31, -64.21
    plots = [(_point_at(rlat, rlon, 10.0, 50.0) + ("50",)) for _ in range(3)]
    res = compute_coverage(plots, rlat, rlon)
    assert all(r == 0.0 for r in res.levels[50])
