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


from player.tracking.lifecycle import (MonoradarLifecycle, TENTATIVE,
                                        CONFIRMED)

# scan_period fijo de 4 s (RPM=15) para todas las pruebas de ciclo
def _lc():
    return MonoradarLifecycle(scan_period_fn=lambda sac, sic: 4.0)


def _p(tod, code="1234", x=0.0, y=0.0):
    return _plot(timestamp=tod, mode3a=code, x=x, y=y, category=48)


def test_cuatro_vueltas_confirman():
    lc = _lc()
    for i, tod in enumerate([0.0, 4.0, 8.0]):     # vueltas 0,1,2
        lc.procesar(_p(tod))
        assert lc.estado("1234") == TENTATIVE
    lc.procesar(_p(12.0))                          # vuelta 3 → 4ª detección
    assert lc.estado("1234") == CONFIRMED
    assert lc.faltas("1234") == 0


def test_tres_vueltas_siguen_tentativas():
    lc = _lc()
    for tod in [0.0, 4.0, 8.0]:
        lc.procesar(_p(tod))
    assert lc.estado("1234") == TENTATIVE


def test_pista_nueva_arranca_tentativa():
    lc = _lc()
    lc.procesar(_p(0.0))
    assert lc.estado("1234") == TENTATIVE
    assert lc.faltas("1234") == 0
