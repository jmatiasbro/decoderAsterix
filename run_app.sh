#!/bin/bash

# Configurar variables de display
export DISPLAY=:0
export QT_QPA_PLATFORM=xcb

cd /mnt/c/documentos/decode_asterix

# Ejecutar la aplicación y guardar salida
echo "Iniciando aplicación ATC..."
.venv/bin/python main.py > app_output.log 2>&1 &
APP_PID=$!

echo "PID de la aplicación: $APP_PID"
echo "Esperando 3 segundos para que se cargue..."
sleep 3

# Verificar si el proceso está corriendo
if ps -p $APP_PID > /dev/null; then
    echo "✓ Aplicación corriendo (PID: $APP_PID)"
    echo "✓ La ventana debería estar visible en tu pantalla"
    echo "✓ Para detener la aplicación, ejecuta: kill $APP_PID"
    
    # Intentar traer la ventana al frente si está minimizada
    if which wmctrl > /dev/null 2>&1; then
        wmctrl -a "ATC" 2>/dev/null || wmctrl -l | head -3
    fi
else
    echo "✗ Error: La aplicación no se inició correctamente"
    echo "Revisar app_output.log para más detalles:"
    cat app_output.log
fi
