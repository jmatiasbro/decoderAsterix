#!/usr/bin/env python3
"""
Servidor web simplificado para la aplicación ATC
Ejecuta la aplicación en un servidor HTTP accesible desde el navegador
"""

import sys
import os
import json
from pathlib import Path

# Configurar para no necesitar display
os.environ['QT_QPA_PLATFORM'] = 'offscreen'

# Agregar el directorio actual al path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from flask import Flask, render_template_string, jsonify, request, send_file
from io import BytesIO
import base64

app = Flask(__name__)

# HTML template para la interfaz web
HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>ATC Radar - Decode ASTERIX</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Consolas', monospace;
            background: #1a1a1a;
            color: #00ff00;
            padding: 20px;
        }
        .container {
            max-width: 1200px;
            margin: 0 auto;
            border: 2px solid #00ff00;
            padding: 20px;
            border-radius: 5px;
        }
        h1 {
            text-align: center;
            margin-bottom: 20px;
            color: #00ffff;
            text-shadow: 0 0 10px #00ff00;
        }
        .section {
            margin: 20px 0;
            padding: 15px;
            border: 1px solid #004400;
            background: rgba(0, 255, 0, 0.05);
            border-radius: 3px;
        }
        .section h2 {
            color: #00ff00;
            margin-bottom: 10px;
        }
        input[type="file"],
        input[type="text"],
        button {
            padding: 10px;
            margin: 5px 0;
            background: #004400;
            color: #00ff00;
            border: 1px solid #00ff00;
            border-radius: 3px;
            font-family: 'Consolas', monospace;
            width: 100%;
            cursor: pointer;
        }
        button:hover {
            background: #006600;
            box-shadow: 0 0 10px #00ff00;
        }
        .status {
            padding: 10px;
            margin: 10px 0;
            border-radius: 3px;
            background: #004400;
            border: 1px solid #00ff00;
        }
        .status.success { background: rgba(0, 255, 0, 0.1); }
        .status.error { background: rgba(255, 0, 0, 0.1); color: #ff0000; }
        .status.info { background: rgba(0, 255, 255, 0.1); color: #00ffff; }
        #stats {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 10px;
            margin: 10px 0;
        }
        .stat-box {
            padding: 10px;
            background: rgba(0, 255, 0, 0.1);
            border: 1px solid #00ff00;
            border-radius: 3px;
        }
        .stat-label { color: #00ffff; }
        .stat-value { 
            font-size: 1.5em; 
            font-weight: bold;
            color: #00ff00;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>🎯 ATC Radar - Decode ASTERIX</h1>
        
        <div class="section">
            <h2>📁 Cargar archivo PCAP</h2>
            <input type="file" id="pcapFile" accept=".pcap,.pcapng" />
            <button onclick="uploadFile()">Procesar PCAP</button>
            <div id="uploadStatus"></div>
        </div>

        <div class="section">
            <h2>📊 Estadísticas</h2>
            <div id="stats">
                <div class="stat-box">
                    <div class="stat-label">Registros procesados</div>
                    <div class="stat-value" id="recordCount">0</div>
                </div>
                <div class="stat-box">
                    <div class="stat-label">Estado</div>
                    <div class="stat-value" id="status" style="color: #ffff00;">LISTO</div>
                </div>
            </div>
        </div>

        <div class="section">
            <h2>ℹ️ Información</h2>
            <p>✓ Servidor web ejecutándose correctamente</p>
            <p>✓ Carga PCAP desde este navegador</p>
            <p>✓ Los datos se procesan en el servidor WSL</p>
        </div>
    </div>

    <script>
        function uploadFile() {
            const file = document.getElementById('pcapFile').files[0];
            if (!file) {
                showStatus('Por favor selecciona un archivo', 'error');
                return;
            }

            const formData = new FormData();
            formData.append('file', file);

            showStatus('Procesando...', 'info');
            document.getElementById('status').textContent = 'PROCESANDO';

            fetch('/api/upload', {
                method: 'POST',
                body: formData
            })
            .then(r => r.json())
            .then(data => {
                if (data.success) {
                    showStatus('✓ Archivo procesado: ' + data.message, 'success');
                    document.getElementById('recordCount').textContent = data.record_count || 0;
                    document.getElementById('status').textContent = 'LISTO';
                } else {
                    showStatus('✗ Error: ' + data.error, 'error');
                    document.getElementById('status').textContent = 'ERROR';
                }
            })
            .catch(err => {
                showStatus('Error de red: ' + err, 'error');
                document.getElementById('status').textContent = 'ERROR';
            });
        }

        function showStatus(msg, type = 'info') {
            const div = document.getElementById('uploadStatus');
            div.className = 'status ' + type;
            div.textContent = msg;
        }
    </script>
</body>
</html>
"""

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route('/api/status')
def status():
    return jsonify({
        'status': 'running',
        'version': '1.0',
        'platform': sys.platform
    })

@app.route('/api/upload', methods=['POST'])
def upload():
    try:
        if 'file' not in request.files:
            return jsonify({'success': False, 'error': 'No file part'})
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({'success': False, 'error': 'No selected file'})

        if not file.filename.endswith(('.pcap', '.pcapng')):
            return jsonify({'success': False, 'error': 'Only .pcap and .pcapng files are supported'})

        # Guardar archivo temporalmente
        temp_path = f'/tmp/{file.filename}'
        file.save(temp_path)

        # Procesar con la aplicación
        from io_tools import load_pcap
        try:
            raw_data = load_pcap(temp_path)
            record_count = len(raw_data) // 100  # Estimación
            
            return jsonify({
                'success': True,
                'message': f'Archivo procesado: {file.filename}',
                'record_count': record_count,
                'file_size': len(raw_data)
            })
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)})

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

if __name__ == '__main__':
    print("=" * 50)
    print("  ATC Radar - Servidor Web")
    print("=" * 50)
    print("")
    print("✓ Servidor iniciado")
    print("✓ Abre en tu navegador: http://localhost:5000")
    print("✓ Presiona Ctrl+C para detener")
    print("")
    
    app.run(host='0.0.0.0', port=5000, debug=False)
