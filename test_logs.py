import sys
import time
from PyQt6.QtCore import QCoreApplication
from track_manager import TrackManager, TargetProcessor, SensorRegistry
from config import get_sensor_position
from decoders import AsterixRecord, map_to_asterix_record
from projection import RadarProjectionSystem
from main_pyqt import PcapFileWorker

app = QCoreApplication(sys.argv)

sensor_registry = SensorRegistry(config_dir="default-site-params")
projection_system = RadarProjectionSystem()
processor = TargetProcessor(projection_system)
track_manager = TrackManager(history_minutes=10, timeout_seconds=60, sensor_registry=sensor_registry)

file_paths = ['fds260429.pcap'] # Try with an existing file
worker = PcapFileWorker(file_paths, processor, track_manager, sensor_registry)
worker.start()

def on_finished():
    app.quit()
worker.finished.connect(on_finished)

# just run for 2 seconds to get logs
QCoreApplication.processEvents()
time.sleep(2)
app.quit()
