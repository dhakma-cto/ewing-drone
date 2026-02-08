"""Bounding box selection, OSD overlay, and state display."""

import cv2


# Colors (BGR)
GREEN = (0, 255, 0)
RED = (0, 0, 255)
YELLOW = (0, 255, 255)
WHITE = (255, 255, 255)
CYAN = (255, 255, 0)
ORANGE = (0, 165, 255)


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
