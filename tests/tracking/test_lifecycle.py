from types import SimpleNamespace as S

from player.tracking.lifecycle import identidad_codigo


def _plot(**kw):
    base = dict(timestamp=0.0, sac=1, sic=44, x=0.0, y=0.0,
                mode3a=None, mode_s=None, callsign=None, category=48)
    base.update(kw)
    return S(**base)


def test_squawk_es_la_clave():
    assert identidad_codigo(_plot(mode3a=0o1234)) == "1234"
    assert identidad_codigo(_plot(mode3a="2701")) == "2701"


def test_squawk_invalido_no_es_clave_sin_adsb():
    assert identidad_codigo(_plot(mode3a="0000", category=48)) is None
    assert identidad_codigo(_plot(mode3a="----", category=48)) is None


def test_adsb_usa_callsign_luego_mode_s():
    assert identidad_codigo(_plot(category=21, mode3a=None, callsign="AAL123",
                                  mode_s="ABCDEF")) == "AAL123"
    assert identidad_codigo(_plot(category=21, mode3a=None, callsign=None,
                                  mode_s="ABCDEF")) == "ABCDEF"


def test_psr_puro_sin_codigo_es_none():
    assert identidad_codigo(_plot(category=48, mode3a=None, mode_s=None,
                                  callsign=None)) is None
