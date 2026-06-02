#!/usr/bin/env python3
"""
Ejecutor de GUI PyQt con servidor VNC integrado
Esto permite visualizar la aplicación PyQt directamente desde VNC
"""

import sys
import os

# Configurar antes de importar PyQt
os.environ['QT_QPA_PLATFORM'] = 'vnc'
os.environ['QT_QPA_SCREEN_OPTS'] = 'size=1920x1080'

if __name__ == '__main__':
    print("=" * 60)
    print("  APLICACIÓN ATC - INTERFAZ GRÁFICA COMPLETA")
    print("=" * 60)
    print("")
    print("Conectándote con VNC para visualizar la interfaz...")
    print("")
    print("PASO 1: Abre un cliente VNC en Windows")
    print("  - Descarga: https://www.realvnc.com/download/viewer/")
    print("  - O usa: TightVNC Viewer")
    print("")
    print("PASO 2: Conecta a")
    print("  - localhost:5900")
    print("  o")
    print("  - 172.18.189.158:5900")
    print("")
    print("PASO 3: Presiona Ctrl+C en esta terminal para detener")
    print("")
    print("=" * 60)
    print("")
    
    # Importar y ejecutar la aplicación principal
    from PyQt6.QtWidgets import QApplication
    from player.main_window import MainWindow
    
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    
    print("✓ Interfaz gráfica iniciada")
    print("✓ Conecta mediante VNC para visualizar")
    print("")
    
    sys.exit(app.exec())
