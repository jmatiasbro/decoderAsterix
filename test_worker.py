import sys
from PyQt6.QtWidgets import QApplication
from asterix_worker import AsterixWorker
from geo_utils import cargar_sensores

app = QApplication(sys.argv)
sensores = cargar_sensores("default-site-params")
worker = AsterixWorker("260429.pcap", sensores)
worker.scan()
print("Plots cacheados:", len(worker._plots))
