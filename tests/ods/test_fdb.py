from player.ods import fdb


class P:
    def __init__(self, callsign="", mode3a=None, fl=None, gs=None, vrate=None):
        self.callsign = callsign
        self.mode3a = mode3a
        self.flight_level = fl
        self.ground_speed = gs
        self.vertical_rate_ftmin = vrate


def test_level_con_tendencia_subiendo():
    assert fdb.format_level(330, 800) == "FL330↑"

def test_level_con_tendencia_bajando():
    assert fdb.format_level(330, -800) == "FL330↓"

def test_level_nivelado():
    assert fdb.format_level(330, 50) == "FL330="

def test_fdb_tres_lineas_track_correlado():
    p = P(callsign="IBE123", mode3a="2345", fl=330, gs=420, vrate=0)
    lines = fdb.build_lines(p, full=True)
    assert lines[0] == "IBE123"
    assert lines[1] == "FL330="
    assert lines[2] == "420"

def test_ldb_sin_callsign_usa_squawk():
    p = P(callsign="", mode3a="2345", fl=330)
    lines = fdb.build_lines(p, full=False)
    assert lines[0] == "2345"
