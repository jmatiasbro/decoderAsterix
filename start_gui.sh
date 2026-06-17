#!/bin/bash

# Usar VNC con un puerto dinámico
export QT_QPA_PLATFORM=vnc
export QT_QPA_PLATFORM_PLUGIN_PATH=.venv/lib/python3.8/site-packages/PyQt6/plugins/platforms
export QT_QPA_SCREEN_OPTS="size=1280x800"

cd /mnt/c/documentos/decode_asterix

echo "================================================"
echo "  Iniciando aplicación ATC con backend VNC"
echo "================================================"
echo ""
echo "Conexión VNC: localhost:5900"
echo ""
echo "Paso 1: Abre un cliente VNC en Windows"
echo "  - RealVNC Viewer: https://www.realvnc.com/download/viewer/"
echo "  - TightVNC: https://www.tightvnc.com/"
echo ""
echo "Paso 2: Conecta a: localhost:5900"
echo ""
echo "Presiona Ctrl+C en esta terminal para detener"
echo "================================================"
echo ""

.venv/bin/python main.py
