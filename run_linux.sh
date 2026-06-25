#!/usr/bin/env bash
# Arranca la consola ASTERIX en Linux.
# - Crea el venv .venv-linux la primera vez e instala las dependencias.
# - En ejecuciones posteriores solo activa el venv y lanza la app.
#
# Uso:
#   ./run_linux.sh            # arranca la GUI (python main.py)
#   ./run_linux.sh --reinstall  # fuerza reinstalar dependencias
#
# El .venv/ del repo es de WSL y no sirve en Linux nativo: por eso se usa .venv-linux.
set -euo pipefail

# Ubicarse en la carpeta del script (raíz del proyecto), sin importar desde dónde se llame.
cd "$(dirname "$(readlink -f "$0")")"

VENV=".venv-linux"
REQS="requirements-linux.txt"
PY="${PYTHON:-python3}"

if [[ "${1:-}" == "--reinstall" ]]; then
    rm -rf "$VENV"
    shift || true
fi

if [[ ! -d "$VENV" ]]; then
    echo "[run_linux] Creando entorno virtual en $VENV ..."
    "$PY" -m venv "$VENV"
    # shellcheck disable=SC1091
    source "$VENV/bin/activate"
    pip install --upgrade pip
    echo "[run_linux] Instalando dependencias desde $REQS ..."
    pip install -r "$REQS"
else
    # shellcheck disable=SC1091
    source "$VENV/bin/activate"
fi

# WSLg (WSL2 con GUI): el socket Wayland vive en /mnt/wslg/runtime-dir, pero al
# entrar como root XDG_RUNTIME_DIR suele apuntar a /run/user/0 (vacío), y Qt falla
# con "Failed to create wl_display". Si estamos en WSL y el socket está ahí, lo
# corregimos. En Linux nativo /mnt/wslg no existe, así que no se toca nada.
if grep -qi microsoft /proc/sys/kernel/osrelease 2>/dev/null \
   && [[ -S /mnt/wslg/runtime-dir/wayland-0 ]] \
   && [[ ! -S "${XDG_RUNTIME_DIR:-}/wayland-0" ]]; then
    export XDG_RUNTIME_DIR=/mnt/wslg/runtime-dir
    echo "[run_linux] WSLg detectado: XDG_RUNTIME_DIR=$XDG_RUNTIME_DIR"
fi

# Plataforma Qt: las ventanas flotantes de alertas (MSAW/APW) y otros paneles se
# posicionan y arrastran con move(), algo que Wayland NO permite a las apps (las
# centra sobre el mapa y no deja moverlas). xcb (X11 / XWayland) sí lo permite, así
# que se usa por defecto, salvo que el usuario fije QT_QPA_PLATFORM explícitamente.
# Requiere libxkbcommon-x11-0 instalado (ver docs/INSTALL_LINUX.md).
export QT_QPA_PLATFORM="${QT_QPA_PLATFORM:-xcb}"

echo "[run_linux] Lanzando la app (main.py) [QT_QPA_PLATFORM=$QT_QPA_PLATFORM] ..."
exec python main.py "$@"
