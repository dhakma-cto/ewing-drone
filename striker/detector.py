"""Hailo YOLOv8 inference via HailoRT Python API, threaded."""

import threading
import queue
import numpy as np
import cv2

try:
    from hailo_platform import (
        HEF, VDevice, HailoStreamInterface,
        ConfigureParams, InferVStreams, InputVStreamParams,
        OutputVStreamParams, FormatType
    )
    HAILO_AVAILABLE = True
except ImportError:
    HAILO_AVAILABLE = False


class HailoDetector:
    """Threaded Hailo YOLOv8 detector. Class-agnostic — returns all detections."""

    def __init__(self, hef_path, conf_threshold=0.3, input_size=(640, 640)):
        self.hef_path = hef_path
        self.conf_threshold = conf_threshold
        self.input_w, self.input_h = input_size

        self._input_queue = queue.Queue(maxsize=1)
        self._output_queue = queue.Queue(maxsize=1)
        self._thread = None
        self._running = False

        # Set during _load_model
        self._hef = None
        self._vdevice = None
        self._network_group = None
        self._input_vstream_info = None
        self._output_vstream_info = None

    def start(self):
        """Load model and start inference thread."""
        if not HAILO_AVAILABLE:
            print("[detector] HailoRT not available — running in stub mode")
            self._running = True
            self._thread = threading.Thread(target=self._stub_loop, daemon=True)
            self._thread.start()
            return

        self._load_model()
        self._running = True
        self._thread = threading.Thread(target=self._inference_loop, daemon=True)
        self._thread.start()

    def _load_model(self):
        """Load HEF and configure Hailo device."""
        self._hef = HEF(self.hef_path)
        self._vdevice = VDevice()

        configure_params = ConfigureParams.create_from_hef(
            self._hef, interface=HailoStreamInterface.PCIe
        )
        self._network_group = self._vdevice.configure(
            self._hef, configure_params
        )[0]

        self._input_vstream_info = self._hef.get_input_vstream_infos()
        self._output_vstream_info = self._hef.get_output_vstream_infos()

        print(f"[detector] Loaded {self.hef_path}")
        for info in self._input_vstream_info:
            print(f"  Input:  {info.name} shape={info.shape} dtype={info.format.type}")
        for info in self._output_vstream_info:
            print(f"  Output: {info.name} shape={info.shape}")

    def request_inference(self, frame):
        """Submit a frame for async inference. Non-blocking, drops old frames."""
        # Store original frame dimensions for coordinate scaling
        try:
            self._input_queue.get_nowait()  # drop old frame
        except queue.Empty:
            pass
        self._input_queue.put((frame.copy(), frame.shape[1], frame.shape[0]))

    def get_results(self):
        """Get latest detection results. Non-blocking.

        Returns:
            list of (class_id, confidence, x, y, w, h) in original frame coords,
            or None if no results ready.
        """
        try:
            return self._output_queue.get_nowait()
        except queue.Empty:
            return None

    def _preprocess(self, frame):
        """Resize and format frame for Hailo input."""
        resized = cv2.resize(frame, (self.input_w, self.input_h))
        # BGR to RGB
        rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
        # HailoRT expects uint8 NHWC
        return np.expand_dims(rgb, axis=0).astype(np.uint8)

    def _inference_loop(self):
        """Main inference loop running in background thread."""
        input_params = InputVStreamParams.make(
            self._network_group, format_type=FormatType.UINT8
        )
        output_params = OutputVStreamParams.make(self._network_group)

        with InferVStreams(self._network_group, input_params, output_params) as pipeline:
            while self._running:
                try:
                    frame, orig_w, orig_h = self._input_queue.get(timeout=0.1)
                except queue.Empty:
                    continue

                input_data = self._preprocess(frame)

                input_dict = {
                    self._input_vstream_info[0].name: input_data
                }
                raw_output = pipeline.infer(input_dict)

                detections = self._postprocess(raw_output, orig_w, orig_h)

                try:
                    self._output_queue.get_nowait()
                except queue.Empty:
                    pass
                self._output_queue.put(detections)

    def _postprocess(self, raw_output, orig_w, orig_h):
        """Parse Hailo NMS output into detection list.

        YOLOv8s with built-in NMS outputs a tensor of shape
        [1, num_detections, 6] where each detection is:
        [y1_norm, x1_norm, y2_norm, x2_norm, confidence, class_id]

        The exact format depends on the HEF compilation. We handle
        the common Hailo NMS output format.
        """
        detections = []

        for name, tensor in raw_output.items():
            data = np.array(tensor)

            # Hailo NMS output: may be list of arrays per class or flat array
            if data.ndim == 1 and data.size == 0:
                continue

            # Flatten if needed — handle various Hailo output shapes
            if data.ndim == 3:
                # Shape: [1, N, 6] — standard NMS
                data = data.reshape(-1, data.shape[-1])
            elif data.ndim == 2:
                pass  # already [N, cols]
            elif data.ndim == 1:
                if data.size % 6 == 0:
                    data = data.reshape(-1, 6)
                else:
                    continue
            else:
                continue

            if data.shape[0] == 0:
                continue

            for det in data:
                if len(det) < 5:
                    continue

                # Try standard format: [y1, x1, y2, x2, confidence, class_id]
                if len(det) >= 6:
                    y1_n, x1_n, y2_n, x2_n, conf, cls_id = det[:6]
                else:
                    y1_n, x1_n, y2_n, x2_n, conf = det[:5]
                    cls_id = 0

                if conf < self.conf_threshold:
                    continue

                # Scale to original frame coordinates
                x1 = int(x1_n * orig_w)
                y1 = int(y1_n * orig_h)
                x2 = int(x2_n * orig_w)
                y2 = int(y2_n * orig_h)
                w = x2 - x1
                h = y2 - y1

                if w > 0 and h > 0:
                    detections.append((int(cls_id), float(conf), x1, y1, w, h))

        return detections

    def _stub_loop(self):
        """Stub loop when Hailo hardware is not available."""
        while self._running:
            try:
                frame, orig_w, orig_h = self._input_queue.get(timeout=0.1)
            except queue.Empty:
                continue
            # Return empty detections in stub mode
            try:
                self._output_queue.get_nowait()
            except queue.Empty:
                pass
            self._output_queue.put([])

    def stop(self):
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=2.0)
        if self._vdevice is not None:
            del self._vdevice
            self._vdevice = None
