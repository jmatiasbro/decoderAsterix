import inspect
from player.ods import symbology as S
from player.ods.track_state import PSR_ONLY, SSR, COMBINED, ADSB, SYSTEM_TRACK, COASTING


def test_cada_estado_tiene_spec():
    for st in (PSR_ONLY, SSR, COMBINED, ADSB, SYSTEM_TRACK, COASTING):
        spec = S.symbol_spec(st)
        assert spec.shape in S.SHAPES
        assert spec.size_px > 0

def test_psr_y_ssr_tienen_formas_distintas():
    assert S.symbol_spec(PSR_ONLY).shape != S.symbol_spec(SSR).shape

def test_coasting_es_punteado():
    assert S.symbol_spec(COASTING).dashed is True

def test_system_track_no_es_punteado():
    assert S.symbol_spec(SYSTEM_TRACK).dashed is False

def test_tamano_constante_no_depende_de_zoom():
    assert "zoom" not in inspect.signature(S.symbol_spec).parameters
