# STATUS — Last updated 2025-02-07

## What's Built

Full end-to-end PoC pipeline — 10 Python modules in `striker/`:

| Module | Status | Notes |
|--------|--------|-------|
| `camera.py` | VERIFIED on Pi | 1536x864 BGR frames, picamera2 working |
| `tracker.py` | Code complete | CSRT with confidence heuristics, needs GUI test |
| `detector.py` | VERIFIED on Pi | Hailo loads HEF, inference runs, NMS parsing correct |
| `recovery.py` | Code complete | Centroid + aspect ratio matching |
| `servo.py` | Code complete | Dual-axis PID, tested in pure Python |
| `mavlink_io.py` | Code complete | Stub mode (FC not connected) |
| `ui.py` | Code complete | ROI selection + full OSD overlay |
| `main.py` | Code complete | State machine wired, needs GUI test on Pi via VNC |
| `utils.py` | VERIFIED | Geometry helpers, FPS counter |
| `config.yaml` | Complete | All parameters tunable |

## What's Verified Working on Pi

1. Camera capture: picamera2 → 1536x864 BGR numpy arrays
2. Hailo NPU: model loads, network group activates, inference executes
3. NMS output parsing: shape `(1, 80, N, 5)` handled correctly
4. All Python imports resolve (including hailo_platform)
5. 0 detections returned in dark room — expected, not an error

## What Needs Testing (Tomorrow)

1. **GUI test via VNC** — run `python3 striker/main.py` on Pi desktop
2. **Target selection** — press S, draw bounding box, verify CSRT tracks
3. **YOLO fallback** — occlude target, verify detector fires and recovery re-acquires
4. **FPS measurement** — verify 30+ fps during CSRT tracking
5. **Visual servoing overlay** — error vector, crosshair, HUD readouts
6. **Point camera at objects** — need COCO-recognizable objects for YOLO to detect

## Known Issues / Risks

- Hailo NMS output coordinate order (y1,x1,y2,x2 vs x1,y1,x2,y2) — assumed y1,x1,y2,x2 based on Hailo convention, needs verification with actual detections
- CSRT confidence is a heuristic (area/aspect change), not a real confidence score — may need tuning
- Camera auto-exposure needs settling time (~30 frames) for good exposure

## Next Steps After PoC Demo

1. Tune CSRT confidence thresholds with real tracking data
2. Measure Hailo inference latency
3. Connect flight controller (RRFCH7 USB), test MAVLink
4. Network video streaming (for operator display)
5. Test outdoors with real target at distance
