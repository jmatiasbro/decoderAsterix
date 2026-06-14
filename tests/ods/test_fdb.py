from player.ods import fdb


class P:
    def __init__(self, callsign="", mode3a=None, fl=None, gs=None, vrate=None, mode_s=None):
        self.callsign = callsign
        self.mode3a = mode3a
        self.flight_level = fl
        self.ground_speed = gs
        self.vertical_rate_ftmin = vrate
        self.mode_s = mode_s


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

def test_filtro_oculta_velocidad():
    p = P(callsign="IBE123", fl=330, gs=420, vrate=0)
    lines = fdb.build_lines(p, full=True, fields={"velocidad": False})
    assert lines == ["IBE123", "FL330="]

def test_filtro_oculta_callsign_cae_a_squawk():
    p = P(callsign="IBE123", mode3a="2345", fl=330)
    lines = fdb.build_lines(p, full=True, fields={"identific_aeronave": False})
    assert lines[0] == "2345"

def test_filtro_agrega_direccion_mode_s():
    p = P(callsign="IBE123", mode_s="780D74", fl=330)
    lines = fdb.build_lines(p, full=True, fields={"direccion_aeronave": True})
    assert lines[0] == "IBE123 780D74"

def test_filtro_oculta_direccion_mode_s_por_defecto_sin_fields():
    # Sin fields (None) no se agrega Mode S salvo que el plot lo tenga y el
    # comportamiento histórico mostraba solo callsign.
    p = P(callsign="IBE123", mode_s="780D74", fl=330)
    lines = fdb.build_lines(p, full=True, fields={"direccion_aeronave": False})
    assert lines[0] == "IBE123"

def test_filtro_oculta_nivel_requiere_ambos_off():
    p = P(callsign="IBE123", fl=330, gs=420)
    lines = fdb.build_lines(p, full=True, fields={"codigo_c": False, "altitud_adsb": False})
    assert "FL330=" not in lines
    lines2 = fdb.build_lines(p, full=True, fields={"codigo_c": False})
    assert any(s.startswith("FL330") for s in lines2)
