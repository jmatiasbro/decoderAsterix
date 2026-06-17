import time

class AlphaBetaFilter:
    """
    Filtro Alpha-Beta para suavizado de trayectorias cinemáticas (X, Y en metros).
    Mitiga el jitter causado por desalineación de sensores en entornos multisensor (Modo Integrado).
    """
    def __init__(self, initial_x, initial_y, alpha=0.6, beta=0.005):
        self.x = initial_x
        self.y = initial_y
        self.vx = 0.0
        self.vy = 0.0
        self.alpha = alpha
        self.beta = beta
        self.last_update = time.time()

    def update(self, meas_x, meas_y, current_time=None):
        if current_time is None: 
            current_time = time.time()
        dt = current_time - self.last_update
        if dt <= 0: 
            return self.x, self.y

        # Protección contra interrupciones de señal prolongadas (coasting de más de 20 segundos)
        # Resetea el filtro a la nueva medición para evitar runaway projections extremas
        if dt > 20.0:
            self.x = meas_x
            self.y = meas_y
            self.vx = 0.0
            self.vy = 0.0
            self.last_update = current_time
            return self.x, self.y

        pred_x = self.x + (self.vx * dt)
        pred_y = self.y + (self.vy * dt)

        res_x = meas_x - pred_x
        res_y = meas_y - pred_y

        self.x = pred_x + (self.alpha * res_x)
        self.y = pred_y + (self.alpha * res_y)
        self.vx = self.vx + (self.beta * res_x / dt)
        self.vy = self.vy + (self.beta * res_y / dt)

        self.last_update = current_time
        return self.x, self.y
