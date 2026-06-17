import sys
import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
from PyQt6.QtWidgets import QApplication
from main_pyqt import ATCNightWindow

def excepthook(type, value, traceback):
    print("UNHANDLED EXCEPTION:", type, value)
sys.excepthook = excepthook

app = QApplication(sys.argv)
window = ATCNightWindow()
# Connect error signals
def on_error(err):
    print("WORKER ERROR:", err)
window._start_ingestion(['260429.pcap'])
window.worker.error.connect(on_error)

import time
from PyQt6.QtCore import QTimer

def check_progress():
    print("Worker running:", window.worker.isRunning())

timer = QTimer()
timer.timeout.connect(check_progress)
timer.start(1000)

QTimer.singleShot(10000, app.quit)
sys.exit(app.exec())
