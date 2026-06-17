"""
analysis/quality_manager.py — Módulo de Filtrado de Calidad de Datos (DQF) y Logging
====================================================================================
Implementa el motor de evaluación de calidad de pistas para detectar anomalías
como solapamientos (Garbling), trazas inmaduras y FRUIT con registro en archivo log.

Cada anomalía tiene un color visual distinto para diagnóstico inmediato:
  - GARBLING:       Magenta brillante (#FF00FF)
  - FRUIT:          Naranja (#FFA500)
  - PISTA INMADURA: Amarillo ámbar (#FFD700) — transitorio, desaparece tras 2 actualizaciones
  - DUPLICACIÓN:    Ya manejado por is_reflection/has_reflection en radar_widget

Definición correcta de FRUIT:
  Un FRUIT (False Reply Unsynchronized In Time) es una respuesta de transpondedor
  recibida fuera de sincronismo con la interrogación del radar local. Aparece como
  un plot aislado que NO se correlaciona en la siguiente vuelta de antena.
  
  Por lo tanto, un blanco SOLO puede ser confirmado como FRUIT si:
    1. Tiene exactamente 1 actualización, Y
    2. Han pasado más de 1 período de rotación de antena (~6 segundos) sin
       recibir una segunda detección.
  
  Un blanco nuevo en su primera vuelta NO es FRUIT — es simplemente una pista
  que aún no ha tenido oportunidad de ser confirmada.
"""

import logging
import os

# Razones como constantes para comparar eficientemente
DQF_GARBLING = "GARBLING"
DQF_FRUIT = "FRUIT"
DQF_INMADURA = "PISTA INMADURA"
DQF_OK = ""

# Colores HEX por tipo de anomalía para referencia rápida desde paintEvent
DQF_COLORS = {
    DQF_GARBLING:  "#FF00FF",   # Magenta brillante — solapamiento de señales SSR
    DQF_FRUIT:     "#FFA500",   # Naranja — ploteo huérfano sin correlación
    DQF_INMADURA:  "#FFD700",   # Dorado/ámbar — pista con pocas actualizaciones (transitorio)
}

# Tiempo mínimo (segundos) que debe transcurrir antes de confirmar FRUIT.
# Corresponde a ~1.5 rotaciones de antena típica de un radar SSR (4-5 seg/vuelta).
FRUIT_CONFIRMATION_TIME = 8.0


class QualityManager:
    def __init__(self, log_file="radar_quality.log"):
        # Asegurar ruta absoluta para el log en la carpeta de trabajo
        log_path = os.path.abspath(log_file)
        
        self.logger = logging.getLogger("DataQuality")
        self.logger.setLevel(logging.INFO)
        
        # Evitar duplicar handlers al instanciar múltiples veces
        if not self.logger.handlers:
            handler = logging.FileHandler(log_path, encoding='utf-8')
            formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)
            
        # Estado de los filtros (controlables desde la UI del operador)
        self.filtro_garbling_activo = True
        self.filtro_fruit_activo = True
        self.filtro_inmaduras_activo = True
        
        print(f"[DQF] Módulo de Calidad inicializado. Logs en: {log_path}")

    def evaluar_pista(self, track_id: str, track_data: dict) -> tuple:
        """
        Evalúa la integridad de una pista.
        Retorna:
          (degradada: bool, razon: str)
        
        La razón es una de las constantes DQF_* para que paintEvent pueda
        asignar un color específico por tipo de anomalía.
        
        Prioridad (de mayor a menor severidad):
          1. GARBLING — el dato SSR es físicamente corrupto
          2. FRUIT — 1 solo ploteo huérfano SIN segunda detección tras 1+ rotación
          3. PISTA INMADURA — menos de 2 actualizaciones (transitorio)
        """
        updates = track_data.get('update_count', 1)

        # 1. Detección de Garbling (Bit de solapamiento SSR decodificado desde ASTERIX CAT 048)
        if self.filtro_garbling_activo and track_data.get('garbled', False):
            self.logger.warning(f"Track {track_id} marcada como degradada. Razón: {DQF_GARBLING}")
            return True, DQF_GARBLING

        # 2. Detección de FRUIT / Ruido
        #    Un blanco SOLO se confirma como FRUIT si tiene 1 sola actualización
        #    Y han pasado más de FRUIT_CONFIRMATION_TIME segundos desde que apareció.
        #    Esto evita marcar como FRUIT a aviones legítimos que acaban de entrar en cobertura.
        if self.filtro_fruit_activo and updates == 1:
            age = track_data.get('age', 0.0)
            if age >= FRUIT_CONFIRMATION_TIME:
                self.logger.warning(f"Track {track_id} confirmada como FRUIT. Edad: {age:.1f}s, Updates: {updates}")
                return True, DQF_FRUIT

        # 3. Detección de Pistas Inmaduras (Umbral de menos de 2 actualizaciones de radar)
        #    Este filtro es TRANSITORIO: una vez que la pista recibe su 2da actualización,
        #    se limpia automáticamente y la pista pasa a ser normal.
        if self.filtro_inmaduras_activo and updates < 2:
            self.logger.warning(f"Track {track_id} marcada como degradada. Razón: {DQF_INMADURA}")
            return True, DQF_INMADURA

        return False, DQF_OK
