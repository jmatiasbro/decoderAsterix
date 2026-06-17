from player.msaw.model import ApmCorridor, ProfileCorridor, SuppressionSet

# Corredor sintético: eje sur->norte de (0,0) [umbral, elev 0] a (0.2,0) [far].
# 0.2° lat ~ 12 NM. half_wide 1 NM, slopes 2.5/4.8°, min/max 3..12 NM.
APM = ApmCorridor(airport="T", runway="01", near=(0.0, 0.0), far=(0.2, 0.0),
                  half_wide_nm=1.0, min_dist=3.0, max_dist=12.0,
                  lower_slope=2.5, upper_slope=4.8, glide_slope=3.0,
                  thr_elev_ft=0)


def _alt_a(d_nm, slope_deg):
    import math
    return d_nm * 6076.12 * math.tan(math.radians(slope_deg))


def test_apm_en_corredor_y_envelope_suprime():
    d = 6.0
    lat = d / 60.0
    alt = _alt_a(d, 3.0)            # glide nominal, dentro de [2.5, 4.8]
    assert APM.en_corredor(lat, 0.0) is True
    assert APM.en_envelope(lat, 0.0, alt) is True


def test_apm_fuera_lateral_no_suprime():
    lat = 6.0 / 60.0
    lon = 2.0 / (60.0 * 1.0)       # 2 NM al este -> fuera de half_wide=1
    assert APM.en_corredor(lat, lon) is False


def test_apm_fuera_de_banda_distancia():
    lat = 1.0 / 60.0               # 1 NM along (< min_dist 3)
    assert APM.en_corredor(lat, 0.0) is False


def test_apm_demasiado_bajo_fuera_de_envelope():
    d = 6.0
    lat = d / 60.0
    alt = _alt_a(d, 1.0)           # 1° < lower 2.5 -> demasiado bajo
    assert APM.en_corredor(lat, 0.0) is True
    assert APM.en_envelope(lat, 0.0, alt) is False


def test_suppression_set_apm():
    ss = SuppressionSet(apm=[APM], profiles=[],
                        params={"tol_altitude_ft": 300})
    d = 6.0
    lat = d / 60.0
    assert ss.suprime(lat, 0.0, _alt_a(d, 3.0)) is True
    assert ss.suprime(lat, 0.0, _alt_a(d, 1.0)) is False     # bajo envelope
    assert ss.suprime(2.0, 2.0, 5000) is False               # lejos


def test_profile_corridor_envelope():
    pc = ProfileCorridor(profile="P", kind="A",
                         points=[(0.0, 0.0, 2000, 0.5, 0),
                                 (0.1, 0.0, 4000, 0.5, 0)])
    # a mitad de camino (0.05 lat) el perfil interpola ~3000 ft
    assert pc.en_corredor(0.05, 0.0) is True
    assert pc.en_envelope(0.05, 0.0, 3100, tol_ft=300) is True
    assert pc.en_envelope(0.05, 0.0, 2000, tol_ft=300) is False
