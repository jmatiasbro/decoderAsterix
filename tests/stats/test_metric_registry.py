from player.stats.metric_registry import METRICS, DIMENSIONS, aggregate, metric_by_id

def _rows():
    return [
        {"sac_sic": "25/01", "timestamp": 0.0, "flight_level": "100",
         "mode3a": "7000", "raw_range": 100.0, "raw_azimuth": 10.0},
        {"sac_sic": "25/01", "timestamp": 3600.0, "flight_level": "200",
         "mode3a": "7000", "raw_range": 50.0, "raw_azimuth": 20.0},
        {"sac_sic": "07/10", "timestamp": 0.0, "flight_level": "100",
         "mode3a": "1200", "raw_range": 200.0, "raw_azimuth": 30.0},
    ]

def test_registry_has_core_metrics_and_dims():
    ids = {m.id for m in METRICS}
    assert {"count", "avg_range", "p95_range"}.issubset(ids)
    assert {"radar", "hour", "mode3a"}.issubset(set(DIMENSIONS))

def test_aggregate_count_by_radar():
    res = dict(aggregate(_rows(), metric_by_id("count"), "radar"))
    assert res == {"25/01": 2, "07/10": 1}

def test_aggregate_avg_range_by_radar():
    res = dict(aggregate(_rows(), metric_by_id("avg_range"), "radar"))
    assert abs(res["25/01"] - 75.0) < 1e-9     # (100+50)/2
    assert abs(res["07/10"] - 200.0) < 1e-9

def test_aggregate_count_by_mode3a():
    res = dict(aggregate(_rows(), metric_by_id("count"), "mode3a"))
    assert res["7000"] == 2 and res["1200"] == 1
