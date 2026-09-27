class PIController:
    def __init__(
        self,
        kp: float,
        ki: float,
        output_min=None,
        output_max=None
    ):
        self.kp = kp
        self.ki = ki
        self.output_min = output_min
        self.output_max = output_max
        self.integral = 0.0

    def update(self, error: float, dt: float) -> float:
        previous_integral = self.integral

        self.integral += self.ki * error * dt

        output = self.kp * error + self.integral

        if self.output_max is not None and output > self.output_max:
            if error > 0.0:
                self.integral = previous_integral
            output = self.output_max

        if self.output_min is not None and output < self.output_min:
            if error < 0.0:
                self.integral = previous_integral
            output = self.output_min

        return output

    def reset(self):
        self.integral = 0.0

    def track_output(self, applied: float, requested: float, dt: float, gain: float):
        """Back-calculate the integrator when a downstream limit changes output."""
        self.integral += gain * dt * (applied - requested)
