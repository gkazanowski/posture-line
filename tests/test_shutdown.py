"""Exercise actual subprocess shutdown and GUI lifecycle without camera hardware."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import time
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import QProcess, QTimer
from PySide6.QtWidgets import QApplication
from posture_line.app import MainWindow
from posture_line.worker import CameraWorker

FIXTURE = Path(__file__).with_name("camera_fixture.py")


class ShutdownTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self):
        self.window = MainWindow(0, Path("unused.task"))
        self.window.show()
        self.ticks = 0
        self.timer = QTimer()
        self.timer.timeout.connect(self.tick)
        self.timer.start(20)

    def tick(self):
        self.ticks += 1

    def wait_until(self, condition, seconds=10):
        deadline = time.monotonic() + seconds
        while not condition() and time.monotonic() < deadline:
            self.app.processEvents()
            time.sleep(0.005)
        self.assertTrue(condition(), "Timed out waiting for subprocess/GUI state")

    def start_fixture(self, mode):
        with patch.object(CameraWorker, "_arguments", return_value=[str(FIXTURE), mode]):
            self.window.start_camera()
        worker = self.window.worker
        exits = []
        worker.process.finished.connect(lambda code, status: exits.append((code, status)))
        return exits

    def tearDown(self):
        self.timer.stop()
        if self.window.worker is not None:
            self.window.worker.process.kill()
            self.wait_until(lambda: self.window.worker is None, 5)
        self.window.close()
        self.app.processEvents()

    def test_close_terminates_blocked_read_and_keeps_gui_responsive(self):
        exits = self.start_fixture("blocked")
        self.wait_until(lambda: self.window.status.text() == "Test camera read blocked")
        ticks_before = self.ticks
        started = time.monotonic()
        self.window.close()
        self.window.close()  # Repeated requests must not extend the deadline.
        self.wait_until(lambda: self.window.worker is None, 4)
        self.assertLess(time.monotonic() - started, 4)
        self.assertFalse(self.window.isVisible())
        self.assertTrue(exits, "The subprocess must exit before the window closes")
        self.assertGreater(self.ticks, ticks_before + 3)

    def test_stop_blocked_read_then_restart_and_stop_gracefully(self):
        self.start_fixture("blocked")
        self.wait_until(lambda: self.window.status.text() == "Test camera read blocked")
        self.window.stop_camera()
        self.wait_until(lambda: self.window.worker is None, 4)
        self.assertTrue(self.window.start_button.isEnabled())
        self.assertFalse(self.window.stop_button.isEnabled())
        self.assertFalse(self.window._error)
        exits = self.start_fixture("normal")
        self.wait_until(lambda: self.window._pixmap is not None)
        self.assertTrue(all("°" in label.text() for label, _ in self.window.metrics.values()))
        self.window.stop_camera()
        self.wait_until(lambda: self.window.worker is None, 4)
        self.assertEqual(exits, [(0, QProcess.ExitStatus.NormalExit)])

    def test_close_terminates_blocked_camera_startup(self):
        self.start_fixture("startup")
        self.wait_until(lambda: self.window.status.text() == "Test camera startup blocked")
        self.window.close()
        self.wait_until(lambda: self.window.worker is None, 4)
        self.assertFalse(self.window.isVisible())

    def test_close_immediately_after_start(self):
        self.start_fixture("normal")
        self.window.close()
        self.wait_until(lambda: self.window.worker is None, 4)
        self.assertFalse(self.window.isVisible())

    def test_camera_error_is_reported_and_start_is_reenabled(self):
        exits = self.start_fixture("failure")
        self.wait_until(lambda: self.window.worker is None)
        self.assertIn("Simulated camera read failure", self.window.status.text())
        self.assertTrue(self.window._error)
        self.assertTrue(self.window.start_button.isEnabled())
        self.assertEqual(exits, [(0, QProcess.ExitStatus.NormalExit)])


if __name__ == "__main__":
    unittest.main()
