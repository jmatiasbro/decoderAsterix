from player.ods import compass


def test_ticks_cada_10_grados():
    ticks = compass.bearing_ticks()
    assert len(ticks) == 36

def test_mayores_cada_30_grados_rotulados():
    ticks = {t.deg: t for t in compass.bearing_ticks()}
    assert ticks[0].major and ticks[0].label == "360"
    assert ticks[30].major and ticks[30].label == "030"
    assert not ticks[10].major and ticks[10].label == ""

def test_range_marks_devuelve_nm_y_radio_px():
    marks = compass.range_marks(radius_px=300.0, range_nm=60.0, step_nm=20.0)
    assert marks[0] == (20.0, 100.0)
    assert marks[-1][0] <= 60.0
