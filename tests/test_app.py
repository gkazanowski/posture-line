import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import unittest
import threading
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import numpy as np
from PySide6.QtWidgets import QApplication

from posture_line.app import MainWindow
from posture_line.geometry import analyze, angle
from posture_line.worker import CameraWorker
from posture_line.camera_process import run_camera


class GeometryTests(unittest.TestCase):
    def test_reference_angles_from_html(self):
        point = lambda x, y: SimpleNamespace(x=x, y=y)
        self.assertEqual(angle(point(0, 1), point(0, 0), point(1, 0)), 90)
        self.assertEqual(angle(point(-1, 0), point(0, 0), point(1, 0)), 180)

    def test_occlusion_only_invalidates_selected_side(self):
        landmarks = [SimpleNamespace(x=i / 33, y=i / 66, visibility=1.0) for i in range(33)]
        landmarks[13].visibility = 0.1
        self.assertIsNone(analyze(landmarks, "left"))
        self.assertIsNotNone(analyze(landmarks, "right"))
        self.assertIsNone(analyze([], "right"))


class ApplicationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_lost_pose_clears_previous_measurements(self):
        window = MainWindow(0, Path("unused.task"))
        window.set_metrics({"elbow": 90, "knee": 170, "torso": 20})
        window.worker = MagicMock()
        window.worker.take_latest.return_value = (np.zeros((100, 160, 3), dtype=np.uint8), [])
        window.refresh()
        self.assertTrue(all("—" in label.text() for label, _ in window.metrics.values()))
        self.assertIn("Looking for", window.status.text())
        window.worker = None
        window.close()

    @patch("posture_line.camera_process.ensure_model", return_value=Path("unused.task"))
    @patch("posture_line.camera_process.mp.tasks.vision.PoseLandmarker.create_from_options")
    @patch("posture_line.camera_process.cv2.VideoCapture")
    def test_inference_failure_releases_camera(self, capture_factory, detector_factory, model):
        capture = capture_factory.return_value
        capture.isOpened.return_value = True
        capture.read.return_value = (True, np.zeros((100, 160, 3), dtype=np.uint8))
        detector = detector_factory.return_value.__enter__.return_value
        detector.detect_for_video.side_effect = RuntimeError("simulated inference failure")
        messages = []
        run_camera(0, Path("unused.task"), threading.Event(), messages.append)
        errors = [message["message"] for message in messages if message["type"] == "error"]
        capture.release.assert_called_once()
        self.assertEqual(len(errors), 1)
        self.assertIn("simulated inference failure", errors[0])
        detector_factory.return_value.__exit__.assert_called_once()


if __name__ == "__main__":
    unittest.main()
