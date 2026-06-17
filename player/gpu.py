"""Detección de aceleración por GPU (OpenGL) con fallback a software.

`USAR_GL` lo fija `detectar_gpu()` una vez creada la QApplication. El widget del
radar lee este flag en tiempo de importación para elegir su clase base
(QOpenGLWidget si hay GPU utilizable, QWidget en software).
"""

USAR_GL = False


def detectar_gpu() -> bool:
    """True si se puede crear un contexto OpenGL (GPU/driver utilizable).

    Requiere una QGuiApplication ya instanciada.
    """
    global USAR_GL
    try:
        from PyQt6.QtGui import QOpenGLContext, QOffscreenSurface
        ctx = QOpenGLContext()
        if not ctx.create():
            USAR_GL = False
            return False
        surf = QOffscreenSurface()
        surf.create()
        ok = bool(surf.isValid() and ctx.makeCurrent(surf))
        if ok:
            ctx.doneCurrent()
        USAR_GL = ok
        return ok
    except Exception:
        USAR_GL = False
        return False
