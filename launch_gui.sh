#!/bin/bash

export QT_QPA_PLATFORM=vnc
export QT_QPA_SCREEN_OPTS=size=1920x1080

echo "========================================"
echo "  ATC RADAR - GUI COMPLETA"
echo "========================================"
echo ""
echo "Servidor VNC iniciado:"
echo "  Dirección: localhost:5900"
echo "             172.18.189.158:5900"
echo ""
echo "Conexión:"
echo "  1. Descarga VNC Viewer en Windows"
echo "     https://www.realvnc.com/download/viewer/"
echo ""
echo "  2. Conecta a: localhost:5900"
echo ""
echo "  3. ¡Verás la interfaz gráfica completa!"
echo ""
echo "Para detener: Ctrl+C"
echo "========================================"
echo ""

cd /mnt/c/documentos/decode_asterix
.venv/bin/python -c "
import os
import sys

os.environ['QT_QPA_PLATFORM'] = 'vnc'
os.environ['QT_QPA_SCREEN_OPTS'] = 'size=1920x1080'

from PyQt6.QtWidgets import QApplication
from main_pyqt import ATCNightWindow

print('✓ Interfaz gráfica iniciando...')
print('✓ Conecta mediante VNC Viewer a localhost:5900')
print('')

app = QApplication(sys.argv)
window = ATCNightWindow()
window.show()

print('✓ Interfaz lista para usar')
print('')

sys.exit(app.exec())
"
