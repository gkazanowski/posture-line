"""Supervise camera processing without blocking the GUI on native camera calls."""
import base64
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import cv2
import numpy as np
from PySide6.QtCore import QObject, QProcess, QTimer, Signal


class CameraWorker(QObject):
    status = Signal(str)
    failed = Signal(str)
    finished = Signal()
    STOP_GRACE_MS = 1000
    KILL_GRACE_MS = 500

    def __init__(self, camera_index: int, model_path: Path):
        super().__init__()
        self.camera_index = camera_index
        self.model_path = model_path
        self._latest = None
        self._buffer = bytearray()
        self._stopping = False
        self._finished = False
        self._reported_error = False
        self._stderr = ""
        self.process = QProcess(self)
        self.process.readyReadStandardOutput.connect(self._read_output)
        self.process.readyReadStandardError.connect(self._read_error_output)
        self.process.finished.connect(self._process_finished)
        self.process.errorOccurred.connect(self._process_error)
        self.process.started.connect(self._started)
        self._terminate_timer = QTimer(self)
        self._terminate_timer.setSingleShot(True)
        self._terminate_timer.timeout.connect(self._terminate)
        self._kill_timer = QTimer(self)
        self._kill_timer.setSingleShot(True)
        self._kill_timer.timeout.connect(self.process.kill)

    def _arguments(self):
        return ["-u", "-m", "posture_line.camera_process", "--camera", str(self.camera_index),
                "--model", str(self.model_path.resolve())]

    def start(self):
        self.status.emit("Preparing camera process…")
        self.process.start(sys.executable, self._arguments())

    def take_latest(self):
        latest, self._latest = self._latest, None
        return latest

    def requestInterruption(self):
        if self._stopping or self._finished:
            return
        self._stopping = True
        self._latest = None
        if self.process.state() == QProcess.ProcessState.Running:
            self.process.write(b"stop\n")
        self._terminate_timer.start(self.STOP_GRACE_MS)

    def _started(self):
        if self._stopping:
            self.process.write(b"stop\n")

    def _terminate(self):
        if self.process.state() != QProcess.ProcessState.NotRunning:
            self.process.terminate()
            self._kill_timer.start(self.KILL_GRACE_MS)

    def _read_error_output(self):
        self._stderr = (self._stderr + bytes(self.process.readAllStandardError()).decode(
            "utf-8", errors="replace"))[-4000:]

    def _read_output(self):
        self._buffer.extend(bytes(self.process.readAllStandardOutput()))
        # Only decode the newest frame if several arrive before the GUI is ready.
        newest = None
        while b"\n" in self._buffer:
            line, _, rest = self._buffer.partition(b"\n")
            self._buffer = bytearray(rest)
            if self._stopping:
                continue
            try:
                message = json.loads(line)
                if message["type"] == "frame":
                    newest = message
                elif message["type"] == "status":
                    self.status.emit(message["message"])
                elif message["type"] == "error":
                    self._reported_error = True
                    self.failed.emit(message["message"])
            except (ValueError, KeyError, TypeError) as error:
                self._protocol_error(error)
                return
        if newest is not None and not self._stopping:
            try:
                data = np.frombuffer(base64.b64decode(newest["image"], validate=True), dtype=np.uint8)
                frame = cv2.imdecode(data, cv2.IMREAD_COLOR)
                if frame is None:
                    raise ValueError("Invalid preview image")
                landmarks = [SimpleNamespace(**point) for point in newest["landmarks"]]
                self._latest = frame, landmarks
            except (ValueError, KeyError, TypeError, cv2.error) as error:
                self._protocol_error(error)

    def _protocol_error(self, error):
        self._reported_error = True
        self.failed.emit(f"Camera process communication failed: {error}")
        self.requestInterruption()

    def _process_error(self, error):
        if error == QProcess.ProcessError.FailedToStart:
            self._reported_error = True
            self.failed.emit(f"Cannot start camera process: {self.process.errorString()}")
            self._finish()

    def _process_finished(self, exit_code, exit_status):
        self._read_output()
        self._read_error_output()
        if not self._stopping and not self._reported_error and (
            exit_code != 0 or exit_status == QProcess.ExitStatus.CrashExit
        ):
            self.failed.emit(f"Camera process exited unexpectedly: {self._stderr.strip() or exit_code}")
        self._finish()

    def _finish(self):
        if self._finished:
            return
        self._finished = True
        self._terminate_timer.stop()
        self._kill_timer.stop()
        self._latest = None
        self._buffer.clear()
        self.finished.emit()
