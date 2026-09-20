import argparse
import sys
from pathlib import Path

import cv2
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QApplication, QButtonGroup, QHBoxLayout, QLabel, QMainWindow,
    QPushButton, QSizePolicy, QVBoxLayout, QWidget,
)

from .geometry import analyze
from .worker import CameraWorker

STYLE = """
QWidget { background: #08111e; color: #eaf1ff; font-size: 14px; }
QLabel#title { font-size: 30px; font-weight: bold; }
QLabel#preview { background: #050a12; border: 1px solid #293a54; border-radius: 12px; }
QPushButton { background: #24334c; border: none; border-radius: 8px; padding: 12px; }
QPushButton#start { background: #91a7ff; color: #0c1530; font-weight: bold; }
QPushButton:checked { background: #62e6c2; color: #08221d; }
QPushButton:disabled { background: #182238; color: #687589; }
QLabel#metric { background: #111b2b; padding: 14px; color: #ffc772; border-radius: 8px; }
"""


class MainWindow(QMainWindow):
    def __init__(self, camera_index, model_path):
        super().__init__()
        self.camera_index, self.model_path = camera_index, model_path
        self.worker = None
        self.side = "left"
        self._closing = False
        self._stopping = False
        self._error = False
        self._pixmap = None
        self.setWindowTitle("Posture Line — Live Analysis")
        self.resize(1180, 760)
        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(24, 24, 24, 24)
        title = QLabel("Posture Line")
        title.setObjectName("title")
        layout.addWidget(title)
        layout.addWidget(QLabel("Real-time body landmark analysis from your camera."))
        body = QHBoxLayout()
        layout.addLayout(body, 1)
        self.preview = QLabel("Ready to analyze\nStart the camera and keep your whole body in view.")
        self.preview.setObjectName("preview")
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setMinimumSize(320, 240)
        self.preview.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Expanding)
        body.addWidget(self.preview, 1)
        panel = QWidget()
        panel.setFixedWidth(288)
        controls = QVBoxLayout(panel)
        body.addWidget(panel)
        self.start_button = QPushButton("Start camera")
        self.start_button.setObjectName("start")
        self.stop_button = QPushButton("Stop")
        self.stop_button.setEnabled(False)
        self.start_button.clicked.connect(self.start_camera)
        self.stop_button.clicked.connect(self.stop_camera)
        controls.addWidget(self.start_button)
        controls.addWidget(self.stop_button)
        sides = QHBoxLayout()
        self.side_group = QButtonGroup(self)
        for side, text in (("left", "Left side"), ("right", "Right side")):
            button = QPushButton(text)
            button.setCheckable(True)
            button.setChecked(side == self.side)
            button.clicked.connect(lambda checked=False, selected=side: self.set_side(selected))
            self.side_group.addButton(button)
            sides.addWidget(button)
        controls.addLayout(sides)
        controls.addWidget(QLabel("DETECTION STATUS"))
        self.status = QLabel("The model will be downloaded on first use.")
        self.status.setWordWrap(True)
        self.status.setMinimumHeight(90)
        controls.addWidget(self.status)
        controls.addWidget(QLabel("MEASUREMENTS"))
        self.metrics = {}
        for key, text in (("elbow", "Elbow"), ("knee", "Knee"), ("torso", "Torso")):
            label = QLabel()
            label.setObjectName("metric")
            self.metrics[key] = (label, text)
            controls.addWidget(label)
        legend = QLabel("Line: wrist → elbow → shoulder → hip → knee → ankle.\n\nKeep the entire selected side of your body in view.\n\nAngles: preliminary calculations from the HTML prototype.")
        legend.setWordWrap(True)
        controls.addWidget(legend)
        controls.addStretch()
        self.set_metrics()
        self.timer = QTimer(self)
        self.timer.setInterval(33)
        self.timer.timeout.connect(self.refresh)

    def set_metrics(self, values=None):
        for key, (label, title) in self.metrics.items():
            value = f"{values[key]}°" if values else "—"
            label.setText(f"{title}: {value}")

    def set_side(self, side):
        self.side = side
        self.set_metrics()
        self._pixmap = None
        self.preview.setText("Waiting for the selected side…" if self.worker else "Ready to analyze")

    def start_camera(self):
        if self.worker is not None:
            return
        self._error = self._stopping = False
        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.worker = CameraWorker(self.camera_index, self.model_path)
        self.worker.status.connect(self.show_status)
        self.worker.failed.connect(self.show_error)
        self.worker.finished.connect(self.camera_finished)
        self.worker.start()
        self.timer.start()

    def show_status(self, message):
        if not self._stopping:
            self.status.setText(message)

    def show_error(self, message):
        self._error = True
        self.status.setText(message)

    def stop_camera(self):
        if self.worker:
            self._stopping = True
            self.timer.stop()
            self.worker.requestInterruption()
            self.stop_button.setEnabled(False)
            self.status.setText("Stopping camera…")
            self.set_metrics()

    def camera_finished(self):
        self.timer.stop()
        self.worker.deleteLater()
        self.worker = None
        self._pixmap = None
        self.preview.setText("Camera stopped")
        self.set_metrics()
        self.start_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        if not self._error:
            self.status.setText("Camera stopped.")
        if self._closing:
            self.close()

    def refresh(self):
        latest = self.worker.take_latest() if self.worker else None
        if latest is None:
            return
        frame, landmarks = latest
        result = analyze(landmarks, self.side)
        if result:
            chain, values = result
            height, width = frame.shape[:2]
            points = [(int(p.x * width), int(p.y * height)) for p in chain]
            for a, b in zip(points, points[1:]):
                cv2.line(frame, a, b, (194, 230, 98), 3, cv2.LINE_AA)
            for point in points:
                cv2.circle(frame, point, 4, (112, 189, 255), -1, cv2.LINE_AA)
            for index, key in ((1, "elbow"), (3, "torso"), (4, "knee")):
                x, y = points[index]
                text = str(values[key])
                x, y = max(0, min(x + 12, width - 65)), max(22, min(y, height - 8))
                cv2.putText(frame, text, (x, y), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 0, 0), 4, cv2.LINE_AA)
                cv2.putText(frame, text, (x, y), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (174, 223, 255), 2, cv2.LINE_AA)
            self.set_metrics(values)
            self.status.setText(f"Pose detected — analyzing the {self.side} side.")
        else:
            self.set_metrics()
            self.status.setText("Keep the entire selected side of your body in view." if landmarks else "Looking for a person in the frame…")
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        h, w = rgb.shape[:2]
        image = QImage(rgb.data, w, h, rgb.strides[0], QImage.Format.Format_RGB888).copy()
        self._pixmap = QPixmap.fromImage(image)
        self.update_preview()

    def update_preview(self):
        if self._pixmap is not None:
            self.preview.setPixmap(self._pixmap.scaled(
                self.preview.size(), Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            ))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.update_preview()

    def closeEvent(self, event):
        if self.worker is not None:
            self._closing = True
            self.stop_camera()
            event.ignore()
        else:
            event.accept()


def main():
    parser = argparse.ArgumentParser(description="Posture Line — Camera Analysis")
    parser.add_argument("--camera", type=int, default=0, help="Camera index (default: 0)")
    parser.add_argument("--model", type=Path, default=Path("models/pose_landmarker_lite.task"))
    args = parser.parse_args()
    app = QApplication(sys.argv[:1])
    app.setStyleSheet(STYLE)
    window = MainWindow(args.camera, args.model)
    window.show()
    sys.exit(app.exec())
