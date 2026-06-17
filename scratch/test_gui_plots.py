import sys
import os
import time
from PyQt6.QtWidgets import QApplication
from player.main_window import MainWindow

def test_playback():
    print("[TEST] Inicializando QApplication...")
    app = QApplication(sys.argv)
    
    print("[TEST] Creando MainWindow...")
    win = MainWindow()
    
    pcap_path = os.path.abspath("260429.pcap")
    print(f"[TEST] Cargando archivo PCAP de prueba: {pcap_path}")
    
    # Simular la carga del archivo
    win.pcap_path = pcap_path
    win.radar.limpiar_pantalla()
    win.sensores_conocidos.clear()
    win.sensores_activos.clear()
    win.autocentered_on_first_sensor = False
    win._sensor_categories.clear()
    win._sensor_rpms.clear()
    win.radar.sensores_visibles = win.sensores_activos.copy()
    win.total_messages_received = 0
    win.selected_messages_received = 0
    
    if win.worker:
        win.worker.stop()
        win.worker.wait()
    
    # Crear y arrancar worker
    from player.playback_worker import PlaybackWorker
    win.worker = PlaybackWorker(
        pcap_file=pcap_path,
        sensores=win.sensores,
        cache_dir=win.cache_dir
    )
    win.worker.new_plot_batch.connect(win._on_new_plot_batch)
    win.worker.progress_updated.connect(win._on_decoding_progress)
    win.worker.tod_updated.connect(win._on_tod_update)
    win.worker.scan_complete.connect(win._on_scan_complete)
    win.worker.playback_finished.connect(win._on_playback_finished)
    win.worker.sensor_detected.connect(win._on_sensor_detected)
    win.worker.rotation_speed_detected.connect(win._on_rotation_speed_detected)
    
    print("[TEST] Iniciando escaneo PCAP...")
    win.worker.start()
    
    # Esperar a que termine de escanear (máx 15s)
    start_time = time.time()
    while not win.worker.scanned and time.time() - start_time < 15.0:
        app.processEvents()
        time.sleep(0.1)
        
    print(f"[TEST] Escaneado: {win.worker.scanned}. Plots totales en worker: {win.worker.total_frames}")
    if not win.worker.scanned:
        print("[TEST] ERROR: El escaneo no terminó a tiempo.")
        sys.exit(1)
        
    # Activar reproducción
    print("[TEST] Iniciando reproducción...")
    win._toggle_play()
    
    # Dejar correr por 5 segundos para recibir plots
    print("[TEST] Recibiendo plots durante 5 segundos...")
    start_play = time.time()
    while time.time() - start_play < 5.0:
        app.processEvents()
        time.sleep(0.1)
        
    # Verificar cantidad de plots en el RadarWidget
    total_in_radar = len(win.radar.tracks) + len(win.radar.pending_tracks)
    print(f"[TEST] Fin de prueba de 5 segundos.")
    print(f"[TEST] Mensajes recibidos en MainWindow: {win.total_messages_received}")
    print(f"[TEST] Mensajes seleccionados (que pasaron filtros): {win.selected_messages_received}")
    print(f"[TEST] Plots en radar.tracks: {len(win.radar.tracks)}")
    print(f"[TEST] Plots en radar.pending_tracks: {len(win.radar.pending_tracks)}")
    print(f"[TEST] Total de plots activos en RadarWidget: {total_in_radar}")
    
    # Detener worker
    win._stop()
    sys.exit(0)

if __name__ == "__main__":
    test_playback()
