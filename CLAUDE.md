# STRIKER EDGE AI - Raspberry Pi 5 Drone Vision System

## PROJECT OVERVIEW

Real-time visual tracking and terminal guidance system for autonomous drone strike on stationary targets. Competition deadline: ~2 weeks. Hardware: Raspberry Pi 5 + Hailo AI HAT+ (26 TOPS NPU).

## MISSION CONTEXT

- Drone flies 10km to target area (manual/waypoint)
- At altitude, operator has signal and sees video feed
- Operator draws bounding box around unknown target on screen
- System locks and tracks target
- Operator commands "strike" → drone autonomously descends to target
- Signal may drop at low altitude → autonomy must complete the mission
- Target is STATIONARY (confirmed)
- Target type is UNKNOWN until operator sees it (no pre-trained class dependency)

## CRITICAL REQUIREMENTS

1. Model-agnostic tracking - cannot rely on YOLO classification, target is unknown
2. Pixel-level lock - must track even when target is small/distant (no telephoto lens)
3. Obstruction recovery - if target occluded, must re-acquire using YOLO fallback
4. GPS-free terminal guidance - visual servoing only, minimize pixel error from frame center
5. Runs on Pi 5 + Hailo NPU - must hit 30fps detection, 100Hz+ control loop

## ARCHITECTURE

```
PRIMARY: CSRT Pixel Tracker (fast, every frame on CPU)
    ↓ (on track loss)
FALLBACK: YOLOv8s on Hailo NPU (class-agnostic, threaded)
    ↓
RE-ACQUIRE: Match nearest detection to last known position/size
    ↓
CONTROL: PID visual servoing → MAVLink → Flight Controller
```

## HARDWARE (VERIFIED)

- Raspberry Pi 5 8GB, Bookworm, Python 3.13, IP: 192.168.1.31 (hostname: ewingpi)
- 2x IMX708 Pi Camera Module 3 (both detected and working)
- Hailo-8 NPU: FW 4.23.0, HailoRT 4.23, `/dev/hailo0`
- OpenCV 4.10, picamera2 0.3.32, TAPPAS 5.1
- HEF model: `/usr/share/hailo-models/yolov8s_h8.hef` (640x640 RGB, NMS built-in)
- Flight controller: RRFCH7 v1.1 (ArduPilot, MAVLink over USB) — NOT connected yet

## SOFTWARE STACK

- OS: Raspberry Pi OS 64-bit (Bookworm)
- Inference: HailoRT Python API (direct, not TAPPAS/GStreamer)
- Detection: YOLOv8s compiled to HEF — class-agnostic mode
- Tracking: OpenCV CSRT tracker
- Control: PID controller, pymavlink for MAVLink commands
- Camera: picamera2 direct (not rpicam-apps)
- Language: Python 3

## DIRECTORY STRUCTURE (ACTUAL)

```
ewing-drone/
├── CLAUDE.md              # This file — project context for AI assistants
├── STATUS.md              # Current progress, what works, what's next
├── requirements.txt
├── .gitignore
└── striker/
    ├── config.yaml        # All tunable parameters
    ├── main.py            # Entry point, state machine, main loop
    ├── camera.py          # picamera2 capture wrapper
    ├── tracker.py         # OpenCV CSRT tracker + confidence heuristics
    ├── detector.py        # Threaded Hailo YOLOv8 inference
    ├── recovery.py        # Re-acquisition (match YOLO dets to last target)
    ├── servo.py           # PID controller + visual servoing
    ├── mavlink_io.py      # MAVLink interface (stubbed until FC connected)
    ├── ui.py              # ROI selection, OSD overlay, HUD
    └── utils.py           # Geometry helpers, FPS counter
```

## STATE MACHINE

```
IDLE → TARGET_SELECT → TRACKING → STRIKE_ARMED → TERMINAL → COMPLETE
                          ↑            ↓
                          └─ TRACK_LOST ┘
```

Keyboard controls: [S]elect target, [A]rm strike, [X]execute strike, [R]eset, [Q]uit

## HAILO NPU DETAILS

- HailoRT Python API: `from hailo_platform import HEF, VDevice, InferVStreams, ...`
- Must call `network_group.activate()` before inference
- YOLOv8s NMS output shape: `(1, 80, N, 5)` where:
  - 80 = COCO classes
  - N = variable number of detections (0 if none)
  - 5 = [y1_norm, x1_norm, y2_norm, x2_norm, confidence]
- Max shape reported by `get_output_vstream_infos()` is `(80, 5, 100)` — but runtime shape differs
- Input: 640x640 RGB uint8

## DEV WORKFLOW

- Code on WSL2 with Claude Code, push to GitHub, pull on Pi to test
- WSL2 has no cv2/picamera2 — use `--fake` flag for webcam/test pattern dev
- Pi display via VNC (RealVNC Viewer on Windows → 192.168.1.31)
- `cv2.imshow()` runs natively on Pi desktop via VNC
- GitHub repo: `git@github.com:dhakma-cto/ewing-drone.git`

## RUNNING

```bash
python3 striker/main.py              # Pi camera (run on Pi via VNC)
python3 striker/main.py --fake       # Webcam/test pattern (dev mode)
python3 striker/main.py --video FILE # Video file input
```

## CONSTRAINTS

- Outdoor daytime lighting
- Target ~1m² at 100-130m altitude (small in frame, 15-30px at 1080p)
- No telephoto lens available
- Signal dropout expected at low altitude — autonomy critical
- Made in USA matters for competition scoring

## CONVENTIONS

- No Claude/AI references in commit messages
- Flat module layout in `striker/` — no subpackages
- `sys.path.insert(0, dirname)` in main.py for relative imports
- HAILO_AVAILABLE flag for graceful fallback when Hailo not present
- Prioritize working code over perfect code — 2 week deadline
