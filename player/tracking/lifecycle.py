"""Ciclo de vida de pista monoradar (confirmación M-de-N + coasting por vueltas).

Determinista por ToD ASTERIX: nada de time.time(). Headless (sin Qt).
"""
import math

NM_M = 1852.0

TENTATIVE = "TENTATIVE"
CONFIRMED = "CONFIRMED"
COASTING = "COASTING"
DELETED = "DELETED"
DUPLICADO_LEJANO = "DUPLICADO_LEJANO"


def _squawk(plot):
    m = getattr(plot, "mode3a", None)
    s = f"{m:04o}" if isinstance(m, int) else str(m or "").strip()
    if s and s not in ("----", "0000"):
        return s
    return None


class _Pista:
    __slots__ = ("codigo", "estado", "detecciones", "faltas",
                 "ultima_tod", "scan_period", "x", "y")

    def __init__(self, codigo, ultima_tod, scan_period, x, y):
        self.codigo = codigo
        self.estado = TENTATIVE
        self.detecciones = 1
        self.faltas = 0
        self.ultima_tod = ultima_tod    # ToD de la última detección
        self.scan_period = scan_period
        self.x = x
        self.y = y


class MonoradarLifecycle:
    """Confirma/mantiene/borra pistas monoradar por vueltas de antena.

    scan_period_fn(sac, sic) -> período de barrido en s (60/RPM).
    confirm_n: detecciones para confirmar. drop_misses: faltas para borrar.
    pair_nm: umbral para colapsar dos plots del mismo código en la misma vuelta.
    """

    def __init__(self, scan_period_fn, confirm_n=4, drop_misses=4, pair_nm=1.0):
        self._period_fn = scan_period_fn
        self.confirm_n = confirm_n
        self.drop_misses = drop_misses
        self.pair_m = pair_nm * NM_M
        self.pistas = {}

    def _periodo(self, plot):
        p = self._period_fn(getattr(plot, "sac", None), getattr(plot, "sic", None))
        return p if p and p > 0 else 4.0

    def procesar(self, plot):
        """Registra una detección. Devuelve el código tratado o None."""
        codigo = identidad_codigo(plot)
        if codigo is None:
            return None
        pista = self.pistas.get(codigo)
        if pista is None:
            self.pistas[codigo] = _Pista(codigo, plot.timestamp,
                                         self._periodo(plot), plot.x, plot.y)
            return codigo
        # Conteo por TIEMPO TRANSCURRIDO desde la última detección (robusto a saltos
        # de ToD y ráfagas de carga), no por índice absoluto floor(tod/período).
        period = pista.scan_period
        elapsed = plot.timestamp - pista.ultima_tod
        if elapsed < 0:
            elapsed = 0.0                       # fuera de orden: tratar como misma vuelta

        if elapsed < period * 0.5:
            # Misma vuelta: duplicado. Colapsar si está cerca; si no, duplicado lejano.
            dist = math.hypot(plot.x - pista.x, plot.y - pista.y)
            if dist < self.pair_m:
                if pista.estado == TENTATIVE:
                    pista.detecciones += 1
                    if pista.detecciones >= self.confirm_n:
                        pista.estado = CONFIRMED
                pista.x, pista.y = plot.x, plot.y
                pista.ultima_tod = plot.timestamp
                return codigo
            return DUPLICADO_LEJANO

        # Detección en una vuelta posterior.
        if pista.estado in (CONFIRMED, COASTING):
            pista.estado = CONFIRMED            # recuperación
        else:
            if elapsed >= period * 1.5:         # se saltó ≥1 vuelta entera → reiniciar racha
                pista.detecciones = 0
            pista.detecciones += 1
            if pista.detecciones >= self.confirm_n:
                pista.estado = CONFIRMED
        pista.faltas = 0
        pista.ultima_tod = plot.timestamp
        pista.x, pista.y = plot.x, plot.y
        return codigo

    def tick(self, tod_actual):
        """Envejece faltas según el ToD actual. Devuelve [(codigo, evento)].

        faltas = vueltas enteras transcurridas desde la última detección
        (int((tod - ultima_tod)/período)). Tentativa que pierde una vuelta → se
        descarta; confirmada/coasting → COASTING y, al llegar a drop_misses, DELETE.
        """
        eventos = []
        for codigo in list(self.pistas.keys()):
            pista = self.pistas[codigo]
            period = pista.scan_period or 4.0
            faltantes = int((tod_actual - pista.ultima_tod) / period)
            if faltantes <= 0:
                continue
            if pista.estado == TENTATIVE:
                # sin confirmar y perdió una vuelta → descartar
                del self.pistas[codigo]
                eventos.append((codigo, DELETED))
                continue
            pista.faltas = faltantes
            if faltantes >= self.drop_misses:
                del self.pistas[codigo]
                eventos.append((codigo, DELETED))
            else:
                pista.estado = COASTING
                eventos.append((codigo, COASTING))
        return eventos

    def estado(self, codigo):
        p = self.pistas.get(codigo)
        return p.estado if p else None

    def faltas(self, codigo):
        p = self.pistas.get(codigo)
        return p.faltas if p else 0


def identidad_codigo(plot):
    """Clave de identidad del plot, o None.

    SSR/PSR-SSR → squawk (Modo 3/A). ADS-B (cat 21) sin squawk → callsign;
    si falta → dirección Mode S.
    """
    sq = _squawk(plot)
    if sq:
        return sq
    if getattr(plot, "category", None) == 21:
        cs = (getattr(plot, "callsign", None) or "").strip().upper()
        if cs:
            return cs
        ms = (getattr(plot, "mode_s", None) or "").strip().upper()
        if ms and ms != "----":
            return ms
    return None
