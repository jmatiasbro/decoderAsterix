import os
import tempfile

from player.firmap.mbtiles import MBTilesWriter, MBTilesReader


def _tmp():
    d = tempfile.mkdtemp()
    return os.path.join(d, "t.mbtiles")


def test_put_get_roundtrip():
    p = _tmp()
    w = MBTilesWriter(p)
    w.put_tile(5, 10, 20, b"HELLO")
    w.close()
    r = MBTilesReader(p)
    assert r.get_tile(5, 10, 20) == b"HELLO"
    assert r.get_tile(5, 10, 21) is None
    r.close()


def test_has_tile_y_metadata():
    p = _tmp()
    w = MBTilesWriter(p)
    w.set_metadata(name="x", attribution="EOX", minzoom=4, maxzoom=12)
    assert not w.has_tile(3, 1, 1)
    w.put_tile(3, 1, 1, b"\x00")
    assert w.has_tile(3, 1, 1)
    w.close()
    meta = MBTilesReader(p).metadata()
    assert meta["attribution"] == "EOX"
    assert meta["maxzoom"] == "12"


def test_tms_y_flip_distingue_filas():
    """Dos tiles XYZ con distinto y no deben colisionar (flip TMS correcto)."""
    p = _tmp()
    w = MBTilesWriter(p)
    w.put_tile(4, 2, 3, b"A")
    w.put_tile(4, 2, 4, b"B")
    w.close()
    r = MBTilesReader(p)
    assert r.get_tile(4, 2, 3) == b"A"
    assert r.get_tile(4, 2, 4) == b"B"
