from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QGroupBox, QCheckBox, 
    QScrollArea, QWidget, QPushButton, QHBoxLayout, QLabel
)
from PyQt6.QtCore import Qt

class MapEditorDialog(QDialog):
    def __init__(self, map_manager, parent=None):
        super().__init__(parent)
        self.map_manager = map_manager
        self.setWindowTitle("Gestor de Capas del Sector")
        self.setMinimumSize(350, 400)
        self.setStyleSheet("""
            QDialog {
                background-color: #0B0E14;
                color: #E0E6ED;
            }
            QGroupBox {
                border: 1px solid rgba(0, 229, 255, 60);
                border-radius: 6px;
                margin-top: 15px;
                padding-top: 15px;
            }
            QGroupBox::title {
                color: #00E5FF;
                subcontrol-origin: margin;
                subcontrol-position: top left;
                padding: 0 5px;
                background-color: #0B0E14;
            }
            QCheckBox {
                color: #E0E6ED;
                spacing: 8px;
            }
            QCheckBox::indicator {
                width: 16px;
                height: 16px;
                border: 1px solid rgba(0, 229, 255, 100);
                background: #1A2130;
                border-radius: 3px;
            }
            QCheckBox::indicator:checked {
                background: #00E5FF;
            }
            QScrollArea {
                border: none;
                background-color: transparent;
            }
            QScrollArea > QWidget > QWidget {
                background-color: transparent;
            }
        """)
        
        layout = QVBoxLayout(self)
        
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        container = QWidget()
        self.vbox = QVBoxLayout(container)
        
        self.group_estructural = QGroupBox("Mapas Estructurales (Solo Lectura)")
        self.layout_estructural = QVBoxLayout(self.group_estructural)
        self.vbox.addWidget(self.group_estructural)
        
        self.group_tactico = QGroupBox("Mapas Tácticos (Temporales)")
        self.layout_tactico = QVBoxLayout(self.group_tactico)
        self.vbox.addWidget(self.group_tactico)
        
        self.vbox.addStretch()
        
        scroll.setWidget(container)
        layout.addWidget(scroll)
        
        self._populate_layers()
        
    def _populate_layers(self):
        # Limpiar layouts
        for i in reversed(range(self.layout_estructural.count())): 
            self.layout_estructural.itemAt(i).widget().setParent(None)
        for i in reversed(range(self.layout_tactico.count())): 
            self.layout_tactico.itemAt(i).widget().setParent(None)
            
        for layer_name, layer in self.map_manager.layers.items():
            cb = QCheckBox(f"Mostrar {layer_name}")
            cb.setChecked(layer.visible)
            
            # Conectar estado
            cb.toggled.connect(lambda checked, ln=layer_name: self._toggle_layer(ln, checked))
            
            if layer.tipo == "ESTRUCTURAL":
                self.layout_estructural.addWidget(cb)
            else:
                # Layout para táctico con botón de eliminar
                row = QHBoxLayout()
                row.addWidget(cb)
                btn_del = QPushButton("X")
                btn_del.setFixedSize(20, 20)
                btn_del.setStyleSheet("background-color: #ff3366; color: white; border-radius: 10px; font-weight: bold;")
                btn_del.clicked.connect(lambda _, ln=layer_name: self._delete_tactico(ln))
                row.addWidget(btn_del)
                
                wrapper = QWidget()
                wrapper.setLayout(row)
                row.setContentsMargins(0, 0, 0, 0)
                self.layout_tactico.addWidget(wrapper)
                
    def _toggle_layer(self, layer_name: str, visible: bool):
        if layer_name in self.map_manager.layers:
            self.map_manager.layers[layer_name].visible = visible
            
            # Emitir señal al padre para redibujar
            parent = self.parent()
            if parent and hasattr(parent, 'radar'):
                parent.radar.update()
                
    def _delete_tactico(self, layer_name: str):
        if layer_name in self.map_manager.layers:
            del self.map_manager.layers[layer_name]
            self._populate_layers()
            
            parent = self.parent()
            if parent and hasattr(parent, 'radar'):
                parent.radar.update()
