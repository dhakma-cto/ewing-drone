"""Bounding box selection, OSD overlay, and state display."""

import cv2


# Colors (BGR)
GREEN = (0, 255, 0)
RED = (0, 0, 255)
YELLOW = (0, 255, 255)
WHITE = (255, 255, 255)
CYAN = (255, 255, 0)
ORANGE = (0, 165, 255)


class ROISelector:
    """Non-blocking ROI cursor controlled by RC sticks or keyboard.

    Each frame, call update_rc() and/or update_keyboard(), then draw().
    When the operator confirms, .confirmed becomes True and .bbox has the ROI.
    """

    def __init__(self, cfg=None):
        cfg = cfg or {}

        # RC channel mappings
        self.ch_move_x = cfg.get("ch_move_x", 1)
        self.ch_move_y = cfg.get("ch_move_y", 2)
        self.ch_size_w = cfg.get("ch_size_w", 4)
        self.ch_size_h = cfg.get("ch_size_h", 3)
        self.ch_confirm = cfg.get("ch_confirm", 10)
        self.stick_deadband = cfg.get("stick_deadband", 50)
        self.cursor_speed = cfg.get("cursor_speed", 8.0)
        self.size_speed = cfg.get("size_speed", 3.0)
        self.throttle_is_size_h = cfg.get("throttle_is_size_h", True)
        self.min_roi = cfg.get("min_roi_size", 15)
        self.max_roi = cfg.get("max_roi_size", 400)
        self.default_w = float(cfg.get("default_roi_w", 120))
        self.default_h = float(cfg.get("default_roi_h", 120))

        # Frame dimensions — set on first draw() from actual frame
        self.frame_w = 0
        self.frame_h = 0

        # Cursor state
        self.cx = 0.0
        self.cy = 0.0
        self.roi_w = self.default_w
        self.roi_h = self.default_h

        self.active = False
        self.confirmed = False
        self.cancelled = False
        self.bbox = None  # (x, y, w, h) int tuple when confirmed

    def activate(self):
        """Start ROI selection mode. Cursor centers on first draw()."""
        self.roi_w = self.default_w
        self.roi_h = self.default_h
        self.active = True
        self.confirmed = False
        self.cancelled = False
        self.bbox = None
        # cx/cy set on first draw() from actual frame size
        self._needs_center = True
        print(f"[roi] Activated — waiting for frame to center cursor")

    def deactivate(self):
        self.active = False

    def update_rc(self, rc):
        """Update cursor from RC stick input. rc is an RCInput instance."""
        if not self.active or rc is None or not rc.connected:
            return

        # Move position — right stick
        dx = rc.get_stick_normalized(self.ch_move_x, self.stick_deadband)
        dy = rc.get_stick_normalized(self.ch_move_y, self.stick_deadband)
        self.cx += dx * self.cursor_speed
        self.cy -= dy * self.cursor_speed  # stick up = negative PWM offset = move up

        # Size — left stick horizontal = width
        dw = rc.get_stick_normalized(self.ch_size_w, self.stick_deadband)
        self.roi_w += dw * self.size_speed

        # Size — throttle = height (absolute mapping)
        if self.throttle_is_size_h:
            t = rc.get_throttle_normalized(self.ch_size_h)
            self.roi_h = self.min_roi + t * (self.max_roi - self.min_roi)
        else:
            dh = rc.get_stick_normalized(self.ch_size_h, self.stick_deadband)
            self.roi_h += dh * self.size_speed

        self._clamp()

        # Confirm — switch
        if rc.get_switch(self.ch_confirm):
            self._confirm()

    def update_keyboard(self, key):
        """Update cursor from keyboard input. key is from cv2.waitKey() & 0xFF."""
        if not self.active:
            return

        speed = self.cursor_speed
        sz_speed = self.size_speed

        # WASD movement
        if key == ord('w'):
            self.cy -= speed * 3
        elif key == ord('s'):
            self.cy += speed * 3
        elif key == ord('a'):
            self.cx -= speed * 3
        elif key == ord('d'):
            self.cx += speed * 3

        # +/- for size (= key is + without shift on most keyboards)
        elif key == ord('+') or key == ord('='):
            self.roi_w += sz_speed * 3
            self.roi_h += sz_speed * 3
        elif key == ord('-'):
            self.roi_w -= sz_speed * 3
            self.roi_h -= sz_speed * 3

        # Brackets for width only, shift-brackets for height only
        elif key == ord(']'):
            self.roi_w += sz_speed * 3
        elif key == ord('['):
            self.roi_w -= sz_speed * 3
        elif key == ord('.'):
            self.roi_h += sz_speed * 3
        elif key == ord(','):
            self.roi_h -= sz_speed * 3

        # Enter to confirm
        elif key == 13:  # Enter
            self._confirm()

        # Escape to cancel
        elif key == 27:  # ESC
            self.cancelled = True
            self.active = False

        self._clamp()

    def _clamp(self):
        """Clamp cursor position and ROI size to valid ranges."""
        if self.frame_w == 0:
            return
        self.roi_w = max(self.min_roi, min(self.max_roi, self.roi_w))
        self.roi_h = max(self.min_roi, min(self.max_roi, self.roi_h))
        half_w = self.roi_w / 2
        half_h = self.roi_h / 2
        self.cx = max(half_w, min(self.frame_w - half_w, self.cx))
        self.cy = max(half_h, min(self.frame_h - half_h, self.cy))

    def _confirm(self):
        """Lock in the current ROI."""
        x = int(self.cx - self.roi_w / 2)
        y = int(self.cy - self.roi_h / 2)
        w = int(self.roi_w)
        h = int(self.roi_h)
        self.bbox = (x, y, w, h)
        self.confirmed = True
        self.active = False
        print(f"[roi] Confirmed: ({x}, {y}, {w}, {h})")

    def draw(self, frame):
        """Draw ROI cursor overlay on frame (mutates in place)."""
        if not self.active:
            return

        # Sync frame dimensions from actual frame
        fh, fw = frame.shape[:2]
        if self.frame_w != fw or self.frame_h != fh:
            self.frame_w = fw
            self.frame_h = fh

        # Center cursor on first frame after activate
        if getattr(self, '_needs_center', False):
            self.cx = fw / 2.0
            self.cy = fh / 2.0
            self._needs_center = False
            print(f"[roi] Centered cursor at ({self.cx:.0f}, {self.cy:.0f}) on {fw}x{fh} frame")

        cx_i = int(self.cx)
        cy_i = int(self.cy)
        half_w = int(self.roi_w / 2)
        half_h = int(self.roi_h / 2)
        x1 = cx_i - half_w
        y1 = cy_i - half_h
        x2 = cx_i + half_w
        y2 = cy_i + half_h

        # Black outline for contrast, then bright green box
        cv2.rectangle(frame, (x1 - 1, y1 - 1), (x2 + 1, y2 + 1), (0, 0, 0), 3)
        cv2.rectangle(frame, (x1, y1), (x2, y2), GREEN, 2)

        # Corner brackets for extra visibility
        corner_len = max(15, min(half_w, half_h) // 3)
        for (cx1, cy1), (dx, dy) in [
            ((x1, y1), (1, 1)), ((x2, y1), (-1, 1)),
            ((x1, y2), (1, -1)), ((x2, y2), (-1, -1)),
        ]:
            cv2.line(frame, (cx1, cy1), (cx1 + dx * corner_len, cy1), GREEN, 3)
            cv2.line(frame, (cx1, cy1), (cx1, cy1 + dy * corner_len), GREEN, 3)

        # Crosshair at cursor center
        cross_size = max(20, min(half_w, half_h))
        cv2.line(frame, (cx_i - cross_size, cy_i),
                 (cx_i + cross_size, cy_i), GREEN, 1)
        cv2.line(frame, (cx_i, cy_i - cross_size),
                 (cx_i, cy_i + cross_size), GREEN, 1)
        cv2.circle(frame, (cx_i, cy_i), 4, GREEN, -1)

        # Size readout above box with dark background
        size_text = f"ROI {int(self.roi_w)}x{int(self.roi_h)}"
        (tw, th), _ = cv2.getTextSize(size_text, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
        cv2.rectangle(frame, (x1, y1 - th - 12), (x1 + tw + 4, y1 - 2), (0, 0, 0), -1)
        cv2.putText(frame, size_text, (x1 + 2, y1 - 8),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, GREEN, 2)

        # Large "SELECT TARGET" banner at top center
        banner = "SELECT TARGET"
        (bw, bh), _ = cv2.getTextSize(banner, cv2.FONT_HERSHEY_SIMPLEX, 1.0, 2)
        bx = (fw - bw) // 2
        cv2.rectangle(frame, (bx - 10, 5), (bx + bw + 10, bh + 20), (0, 0, 0), -1)
        cv2.putText(frame, banner, (bx, bh + 12),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.0, GREEN, 2)

        # Instructions at bottom with dark background
        instr = "WASD:move  +/-:size  Enter:confirm  ESC:cancel"
        (iw, ih), _ = cv2.getTextSize(instr, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
        cv2.rectangle(frame, (5, fh - ih - 50), (15 + iw, fh - 34), (0, 0, 0), -1)
        cv2.putText(frame, instr, (10, fh - 40),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, GREEN, 1)


class TargetSelector:
    """Wraps cv2.selectROI for operator target selection."""

    WINDOW_NAME = "STRIKER"

    @staticmethod
    def select(frame, window_name="STRIKER"):
        """Show frame and let operator draw bounding box.

        Returns:
            (x, y, w, h) tuple, or None if cancelled.
        """
        bbox = cv2.selectROI(window_name, frame, fromCenter=False, showCrosshair=True)
        if bbox[2] == 0 or bbox[3] == 0:
            return None
        return tuple(int(v) for v in bbox)


class OverlayRenderer:
    """Draw tracking overlay, crosshair, error vectors, state info."""

    def draw(self, frame, state, bbox=None, confidence=0.0,
             error_x=0.0, error_y=0.0, fps=0.0, cmd_str="",
             detections=None, lost_frames=0):
        """Draw full overlay on frame (mutates in place).

        Args:
            frame: BGR numpy array
            state: current state string
            bbox: (x, y, w, h) of tracked target, or None
            confidence: tracker confidence 0-1
            error_x, error_y: normalized error -1 to +1
            fps: current FPS
            cmd_str: velocity command string for display
            detections: list of YOLO detections for debug display
            lost_frames: frames since track was lost
        """
        h, w = frame.shape[:2]
        cx, cy = w // 2, h // 2

        # Crosshair at frame center
        self._draw_crosshair(frame, cx, cy)

        # Tracking bbox
        if bbox is not None:
            color = self._state_color(state)
            x, y, bw, bh = [int(v) for v in bbox]
            cv2.rectangle(frame, (x, y), (x + bw, y + bh), color, 2)

            # Target center dot
            tcx, tcy = x + bw // 2, y + bh // 2
            cv2.circle(frame, (tcx, tcy), 4, color, -1)

            # Error vector from frame center to target center
            cv2.arrowedLine(frame, (cx, cy), (tcx, tcy), CYAN, 2, tipLength=0.05)

            # Pixel error readout near target
            px_err_x = error_x * w / 2
            px_err_y = error_y * h / 2
            err_text = f"err: ({px_err_x:+.0f}, {px_err_y:+.0f})px"
            cv2.putText(frame, err_text, (x, y - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)

        # YOLO detections (debug, draw in orange)
        if detections:
            for det in detections:
                _, conf, dx, dy, dw, dh = det
                cv2.rectangle(frame, (dx, dy), (dx + dw, dy + dh), ORANGE, 1)
                cv2.putText(frame, f"{conf:.2f}", (dx, dy - 5),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.4, ORANGE, 1)

        # HUD - top left
        self._draw_hud(frame, state, fps, confidence, error_x, error_y,
                       cmd_str, lost_frames)

        # Controls help - bottom
        self._draw_controls(frame)

    def _draw_crosshair(self, frame, cx, cy, size=20):
        """Draw center crosshair."""
        cv2.line(frame, (cx - size, cy), (cx + size, cy), WHITE, 1)
        cv2.line(frame, (cx, cy - size), (cx, cy + size), WHITE, 1)
        cv2.circle(frame, (cx, cy), 3, WHITE, 1)

    def _state_color(self, state):
        colors = {
            "IDLE": WHITE,
            "TARGET_SELECT": YELLOW,
            "TRACKING": GREEN,
            "TRACK_LOST": RED,
            "STRIKE_ARMED": ORANGE,
            "TERMINAL": RED,
            "COMPLETE": WHITE,
        }
        return colors.get(state, WHITE)

    def _draw_hud(self, frame, state, fps, confidence, error_x, error_y,
                  cmd_str, lost_frames):
        """Draw heads-up display in top-left corner."""
        lines = [
            f"STATE: {state}",
            f"FPS: {fps:.1f}",
        ]

        if state in ("TRACKING", "STRIKE_ARMED", "TERMINAL"):
            lines.append(f"CONF: {confidence:.2f}")
            lines.append(f"ERR: ({error_x:+.3f}, {error_y:+.3f})")

        if state == "TRACK_LOST":
            lines.append(f"LOST: {lost_frames} frames")

        if cmd_str:
            lines.append(cmd_str)

        y = 25
        for line in lines:
            # Background for readability
            (tw, th), _ = cv2.getTextSize(line, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 1)
            cv2.rectangle(frame, (8, y - th - 4), (16 + tw, y + 4), (0, 0, 0), -1)
            cv2.putText(frame, line, (10, y),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, GREEN, 1)
            y += 25

    def _draw_controls(self, frame):
        """Draw keyboard controls at bottom of frame."""
        h = frame.shape[0]
        controls = "[S]elect  [A]rm  [X]strike  [R]eset  [Q]uit"
        cv2.putText(frame, controls, (10, h - 15),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, WHITE, 1)
