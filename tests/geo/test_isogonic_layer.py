import os
import pytest

pytestmark = pytest.mark.skipif(
    not os.path.exists("data/magnetic/isogonic_lines.geojson"),
    reason="requiere el artefacto generado (Task 3)")


def test_geojson_loads_as_map_layer():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PyQt6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    from player.video_map_manager import VideoMapManager
    mm = VideoMapManager()
    mm.load_geojson("data/magnetic/isogonic_lines.geojson",
                    "MAGVAR::ISOGONAS", "TACTICO")
    assert "MAGVAR::ISOGONAS" in mm.layers
    segs = mm.layers["MAGVAR::ISOGONAS"].raw_segments
    kinds = {s[0] for s in segs}
    assert "M" in kinds and "L" in kinds   # polilíneas
    assert "T" in kinds                    # etiquetas de nivel
