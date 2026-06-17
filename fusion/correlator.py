"""
fusion/correlator.py — Núcleo de correlación multisensor headless (sin Qt).

Extrae la lógica pura de identidad/proximidad/asociación que vivía embebida en
player.radar_widget, para que la compartan el motor en vivo (RadarWidget) y la
futura herramienta de calibración offline. Opera sobre objetos "track" con
duck-typing (cualquier objeto que exponga: x, y, timestamp, mode_s, mode3a,
flight_level, altitude_ft, y opcionalmente _smooth_vx/_smooth_vy, ground_speed,
track_angle). Determinista y testeable.

El tiempo (para el TTL de la asociación aprendida) se inyecta vía now_fn:
  - vivo/widget: now_fn = SimulationTime.time
  - offline:     now_fn = lambda: <último ToD procesado>
"""
import math
from dataclasses import dataclass

METERS_PER_NM = 1852.0


@dataclass
class CorrelatorConfig:
    gate_estricto_nm: float = 0.7      # co-ubicación => mismo avión con alta confianza
    gate_asociado_nm: float = 5.0      # sanidad para mantener una asociación aprendida
    gate_vertical_ft: float = 1500.0   # separación vertical máxima para considerarlos el mismo
    assoc_ttl_s: float = 300.0         # vida de una asociación squawk<->Mode S aprendida
    vel_fallback_max_mps: float = 600.0  # tope al derivar velocidad de ground_speed/track_angle
    extrapol_max_dt_s: float = 30.0    # |dt| máximo para extrapolar (evita saltos absurdos)


class Correlator:
    """Predicados de correlación + tabla de asociación aprendida."""

    def __init__(self, cfg: CorrelatorConfig = None, now_fn=None):
        self.cfg = cfg or CorrelatorConfig()
        self._now = now_fn or (lambda: 0.0)
        self._assoc = {}  # ('MS'|'SQ', valor) -> (clave_pareja, t_aprendizaje)

    # ---- identidad ----------------------------------------------------
    def claves_identidad(self, t) -> list:
        """Claves de identidad discretas: ('MS', addr) y/o ('SQ', code)."""
        keys = []
        ms = (getattr(t, 'mode_s', None) or "").strip().upper()
        if ms and ms != "----":
            keys.append(('MS', ms))
        m = getattr(t, 'mode3a', None)
        s = f"{m:04o}" if isinstance(m, int) else str(m or "").strip()
        if s and s not in ("----", "0000", "1200", "2000", "7000"):
            keys.append(('SQ', s))
        return keys

    # ---- cinemática ---------------------------------------------------
    def velocidad(self, track) -> tuple:
        """(vx, vy) en m/s, mismo plano proyectado que x,y. Prioriza la
        velocidad suavizada; si no hay, deriva de ground_speed/track_angle
        (convención STCA: x=Este=sin, y=Norte=cos)."""
        sv = getattr(track, '_smooth_vx', None)
        if sv is not None:
            return sv, getattr(track, '_smooth_vy', 0.0)
        gs = getattr(track, 'ground_speed', None)
        ta = getattr(track, 'track_angle', None)
        if gs is not None and ta is not None:
            v = gs * (METERS_PER_NM / 3600.0)  # kt -> m/s
            if 1.0 <= v <= self.cfg.vel_fallback_max_mps:
                rad = math.radians(ta)
                return v * math.sin(rad), v * math.cos(rad)
        return 0.0, 0.0

    def extrapolar(self, track, t_target) -> tuple:
        """Proyecta la posición de la pista a t_target con su velocidad."""
        ts = getattr(track, 'timestamp', None)
        if t_target is None or ts is None:
            return track.x, track.y
        dt = t_target - ts
        if dt < -40000:  # rollover de medianoche
            dt += 86400.0
        if not (-self.cfg.extrapol_max_dt_s <= dt <= self.cfg.extrapol_max_dt_s):
            return track.x, track.y
        vx, vy = self.velocidad(track)
        return track.x + vx * dt, track.y + vy * dt

    # ---- mismo avión --------------------------------------------------
    def son_misma_aeronave(self, a, b) -> bool:
        """True si a y b son con alta confianza el mismo avión (identidades
        no contradictorias + co-ubicación estrecha extrapolada + FL compatible),
        o si ya se aprendió la asociación squawk<->Mode S en un match previo."""
        ms_a = (getattr(a, 'mode_s', None) or "").strip().upper()
        ms_b = (getattr(b, 'mode_s', None) or "").strip().upper()
        if ms_a and ms_b and ms_a != "----" and ms_b != "----" and ms_a != ms_b:
            return False  # dos Mode S distintos => aviones distintos

        def sq(t):
            m = getattr(t, 'mode3a', None)
            s = f"{m:04o}" if isinstance(m, int) else str(m or "").strip()
            return s if s and s not in ("----", "0000") and s not in ("1200", "2000", "7000") else None
        sq_a, sq_b = sq(a), sq(b)
        if sq_a and sq_b and sq_a != sq_b:
            return False  # dos squawks discretos distintos => aviones distintos

        fl_a = self._fl(a)
        fl_b = self._fl(b)
        if fl_a is not None and fl_b is not None and abs(fl_a - fl_b) * 100.0 >= self.cfg.gate_vertical_ft:
            return False

        t_ref = max(getattr(a, 'timestamp', 0.0) or 0.0, getattr(b, 'timestamp', 0.0) or 0.0)
        ax, ay = self.extrapolar(a, t_ref)
        bx, by = self.extrapolar(b, t_ref)
        dist_m = math.hypot(ax - bx, ay - by)

        if dist_m <= self.cfg.gate_estricto_nm * METERS_PER_NM:
            return True

        # Asociación aprendida (mantiene fusión pese a registración / pérdida de pista).
        if self._assoc and dist_m <= self.cfg.gate_asociado_nm * METERS_PER_NM:
            ahora = self._now()
            keys_b = self.claves_identidad(b)
            for ka in self.claves_identidad(a):
                rec = self._assoc.get(ka)
                if rec and (ahora - rec[1]) <= self.cfg.assoc_ttl_s and rec[0] in keys_b:
                    return True
        return False

    # ---- asociación aprendida ----------------------------------------
    def registrar_asociacion(self, *tracks) -> None:
        """Vincula (bidireccional) todas las claves de identidad de los tracks
        dados, con timestamp actual. Llamar al fusionar dos pistas confirmadas."""
        ahora = self._now()
        keys = []
        for t in tracks:
            keys.extend(self.claves_identidad(t))
        for k1 in keys:
            for k2 in keys:
                if k1 != k2:
                    self._assoc[k1] = (k2, ahora)

    @staticmethod
    def _fl(t):
        fl = getattr(t, 'flight_level', None)
        if fl is not None:
            return fl
        alt = getattr(t, 'altitude_ft', None)
        return alt / 100.0 if alt else None
