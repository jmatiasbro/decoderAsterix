import math

def calcular_distancia_nm(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Calcula la distancia geodésica en Millas Náuticas (NM) usando la fórmula de Haversine.
    """
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)

    a = (math.sin(dphi / 2)**2 + 
         math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2)**2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    
    # Radio ecuatorial de la Tierra (WGS-84) en metros: 6378137.0
    # 1 Millas Náutica = 1852 metros
    distance_meters = 6378137.0 * c
    return distance_meters / 1852.0

def calcular_rumbo_magnetico(lat1: float, lon1: float, lat2: float, lon2: float, declinacion: float) -> float:
    """
    Calcula el Forward Azimuth (Rumbo Verdadero) entre dos coordenadas geográficas
    y aplica la declinación magnética para retornar el Rumbo Magnético.
    
    Corrección: Rumbo Magnético = Rumbo Verdadero - Declinación
    """
    lat1_rad, lon1_rad, lat2_rad, lon2_rad = map(math.radians, [lat1, lon1, lat2, lon2])
    dlon = lon2_rad - lon1_rad
    
    x = math.sin(dlon) * math.cos(lat2_rad)
    y = math.cos(lat1_rad) * math.sin(lat2_rad) - (math.sin(lat1_rad) * math.cos(lat2_rad) * math.cos(dlon))
    
    rumbo_verdadero = (math.degrees(math.atan2(x, y)) + 360) % 360
    
    # Aplicar corrección: Rumbo Magnético = Rumbo Verdadero - Declinación
    rumbo_magnetico = (rumbo_verdadero - declinacion + 360) % 360
    return rumbo_magnetico
