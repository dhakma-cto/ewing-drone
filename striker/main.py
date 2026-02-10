#!/usr/bin/env python3
"""STRIKER EDGE AI — Main loop and state machine.

Usage:
    python3 main.py                 # Run with Pi camera
    python3 main.py --fake          # Run with webcam/test pattern (dev mode)
    python3 main.py --video FILE    # Run on video file
"""

import sys
import os
import argparse
import cv2
import yaml

# Add striker directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from camera import CameraStream, FakeCameraStream
from tracker import PixelTracker
from detector import HailoDetector
from recovery import RecoveryManager
from servo import VisualServo
from mavlink_io import MAVLinkInterface
from rc_input import RCInput
from ui import TargetSelector, ROISelector, OverlayRenderer
from utils import FPSCounter


# --- State constants ---
IDLE = "IDLE"
TARGET_SELECT = "TARGET_SELECT"
TRACKING = "TRACKING"
TRACK_LOST = "TRACK_LOST"
STRIKE_ARMED = "STRIKE_ARMED"
TERMINAL = "TERMINAL"
COMPLETE = "COMPLETE"

WINDOW_NAME = "STRIKER"


def load_config(path):
    with open(path) as f:
        return yaml.safe_load(f)


def main():
    parser = argparse.ArgumentParser(description="STRIKER EDGE AI PoC")
    parser.add_argument("--fake", action="store_true",
                        help="Use webcam or test pattern instead of Pi camera")
    parser.add_argument("--video", type=str, default=None,
                        help="Path to video file for testing")
    parser.add_argument("--config", type=str,
                        default=os.path.join(os.path.dirname(__file__), "config.yaml"),
                        help="Path to config YAML")
    args = parser.parse_args()

    # --- Load config ---
    cfg = load_config(args.config)
    cam_cfg = cfg["camera"]
    trk_cfg = cfg["tracker"]
    det_cfg = cfg["detector"]
    rec_cfg = cfg["recovery"]
    pid_cfg = cfg["pid"]
    srv_cfg = cfg["servo"]
    mav_cfg = cfg["mavlink"]
    rc_cfg = cfg.get("rc_input", {})

    # --- Initialize modules ---
    # Camera
    if args.video:
        camera = FakeCameraStream(cam_cfg["width"], cam_cfg["height"],
                                  source=args.video)
    elif args.fake:
        camera = FakeCameraStream(cam_cfg["width"], cam_cfg["height"])
    else:
        camera = CameraStream(cam_cfg["width"], cam_cfg["height"],
                              cam_cfg["index"])

    # Tracker
    tracker = PixelTracker(
        area_change_ratio=trk_cfg["area_change_ratio"],
        aspect_change_ratio=trk_cfg["aspect_change_ratio"],
        max_frames_lost=trk_cfg["max_frames_lost"],
    )

    # Detector
    detector = HailoDetector(
        hef_path=det_cfg["hef_path"],
        conf_threshold=det_cfg["confidence_threshold"],
        input_size=(det_cfg["input_width"], det_cfg["input_height"]),
    )

    # Recovery
    recovery = RecoveryManager(
        max_centroid_distance=rec_cfg["max_centroid_distance"],
        aspect_ratio_tolerance=rec_cfg["aspect_ratio_tolerance"],
    )

    # Visual servoing
    servo = VisualServo(
        pid_x_params={"kp": pid_cfg["x"]["kp"], "ki": pid_cfg["x"]["ki"],
                       "kd": pid_cfg["x"]["kd"]},
        pid_y_params={"kp": pid_cfg["y"]["kp"], "ki": pid_cfg["y"]["ki"],
                       "kd": pid_cfg["y"]["kd"]},
        deadband=srv_cfg["deadband"],
        max_velocity=srv_cfg["max_velocity"],
        descent_rate=srv_cfg["descent_rate"],
    )

    # MAVLink (stub by default)
    mavlink = MAVLinkInterface(
        port=mav_cfg["port"],
        baud=mav_cfg["baud"],
        stub=True,
    )

    # RC input (skip in --fake mode, graceful failure)
    rc = RCInput(
        port=rc_cfg.get("port", "/dev/serial0"),
        baud=rc_cfg.get("baud", 57600),
        rate_hz=rc_cfg.get("rate_hz", 10),
    )
    if not args.fake and not args.video:
        rc.start()  # returns False gracefully on failure

    # ROI selector (non-blocking, gets frame size from actual frame on first draw)
    roi_selector = ROISelector(rc_cfg)

    # UI
    overlay = OverlayRenderer()
    fps_counter = FPSCounter()

    # --- State ---
    state = IDLE
    current_bbox = None
    current_confidence = 0.0
    last_detections = None
    recovery_frames = 0
    max_recovery_frames = rec_cfg["max_recovery_frames"]
    cmd_str = ""

    # RC switch channels and edge detection
    ch_mode = rc_cfg.get("ch_mode", 9)    # SE — Manual/AI
    ch_state = rc_cfg.get("ch_state", 8)  # SD — state transitions
    prev_mode_pos = -1   # -1 = not yet read (suppress startup trigger)
    prev_state_pos = -1
    ai_mode = False

    # --- Start modules ---
    print("[main] Starting STRIKER EDGE AI PoC...")
    camera.start()
    detector.start()
    mavlink.connect()

    cv2.namedWindow(WINDOW_NAME, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(WINDOW_NAME, cam_cfg["width"], cam_cfg["height"])

    print("[main] Running. Press 'S' to select target, 'Q' to quit.")

    try:
        while True:
            frame = camera.read()
            if frame is None:
                continue

            fps_counter.tick()
            key = cv2.waitKey(1) & 0xFF

            # --- Global key handlers ---
            if key == ord('q'):
                print("[main] Quit requested")
                break
            elif key == ord('r'):
                # Reset to idle
                state = IDLE
                tracker.reset()
                servo.reset()
                roi_selector.deactivate()
                current_bbox = None
                current_confidence = 0.0
                recovery_frames = 0
                cmd_str = ""
                print("[main] Reset to IDLE")

            # --- RC switch handling (edge-triggered) ---
            if rc.connected:
                mode_pos = rc.get_switch_3way(ch_mode)
                state_pos = rc.get_switch_3way(ch_state)

                # First read — store positions, don't act
                if prev_mode_pos == -1:
                    prev_mode_pos = mode_pos
                    prev_state_pos = state_pos
                    ai_mode = (mode_pos == 2)
                    if ai_mode:
                        print("[main] Started in AI mode")
                    else:
                        print("[main] Started in MANUAL mode")

                # Mode switch: down=AI, up/mid=Manual
                if mode_pos != prev_mode_pos:
                    if mode_pos == 2 and not ai_mode:
                        ai_mode = True
                        print("[main] >>> AI MODE ENABLED")
                    elif mode_pos != 2 and ai_mode:
                        ai_mode = False
                        # Immediate override — kill everything
                        state = IDLE
                        tracker.reset()
                        servo.reset()
                        roi_selector.deactivate()
                        current_bbox = None
                        current_confidence = 0.0
                        recovery_frames = 0
                        cmd_str = ""
                        print("[main] >>> MANUAL MODE — AI disengaged")
                    prev_mode_pos = mode_pos

                # State switch (only in AI mode, edge-triggered)
                if ai_mode and state_pos != prev_state_pos:
                    # Up → Mid: Select target
                    if prev_state_pos == 0 and state_pos == 1:
                        if state == IDLE:
                            roi_selector.activate()
                            state = TARGET_SELECT
                            print("[main] [SD] Select target")
                    # Mid → Down: Arm or Execute
                    elif prev_state_pos == 1 and state_pos == 2:
                        if state == TRACKING:
                            state = STRIKE_ARMED
                            print("[main] [SD] STRIKE ARMED")
                        elif state == STRIKE_ARMED:
                            state = TERMINAL
                            print("[main] [SD] STRIKE EXECUTE → TERMINAL")
                    # Any → Up: Reset
                    elif state_pos == 0:
                        state = IDLE
                        tracker.reset()
                        servo.reset()
                        roi_selector.deactivate()
                        current_bbox = None
                        current_confidence = 0.0
                        recovery_frames = 0
                        cmd_str = ""
                        print("[main] [SD] Reset to IDLE")
                    prev_state_pos = state_pos

            # --- State machine ---
            if state == IDLE:
                if key == ord('s'):
                    roi_selector.activate()
                    state = TARGET_SELECT
                    print("[main] ROI selection started")

            elif state == TARGET_SELECT:
                roi_selector.update_rc(rc)
                roi_selector.update_keyboard(key)
                roi_selector.draw(frame)

                if roi_selector.confirmed:
                    bbox = roi_selector.bbox
                    tracker.init(frame, bbox)
                    recovery.store_target(bbox)
                    current_bbox = bbox
                    servo.reset()
                    state = TRACKING
                    print(f"[main] Target selected: {bbox} → TRACKING")
                elif roi_selector.cancelled:
                    state = IDLE
                    print("[main] Selection cancelled → IDLE")

            elif state == TRACKING:
                ok, bbox, conf = tracker.update(frame)
                current_confidence = conf

                if ok:
                    current_bbox = bbox
                    recovery.store_target(bbox)  # update reference
                    servo.update(bbox, camera.frame_size)
                    cmd_str = mavlink.log_command(servo.cmd_vx, servo.cmd_vy,
                                                  servo.descent_rate)
                else:
                    # Track lost — trigger YOLO
                    detector.request_inference(frame)
                    state = TRACK_LOST
                    recovery_frames = 0
                    print("[main] Track lost → TRACK_LOST, requesting YOLO")

                if key == ord('a'):
                    state = STRIKE_ARMED
                    print("[main] STRIKE ARMED")

            elif state == TRACK_LOST:
                recovery_frames += 1

                # Check for YOLO results
                detections = detector.get_results()
                if detections is not None:
                    last_detections = detections

                if detections:
                    match = recovery.find_best_match(detections)
                    if match:
                        tracker.init(frame, match)
                        current_bbox = match
                        state = TRACKING
                        print(f"[main] Re-acquired target: {match} → TRACKING")
                    else:
                        # No good match, keep trying
                        detector.request_inference(frame)
                elif detections is not None:
                    # YOLO returned but no detections
                    detector.request_inference(frame)

                if recovery_frames >= max_recovery_frames:
                    print("[main] Recovery timeout → IDLE")
                    state = IDLE
                    tracker.reset()
                    current_bbox = None

            elif state == STRIKE_ARMED:
                ok, bbox, conf = tracker.update(frame)
                current_confidence = conf

                if ok:
                    current_bbox = bbox
                    recovery.store_target(bbox)
                    servo.update(bbox, camera.frame_size)
                    cmd_str = mavlink.log_command(servo.cmd_vx, servo.cmd_vy,
                                                  servo.descent_rate)
                else:
                    detector.request_inference(frame)
                    state = TRACK_LOST
                    recovery_frames = 0
                    print("[main] Track lost while armed → TRACK_LOST")

                if key == ord('x'):
                    state = TERMINAL
                    print("[main] STRIKE EXECUTE → TERMINAL")

            elif state == TERMINAL:
                ok, bbox, conf = tracker.update(frame)
                current_confidence = conf

                if ok:
                    current_bbox = bbox
                    recovery.store_target(bbox)
                    vx, vy, vz = servo.update(bbox, camera.frame_size)
                    mavlink.send_velocity(vx, vy, vz)
                    cmd_str = mavlink.log_command(vx, vy, vz)
                else:
                    # In terminal, try recovery but keep descending
                    detector.request_inference(frame)
                    detections = detector.get_results()
                    if detections:
                        match = recovery.find_best_match(detections)
                        if match:
                            tracker.init(frame, match)
                            current_bbox = match

                # For PoC, terminal runs until user quits or resets

            elif state == COMPLETE:
                cmd_str = "MISSION COMPLETE"

            # --- Draw overlay ---
            overlay.draw(
                frame,
                state=state,
                bbox=current_bbox,
                confidence=current_confidence,
                error_x=servo.error_x,
                error_y=servo.error_y,
                fps=fps_counter.fps(),
                cmd_str=cmd_str,
                detections=last_detections if state == TRACK_LOST else None,
                lost_frames=recovery_frames if state == TRACK_LOST else 0,
            )

            cv2.imshow(WINDOW_NAME, frame)

    except KeyboardInterrupt:
        print("\n[main] Interrupted")
    finally:
        print("[main] Shutting down...")
        rc.stop()
        detector.stop()
        camera.stop()
        mavlink.disconnect()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
