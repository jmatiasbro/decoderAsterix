from player.msaw.model import MsaPolygon

# Cuadrado ~ (0,0)-(0,1)-(1,1)-(1,0) en lat/lon
SQUARE = [(0.0, 0.0), (0.0, 1.0), (1.0, 1.0), (1.0, 0.0)]


def test_dentro():
    p = MsaPolygon("Z", 5000, SQUARE)
    assert p.contiene(0.5, 0.5) is True
    assert p.msa_en(0.5, 0.5) == 5000


def test_fuera():
    p = MsaPolygon("Z", 5000, SQUARE)
    assert p.contiene(2.0, 2.0) is False
    assert p.msa_en(2.0, 2.0) is None


def test_pocos_vertices_no_contiene():
    p = MsaPolygon("Z", 5000, [(0.0, 0.0), (1.0, 1.0)])
    assert p.contiene(0.5, 0.5) is False
