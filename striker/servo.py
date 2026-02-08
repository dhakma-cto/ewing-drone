"""PID controller and visual servoing error calculation."""

import time
from utils import bbox_center


class PIDController:
    """Single-axis PID controller with anti-windup."""

    def __init__(self, kp=0.5, ki=0.01, kd=0.1, windup_limit=0.5):
        self.kp = kp
        self.ki = ki
        self.kd = kd
        self.windup_limit = windup_limit

        self._integral = 0.0
        self._prev_error = 0.0
        self._prev_time = None

    def update(self, error):
        """Compute PID output for given error value.

        Returns:
            float: control output
        """
        now = time.monotonic()
        if self._prev_time is None:
            dt = 0.033  # assume ~30fps on first call
        else:
            dt = now - self._prev_time
            dt = max(dt, 0.001)  # prevent division by zero
        self._prev_time = now

        # Proportional
        p = self.kp * error

        # Integral with anti-windup
        self._integral += error * dt
        self._integral = max(-self.windup_limit,
                             min(self.windup_limit, self._integral))
        i = self.ki * self._integral

        # Derivative
        d = self.kd * (error - self._prev_error) / dt
        self._prev_error = error

        return p + i + d

    def reset(self):
        self._integral = 0.0
        self._prev_error = 0.0
        self._prev_time = None


class VisualServo:
    """Dual-axis visual servoing: compute velocity commands from pixel error."""

    def __init__(self, pid_x_params, pid_y_params, deadband=0.02,
                 max_velocity=1.0, descent_rate=-0.5):
        self.pid_x = PIDController(**pid_x_params)
        self.pid_y = PIDController(**pid_y_params)
        self.deadband = deadband
        self.max_velocity = max_velocity
        self.descent_rate = descent_rate

        # Last computed errors for display
        self.error_x = 0.0
        self.error_y = 0.0
        self.cmd_vx = 0.0
        self.cmd_vy = 0.0

    def update(self, target_bbox, frame_size):
        """Compute velocity commands to center target in frame.

        Args:
            target_bbox: (x, y, w, h) of tracked target
            frame_size: (width, height) of frame

        Returns:
            (vx, vy, vz): velocity commands.
                vx = forward/back (positive = forward)
                vy = left/right (positive = right)
                vz = up/down (positive = down for descent)
        """
        frame_w, frame_h = frame_size
        cx, cy = bbox_center(target_bbox)

        # Normalized error: -1 to +1
        self.error_x = (cx - frame_w / 2) / (frame_w / 2)
        self.error_y = (cy - frame_h / 2) / (frame_h / 2)

        # Apply deadband
        vx = 0.0
        vy = 0.0

        if abs(self.error_x) > self.deadband:
            vy = self.pid_x.update(self.error_x)

        if abs(self.error_y) > self.deadband:
            vx = -self.pid_y.update(self.error_y)  # negative: forward reduces y-error

        # Clamp velocities
        vx = max(-self.max_velocity, min(self.max_velocity, vx))
        vy = max(-self.max_velocity, min(self.max_velocity, vy))

        self.cmd_vx = vx
        self.cmd_vy = vy

        return (vx, vy, self.descent_rate)

    def get_error_pixels(self, frame_size):
        """Return error in pixels for display."""
        fw, fh = frame_size
        return (self.error_x * fw / 2, self.error_y * fh / 2)

    def reset(self):
        self.pid_x.reset()
        self.pid_y.reset()
        self.error_x = 0.0
        self.error_y = 0.0
