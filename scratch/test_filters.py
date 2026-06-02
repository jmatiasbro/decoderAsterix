import sys
sys.path.insert(0, r"c:\documentos\decode_asterix")
from analysis.filters import AlphaBetaFilter

def test_alpha_beta_filter():
    print("Testing AlphaBetaFilter...")
    
    # Inicializar en (0, 0)
    ab = AlphaBetaFilter(initial_x=0.0, initial_y=0.0, alpha=0.6, beta=0.005)
    ab.last_update = 100.0
    
    # 1. Primera medición en (10.0, 20.0) a t=101.0 (dt=1.0)
    x1, y1 = ab.update(10.0, 20.0, current_time=101.0)
    print(f"Update 1 (meas=10, 20): Smoothed x={x1:.2f}, y={y1:.2f}, vx={ab.vx:.4f}, vy={ab.vy:.4f}")
    
    # Debería converger parcialmente hacia la medición (alpha=0.6)
    # pred_x = 0, pred_y = 0
    # res_x = 10, res_y = 20
    # x = 0 + 0.6 * 10 = 6.0
    # y = 0 + 0.6 * 20 = 12.0
    # vx = 0 + 0.005 * 10 / 1.0 = 0.05
    # vy = 0 + 0.005 * 20 / 1.0 = 0.10
    assert abs(x1 - 6.0) < 1e-5
    assert abs(y1 - 12.0) < 1e-5
    assert abs(ab.vx - 0.05) < 1e-5
    assert abs(ab.vy - 0.10) < 1e-5
    
    # 2. Segunda medición en (20.0, 40.0) a t=102.0 (dt=1.0)
    x2, y2 = ab.update(20.0, 40.0, current_time=102.0)
    print(f"Update 2 (meas=20, 40): Smoothed x={x2:.2f}, y={y2:.2f}, vx={ab.vx:.4f}, vy={ab.vy:.4f}")
    
    # pred_x = 6.0 + 0.05 * 1.0 = 6.05
    # pred_y = 12.0 + 0.10 * 1.0 = 12.10
    # res_x = 20.0 - 6.05 = 13.95
    # res_y = 40.0 - 12.10 = 27.90
    # x = 6.05 + 0.6 * 13.95 = 14.42
    # y = 12.10 + 0.6 * 27.90 = 28.84
    assert abs(x2 - 14.42) < 1e-2
    assert abs(y2 - 28.84) < 1e-2

    # 3. Prueba de protección contra coasting (> 20 segundos)
    # A t=130.0 (dt=28.0s), debería resetearse instantáneamente a la nueva medición para evitar saltos locos
    x3, y3 = ab.update(100.0, 100.0, current_time=130.0)
    print(f"Update 3 (meas=100, 100 after 28s delay): Smoothed x={x3:.2f}, y={y3:.2f}, vx={ab.vx:.4f}")
    assert abs(x3 - 100.0) < 1e-5
    assert abs(y3 - 100.0) < 1e-5
    assert abs(ab.vx - 0.0) < 1e-5
    assert abs(ab.vy - 0.0) < 1e-5

    print("AlphaBetaFilter tests PASSED successfully!")

if __name__ == "__main__":
    test_alpha_beta_filter()
