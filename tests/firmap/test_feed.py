from player.firmap.feed import build_tracks


class _Proj:
    # Fiel a StereographicLocal: expone `activo` y xy_to_latlon (NO `proj`).
    activo = True

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
    r.proy = _Proj()
    r.proy.activo = False
    assert build_tracks(r) == []


def test_heading_desde_movimiento_si_falta_track_angle():
    from types import SimpleNamespace as S
    from player.firmap.feed import _heading
    p = S(track_angle=None, _smooth_vx=None, _smooth_vy=None)
    este = [S(x=0, y=0), S(x=100, y=0)]
    norte = [S(x=0, y=0), S(x=0, y=100)]
    assert round(_heading(p, este)) == 90    # x este -> 90
    assert round(_heading(p, norte)) == 0     # y norte -> 0
    assert _heading(S(track_angle=270.0), None) == 270.0
