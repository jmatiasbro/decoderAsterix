from PyQt6.QtWidgets import QApplication

_MENUBAR = {
    "DAY": """
        QMenuBar { background-color: #d1d9e6; color: #0f172a; border-bottom: 1px solid #94a3b8; }
        QMenuBar::item { background-color: transparent; padding: 5px 10px; }
        QMenuBar::item:selected { background-color: #94a3b8; color: #0f172a; }
        QMenu { background-color: #e2e8f0; color: #0f172a; border: 1px solid #94a3b8; }
        QMenu::item { padding: 6px 20px; }
        QMenu::item:selected { background-color: #cbd5e1; color: #0f172a; }
    """,
    "DUSK": """
        QMenuBar { background-color: #121824; color: #E0E6ED; border-bottom: 1px solid rgba(0, 229, 255, 50); }
        QMenuBar::item { background-color: transparent; padding: 5px 10px; }
        QMenuBar::item:selected { background-color: rgba(0, 229, 255, 30); color: #39FF14; }
        QMenu { background-color: #0E131F; color: #E0E6ED; border: 1px solid #00E5FF; }
        QMenu::item { padding: 6px 20px; }
        QMenu::item:selected { background-color: rgba(0, 229, 255, 30); color: #39FF14; }
    """,
    "NIGHT": """
        QMenuBar { background-color: #0a0d14; color: #ff9900; border-bottom: 1px solid #cc5500; }
        QMenuBar::item { background-color: transparent; padding: 5px 10px; }
        QMenuBar::item:selected { background-color: rgba(204, 85, 0, 30); color: #ffaa00; }
        QMenu { background-color: #030508; color: #ff9900; border: 1px solid #cc5500; }
        QMenu::item { padding: 6px 20px; }
        QMenu::item:selected { background-color: rgba(204, 85, 0, 30); color: #ffaa00; }
    """,
}

_PALETAS = {
    # ── DÍA: gris pizarra medio, descansado para la vista ──────────────────────
    "DAY": """
        QMainWindow, QDialog, QWidget { background-color: #9aaab8; color: #1a2332; }

        QToolBar {
            background-color: #8899a8; border-bottom: 1px solid #6a7f90; spacing: 4px;
        }
        QToolBar QToolButton {
            background-color: transparent; color: #1a2332; border-radius: 4px; padding: 4px 8px;
        }
        QToolBar QToolButton:hover { background-color: rgba(0,0,0,15); }

        QDockWidget { color: #1a2332; }
        QDockWidget::title {
            background-color: #7a8fa0; padding: 5px 8px;
            border-bottom: 1px solid #6a7f90; font-weight: bold; color: #0f1e2c;
        }
        QStatusBar { background-color: #8899a8; color: #2a3a4a; border-top: 1px solid #6a7f90; }
        QSplitter::handle { background-color: #6a7f90; }

        QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QTimeEdit {
            background-color: #c8d4dc; border: 1px solid #6a7f90;
            color: #1a2332; font-weight: bold; border-radius: 4px; padding: 3px;
        }
        QTextEdit { background-color: #c8d4dc; border: 1px solid #6a7f90; color: #1a2332; }
        QPushButton {
            background-color: #7a8fa0; border: 1px solid #6a7f90;
            color: #0f1e2c; padding: 6px; font-weight: bold; border-radius: 4px;
        }
        QPushButton:hover { background-color: #6a7f90; }
        QPushButton:disabled { color: #7a8fa0; background-color: #9aaab8; border-color: #8899a8; }
        QLabel { color: #1a2332; font-family: 'Segoe UI'; font-size: 9pt; }
        QGroupBox {
            border: 1px solid #6a7f90; border-radius: 6px;
            margin-top: 15px; padding-top: 10px;
            color: #0f1e2c; font-size: 9pt; font-weight: bold;
        }
        QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 3px; }
        QCheckBox, QRadioButton { color: #1a2332; font-size: 9pt; }
        QCheckBox::indicator, QRadioButton::indicator {
            width: 14px; height: 14px;
            border: 1px solid #6a7f90; background-color: #c8d4dc; border-radius: 3px;
        }
        QCheckBox::indicator:checked, QRadioButton::indicator:checked {
            background-color: #2a5a80; border: 1px solid #2a5a80;
        }
        QListWidget { background-color: #b0c0cc; border: 1px solid #6a7f90; color: #1a2332; }
        QListWidget::item:selected { background-color: #6a7f90; color: #0f1e2c; }
        QScrollBar:vertical { background: #9aaab8; width: 8px; border-radius: 4px; }
        QScrollBar::handle:vertical { background: #6a7f90; border-radius: 4px; }
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
        QTabBar::tab { background: #8899a8; color: #1a2332; padding: 6px 12px; border-radius: 4px 4px 0 0; }
        QTabBar::tab:selected { background: #6a7f90; color: #0f1e2c; }
        QTableWidget { background-color: #b0c0cc; color: #1a2332; gridline-color: #6a7f90; border: 1px solid #6a7f90; }
        QTableWidget::item:selected { background-color: #6a7f90; color: #0f1e2c; }
        QHeaderView::section { background-color: #7a8fa0; color: #0f1e2c; padding: 6px; border: 1px solid #6a7f90; font-weight: bold; }
    """,

    # ── CREPÚSCULO: azul noche operacional, acento cian ────────────────────────
    "DUSK": """
        QMainWindow, QDialog, QWidget { background-color: #0b131c; color: #c8d8e8; }

        QToolBar {
            background-color: #0e1a26; border-bottom: 1px solid #1a3048; spacing: 4px;
        }
        QToolBar QToolButton {
            background-color: transparent; color: #c8d8e8; border-radius: 4px; padding: 4px 8px;
        }
        QToolBar QToolButton:hover { background-color: rgba(0, 229, 255, 20); }

        QDockWidget { color: #c8d8e8; }
        QDockWidget::title {
            background-color: #0e1a26; padding: 5px 8px;
            border-bottom: 1px solid #1a3048; font-weight: bold; color: #00e5ff;
        }
        QStatusBar { background-color: #0e1a26; color: #7a9ab8; border-top: 1px solid #1a3048; }
        QSplitter::handle { background-color: #1a3048; }

        QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QTimeEdit {
            background-color: #111e2e; border: 1px solid #1e3a5f;
            color: #00ff66; font-weight: bold; border-radius: 4px; padding: 3px;
        }
        QTextEdit { background-color: #111e2e; color: #c8d8e8; border: 1px solid #1e3a5f; }
        QPushButton {
            background-color: #172a40; border: 1px solid #243e56;
            color: #c8d8e8; padding: 6px; border-radius: 4px;
        }
        QPushButton:hover { background-color: #1e3a52; border-color: #00e5ff; color: #00e5ff; }
        QPushButton:disabled { color: #3a5068; background-color: #0d1520; border-color: #1a2a3a; }
        QLabel { color: #8aaac8; font-family: 'Segoe UI'; font-size: 9pt; }
        QGroupBox {
            border: 1px solid #1e3a5f; border-radius: 6px;
            margin-top: 15px; padding-top: 10px;
            color: #00e5ff; font-size: 9pt; font-weight: bold;
        }
        QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 3px; }
        QCheckBox, QRadioButton { color: #c8d8e8; font-size: 9pt; }
        QCheckBox::indicator, QRadioButton::indicator {
            width: 14px; height: 14px;
            border: 1px solid #1e3a5f; background-color: #111e2e; border-radius: 3px;
        }
        QCheckBox::indicator:checked, QRadioButton::indicator:checked {
            background-color: #00ff66; border: 1px solid #00ff66;
        }
        QListWidget { background-color: #0b131c; border: 1px solid #1e3a5f; color: #c8d8e8; }
        QListWidget::item:selected { background-color: #172a40; color: #00e5ff; }
        QScrollBar:vertical { background: #0b131c; width: 8px; border-radius: 4px; }
        QScrollBar::handle:vertical { background: #1e3a5f; border-radius: 4px; }
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
        QTabBar::tab { background: #111e2e; color: #7a9ab8; padding: 6px 12px; border-radius: 4px 4px 0 0; }
        QTabBar::tab:selected { background: #172a40; color: #00e5ff; }
        QTableWidget { background-color: #111e2e; color: #c8d8e8; gridline-color: #1e3a5f; border: 1px solid #1e3a5f; }
        QTableWidget::item:selected { background-color: rgba(0, 229, 255, 25); color: #00e5ff; }
        QHeaderView::section { background-color: #172a40; color: #00e5ff; padding: 6px; border: 1px solid #1e3a5f; font-weight: bold; }
    """,

    # ── NOCHE: casi negro, ámbar suave para preservar visión nocturna ───────────
    "NIGHT": """
        QMainWindow, QDialog, QWidget { background-color: #07090f; color: #c87820; }

        QToolBar {
            background-color: #0a0d16; border-bottom: 1px solid #2a1a00; spacing: 4px;
        }
        QToolBar QToolButton {
            background-color: transparent; color: #c87820; border-radius: 4px; padding: 4px 8px;
        }
        QToolBar QToolButton:hover { background-color: rgba(200, 120, 32, 15); }

        QDockWidget { color: #c87820; }
        QDockWidget::title {
            background-color: #0a0d16; padding: 5px 8px;
            border-bottom: 1px solid #2a1a00; font-weight: bold; color: #e08828;
        }
        QStatusBar { background-color: #0a0d16; color: #7a4a10; border-top: 1px solid #2a1a00; }
        QSplitter::handle { background-color: #2a1a00; }

        QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QTimeEdit {
            background-color: #0d1018; border: 1px solid #3a2200;
            color: #e08828; font-weight: bold; border-radius: 4px; padding: 3px;
        }
        QTextEdit { background-color: #0d1018; color: #c87820; border: 1px solid #3a2200; }
        QPushButton {
            background-color: #110d04; border: 1px solid #3a2200;
            color: #c87820; padding: 6px; border-radius: 4px;
        }
        QPushButton:hover { background-color: #1c1400; border-color: #e08828; color: #e08828; }
        QPushButton:disabled { color: #4a3010; background-color: #07090f; border-color: #2a1a00; }
        QLabel { color: #8a5818; font-family: 'Segoe UI'; font-size: 9pt; }
        QGroupBox {
            border: 1px solid #3a2200; border-radius: 6px;
            margin-top: 15px; padding-top: 10px;
            color: #e08828; font-size: 9pt; font-weight: bold;
        }
        QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 3px; }
        QCheckBox, QRadioButton { color: #c87820; font-size: 9pt; }
        QCheckBox::indicator, QRadioButton::indicator {
            width: 14px; height: 14px;
            border: 1px solid #3a2200; background-color: #0d1018; border-radius: 3px;
        }
        QCheckBox::indicator:checked, QRadioButton::indicator:checked {
            background-color: #c87820; border: 1px solid #e08828;
        }
        QListWidget { background-color: #07090f; border: 1px solid #3a2200; color: #c87820; }
        QListWidget::item:selected { background-color: #1c1400; color: #e08828; }
        QScrollBar:vertical { background: #07090f; width: 8px; border-radius: 4px; }
        QScrollBar::handle:vertical { background: #3a2200; border-radius: 4px; }
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
        QTabBar::tab { background: #0d1018; color: #8a5818; padding: 6px 12px; border-radius: 4px 4px 0 0; }
        QTabBar::tab:selected { background: #1c1400; color: #e08828; }
        QTableWidget { background-color: #0d1018; color: #c87820; gridline-color: #3a2200; border: 1px solid #3a2200; }
        QTableWidget::item:selected { background-color: rgba(200, 120, 32, 20); color: #e08828; }
        QHeaderView::section { background-color: #110d04; color: #e08828; padding: 6px; border: 1px solid #3a2200; font-weight: bold; }
    """,
}


class StyleManager:
    _modo: str = "DUSK"

    @classmethod
    def set_modo(cls, modo: str) -> None:
        cls._modo = modo if modo in _PALETAS else "DUSK"
        app = QApplication.instance()
        if app:
            app.setStyleSheet(_PALETAS[cls._modo])

    @classmethod
    def get_modo(cls) -> str:
        return cls._modo

    @classmethod
    def get_estilo(cls) -> str:
        return _PALETAS.get(cls._modo, _PALETAS["DUSK"])

    @classmethod
    def get_estilo_menubar(cls) -> str:
        return _MENUBAR.get(cls._modo, _MENUBAR["DUSK"])

    @staticmethod
    def aplicar(widget) -> None:
        """Limpia el stylesheet propio del widget; hereda del QApplication."""
        widget.setStyleSheet("")
