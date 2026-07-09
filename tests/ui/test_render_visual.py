"""Regresión visual del render PPI (SSA-A2 / FC-HMI-01/02, cierra el residual de la SSA).

No compara imágenes doradas (frágil): verifica propiedades visuales invariantes
renderizando offscreen a QImage:
  1. Todo track vivo produce píxeles no-fondo en su posición de pantalla
     (FC-HMI-01: la omisión silenciosa del símbolo sería invisible para los
     tests de modelo; aquí se comprueba el píxel pintado).
  2. Una región vacía lejos de los tracks queda en color de fondo (control
     negativo: descarta que el test pase por ruido de render).
  3. El indicador HUD de estado de safety-nets pinta en su rectángulo (SSR-10).
"""
import pytest
from unittest.mock import patch

from tests.tracking.test_matching import app  # noqa: F401


W, H = 800, 600
T0 = 1000.0


@pytest.fixture
def w(app):
    from player.radar_widget import RadarWidget
    widget = RadarWidget()
    widget.projection_set = True
    widget.sensores_visibles = None
    widget.limpiar_pantalla()
    widget.resize(W, H)
    widget.zoom_factor = 0.005          # 30 km → 150 px: tracks bien adentro del viewport
    widget.pan_x = widget.pan_y = 0.0
    return widget


def _tracks(w, posiciones):
    """Inyecta un track CAT21 (promoción inmediata) por posición (x_m, y_m)."""
    with patch("player.radar_widget.SimulationTime.time", return_value=T0):
        for i, (x, y) in enumerate(posiciones):
            w._process_plot_data({
                "sac_sic": "226/210", "category": 21, "time": T0,
                "x_meters": float(x), "y_meters": float(y),
                "mode_s": f"{i:06X}", "callsign": f"TST{i:03d}",
            })


def _render(w):
    from PyQt6.QtGui import QImage, QPainter
    img = QImage(W, H, QImage.Format.Format_RGB32)
    img.fill(0xFF000000)                # fondo negro de referencia
    p = QPainter(img)
    w.render(p)
    p.end()
    return img


def _pintados_en(img, cx, cy, radio=14, umbral_lum=40):
    """Cuenta píxeles con luminancia > umbral en una caja alrededor de (cx, cy)."""
    n = 0
    for dy in range(-radio, radio + 1):
        for dx in range(-radio, radio + 1):
            x, y = int(cx) + dx, int(cy) + dy
            if 0 <= x < img.width() and 0 <= y < img.height():
                c = img.pixel(x, y)
                r, g, b = (c >> 16) & 0xFF, (c >> 8) & 0xFF, c & 0xFF
                if (r + g + b) / 3.0 > umbral_lum:
                    n += 1
    return n


def test_todo_track_vivo_pinta_simbolo(w):
    """FC-HMI-01: cada track vivo deja píxeles no-fondo en su posición proyectada.

    Nota: se excluye (0,0) porque el centro del PPI ya pinta su propia marca sin
    tracks (verificado por mutación) y pasaría en vacío."""
    posiciones = [(20000.0, 10000.0), (-30000.0, -15000.0), (15000.0, -25000.0), (-18000.0, 22000.0)]
    _tracks(w, posiciones)
    img = _render(w)
    sin_pintar = []
    for x, y in posiciones:
        pt = w._world_to_screen(x, y)
        assert pt is not None
        if _pintados_en(img, pt.x(), pt.y()) == 0:
            sin_pintar.append((x, y))
    assert not sin_pintar, f"Tracks sin píxel pintado en pantalla: {sin_pintar}"


def test_region_vacia_queda_en_fondo(w):
    """Control negativo: una zona sin tracks ni HUD no tiene píxeles brillantes."""
    _tracks(w, [(0.0, 0.0)])
    img = _render(w)
    # Esquina inferior izquierda, lejos del track central, del HUD y del reloj.
    assert _pintados_en(img, 60, H - 120, radio=10, umbral_lum=90) == 0


def test_hud_estado_safety_nets_pinta(w):
    """SSR-10: el indicador de estado (rect 10,10,150,20) deja píxeles visibles."""
    _tracks(w, [(0.0, 0.0)])
    img = _render(w)
    assert _pintados_en(img, 85, 20, radio=10) > 0, "HUD de safety-nets no pintado"


def test_track_inhibido_cambia_color_hud(w):
    """El HUD refleja la inhibición: con APW inhibida aparecen píxeles rojos."""
    w.apw_habilitado = False
    _tracks(w, [(0.0, 0.0)])
    img = _render(w)
    rojos = 0
    for yy in range(10, 30):
        for xx in range(10, 160):
            c = img.pixel(xx, yy)
            r, g, b = (c >> 16) & 0xFF, (c >> 8) & 0xFF, c & 0xFF
            if r > 150 and g < 100 and b < 100:
                rojos += 1
    assert rojos > 0, "Inhibición APW sin indicación roja en el HUD"
