#!/bin/bash

echo "================================================"
echo "  APLICACIÓN ATC RADAR - GUI COMPLETA"
echo "================================================"
echo ""
echo "Iniciando interfaz gráfica PyQt con VNC..."
echo ""
echo "VNC SERVER:"
echo "  Puerto: 5900"
echo "  Host: localhost o 172.18.189.158"
echo ""
echo "Para visualizar:"
echo "  1. Descarga VNC Viewer en Windows"
echo "  2. Conecta a: localhost:5900"
echo "  3. Verás la interfaz gráfica completa"
echo ""
echo "Presiona Ctrl+C para detener"
echo "================================================"
echo ""

cd /mnt/c/documentos/decode_asterix
.venv/bin/python run_gui_vnc.py
