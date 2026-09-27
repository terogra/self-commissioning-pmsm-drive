class PIController:
    def __init__(self, kp: float, ki: float):
        self.kp = kp
        self.ki = ki
        self.integral = 0.0

    def update(self, error: float, dt: float) -> float:
        self.integral += self.ki * error * dt
        return self.kp * error + self.integral

    def reset(self):
        self.integral = 0.0