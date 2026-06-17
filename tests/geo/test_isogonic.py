from player.geo.isogonic import contour_lines


def _grid_value_lon(n_lat, n_lon, lat_min, lon_min, step):
    # value(i, j) = longitud del nodo -> isógonas verticales en lon = nivel
    return [[lon_min + j * step for j in range(n_lon)] for _ in range(n_lat)]


def test_contour_follows_requested_level():
    values = _grid_value_lon(4, 5, 0.0, 0.0, 1.0)
    lines = contour_lines(values, lat_min=0.0, lon_min=0.0, step=1.0, levels=[2.0])
    segs = lines[2.0]
    assert segs, "debe haber al menos un segmento en el nivel 2.0"
    for poly in segs:
        for (lat, lon) in poly:
            assert abs(lon - 2.0) < 1e-9
            assert 0.0 <= lat <= 3.0


def test_auto_levels_are_interior_integers():
    values = _grid_value_lon(3, 5, 0.0, 0.0, 1.0)  # rango lon 0..4
    lines = contour_lines(values, lat_min=0.0, lon_min=0.0, step=1.0)
    assert {1.0, 2.0, 3.0} <= set(lines.keys())
    assert 0.0 not in lines and 4.0 not in lines  # no niveles en los bordes


def test_empty_when_level_out_of_range():
    values = _grid_value_lon(3, 3, 0.0, 0.0, 1.0)  # lon 0..2
    lines = contour_lines(values, lat_min=0.0, lon_min=0.0, step=1.0, levels=[9.0])
    assert lines.get(9.0, []) == []
