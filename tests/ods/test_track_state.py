from player.ods.track_state import classify, PSR_ONLY, SSR, COMBINED, ADSB, SYSTEM_TRACK, COASTING


class P:
    """Stub mínimo con los atributos que lee classify()."""
    def __init__(self, category=48, mode3a=None, mode_s=None, det_type=None):
        self.category = category
        self.mode3a = mode3a
        self.mode_s = mode_s
        self.raw_dict = {"det_type": det_type} if det_type is not None else {}


def test_cat62_es_system_track():
    assert classify(P(category=62), is_coasting=False) == SYSTEM_TRACK

def test_cat21_es_adsb():
    assert classify(P(category=21, mode_s="ABCDEF"), is_coasting=False) == ADSB

def test_cat48_sin_codigo_es_psr():
    assert classify(P(category=48), is_coasting=False) == PSR_ONLY

def test_cat48_con_squawk_es_ssr():
    assert classify(P(category=48, mode3a="7000"), is_coasting=False) == SSR

def test_cat48_combinado_por_det_type():
    assert classify(P(category=48, mode3a="7000", det_type=3), is_coasting=False) == COMBINED

def test_coasting_tiene_prioridad():
    assert classify(P(category=62), is_coasting=True) == COASTING
