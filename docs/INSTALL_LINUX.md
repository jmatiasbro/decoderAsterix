# Ejecutar en Linux

La aplicación es **el mismo código** que en Windows: el núcleo de decodificación es
Python puro, los PCAP se leen con `dpkt` y la captura en vivo usa sockets UDP estándar.
No hay extensiones C que compilar ni APIs de Windows. Para correrla en Linux solo hace
falta preparar el entorno Python; **no se modifica ningún archivo de la aplicación**.

> El `.venv/` que viene en el repo se creó bajo WSL y **no funciona** en Linux nativo:
> hay que crear uno nuevo (no lo commitees).

## 1. Dependencias de sistema (Qt6)

PyQt6 trae sus propias librerías Qt en el wheel, pero necesita algunas librerías del
sistema para el plugin de plataforma (xcb) y OpenGL. En Debian/Ubuntu:

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip \
    libgl1 libegl1 libxkbcommon0 libxkbcommon-x11-0 libxcb-cursor0 \
    libxcb-icccm4 libxcb-image0 libxcb-keysyms1 libxcb-randr0 \
    libxcb-render-util0 libxcb-shape0 libdbus-1-3
```

> `libxkbcommon-x11-0` es **imprescindible**: sin ella el plugin Qt `xcb` no carga.
> La app se ejecuta bajo **xcb** (X11/XWayland), no Wayland nativo (ver nota en §4).

En Fedora/RHEL:

```bash
sudo dnf install -y python3 python3-pip \
    mesa-libGL libxkbcommon libxkbcommon-x11 xcb-util-cursor dbus-libs
```

No se necesita `libpcap`: los archivos PCAP se parsean con `dpkt` (puro Python) y la
captura en vivo usa sockets UDP, no captura cruda.

## 2. Entorno Python y dependencias

```bash
cd decode_asterix
python3 -m venv .venv-linux
source .venv-linux/bin/activate
pip install --upgrade pip
pip install -r requirements-linux.txt
```

Requiere Python 3.12 o superior (probado con 3.12).

## 3. Ejecutar

```bash
source .venv-linux/bin/activate
python main.py
```

- **Punto de entrada canónico:** `main.py` (`player/main_window.py`).
  `main_pyqt.py` es legacy monolítico — no lo uses.
- **Feed en vivo:** UDP, puerto por defecto **20000** (un socket por puerto = multi-sensor).
- **Playback:** cargar un `.pcap`/`.pcapng` desde la UI (rol técnico).

## 4. Notas de portabilidad

- **Wayland vs X11 (importante):** la app usa `QT_QPA_PLATFORM=xcb` (lo fija
  `run_linux.sh`). Bajo **Wayland nativo** las ventanas flotantes de alertas
  (MSAW/APW) aparecen centradas sobre el mapa y **no se pueden mover**, porque
  Wayland no permite a las apps posicionar/mover sus propias ventanas. Con `xcb`
  (X11 directo o XWayland) se posicionan y arrastran normalmente. Si forzás
  `QT_QPA_PLATFORM=wayland`, perdés esa capacidad.
- **Fuentes:** la UI pide `Consolas` (fuente de Windows). En Linux Qt la sustituye
  automáticamente por una monospace del sistema; se ve distinto pero funciona. Para que
  se parezca más, instalá una monospace común: `sudo apt install fonts-dejavu`.
- **Apertura de logs/archivos externos:** usa `xdg-open` en Linux (ya contemplado en el
  código). Asegurate de tener un manejador de archivos por defecto (`xdg-utils`).
- **Smoke test sin pantalla (CI/headless):**
  ```bash
  QT_QPA_PLATFORM=offscreen PYTHONUTF8=1 python -m pytest tests/
  ```
- **GUI real:** requiere un servidor X o Wayland. Si corrés por SSH, usá `ssh -X` o un
  escritorio remoto.

## 5. Verificación rápida

```bash
# Compila y la suite de tests pasa
source .venv-linux/bin/activate
python -m pytest tests/ -q
```
