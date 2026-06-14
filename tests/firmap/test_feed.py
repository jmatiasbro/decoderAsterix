from player.firmap.feed import build_tracks


class _Proj:
    activo = True
    proj = object()

    def xy_to_latlon(self, x, y):
        return (-34.0 + y / 1e5, -64.0 + x / 1e5)


class _Plot:
    def __init__(self, pid, x, y, ta):
        self.id, self.x, self.y, self.track_angle = pid, x, y, ta
        self.category = 62

    def is_alive(self):
        return True


class _Radar:
    def __init__(self):
        self.proy = _Proj()
        self.focused_target_id = "B"
        self.tracks = {"A": _Plot("A", 1000.0, 2000.0, 90.0),
                       "B": _Plot("B", -3000.0, 500.0, None)}

    def _build_plot_label_lines(self, p):
        return [p.id, "F350= 450", "090°"]


def test_build_tracks_reproyecta_y_marca_seleccion():
    tr = {t["lines"][0]: t for t in build_tracks(_Radar())}
    assert set(tr) == {"A", "B"}
    assert abs(tr["A"]["lat"] - (-33.98)) < 1e-6
    assert abs(tr["A"]["lon"] - (-63.99)) < 1e-6
    assert tr["A"]["heading"] == 90.0      # de track_angle
    assert tr["B"]["heading"] == 0.0       # sin track_angle -> default
    assert tr["B"]["selected"] is True
    assert tr["A"]["selected"] is False


def test_build_tracks_sin_proyeccion_devuelve_vacio():
    r = _Radar()
    r.proy.activo = False
    assert build_tracks(r) == []
