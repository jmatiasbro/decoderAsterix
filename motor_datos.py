from PyQt6.QtCore import QThread, pyqtSignal, QObject
import time

class AsterixWorker(QThread):
    """
    Motor de decodificación en segundo plano.
    Lee el archivo crudo y emite registros procesados sin bloquear la GUI.
    """
    # Señales para comunicarse con la interfaz / TrackManager de forma segura
    record_parsed = pyqtSignal(dict)
    finished_parsing = pyqtSignal(int)
    progress = pyqtSignal(int)
    error = pyqtSignal(str)

    def __init__(self, filepath, decoder_instance):
        super().__init__()
        self.filepath = filepath
        self.decoder_instance = decoder_instance
        self._is_running = True

    def run(self):
        try:
            total_records = 0
            # Aquí asumo que usas un generador en tu decodificador actual
            # que permite extraer registro por registro desde el pcap/archivo
            
            # Ejemplo abstracto de iteración sobre tu parser real:
            for record in self.decoder_instance.parse_file_generator(self.filepath):
                if not self._is_running:
                    break
                
                # Emitimos el paquete al hilo principal
                self.record_parsed.emit(record)
                total_records += 1
                
                # Notificar progreso cada 500 paquetes para optimizar el bus de señales de Qt
                if total_records % 500 == 0:
                    self.progress.emit(total_records)
                    
            self.finished_parsing.emit(total_records)
            
        except Exception as e:
            self.error.emit(f"Error crítico en decodificación: {str(e)}")

    def stop(self):
        """Permite cancelar la lectura si el archivo es inmenso."""
        self._is_running = False
        self.wait()


class TrackManager(QObject):
    """
    Enrutador Dinámico y Gestor de Memoria.
    Recibe los datos del Worker y los clasifica estricta y eficientemente.
    """
    # Señal para notificar a la interfaz (cuando la hagamos) que hay datos nuevos listos
    data_updated = pyqtSignal(int) 

    def __init__(self):
        super().__init__()
        # Diccionario de memoria enrutada por categorías ASTERIX
        self.data_store = {
            1: [],
            21: [],
            48: [],
            62: []
        }
        self.total_processed = 0

    def process_record(self, record: dict):
        """
        Recibe un paquete decodificado y lo enruta al cuadrante de memoria correspondiente.
        """
        cat = record.get('category')
        
        # Filtrado estricto: Solo guardamos lo que nos interesa analizar
        if cat in self.data_store:
            self.data_store[cat].append(record)
            self.total_processed += 1
            
            # Emitimos señal para las vistas tácticas sin saturar la cola de eventos
            if len(self.data_store[cat]) % 100 == 0:
                self.data_updated.emit(cat)

    def clear_memory(self):
        """Limpia la memoria antes de cargar un nuevo archivo pcap."""
        for cat in self.data_store:
            self.data_store[cat].clear()
        self.total_processed = 0

    def get_category_data(self, category: int):
        """Retorna la lista completa de paquetes crudos de la categoría solicitada."""
        return self.data_store.get(category, [])
