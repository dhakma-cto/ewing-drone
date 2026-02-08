"""OpenCV CSRT pixel tracker with confidence proxy."""

import cv2
from utils import bbox_area, bbox_aspect_ratio


class PixelTracker:
    """Wraps OpenCV CSRT tracker with loss detection heuristics."""

    def __init__(self, area_change_ratio=3.0, aspect_change_ratio=2.0,
                 max_frames_lost=15):
        self._tracker = None
        self._init_bbox = None
        self._init_area = 0
        self._init_aspect = 1.0
        self._frames_lost = 0
        self._max_frames_lost = max_frames_lost
        self._area_change_ratio = area_change_ratio
        self._aspect_change_ratio = aspect_change_ratio
        self._active = False

    def init(self, frame, bbox):
        """Initialize tracker on frame with bbox (x, y, w, h)."""
        # Ensure bbox values are ints
        bbox = tuple(int(v) for v in bbox)
        self._tracker = cv2.TrackerCSRT.create()
        self._tracker.init(frame, bbox)
        self._init_bbox = bbox
        self._init_area = bbox_area(bbox)
        self._init_aspect = bbox_aspect_ratio(bbox)
        self._frames_lost = 0
        self._active = True

    def update(self, frame):
        """Update tracker with new frame.

        Returns:
            (success, bbox, confidence):
                success: True if track is considered valid
                bbox: (x, y, w, h) or None
                confidence: float 0-1 proxy
        """
        if not self._active or self._tracker is None:
            return False, None, 0.0

        ok, bbox = self._tracker.update(frame)

        if not ok:
            self._frames_lost += 1
            return False, None, 0.0

        bbox = tuple(int(v) for v in bbox)
        confidence = self._compute_confidence(bbox)

        if confidence < 0.3:
            self._frames_lost += 1
            if self._frames_lost >= self._max_frames_lost:
                return False, bbox, confidence
        else:
            self._frames_lost = 0

        return True, bbox, confidence

    def _compute_confidence(self, bbox):
        """Heuristic confidence based on area and aspect ratio change."""
        if self._init_area <= 0:
            return 0.5

        area = bbox_area(bbox)
        aspect = bbox_aspect_ratio(bbox)

        # Penalize large area changes
        area_ratio = max(area, self._init_area) / max(min(area, self._init_area), 1)
        area_score = max(0, 1.0 - (area_ratio - 1) / self._area_change_ratio)

        # Penalize large aspect ratio changes
        aspect_diff = abs(aspect - self._init_aspect)
        aspect_score = max(0, 1.0 - aspect_diff / self._aspect_change_ratio)

        # Penalize zero-size bboxes
        if bbox[2] <= 0 or bbox[3] <= 0:
            return 0.0

        return area_score * 0.6 + aspect_score * 0.4

    def is_lost(self):
        return self._frames_lost >= self._max_frames_lost

    def reset(self):
        self._tracker = None
        self._active = False
        self._frames_lost = 0

    @property
    def active(self):
        return self._active

    @property
    def frames_lost(self):
        return self._frames_lost
