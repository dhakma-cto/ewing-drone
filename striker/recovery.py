"""Re-acquisition logic: match YOLO detections to last known target."""

from utils import bbox_center, bbox_aspect_ratio, centroid_distance


class RecoveryManager:
    """Stores last known target info and finds best match from YOLO detections."""

    def __init__(self, max_centroid_distance=200, aspect_ratio_tolerance=0.5):
        self.max_centroid_distance = max_centroid_distance
        self.aspect_ratio_tolerance = aspect_ratio_tolerance
        self._last_bbox = None
        self._last_center = None
        self._last_aspect = None

    def store_target(self, bbox):
        """Store current target bbox (x, y, w, h) as reference for recovery."""
        self._last_bbox = bbox
        self._last_center = bbox_center(bbox)
        self._last_aspect = bbox_aspect_ratio(bbox)

    def find_best_match(self, detections):
        """Find the detection closest to the last known target.

        Args:
            detections: list of (class_id, confidence, x, y, w, h)

        Returns:
            (x, y, w, h) of best match, or None if no good match found.
        """
        if self._last_bbox is None or not detections:
            return None

        best_match = None
        best_score = float('inf')

        for det in detections:
            _, conf, x, y, w, h = det
            det_bbox = (x, y, w, h)

            # Distance from last known position
            dist = centroid_distance(det_bbox, self._last_bbox)
            if dist > self.max_centroid_distance:
                continue

            # Aspect ratio similarity
            det_aspect = bbox_aspect_ratio(det_bbox)
            aspect_diff = abs(det_aspect - self._last_aspect)
            if aspect_diff > self.aspect_ratio_tolerance:
                continue

            # Score: lower is better (weighted distance + aspect penalty)
            score = dist + aspect_diff * 100

            if score < best_score:
                best_score = score
                best_match = det_bbox

        return best_match

    @property
    def has_reference(self):
        return self._last_bbox is not None

    @property
    def last_bbox(self):
        return self._last_bbox
