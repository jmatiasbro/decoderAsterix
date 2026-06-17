import sys
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QPalette, QColor, QSurfaceFormat, QGuiApplication
from PyQt6.QtCore import Qt


def configurar_aceleracion() -> None:
    """High-DPI responsivo + backend OpenGL para los widgets acelerados.

    Debe llamarse ANTES de instanciar QApplication. La escala fraccional sin
    redondeo mantiene texto/íconos nítidos en cualquier resolución; el formato
    de superficie por defecto habilita MSAA cuando la GPU lo soporta.
    """
    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    # Contextos GL compartidos: requerido al usar QOpenGLWidget en varias ventanas.
    QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts, True)
    fmt = QSurfaceFormat()
    fmt.setSwapInterval(1)
    fmt.setSamples(4)
    QSurfaceFormat.setDefaultFormat(fmt)


def aplicar_tema_oscuro(app: QApplication) -> None:
    """Paleta oscura global alineada al tema radar.

    Afecta a widgets/diálogos no estilizados (QMessageBox, QFileDialog,
    tooltips, scrollbars, popups) para que toda la app sea coherente.
    Requiere el estilo Fusion para que la paleta se respete en Windows.
    """
    app.setStyle("Fusion")

    base = QColor("#0B0E14")      # fondo profundo (campos, listas)
    panel = QColor("#121824")     # paneles / ventanas
    texto = QColor("#E0E6ED")
    acento = QColor("#00E5FF")    # cian del tema
    desactivado = QColor("#6B7A8D")

    p = QPalette()
    p.setColor(QPalette.ColorRole.Window, panel)
    p.setColor(QPalette.ColorRole.WindowText, texto)
    p.setColor(QPalette.ColorRole.Base, base)
    p.setColor(QPalette.ColorRole.AlternateBase, panel)
    p.setColor(QPalette.ColorRole.ToolTipBase, panel)
    p.setColor(QPalette.ColorRole.ToolTipText, texto)
    p.setColor(QPalette.ColorRole.Text, texto)
    p.setColor(QPalette.ColorRole.Button, panel)
    p.setColor(QPalette.ColorRole.ButtonText, texto)
    p.setColor(QPalette.ColorRole.BrightText, QColor("#39FF14"))
    p.setColor(QPalette.ColorRole.Link, acento)
    p.setColor(QPalette.ColorRole.Highlight, acento)
    p.setColor(QPalette.ColorRole.HighlightedText, base)
    p.setColor(QPalette.ColorRole.PlaceholderText, desactivado)

    for grupo in (QPalette.ColorGroup.Disabled,):
        p.setColor(grupo, QPalette.ColorRole.Text, desactivado)
        p.setColor(grupo, QPalette.ColorRole.WindowText, desactivado)
        p.setColor(grupo, QPalette.ColorRole.ButtonText, desactivado)

    app.setPalette(p)


def main():
    configurar_aceleracion()
    app = QApplication(sys.argv)
    aplicar_tema_oscuro(app)
    # Detectar GPU con la app ya creada; el radar lee el flag al importarse.
    from player import gpu
    gpu.detectar_gpu()
    from player.main_window import MainWindow
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
