"""Rechazo de zonas MSAW corruptas en carga (SSR-09 / HLR-MSAW-02, SSA-A1).

El loader `msa_zones()` construye desde datos de configuración; `filtrar_zonas_validas`
garantiza que ninguna zona con altitud o geometría fuera de rango se use silenciosamente.
"""
from player.msaw.data import filtrar_zonas_validas
from player.msaw.model import MsaZone, MsaSector


def _zona(icao="SACO", center=(-31.3, -64.2), radius=25.0, sectors=None):
    return MsaZone(icao=icao, center=center, radius_nm=radius,
                   sectors=sectors if sectors is not None else [MsaSector(0, 360, 4100)])


def test_zona_valida_se_conserva():
    z = _zona()
    assert filtrar_zonas_validas([z]) == [z]


def test_msa_fuera_de_rango_se_descarta():
    """Un sector con msa_ft > 60000 ft (dato corrupto) → zona descartada."""
    mala = _zona(icao="BAD", sectors=[MsaSector(0, 360, 99999)])
    buena = _zona(icao="OK")
    res = filtrar_zonas_validas([mala, buena])
    assert res == [buena]


def test_center_fuera_de_rango_se_descarta():
    mala = _zona(icao="BAD", center=(120.0, -64.2))   # lat > 90
    assert filtrar_zonas_validas([mala]) == []


def test_radio_no_positivo_se_descarta():
    mala = _zona(icao="BAD", radius=0.0)
    assert filtrar_zonas_validas([mala]) == []


def test_descartes_no_lanzan_y_reportan(capsys):
    """El descarte no lanza excepción y deja traza (no es silencioso, EC-9)."""
    filtrar_zonas_validas([_zona(icao="BAD", sectors=[MsaSector(0, 360, -9999)])])
    err = capsys.readouterr().err
    assert "BAD" in err and "descartada" in err
