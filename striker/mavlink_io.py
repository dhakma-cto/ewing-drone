"""MAVLink interface — stubbed for PoC, real FC integration later."""

import time

try:
    from pymavlink import mavutil
    MAVLINK_AVAILABLE = True
except ImportError:
    MAVLINK_AVAILABLE = False


class MAVLinkInterface:
    """Send velocity commands to flight controller via MAVLink.

    PoC mode: logs commands to console. Real mode: sends via serial.
    """

    def __init__(self, port="/dev/ttyACM0", baud=115200, stub=True):
        self.port = port
        self.baud = baud
        self.stub = stub
        self._conn = None

    def connect(self):
        if self.stub:
            print(f"[mavlink] STUB mode — commands will be logged, not sent")
            return True

        if not MAVLINK_AVAILABLE:
            print("[mavlink] pymavlink not available, falling back to stub mode")
            self.stub = True
            return True

        try:
            self._conn = mavutil.mavlink_connection(self.port, baud=self.baud)
            self._conn.wait_heartbeat(timeout=5)
            print(f"[mavlink] Connected to FC on {self.port}")
            return True
        except Exception as e:
            print(f"[mavlink] Connection failed: {e} — falling back to stub")
            self.stub = True
            return True

    def send_velocity(self, vx, vy, vz):
        """Send velocity command (NED frame).

        Args:
            vx: forward velocity (m/s)
            vy: right velocity (m/s)
            vz: down velocity (m/s, positive = descend)
        """
        if self.stub:
            # Only log periodically to avoid spam
            return

        if self._conn is None:
            return

        self._conn.mav.set_position_target_local_ned_send(
            0,  # time_boot_ms
            self._conn.target_system,
            self._conn.target_component,
            mavutil.mavlink.MAV_FRAME_BODY_NED,
            0b0000111111000111,  # type_mask: only velocity
            0, 0, 0,           # position (ignored)
            vx, vy, vz,        # velocity
            0, 0, 0,           # acceleration (ignored)
            0, 0               # yaw, yaw_rate (ignored)
        )

    def log_command(self, vx, vy, vz):
        """Log command for display/debug regardless of mode."""
        return f"CMD: vx={vx:+.2f} vy={vy:+.2f} vz={vz:+.2f}"

    def disconnect(self):
        if self._conn is not None:
            self._conn.close()
            self._conn = None
