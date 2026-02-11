"""picamera2 capture wrapper for Pi Camera Module 3."""

import time
import numpy as np

try:
    from picamera2 import Picamera2
except ImportError:
    Picamera2 = None


class CameraStream:
    """Wraps picamera2 for zero-copy frame capture as NumPy BGR arrays."""

    def __init__(self, width=1536, height=864, camera_index=0):
        self.width = width
        self.height = height
        self.camera_index = camera_index
        self._cam = None
        self._last_retry = 0
        self._retry_interval = 3.0  # seconds between retries

    def start(self):
        if Picamera2 is None:
            print("[camera] picamera2 not installed — waiting for camera")
            return
        self._try_connect()

    def _try_connect(self):
        """Attempt to open the camera. Tries configured index, then the other slot."""
        for idx in [self.camera_index, 1 - self.camera_index]:
            try:
                cam = Picamera2(idx)
                config = cam.create_video_configuration(
                    main={"size": (self.width, self.height), "format": "BGR888"},
                    buffer_count=4,
                )
                cam.configure(config)
                cam.start()
                self._cam = cam
                self.camera_index = idx
                print(f"[camera] Connected (camera {idx})")
                return
            except (IndexError, RuntimeError, OSError):
                try:
                    cam.close()
                except Exception:
                    pass
        self._cam = None

    def read(self):
        """Return a BGR numpy array frame, or None on failure."""
        if self._cam is None:
            now = time.monotonic()
            if now - self._last_retry >= self._retry_interval:
                self._last_retry = now
                self._try_connect()
        if self._cam is None:
            # Black frame with "NO CAMERA" text
            frame = np.zeros((self.height, self.width, 3), dtype=np.uint8)
            import cv2
            cv2.putText(frame, "NO CAMERA", (self.width // 2 - 150, self.height // 2),
                        cv2.FONT_HERSHEY_SIMPLEX, 1.5, (0, 0, 255), 3)
            return frame
        return self._cam.capture_array("main")

    def stop(self):
        if self._cam is not None:
            self._cam.stop()
            self._cam.close()
            self._cam = None

    @property
    def frame_size(self):
        return (self.width, self.height)


class FakeCameraStream:
    """Fallback for development without a Pi camera. Uses webcam or test pattern."""

    def __init__(self, width=1536, height=864, source=0):
        self.width = width
        self.height = height
        self._source = source
        self._cap = None

    def start(self):
        import cv2
        self._cap = cv2.VideoCapture(self._source)
        if not self._cap.isOpened():
            # Generate test pattern frames
            self._cap = None

    def read(self):
        if self._cap is not None:
            ret, frame = self._cap.read()
            if ret:
                import cv2
                return cv2.resize(frame, (self.width, self.height))
        # Test pattern fallback
        frame = np.zeros((self.height, self.width, 3), dtype=np.uint8)
        frame[::2, :] = (40, 40, 40)
        return frame

    def stop(self):
        if self._cap is not None:
            self._cap.release()
            self._cap = None

    @property
    def frame_size(self):
        return (self.width, self.height)
