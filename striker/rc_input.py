"""Threaded MAVLink RC channel reader for TX16S stick input."""

import threading
import time

try:
    from pymavlink import mavutil
    MAVLINK_AVAILABLE = True
except ImportError:
    MAVLINK_AVAILABLE = False


class RCInput:
    """Background reader for RC_CHANNELS via MAVLink.

    Reads RC channel data in a background thread and exposes
    normalized stick values and switch states with zero blocking.
    """

    def __init__(self, port="/dev/serial0", baud=57600, rate_hz=10):
        self.port = port
        self.baud = baud
        self.rate_hz = rate_hz

        self._conn = None
        self._lock = threading.Lock()
        self._channels = {}  # ch_number -> pwm_value
        self._running = False
        self._recv_thread = None
        self._hb_thread = None
        self._connected = False

    def start(self):
        """Connect to FC and start background threads.

        Returns False gracefully if pymavlink unavailable or connection fails.
        """
        if not MAVLINK_AVAILABLE:
            print("[rc_input] pymavlink not available — RC disabled")
            return False

        try:
            self._conn = mavutil.mavlink_connection(self.port, baud=self.baud)
            print(f"[rc_input] Waiting for heartbeat on {self.port}...")
            self._conn.wait_heartbeat(timeout=5)
            print(f"[rc_input] Heartbeat from system {self._conn.target_system}")
        except Exception as e:
            print(f"[rc_input] Connection failed: {e} — RC disabled")
            self._conn = None
            return False

        # Request RC_CHANNELS stream
        self._conn.mav.request_data_stream_send(
            self._conn.target_system,
            self._conn.target_component,
            mavutil.mavlink.MAV_DATA_STREAM_RC_CHANNELS,
            self.rate_hz,
            1,  # start
        )

        self._running = True
        self._connected = True

        self._recv_thread = threading.Thread(target=self._receiver_loop,
                                             daemon=True, name="rc_recv")
        self._recv_thread.start()

        self._hb_thread = threading.Thread(target=self._heartbeat_loop,
                                           daemon=True, name="rc_hb")
        self._hb_thread.start()

        print("[rc_input] RC input started")
        return True

    @property
    def connected(self):
        return self._connected

    def _receiver_loop(self):
        """Background thread: read RC_CHANNELS messages."""
        while self._running:
            try:
                msg = self._conn.recv_match(type='RC_CHANNELS',
                                            blocking=True, timeout=0.5)
                if msg is None:
                    continue

                with self._lock:
                    # RC_CHANNELS has chan1_raw through chan18_raw
                    for i in range(1, 19):
                        val = getattr(msg, f'chan{i}_raw', 0)
                        if val != 0 and val != 65535:
                            self._channels[i] = val
            except Exception:
                if self._running:
                    time.sleep(0.1)

    def _heartbeat_loop(self):
        """Background thread: send heartbeats to keep connection alive."""
        while self._running:
            try:
                if self._conn:
                    self._conn.mav.heartbeat_send(
                        mavutil.mavlink.MAV_TYPE_GCS,
                        mavutil.mavlink.MAV_AUTOPILOT_INVALID,
                        0, 0, 0,
                    )
            except Exception:
                pass
            time.sleep(1.0)

    def get_channel(self, ch):
        """Get raw PWM value for a channel. Returns 0 if unavailable."""
        with self._lock:
            return self._channels.get(ch, 0)

    def get_stick_normalized(self, ch, deadband=50):
        """Get stick value normalized to -1.0..+1.0 with deadband.

        Center is assumed at PWM 1500. Range 1000-2000.
        """
        raw = self.get_channel(ch)
        if raw == 0:
            return 0.0

        offset = raw - 1500
        if abs(offset) < deadband:
            return 0.0

        # Remove deadband from offset
        if offset > 0:
            offset -= deadband
        else:
            offset += deadband

        # Normalize to -1..+1
        max_range = 500 - deadband
        return max(-1.0, min(1.0, offset / max_range))

    def get_throttle_normalized(self, ch):
        """Get throttle value normalized to 0.0..1.0 (absolute, no center).

        PWM 1000 → 0.0, PWM 2000 → 1.0.
        """
        raw = self.get_channel(ch)
        if raw == 0:
            return 0.5  # default mid

        return max(0.0, min(1.0, (raw - 1000) / 1000.0))

    def get_switch(self, ch, threshold=1700):
        """Get switch state: True if PWM > threshold."""
        raw = self.get_channel(ch)
        return raw > threshold

    def stop(self):
        """Stop background threads and close connection."""
        self._running = False
        self._connected = False
        if self._recv_thread:
            self._recv_thread.join(timeout=2.0)
        if self._hb_thread:
            self._hb_thread.join(timeout=2.0)
        if self._conn:
            self._conn.close()
            self._conn = None
        print("[rc_input] Stopped")


if __name__ == "__main__":
    import sys

    port = sys.argv[1] if len(sys.argv) > 1 else "/dev/serial0"
    baud = int(sys.argv[2]) if len(sys.argv) > 2 else 57600

    rc = RCInput(port=port, baud=baud)
    if not rc.start():
        print("Failed to start RC input")
        sys.exit(1)

    print("Reading RC channels... Ctrl+C to stop\n")
    try:
        while True:
            line_parts = []
            for ch in range(1, 11):
                raw = rc.get_channel(ch)
                line_parts.append(f"CH{ch:2d}:{raw:4d}")
            print("  ".join(line_parts), end="\r")
            time.sleep(0.1)
    except KeyboardInterrupt:
        print("\nStopping...")
    finally:
        rc.stop()
