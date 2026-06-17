"""Regresión del núcleo de correlación (sin Qt). Ejecutar:
    python fusion/test_correlator.py
"""
import os
import sys
from dataclasses import dataclass
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from fusion.correlator import Correlator, CorrelatorConfig, METERS_PER_NM as NM


@dataclass
class T:  # track mínimo duck-typed
    x: float; y: float; timestamp: float
    mode_s: Optional[str] = None
    mode3a: Optional[str] = None
    flight_level: Optional[float] = None
    altitude_ft: Optional[float] = None
    is_track: bool = False
    ground_speed: Optional[float] = None
    track_angle: Optional[float] = None


def run():
    reloj = {'t': 1000.0}
    c = Correlator(now_fn=lambda: reloj['t'])
    ok = True

    def chk(nombre, got, exp):
        nonlocal ok
        estado = 'OK ' if got == exp else 'XX '
        if got != exp:
            ok = False
        print(f"{estado}{nombre} -> {got} (esperado {exp})")

    # complementario co-ubicado => mismo avión + aprende asociación
    a = T(0, 0, 1000, mode_s='E0664B', flight_level=370, is_track=True)
    b = T(0.3 * NM, 0, 1000, mode3a='2351', flight_level=370)
    chk("complementario 0.3NM", c.son_misma_aeronave(a, b), True)
    c.registrar_asociacion(a, b)

    # asociación persiste a 2 NM con par nuevo
    c2 = T(0, 0, 1000, mode_s='E0664B', flight_level=370, is_track=True)
    d2 = T(2.0 * NM, 0, 1000, mode3a='2351', flight_level=370)
    chk("asociado 2NM", c.son_misma_aeronave(c2, d2), True)

    # expira el TTL
    reloj['t'] = 1000.0 + 400.0
    chk("asociado vencido (>300s)", c.son_misma_aeronave(c2, d2), False)
    reloj['t'] = 1000.0

    # salvaguardas
    chk("Mode S distintos 10m",
        c.son_misma_aeronave(T(0, 0, 1000, mode_s='AAAAAA', flight_level=370),
                             T(10, 0, 1000, mode_s='BBBBBB', flight_level=370)), False)
    chk("squawks discretos distintos 10m",
        c.son_misma_aeronave(T(0, 0, 1000, mode3a='1234', flight_level=370),
                             T(10, 0, 1000, mode3a='5678', flight_level=370)), False)
    chk("distinto FL co-ubicado",
        c.son_misma_aeronave(T(0, 0, 1000, mode_s='E0664B', flight_level=100, is_track=True),
                             T(10, 0, 1000, mode3a='2351', flight_level=130)), False)
    chk("MS distinto + sq asociado",
        c.son_misma_aeronave(T(0, 0, 1000, mode_s='FFFFFF', flight_level=370, is_track=True),
                             T(1.5 * NM, 0, 1000, mode3a='2351', flight_level=370)), False)

    # extrapolación con ground_speed/track_angle (este: 90° => +x)
    t = T(0, 0, 1000, ground_speed=600, track_angle=90.0)
    ex, ey = c.extrapolar(t, 1010.0)  # 600 kt ~308.6 m/s * 10 s
    chk("extrapola 10s al este", round(ex) == 3087 and round(ey) == 0, True)

    print("\nRESULTADO:", "TODO OK" if ok else "FALLAS")
    return ok


if __name__ == '__main__':
    import sys
    sys.exit(0 if run() else 1)
