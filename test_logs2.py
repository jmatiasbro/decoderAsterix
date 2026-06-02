import sys
from track_manager import TrackManager, TargetProcessor, SensorRegistry
from projection import RadarProjectionSystem
from main_pyqt import PcapFileWorker
from PyQt6.QtCore import QCoreApplication

app = QCoreApplication(sys.argv)

sensor_registry = SensorRegistry(config_dir="default-site-params")
projection_system = RadarProjectionSystem()
processor = TargetProcessor(projection_system)
track_manager = TrackManager(history_minutes=10, timeout_seconds=60, sensor_registry=sensor_registry)

file_paths = ['260429.pcap']
worker = PcapFileWorker(file_paths, processor, track_manager, sensor_registry)
worker.run()
