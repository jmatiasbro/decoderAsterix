from player.stats.data_source import SessionSource

def _rec(sac_sic, t, fl="100", mode3a="7000", rng=100.0, az=45.0):
    # claves al estilo Plot.to_dict() de decoder/data_engine.py
    return {"sac_sic": sac_sic, "time": t, "lat": -31.0, "lon": -64.0,
            "flight_level": fl, "mode3a": mode3a, "raw_range": rng, "raw_azimuth": az}

def test_session_source_normalizes_keys():
    src = SessionSource([_rec("25/01", 1000.0)])
    rows = src.load()
    assert rows[0]["timestamp"] == 1000.0     # 'time' -> 'timestamp'
    assert rows[0]["sac_sic"] == "25/01"
    assert set(["sac_sic","timestamp","lat","lon","flight_level",
                "mode3a","raw_range","raw_azimuth"]).issubset(rows[0].keys())

def test_session_source_radars_sorted_unique():
    src = SessionSource([_rec("25/01", 1.0), _rec("07/10", 2.0), _rec("25/01", 3.0)])
    assert src.radars() == ["07/10", "25/01"]

def test_session_source_filters():
    src = SessionSource([_rec("25/01", 100.0), _rec("07/10", 200.0), _rec("25/01", 300.0)])
    assert len(src.load(radars=["25/01"])) == 2
    assert len(src.load(t_min=150.0, t_max=250.0)) == 1
