import os
import json

class ProfileManager:
    """
    Administrador de perfiles de usuario y configuración del sector.
    Permite cargar y guardar parámetros como la declinación magnética.
    """
    DEFAULT_PROFILE = {
        "name": "Cordoba",
        "declinacion_magnetica": -7.0,  # -7.0 grados (Oeste)
        "center_lat": -31.31548,
        "center_lon": -64.21545,
    }

    def __init__(self, profile_path=None):
        self.profile_path = profile_path or "config/profile.json"
        self.profile = self.DEFAULT_PROFILE.copy()
        self.load_profile()

    def load_profile(self):
        if os.path.exists(self.profile_path):
            try:
                with open(self.profile_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    # Si el archivo tiene la declinación vieja (-3.5), la migramos a -7.0
                    if data.get("declinacion_magnetica") == -3.5:
                        data["declinacion_magnetica"] = -7.0
                        self.profile.update(data)
                        self.save_profile()
                    else:
                        self.profile.update(data)
            except Exception as e:
                print(f"[ProfileManager] Error cargando perfil: {e}. Usando valores por defecto.")
        else:
            # Crear el directorio de configuración si no existe y guardar el perfil por defecto
            os.makedirs(os.path.dirname(self.profile_path), exist_ok=True)
            self.save_profile()

    def save_profile(self):
        try:
            with open(self.profile_path, 'w', encoding='utf-8') as f:
                json.dump(self.profile, f, indent=4)
        except Exception as e:
            print(f"[ProfileManager] Error guardando perfil: {e}")

    def get_declinacion_magnetica(self) -> float:
        return float(self.profile.get("declinacion_magnetica", -7.0))
