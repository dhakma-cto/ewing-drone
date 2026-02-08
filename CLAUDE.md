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
PRIMARY: Pixel/Siamese Tracker (fast, frame-to-frame)
    ↓ (on track loss or low confidence)
FALLBACK: YOLO detection (class-agnostic, finds candidates)
    ↓
RE-ACQUIRE: Match nearest detection to last known position/size
    ↓
CONTROL: PID visual servoing → MAVLink → Flight Controller
```

## HARDWARE

- Raspberry Pi 5 (4GB or 8GB)
- Hailo AI HAT+ (M.2 module, 26 TOPS)
- Pi Camera Module 3
- RRFCH7 v1.1 Flight Controller (ArduPilot, MAVLink over USB)
- Connection: FC USB-C → Pi USB-A

## SOFTWARE STACK

- OS: Raspberry Pi OS 64-bit (Bookworm)
- Inference: Hailo SDK, HEF compiled models
- Detection: YOLOv8n (compiled to HEF) - class-agnostic mode
- Tracking: OpenCV CSRT/KCF as primary tracker
- Control: PID controller, pymavlink for MAVLink commands
- Language: Python primary
- Libraries: OpenCV, NumPy, picamera2, hailo-platform, pymavlink

## DIRECTORY STRUCTURE

```
striker/
├── CLAUDE.md
├── requirements.txt
├── config.yaml
├── src/
│   ├── main.py
│   ├── capture/
│   │   └── camera.py
│   ├── detection/
│   │   ├── hailo_detector.py
│   │   └── models/
│   ├── tracking/
│   │   ├── pixel_tracker.py
│   │   ├── recovery.py
│   │   └── tracker_manager.py
│   ├── control/
│   │   ├── pid.py
│   │   ├── visual_servo.py
│   │   └── mavlink_interface.py
│   ├── ui/
│   │   └── target_selector.py
│   └── utils/
│       ├── geometry.py
│       └── timing.py
├── tests/
├── scripts/
│   ├── install_hailo.sh
│   └── run_demo.sh
└── data/
    └── test_videos/
```

## STATE MACHINE

```
IDLE → OPERATOR_CONTROL → TARGET_SELECTION → TRACKING → STRIKE_ARMED → TERMINAL → COMPLETE
                              ↑                  ↓
                              └── TRACK_LOST ────┘
```

- IDLE: System startup
- OPERATOR_CONTROL: Manual flight, video streaming
- TARGET_SELECTION: Operator draws bounding box
- TRACKING: Pixel tracker active, visual servoing
- TRACK_LOST: YOLO fallback searching for re-acquisition
- STRIKE_ARMED: Target confirmed, waiting for strike command
- TERMINAL: Autonomous descent, no operator input needed
- COMPLETE: Impact or abort

## KEY ALGORITHMS

### Pixel Tracker (Primary)
- OpenCV CSRT tracker - fast, runs on CPU
- Confidence threshold < 0.5 triggers YOLO fallback
- Updates ROI every frame

### YOLO Fallback (Recovery)
- YOLOv8n on Hailo NPU
- Class-agnostic: use ALL detections regardless of class
- Match to last known position by nearest centroid + similar aspect ratio
- Only runs when primary tracker fails

### Visual Servoing
```python
error_x = (target_cx - frame_cx) / frame_width   # normalized -1 to 1
error_y = (target_cy - frame_cy) / frame_height
velocity_cmd = pid.update(error_x, error_y)
# Send velocity_cmd via MAVLink
```

## HARDWARE VERIFICATION COMMANDS

```bash
# Check Hailo NPU
hailortcli fw-control identify

# Check camera
libcamera-hello

# Check FC connection
ls /dev/ttyACM*
```

## IMMEDIATE PRIORITIES (Demo by tomorrow)

1. Install Hailo SDK, verify NPU detected
2. Run camera capture with picamera2
3. Run YOLOv8 example on Hailo
4. Implement OpenCV CSRT tracker
5. Operator draws bounding box → system tracks object
6. Display video with bounding box overlay

## CONSTRAINTS

- Outdoor daytime lighting
- Target ~1m² at 100-130m altitude (small in frame, 15-30px at 1080p)
- No telephoto lens available
- Signal dropout expected at low altitude - autonomy critical
- Made in USA matters for competition scoring

## MY ROLE

I am the architect. You (Claude Code) are my senior software engineer. I direct the architecture and algorithms, you help implement, debug, and iterate fast. Ask clarifying questions if requirements are ambiguous. Prioritize working code over perfect code - we have 2 weeks.
