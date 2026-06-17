from player.ods.declutter import resolve_shifts


def test_dos_etiquetas_encimadas_se_separan():
    centers = {"a": (100.0, 100.0, 40.0), "b": (105.0, 102.0, 40.0)}
    shifts = resolve_shifts(centers, min_dist=50.0, passes=2)
    ax, ay = centers["a"][0] + shifts["a"][0], centers["a"][1] + shifts["a"][1]
    bx, by = centers["b"][0] + shifts["b"][0], centers["b"][1] + shifts["b"][1]
    d = ((ax - bx) ** 2 + (ay - by) ** 2) ** 0.5
    assert d > 5.0

def test_etiquetas_lejanas_no_se_mueven():
    centers = {"a": (0.0, 0.0, 40.0), "b": (500.0, 500.0, 40.0)}
    shifts = resolve_shifts(centers, min_dist=50.0, passes=2)
    assert shifts["a"] == [0.0, 0.0] and shifts["b"] == [0.0, 0.0]
