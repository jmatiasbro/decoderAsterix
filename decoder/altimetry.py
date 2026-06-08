"""
Gestor de altimetría impulsado por perfil de configuración (Data-Driven).
Agnóstico al origen de los datos: su único contrato es leer 'transition_altitude'
del perfil recibido para calcular el Nivel de Transición (TL) dinámico segun la
tabla AIP ENR 1.7 y alternar las etiquetas de altitud A/F en funcion del QNH manual.
"""


class AltimetryManager:
    def __init__(self, profile_config=None):
        # QNH dinámico inicial (modificable manualmente desde el HMI)
        self.qnh_local = 1013.25

        # Extracción de parámetros desde el perfil de configuración inyectado.
        # Se aceptan tanto la clave estándar como la del esquema en español.
        self.transition_altitude = 10000
        self.station_name = "DEFAULT"
        self.apply_profile(profile_config)

    def apply_profile(self, profile_config):
        """Reconfigura el gestor a partir de un nuevo perfil (carga en caliente)."""
        if not profile_config:
            return
        ta = profile_config.get("transition_altitude")
        if ta is not None:
            try:
                self.transition_altitude = int(ta)
            except (TypeError, ValueError):
                self.transition_altitude = 10000
        self.station_name = (
            profile_config.get("station_name")
            or profile_config.get("nombre_usuario")
            or profile_config.get("name")
            or self.station_name
        )

    @property
    def transition_level(self):
        """Calcula el TL dinámico sobre la base de la TA del perfil activo (ENR 1.7)."""
        ta_fl = self.transition_altitude // 100

        # Bandas de presión de la tabla ENR 1.7
        if self.qnh_local >= 1031.7:
            capa_fl = 0
        elif 1013.3 <= self.qnh_local <= 1031.6:
            capa_fl = 5
        elif 995.1 <= self.qnh_local <= 1013.2:
            capa_fl = 10
        elif 977.2 <= self.qnh_local <= 995.0:
            capa_fl = 15
        elif 959.5 <= self.qnh_local <= 977.1:
            capa_fl = 20
        elif 942.2 <= self.qnh_local <= 959.4:
            capa_fl = 25
        else:
            capa_fl = 30

        return ta_fl + capa_fl

    def formatear_altitud(self, asterix_fl):
        """Compara la posición actual contra la TA del perfil para alternar entre A y F."""
        if asterix_fl is None:
            return "F---"

        altitud_std_pies = asterix_fl * 100
        correccion_qnh = (self.qnh_local - 1013.25) * 30.0
        altitud_corregida_pies = altitud_std_pies + correccion_qnh

        # Frontera de corte definida por el perfil
        if altitud_corregida_pies <= self.transition_altitude:
            valor_mostrar = int(round(altitud_corregida_pies / 100.0))
            return f"A{valor_mostrar:03d}"
        else:
            valor_mostrar = int(round(asterix_fl))
            return f"F{valor_mostrar:03d}"
