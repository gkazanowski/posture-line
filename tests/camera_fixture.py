"""Real subprocess fixture replacing only camera/model hardware dependencies."""
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import numpy as np
from posture_line.camera_process import listen_for_stop, run_camera, send


def main():
    mode = sys.argv[1]
    stopped = threading.Event()
    threading.Thread(target=listen_for_stop, args=(stopped,), daemon=True).start()
    capture = MagicMock()
    capture.isOpened.return_value = True
    reads = 0

    def read():
        nonlocal reads
        reads += 1
        if mode == "failure":
            raise RuntimeError("Simulated camera read failure")
        if mode == "blocked" and reads > 1:
            send({"type": "status", "message": "Test camera read blocked"})
            threading.Event().wait()  # Deliberately ignores the stop event.
        time.sleep(0.02)
        return True, np.zeros((120, 160, 3), dtype=np.uint8)

    def open_camera(*args):
        if mode == "startup":
            send({"type": "status", "message": "Test camera startup blocked"})
            threading.Event().wait()
        return capture

    capture.read.side_effect = read
    detector = MagicMock()
    points = [SimpleNamespace(x=i / 40, y=i / 40, visibility=1.0) for i in range(33)]
    detector.detect_for_video.return_value = SimpleNamespace(pose_landmarks=[points])
    with patch("posture_line.camera_process.ensure_model", return_value=Path("unused.task")), \
         patch("posture_line.camera_process.mp.tasks.vision.PoseLandmarker.create_from_options") as factory, \
         patch("posture_line.camera_process.cv2.VideoCapture", side_effect=open_camera):
        factory.return_value.__enter__.return_value = detector
        run_camera(0, Path("unused.task"), stopped)
    if capture.release.call_count != 1:
        raise RuntimeError("Graceful shutdown did not release the camera exactly once")


if __name__ == "__main__":
    main()
