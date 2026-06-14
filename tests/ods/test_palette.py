from player.ods import palette as P
from player.ods.track_state import PSR_ONLY, SSR, COMBINED, ADSB, SYSTEM_TRACK, COASTING


def test_fondo_es_gris_neutro_oscuro():
    r, g, b = P.BG
    assert max(r, g, b) <= 30 and abs(r - g) <= 6 and abs(g - b) <= 6

def test_cada_estado_tiene_color():
    for st in (PSR_ONLY, SSR, COMBINED, ADSB, SYSTEM_TRACK, COASTING):
        assert st in P.STATE_RGB
        assert len(P.STATE_RGB[st]) == 3

def test_seleccionado_es_mas_brillante_que_normal():
    base = P.state_rgb(SYSTEM_TRACK, selected=False)
    sel = P.state_rgb(SYSTEM_TRACK, selected=True)
    assert sum(sel) > sum(base)

def test_alpha_por_intensidad_clampa():
    assert P.layer_alpha("labels", 0.0) == 0
    assert P.layer_alpha("labels", 1.0) == 255
    assert 0 <= P.layer_alpha("labels", 0.5) <= 255

def test_alerta_stca_es_rojo_dominante():
    r, g, b = P.ALERT_STCA
    assert r > 180 and g < 120 and b < 120

def test_capa_tools_existe_para_rbl():
    assert "tools" in P.LAYER_DEFAULT
    assert 0.0 <= P.LAYER_DEFAULT["tools"] <= 1.0

def test_tool_rbl_es_cian_apagado_no_saturado():
    r, g, b = P.TOOL_RBL
    # cian apagado: azul/verde dominan sobre rojo, baja saturación (no alerta)
    assert b >= r and g >= r
    assert max(r, g, b) < 230
