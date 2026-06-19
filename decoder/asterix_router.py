import traceback
import re
from typing import List, Dict, Any, Set

# Precompilar regex de extracción numérica
RE_NUMBERS = re.compile(r"[-+]?\d*\.\d+|\d+")

def extraer_numero(valor):
    if valor is None: return None
    if isinstance(valor, (int, float)): return float(valor)
    if isinstance(valor, str):
        numeros = RE_NUMBERS.findall(valor)
        if numeros: return float(numeros[0])
    return None

# ============================================================
# IMPORTACIÓN DE LOS 4 DECODIFICADORES
# ============================================================
#   cat001 — Monoradar heredado (CAT 01)
#   cat021 — ADS-B (CAT 21)
#   cat048 — Monoradar moderno (CAT 48)
#   cat062 — CAT 062 (System Track, futuro)
# ============================================================
try:
    from decoder.decoders import cat001, cat021, cat048, cat062, cat034, cat023, cat065
except ImportError:
    # Fallback: si alguno no existe (ej. cat062), importamos los disponibles
    from decoder.decoders import cat001, cat021, cat048, cat034
    cat062 = None
    cat023 = None
    cat065 = None


class AsterixRouter:
    """
    Enrutador ASTERIX blindado.

    Toma un payload UDP crudo (solo el Data Block ASTERIX, sin cabeceras de red),
    lo segmenta por cabeceras CAT/LEN y delega la decodificación al módulo
    correspondiente.

    Categorías soportadas: 01, 21, 48, 62 (62 pendiente de implementación).
    Si un decodificador falla, se imprime el TRACEBACK COMPLETO.
    Categorías sin decodificador se registran en modo debug (una vez cada una).
    Los plots se normalizan (SAC/SIC, coordenadas) post-decodificación.
    """

    def __init__(self):
        self._debug_impreso = False
        self._cat_warned: Set[int] = set()

    def _buscar_clave_recursiva(self, diccionario, claves_posibles):
        """Busca claves profundamente anidadas (para atrapar SAC/SIC y coordenadas)."""
        # 1. Fast path: check top-level keys first
        for k, v in diccionario.items():
            k_low = str(k).lower()
            for posible in claves_posibles:
                if posible in k_low:
                    return v
        # 2. Recurse into sub-dictionaries only if top-level match failed
        for v in diccionario.values():
            if isinstance(v, dict):
                resultado = self._buscar_clave_recursiva(v, claves_posibles)
                if resultado is not None:
                    return resultado
        return None

    @staticmethod
    def _aplanar(diccionario, out):
        """Aplana el dict a [(clave_minúscula, valor)] en el MISMO orden de visita
        que _buscar_clave_recursiva (preorden: claves del nodo, luego sub-dicts).
        Lowercasea cada clave una sola vez para reusar entre varias búsquedas."""
        for k, v in diccionario.items():
            out.append(((k if type(k) is str else str(k)).lower(), v))
        for v in diccionario.values():
            if isinstance(v, dict):
                AsterixRouter._aplanar(v, out)
        return out

    @staticmethod
    def _match(flat, claves_posibles):
        """Primera coincidencia por substring sobre el dict ya aplanado."""
        for k_low, v in flat:
            for posible in claves_posibles:
                if posible in k_low:
                    return v
        return None

    def procesar_paquete_udp(self, payload_bytes: bytes, silent: bool = False) -> List[Dict[str, Any]]:
        """
        Recibe el payload UDP crudo (solo ASTERIX, sin Ethernet/IP/UDP).

        Corta los mensajes ASTERIX por su longitud (LEN) y los decodifica.
        """
        plots_normalizados = []
        pointer = 0
        total_len = len(payload_bytes)

        # Bandera de diagnóstico: se imprime UNA SOLA VEZ
        if not self._debug_impreso:
            print(f"[Router] Iniciando procesamiento. Tamaño de payload inicial: {total_len} bytes")
            self._debug_impreso = True

        while pointer < total_len:
            if pointer + 3 > total_len:
                break  # Faltan bytes para la cabecera

            cat = payload_bytes[pointer]
            msg_len = (payload_bytes[pointer + 1] << 8) | payload_bytes[pointer + 2]

            if msg_len <= 0 or pointer + msg_len > total_len:
                break  # Paquete corrupto

            # Extraemos el bloque completo (incluyendo CAT y LEN)
            bloque_asterix = payload_bytes[pointer: pointer + msg_len]
            plots_crudos = []

            # ============================================================
            # ENRUTAMIENTO POR CATEGORÍA
            # ============================================================
            try:
                if cat == 1:
                    # CAT001 — decode(payload, offset, block_length, category)
                    plots_crudos = cat001.decode(bloque_asterix, 3, msg_len, cat)
                elif cat == 21:
                    # CAT021 — decode(payload, offset, block_length, category)
                    plots_crudos = cat021.decode(bloque_asterix, 3, msg_len, cat)
                elif cat == 23 and cat023 is not None:
                    # CAT023 — decode(payload, offset, block_length, category)
                    plots_crudos = cat023.decode(bloque_asterix, 3, msg_len, cat)
                elif cat == 34:
                    # CAT034 — decode(payload, offset, block_length, category)
                    plots_crudos = cat034.decode(bloque_asterix, 3, msg_len, cat)
                elif cat == 48:
                    # CAT048 — decode(payload, offset, block_length, category)
                    plots_crudos = cat048.decode(bloque_asterix, 3, msg_len, cat)
                elif cat == 62 and cat062 is not None:
                    # CAT062 — decodificador futuro
                    plots_crudos = cat062.decode(bloque_asterix, 3, msg_len, cat)
                elif cat == 65 and cat065 is not None:
                    # CAT065 — SDPS Service Status Reports
                    plots_crudos = cat065.decode(bloque_asterix, 3, msg_len, cat)
                else:
                    # Modo Debug para categorías no soportadas
                    if cat not in self._cat_warned:
                        if not silent:
                            print(f"[Router Warning] Detectada Categoría {cat} pero no hay decodificador asignado.")
                        self._cat_warned.add(cat)
            except Exception as e:
                if not silent:
                    print(f"[Router Error] Error decodificando CAT {cat}: {e}")
                    traceback.print_exc()

            # ============================================================
            # NORMALIZACIÓN POST-DECODIFICACIÓN
            # ============================================================
            if isinstance(plots_crudos, dict):
                plots_crudos = [plots_crudos]

            if plots_crudos:
                for plot in plots_crudos:
                    if not isinstance(plot, dict):
                        continue

                    plot['category'] = cat

                    # Aplanar UNA sola vez y reutilizar para todas las extracciones
                    # (antes se recorría el dict 6-7 veces por plot: hotspot del decode).
                    flat = self._aplanar(plot, [])

                    sac = self._match(flat, ['sac', '010_sac'])
                    sic = self._match(flat, ['sic', '010_sic'])

                    if sac is None or sic is None:
                        item_010 = self._match(flat, ['010'])
                        if isinstance(item_010, (list, tuple)) and len(item_010) >= 2:
                            sac, sic = item_010[0], item_010[1]
                        elif isinstance(item_010, dict):
                            sac = item_010.get('SAC', item_010.get('sac'))
                            sic = item_010.get('SIC', item_010.get('sic'))

                    plot['sac_sic'] = (
                        f"{sac}/{sic}"
                        if (sac is not None and sic is not None)
                        else f"UNK_CAT{cat}"
                    )

                    lat = self._match(flat, ['lat', 'latitude'])
                    lon = self._match(flat, ['lon', 'longitude'])

                    if lat is not None and lon is not None:
                        plot['lat'] = float(lat)
                        plot['lon'] = float(lon)

                    # REGLA DE EXTRACCIÓN ESTRICTA DE RHO/THETA:
                    claves_rho = ['rho', 'dist', 'distance', '040_rho', 'i048/040_rho', 'raw_range']
                    claves_theta = ['theta', 'azimuth', 'azi', '040_theta', 'i048/040_theta', 'raw_azimuth']

                    raw_rho = self._match(flat, claves_rho)
                    raw_theta = self._match(flat, claves_theta)

                    # Forzador numérico:
                    rho = extraer_numero(raw_rho)
                    theta = extraer_numero(raw_theta)

                    if rho is not None and theta is not None:
                        plot['rho_render'] = rho
                        plot['theta_render'] = theta

                    # Bytes crudos del bloque ASTERIX (CAT + LEN + registros) para el
                    # inspector de bajo nivel. Es el bloque completo: si trae varios
                    # registros, comparten estos bytes (el desglose por-registro llega
                    # con el deep-decode más adelante).
                    plot['raw_bytes'] = bytes(bloque_asterix)

                    plots_normalizados.append(plot)

            pointer += msg_len

        return plots_normalizados
