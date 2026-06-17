import pyqtgraph as pg
from PyQt6.QtCore import QRectF

class OSMTileLayer(pg.GraphicsObject):
    """
    Capa base sencilla para representar OpenStreetMap (WGS-84) en pyqtgraph.
    (En una versión en producción, esto podría usar QNetworkAccessManager 
    para descargar teselas OSM/TMS o integrar Folium/WebEngineView)
    """
    def __init__(self):
        super().__init__()
        self.source = "osm"
        
    def set_source(self, source: str):
        self.source = source
        self.update()

    def boundingRect(self):
        # Límites globales WGS-84 lógicos
        return QRectF(-180, -90, 360, 180)

    def paint(self, p, *args):
        # Grilla de cuadrantes eliminada a petición del usuario.
        pass