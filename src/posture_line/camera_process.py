"""Run native camera and inference calls in an independently stoppable process."""
import argparse
import base64
import json
import sys
import threading
import time
from pathlib import Path

import cv2
import mediapipe as mp

from .model import ensure_model


def send(message):
    print(json.dumps(message, separators=(",", ":")), flush=True)


def listen_for_stop(stopped):
    # EOF also requests shutdown when the parent closes its input channel.
    sys.stdin.readline()
    stopped.set()


def run_camera(camera_index, model_path, stopped, emit=send):
    capture = None
    phase = "Model download"
    try:
        emit({"type": "status", "message": "Preparing the model (first use requires internet access)…"})
        path = ensure_model(model_path, stopped.is_set)
        if stopped.is_set():
            return
        phase = "Model initialization"
        options = mp.tasks.vision.PoseLandmarkerOptions(
            base_options=mp.tasks.BaseOptions(model_asset_path=str(path)),
            running_mode=mp.tasks.vision.RunningMode.VIDEO,
            num_poses=1,
            min_pose_detection_confidence=0.55,
            min_tracking_confidence=0.55,
        )
        with mp.tasks.vision.PoseLandmarker.create_from_options(options) as detector:
            if stopped.is_set():
                return
            phase = "Camera startup"
            emit({"type": "status", "message": "Starting camera…"})
            capture = cv2.VideoCapture(camera_index)
            if not capture.isOpened():
                raise RuntimeError("Cannot open the camera. Check its index, permissions, and other applications.")
            capture.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
            capture.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
            phase = "Frame analysis"
            previous_ms = -1
            while not stopped.is_set():
                ok, frame = capture.read()
                if stopped.is_set():
                    break
                if not ok:
                    raise RuntimeError("Cannot read a frame from the camera.")
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                timestamp = max(previous_ms + 1, time.monotonic_ns() // 1_000_000)
                previous_ms = timestamp
                result = detector.detect_for_video(
                    mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb), timestamp
                )
                if stopped.is_set():
                    break
                landmarks = result.pose_landmarks[0] if result.pose_landmarks else []
                # Compression affects only the preview, never the input to inference.
                ok, encoded = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 90])
                if not ok:
                    raise RuntimeError("Cannot encode the preview frame.")
                emit({"type": "frame", "image": base64.b64encode(encoded).decode("ascii"),
                      "landmarks": [{"x": p.x, "y": p.y, "visibility": p.visibility} for p in landmarks]})
    except InterruptedError:
        pass
    except Exception as error:
        if not stopped.is_set():
            emit({"type": "error", "message": f"{phase}: {error}"})
    finally:
        if capture is not None:
            capture.release()


def main():
    parser = argparse.ArgumentParser(description="Posture Line camera subprocess")
    parser.add_argument("--camera", type=int, required=True)
    parser.add_argument("--model", type=Path, required=True)
    args = parser.parse_args()
    stopped = threading.Event()
    threading.Thread(target=listen_for_stop, args=(stopped,), daemon=True).start()
    run_camera(args.camera, args.model, stopped)


if __name__ == "__main__":
    main()
