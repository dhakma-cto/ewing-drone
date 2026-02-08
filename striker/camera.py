"""picamera2 capture wrapper for Pi Camera Module 3."""

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

    def start(self):
        if Picamera2 is None:
            raise RuntimeError(
                "picamera2 not installed. Install with: pip install picamera2"
            )
        self._cam = Picamera2(self.camera_index)
        config = self._cam.create_video_configuration(
            main={"size": (self.width, self.height), "format": "BGR888"},
            buffer_count=4,
        )
        self._cam.configure(config)
        self._cam.start()

    def read(self):
        """Return a BGR numpy array frame, or None on failure."""
        if self._cam is None:
            return None
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
