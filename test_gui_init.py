import sys
from PyQt6.QtWidgets import QApplication
from player.main_window import MainWindow
from player.radar_widget import RadarWidget

def test_gui():
    print("[*] Starting GUI Initialization Test...")
    app = QApplication(sys.argv)
    
    print("  [1] Instantiating MainWindow...")
    window = MainWindow()
    assert window is not None, "Failed to instantiate MainWindow"
    print("  [1] MainWindow instantiated successfully!")
    
    print("  [2] Instantiating RadarWidget...")
    radar = RadarWidget()
    assert radar is not None, "Failed to instantiate RadarWidget"
    print("  [2] RadarWidget instantiated successfully!")
    
    print("[OK] All GUI Initialization Tests Passed Successfully!")

if __name__ == "__main__":
    test_gui()
