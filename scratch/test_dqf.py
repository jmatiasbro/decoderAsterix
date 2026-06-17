"""
test_dqf.py — Pruebas unitarias para el motor DQF (Data Quality Filter)
========================================================================
Valida:
  1. Que la clase QualityManager clasifique correctamente pistas como degradadas.
  2. Que los filtros de garbling y FRUIT actúen de acuerdo con las configuraciones.
  3. Que el comportamiento sea determinista y correcto bajo diferentes estados.
"""

import sys
import os

# Agregar directorio raíz al path para importaciones
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from analysis.quality_manager import QualityManager

def test_quality_manager_defaults():
    print("Corriendo test_quality_manager_defaults...")
    qm = QualityManager()
    qm.filtro_garbling_activo = False
    qm.filtro_fruit_activo = False
    qm.filtro_inmaduras_activo = False
    
    # Con filtros inactivos, no se degrada nada
    degradada, razon = qm.evaluar_pista("T1", {"garbled": True, "update_count": 1})
    assert not degradada, "No debería degradar si los filtros están desactivados"
    assert razon == ""
    print("test_quality_manager_defaults PASSED!")

def test_quality_manager_garbling():
    print("Corriendo test_quality_manager_garbling...")
    qm = QualityManager()
    qm.filtro_garbling_activo = True
    qm.filtro_fruit_activo = False
    qm.filtro_inmaduras_activo = False
    
    # Con garbling activo, si garbled es True, se degrada
    degradada, razon = qm.evaluar_pista("T1", {"garbled": True, "update_count": 5})
    assert degradada, "Debería degradar si garbled es True y el filtro de garbling está activo"
    assert "garbling" in razon.lower()
    
    # Con garbling activo, si garbled es False, no se degrada
    degradada, razon = qm.evaluar_pista("T2", {"garbled": False, "update_count": 5})
    assert not degradada, "No debería degradar si garbled es False"
    print("test_quality_manager_garbling PASSED!")

def test_quality_manager_fruit():
    print("Corriendo test_quality_manager_fruit...")
    qm = QualityManager()
    qm.filtro_garbling_activo = False
    qm.filtro_fruit_activo = True
    qm.filtro_inmaduras_activo = False
    
    # Con FRUIT activo, si update_count es 1 (huérfano), se degrada
    degradada, razon = qm.evaluar_pista("T1", {"garbled": False, "update_count": 1})
    assert degradada, "Debería degradar si es 1 ploteo huérfano y el filtro FRUIT está activo"
    assert "fruit" in razon.lower()
    
    # Con FRUIT activo, si update_count es 2, no se degrada por FRUIT
    degradada, razon = qm.evaluar_pista("T2", {"garbled": False, "update_count": 2})
    assert not degradada, "No debería degradar por FRUIT si tiene 2 ploteos"
    print("test_quality_manager_fruit PASSED!")

def test_quality_manager_inmaduras():
    print("Corriendo test_quality_manager_inmaduras...")
    qm = QualityManager()
    qm.filtro_garbling_activo = False
    qm.filtro_fruit_activo = False
    qm.filtro_inmaduras_activo = True
    
    # Con Inmaduras activo, si update_count es 1 (< 2), se degrada
    degradada, razon = qm.evaluar_pista("T1", {"garbled": False, "update_count": 1})
    assert degradada, "Debería degradar si es < 2 actualizaciones"
    assert "inmadura" in razon.lower()
    
    # Con Inmaduras activo, si tiene 2 updates (2 vueltas), ya es maduro!
    degradada, razon = qm.evaluar_pista("T2", {"garbled": False, "update_count": 2})
    assert not degradada, "Debería considerarse maduro a las 2 vueltas de radar"
    print("test_quality_manager_inmaduras PASSED!")

if __name__ == "__main__":
    test_quality_manager_defaults()
    test_quality_manager_garbling()
    test_quality_manager_fruit()
    test_quality_manager_inmaduras()
    print("Todos los tests de DQF concluyeron exitosamente!")
