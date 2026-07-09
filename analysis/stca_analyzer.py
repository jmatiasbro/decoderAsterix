"""Motor STCA (Short Term Conflict Alert) segmentado por volúmenes de espacio aéreo.

Implementa HLR-STCA-01/02/07 (SRS): umbrales de alerta parametrizados por segmento
según los mínimos de separación radar de RAAC / OACI Doc 4444:

  - TMA / espacio inferior  (FL030 ≤ FL < FL245): 3.0 NM / 800 ft
    (mínimo radar terminal 5 NM reducible a 3 NM; alerta antes de perder 1000 ft).
  - Ruta / espacio superior (FL245 ≤ FL ≤ FL600): 5.0 NM / 1000 ft
    (mínimo radar en ruta; detección de intrusión en bloques RVSM).

Transición (HLR-STCA-07): si al menos una aeronave del par está en o por encima
del piso de Ruta, se aplican los umbrales de Ruta (los más conservadores) — evita
el parpadeo de umbral en cruces de FL245 en ascenso/descenso.

Fallback seguro: ante configuración ilegible o inválida, el caller debe usar
`STCAConfig.fallback_seguro()` (3.0 NM / 1000 ft en toda la banda FL030–FL600):
el sistema nunca queda sin red por un error de configuración.

Núcleo headless (sin Qt, sin reloj de pared). SWAL 3 — ver 02_clasificacion_SWAL.
"""
import json
import math
import os
from dataclasses import dataclass

# Supresión de duplicados multiradar del mismo blanco (misma aeronave vista por
# dos sensores sin fusionar): dos aeronaves distintas nunca vuelan a <0.5 NM
# co-altitud (sería colisión) → el umbral no oculta un STCA real. (EC-11)
DUP_SUPRESION_NM = 0.5
DUP_SUPRESION_FT = 200


@dataclass(frozen=True)
class STCASegmento:
    """Volumen de espacio aéreo con sus umbrales de alerta."""
    nombre: str
    fl_piso: int          # FL inclusive
    fl_techo: int         # FL inclusive
    horizontal_nm: float  # umbral de separación horizontal (actual y en CPA)
    vertical_ft: int      # umbral de separación vertical


@dataclass(frozen=True)
class STCAConfig:
    """Configuración operativa del motor (RAAC / Doc 4444 por defecto)."""
    tma: STCASegmento = STCASegmento("TMA", 30, 244, 3.0, 800)
    ruta: STCASegmento = STCASegmento("RUTA", 245, 600, 5.0, 1000)
    velocidad_min_kt: float = 40.0   # blancos más lentos se excluyen (estáticos)
    lookahead_s: float = 120.0       # horizonte de predicción de CPA

    def validar(self):
        """Lanza ValueError si la configuración es incoherente (EC-8)."""
        for seg in (self.tma, self.ruta):
            if not (0 <= seg.fl_piso < seg.fl_techo <= 700):
                raise ValueError(f"{seg.nombre}: banda FL{seg.fl_piso}-{seg.fl_techo} inválida")
            if not (0.0 < seg.horizontal_nm <= 20.0):
                raise ValueError(f"{seg.nombre}: horizontal_nm={seg.horizontal_nm} fuera de (0, 20]")
            if not (0 < seg.vertical_ft <= 5000):
                raise ValueError(f"{seg.nombre}: vertical_ft={seg.vertical_ft} fuera de (0, 5000]")
        if self.tma.fl_techo >= self.ruta.fl_piso:
            raise ValueError("Los segmentos TMA y Ruta se solapan")
        if self.velocidad_min_kt < 0 or self.lookahead_s <= 0:
            raise ValueError("velocidad_min_kt/lookahead_s inválidos")
        return self

    # Banda global evaluable (unión de segmentos)
    @property
    def fl_min(self):
        return self.tma.fl_piso

    @property
    def fl_max(self):
        return self.ruta.fl_techo

    @staticmethod
    def desde_dict(d: dict) -> "STCAConfig":
        """Construye y valida desde un dict (p. ej. config/stca.json)."""
        def _seg(clave, defecto):
            s = d.get(clave)
            if s is None:
                return defecto
            return STCASegmento(
                nombre=defecto.nombre,
                fl_piso=int(s.get("fl_piso", defecto.fl_piso)),
                fl_techo=int(s.get("fl_techo", defecto.fl_techo)),
                horizontal_nm=float(s.get("horizontal_nm", defecto.horizontal_nm)),
                vertical_ft=int(s.get("vertical_ft", defecto.vertical_ft)),
            )
        base = STCAConfig()
        return STCAConfig(
            tma=_seg("tma", base.tma),
            ruta=_seg("ruta", base.ruta),
            velocidad_min_kt=float(d.get("velocidad_min_kt", base.velocidad_min_kt)),
            lookahead_s=float(d.get("lookahead_s", base.lookahead_s)),
        ).validar()

    @staticmethod
    def cargar_archivo(path: str) -> "STCAConfig":
        """Config desde JSON; sin archivo → valores normativos por defecto.
        Un archivo ilegible/ inválido LANZA (el caller decide el fallback)."""
        if not os.path.exists(path):
            return STCAConfig().validar()
        with open(path, "r", encoding="utf-8") as f:
            return STCAConfig.desde_dict(json.load(f))

    @staticmethod
    def fallback_seguro() -> "STCAConfig":
        """Config de emergencia del SRS: 3.0 NM / 1000 ft en TODA la banda
        FL030–FL600. Se usa cuando la configuración operativa no puede leerse:
        el sistema nunca debe quedar sin red de seguridad."""
        return STCAConfig(
            tma=STCASegmento("TMA*", 30, 244, 3.0, 1000),
            ruta=STCASegmento("RUTA*", 245, 600, 3.0, 1000),
        ).validar()


class STCA_Engine:
    def __init__(self, config: STCAConfig = None):
        self.config = (config or STCAConfig()).validar()
        # Compatibilidad de lectura (telemetría/diagnóstico): banda global.
        self.fl_min = self.config.fl_min
        self.fl_max = self.config.fl_max

    @staticmethod
    def haversine_nm(lat1, lon1, lat2, lon2):
        R = 3440.065 # Radio terrestre en NM
        dlat, dlon = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
        a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
        return R * (2 * math.atan2(math.sqrt(a), math.sqrt(1 - a)))

    def _umbrales_par(self, fl1: int, fl2: int) -> STCASegmento:
        """Segmento aplicable a un par (HLR-STCA-07, transición sin parpadeo):
        si al menos una aeronave está en o sobre el piso de Ruta → umbrales de
        Ruta (los más conservadores: 5 NM / 1000 ft). Si no → TMA."""
        if max(fl1, fl2) >= self.config.ruta.fl_piso:
            return self.config.ruta
        return self.config.tma

    def evaluar_conflictos(self, tracks_dict):
        """
        Evalúa conflictos de separación de forma cinemática, con umbrales por
        segmento de espacio aéreo (TMA/Ruta — ver docstring del módulo).
        Retorna una lista de tuplas: (track1_id, track2_id, estado, tiempo, dist_h, dv_ft)
        - estado: 'VIOLATION' (violación actual) o 'PREDICTION' (vulneración futura en t_cpa)
        - tiempo: 0 para VIOLATION, o t_cpa (segundos redondeados) para PREDICTION.
        """
        cfg = self.config
        conflictos = []
        track_ids = list(tracks_dict.keys())

        for i in range(len(track_ids)):
            t1_id = track_ids[i]
            t1 = tracks_dict[t1_id]

            # Excluir blancos estáticos (ej: transpondedores de calibración, reflectores MTR)
            speed1 = t1.get('speed_kt')
            if speed1 is not None and speed1 < cfg.velocidad_min_kt:
                continue

            fl1_str = str(t1.get('flight_level', ''))
            if not fl1_str.isdigit() or not (cfg.fl_min <= int(fl1_str) <= cfg.fl_max): continue
            fl1 = int(fl1_str)

            for j in range(i + 1, len(track_ids)):
                t2_id = track_ids[j]
                t2 = tracks_dict[t2_id]

                speed2 = t2.get('speed_kt')
                if speed2 is not None and speed2 < cfg.velocidad_min_kt:
                    continue

                fl2_str = str(t2.get('flight_level', ''))
                if not fl2_str.isdigit() or not (cfg.fl_min <= int(fl2_str) <= cfg.fl_max): continue
                fl2 = int(fl2_str)

                # Suprimir conflicto si comparten squawk o Mode S → misma aeronave
                m3a1 = t1.get('mode3a', '')
                m3a2 = t2.get('mode3a', '')
                if m3a1 and m3a2 and m3a1 not in ('----', '0000') and m3a1 == m3a2:
                    continue
                ms1 = t1.get('mode_s', '')
                ms2 = t2.get('mode_s', '')
                if ms1 and ms2 and ms1 == ms2:
                    continue

                # Umbrales del par según el volumen (TMA / Ruta / transición)
                seg = self._umbrales_par(fl1, fl2)

                diff_vertical_ft = abs(fl1 - fl2) * 100
                if diff_vertical_ft >= seg.vertical_ft: continue

                lat1, lon1 = t1.get('lat_render'), t1.get('lon_render')
                lat2, lon2 = t2.get('lat_render'), t2.get('lon_render')

                if None in (lat1, lon1, lat2, lon2): continue

                # 1. EVALUACIÓN ACTUAL (Fase de Violación) — posición cruda (HLR-STCA-06)
                dist_actual = self.haversine_nm(lat1, lon1, lat2, lon2)

                # Supresión de DUPLICADOS de la misma aeronave (ver constantes de módulo)
                if dist_actual < DUP_SUPRESION_NM and diff_vertical_ft < DUP_SUPRESION_FT:
                    continue

                if dist_actual < seg.horizontal_nm:
                    conflictos.append((t1_id, t2_id, 'VIOLATION', 0, dist_actual, diff_vertical_ft))
                    continue

                # 2. EVALUACIÓN PREDICTIVA (Fase de Predicción) — cartesiano + velocidad
                x1, y1 = t1.get('x'), t1.get('y')
                x2, y2 = t2.get('x'), t2.get('y')
                vx1, vy1 = t1.get('vx'), t1.get('vy')
                vx2, vy2 = t2.get('vx'), t2.get('vy')

                if None in (x1, y1, x2, y2, vx1, vy1, vx2, vy2):
                    continue

                dx = x1 - x2
                dy = y1 - y2
                dvx = vx1 - vx2
                dvy = vy1 - vy2

                v_sq = dvx**2 + dvy**2
                if v_sq < 1e-4:
                    continue  # Sin movimiento relativo significativo o paralelos

                t_cpa = -(dx * dvx + dy * dvy) / v_sq

                if 0 < t_cpa <= cfg.lookahead_s:
                    x1_cpa = x1 + vx1 * t_cpa
                    y1_cpa = y1 + vy1 * t_cpa
                    x2_cpa = x2 + vx2 * t_cpa
                    y2_cpa = y2 + vy2 * t_cpa

                    dist_cpa_m = math.sqrt((x1_cpa - x2_cpa)**2 + (y1_cpa - y2_cpa)**2)
                    dist_cpa_nm = dist_cpa_m / 1852.0

                    if dist_cpa_nm < seg.horizontal_nm:
                        conflictos.append((t1_id, t2_id, 'PREDICTION', int(round(t_cpa)), dist_cpa_nm, diff_vertical_ft))

        return conflictos
