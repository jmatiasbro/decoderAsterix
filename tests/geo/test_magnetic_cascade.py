from player.magnetic_compensator import MagneticCompensator
from player.geo import declination_grid as dg


def test_grid_used_when_wmm_absent(monkeypatch):
    mc = MagneticCompensator(fallback_deg=-7.0)
    mc._geomag = None                       # simula WMM no disponible
    mc._cache.clear()
    monkeypatch.setattr(dg, "declinacion", lambda lat, lon: 5.0)
    assert mc.obtener_declinacion(-34.6, -58.4) == 5.0


def test_static_fallback_when_grid_absent(monkeypatch):
    mc = MagneticCompensator(fallback_deg=-7.0)
    mc._geomag = None
    mc._cache.clear()
    monkeypatch.setattr(dg, "declinacion", lambda lat, lon: None)
    assert mc.obtener_declinacion(-34.6, -58.4) == -7.0


def test_none_coords_return_fallback():
    mc = MagneticCompensator(fallback_deg=-7.0)
    assert mc.obtener_declinacion(None, None) == -7.0
