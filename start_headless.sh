#!/bin/bash

# Modo headless - Ejecuta sin GUI, solo procesa datos
export QT_QPA_PLATFORM=offscreen

cd /mnt/c/documentos/decode_asterix

echo "Iniciando aplicación en modo servidor..."
echo ""
echo "Esta versión procesa datos sin interfaz gráfica."
echo "Los datos están listos para visualizar con scripts o notebooks."
echo ""

.venv/bin/python -c "
import sys
sys.path.insert(0, '/mnt/c/documentos/decode_asterix')

from main_pyqt import ATCNightWindow
from PyQt6.QtWidgets import QApplication

# Crear la aplicación sin mostrar ventana
app = QApplication(sys.argv)
window = ATCNightWindow()

# window.show() - no mostrar
print('✓ Aplicación inicializada en modo headless')
print('✓ Puedes cargar archivos PCAP mediante la API')

# Mantener la aplicación corriendo
app.exec()
"
