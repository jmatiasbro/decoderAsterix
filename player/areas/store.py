"""Persistencia local de áreas de usuario (temporales y permanentes-de-usuario).

Un archivo JSON por área en `profiles/areas_<user>/<name>.json`. Las áreas
permanentes que el usuario decide oficializar se escriben además en la DB
(ver atm_db.write_area); acá solo vive la copia de trabajo del perfil.
"""
import os
import json
from datetime import time

from player.areas.model import Area, Vigencia

_BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def areas_dir(username: str = "Default") -> str:
    d = os.path.join(_BASE, "profiles", f"areas_{username}")
    os.makedirs(d, exist_ok=True)
    return d


def _t_to_str(t):
    return t.strftime("%H:%M") if isinstance(t, time) else None


def _str_to_t(s):
    if not s:
        return None
    try:
        hh, mm = s.split(":")
        return time(int(hh), int(mm))
    except (ValueError, AttributeError):
        return None


def area_to_dict(a: Area) -> dict:
    v = a.vigencia
    return {
        "name": a.name, "kind": a.kind, "shape": a.shape,
        "lower_fl": a.lower_fl, "upper_fl": a.upper_fl,
        "vertices": [list(p) for p in a.vertices],
        "center": list(a.center) if a.center else None,
        "radius_nm": a.radius_nm, "origen": "usuario",
        "prediction_time": getattr(a, "prediction_time", 120),
        "vigencia": {
            "permanente": v.permanente, "habilitada": v.habilitada,
            "dias": sorted(v.dias), "desde": _t_to_str(v.desde),
            "hasta": _t_to_str(v.hasta),
        },
    }


def area_from_dict(d: dict) -> Area:
    vd = d.get("vigencia", {})
    vig = Vigencia(
        permanente=vd.get("permanente", True),
        habilitada=vd.get("habilitada", True),
        dias=set(vd.get("dias", []) or []),
        desde=_str_to_t(vd.get("desde")), hasta=_str_to_t(vd.get("hasta")),
    )
    return Area(
        name=d["name"], kind=d.get("kind", "C"), shape=d.get("shape", "poly"),
        lower_fl=int(d.get("lower_fl", 0)), upper_fl=int(d.get("upper_fl", 999)),
        vertices=[tuple(p) for p in d.get("vertices", [])],
        center=tuple(d["center"]) if d.get("center") else None,
        radius_nm=d.get("radius_nm"), vigencia=vig, origen="usuario",
        prediction_time=int(d.get("prediction_time", 120)),
    )


def _safe(name: str) -> str:
    return "".join(c for c in name.strip() if c.isalnum() or c in "_-") or "AREA"


def guardar(area: Area, username: str = "Default") -> str:
    path = os.path.join(areas_dir(username), f"{_safe(area.name)}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(area_to_dict(area), f, indent=2, ensure_ascii=False)
    return path


def listar(username: str = "Default"):
    d = areas_dir(username)
    return [f for f in os.listdir(d) if f.lower().endswith(".json")]


def cargar_todas(username: str = "Default"):
    out = []
    d = areas_dir(username)
    for f in listar(username):
        try:
            with open(os.path.join(d, f), encoding="utf-8") as fh:
                out.append(area_from_dict(json.load(fh)))
        except Exception as e:
            print(f"[Áreas] No se pudo leer {f}: {e}")
    return out


def borrar(name: str, username: str = "Default") -> bool:
    path = os.path.join(areas_dir(username), f"{_safe(name)}.json")
    if os.path.exists(path):
        os.remove(path)
        return True
    return False
