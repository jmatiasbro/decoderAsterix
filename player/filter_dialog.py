"""
player/filter_dialog.py — Diálogo táctico de configuración de filtros de calidad (DQF)
=====================================================================================
Permite al operador activar/desactivar filtros de degradación en tiempo real.
"""

from PyQt6.QtWidgets import QDialog, QVBoxLayout, QCheckBox, QPushButton, QLabel
from PyQt6.QtCore import Qt

class QualityFilterDialog(QDialog):
    def __init__(self, quality_manager, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Configuración DQF — Calidad de Datos")
        self.qm = quality_manager
        from player.ui_scaling import escalar_ventana
        escalar_ventana(self, 380, 220, centrar=False)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)

        # Aplicar estilo Dark-Cyber Premium coherente con el RadarWidget
        self.setStyleSheet("""
            QDialog {
                background-color: #0d1117;
                color: #e6edf3;
                font-family: 'Segoe UI', sans-serif;
            }
            QLabel {
                color: #8b949e;
                font-size: 11px;
                margin-bottom: 8px;
            }
            QCheckBox {
                color: #c9d1d9;
                font-size: 11px;
                padding: 4px;
            }
            QCheckBox::indicator {
                width: 14px;
                height: 14px;
                border: 1px solid #30363d;
                border-radius: 4px;
                background-color: #161b22;
            }
            QCheckBox::indicator:checked {
                background-color: #ffa500;  /* Naranja DQF */
                border-color: #ff8c00;
            }
            QPushButton {
                background-color: #21262d;
                border: 1px solid #30363d;
                border-radius: 6px;
                color: #c9d1d9;
                padding: 8px 16px;
                font-weight: bold;
                font-size: 11px;
                margin-top: 12px;
            }
            QPushButton:hover {
                background-color: #30363d;
                border-color: #8b949e;
                color: #ffffff;
            }
            QPushButton:pressed {
                background-color: #ffa500;
                color: #0d1117;
                border-color: #ff8c00;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(6)
        
        lbl = QLabel("Seleccione las reglas de exclusión DQF (Data Quality Filter).\n"
                      "Los blancos degradados serán excluidos del motor STCA:")
        lbl.setWordWrap(True)
        layout.addWidget(lbl)

        self.chk_garbling = QCheckBox("Filtrar Garbling (Solapamiento de señales SSR)")
        self.chk_garbling.setChecked(self.qm.filtro_garbling_activo)
        layout.addWidget(self.chk_garbling)

        self.chk_fruit = QCheckBox("Filtrar FRUIT / Ruido (1 solo ploteo huérfano esparcido)")
        self.chk_fruit.setChecked(self.qm.filtro_fruit_activo)
        layout.addWidget(self.chk_fruit)

        self.chk_inmaduras = QCheckBox("Filtrar Pistas Inmaduras (Menos de 2 vueltas de radar)")
        self.chk_inmaduras.setChecked(self.qm.filtro_inmaduras_activo)
        layout.addWidget(self.chk_inmaduras)

        btn_aplicar = QPushButton("Aplicar Configuración")
        btn_aplicar.clicked.connect(self.aplicar_cambios)
        layout.addWidget(btn_aplicar)

    def aplicar_cambios(self):
        self.qm.filtro_garbling_activo = self.chk_garbling.isChecked()
        self.qm.filtro_fruit_activo = self.chk_fruit.isChecked()
        self.qm.filtro_inmaduras_activo = self.chk_inmaduras.isChecked()
        self.accept()
