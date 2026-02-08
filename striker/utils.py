"""Geometry helpers, timing, and FPS counter."""

import time
from collections import deque


def bbox_center(bbox):
    """Return (cx, cy) center of a (x, y, w, h) bounding box."""
    x, y, w, h = bbox
    return (x + w / 2, y + h / 2)


def bbox_area(bbox):
    """Return area of a (x, y, w, h) bounding box."""
    return bbox[2] * bbox[3]


def bbox_aspect_ratio(bbox):
    """Return width/height aspect ratio. Returns 1.0 if height is 0."""
    _, _, w, h = bbox
    return w / h if h > 0 else 1.0


def centroid_distance(bbox1, bbox2):
    """Euclidean distance between centers of two (x, y, w, h) bboxes."""
    c1 = bbox_center(bbox1)
    c2 = bbox_center(bbox2)
    return ((c1[0] - c2[0]) ** 2 + (c1[1] - c2[1]) ** 2) ** 0.5


def xyxy_to_xywh(x1, y1, x2, y2):
    """Convert (x1, y1, x2, y2) to (x, y, w, h)."""
    return (int(x1), int(y1), int(x2 - x1), int(y2 - y1))


def xywh_to_xyxy(x, y, w, h):
    """Convert (x, y, w, h) to (x1, y1, x2, y2)."""
    return (x, y, x + w, y + h)


class FPSCounter:
    """Sliding-window FPS counter."""

    def __init__(self, window=30):
        self._times = deque(maxlen=window)

    def tick(self):
        self._times.append(time.monotonic())

    def fps(self):
        if len(self._times) < 2:
            return 0.0
        elapsed = self._times[-1] - self._times[0]
        if elapsed <= 0:
            return 0.0
        return (len(self._times) - 1) / elapsed


class RateTimer:
    """Simple rate limiter / interval timer."""

    def __init__(self, hz):
        self._interval = 1.0 / hz if hz > 0 else 0
        self._last = 0.0

    def ready(self):
        now = time.monotonic()
        if now - self._last >= self._interval:
            self._last = now
            return True
        return False
