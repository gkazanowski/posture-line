# Posture Line

A Python desktop starting point based on the original HTML posture analysis prototype.

## Features

- Camera preview with start and stop controls.
- Anatomical left or right side selection, without mirroring.
- Single-person detection using MediaPipe Pose Landmarker Lite.
- A line connecting wrist, elbow, shoulder, hip, knee, and ankle.
- Elbow and knee angles, torso tilt, and detection status.
- Automatic model download on first use.
- Measurement clearing when tracking is lost and camera cleanup when stopped.

**Angle calculations intentionally retain the HTML prototype's behavior.** They use normalized 2D coordinates without aspect ratio correction, calibration, or smoothing. Results can be distorted for non-square images. Further work on angles belongs in `geometry.py`.

## Installation on Windows

Use 64-bit Python 3.10–3.12. The project has been tested with Python 3.12.
Run these commands from the project directory in PowerShell:

```powershell
py -3.12 -m venv .venv
.venv/Scripts/python.exe -m pip install -c requirements-lock.txt -e .
.venv/Scripts/python.exe -m posture_line
```

If the environment is already installed, run only the last command or double-click `Run.cmd`.
Click **Start camera**. The first analysis run downloads the model from Google; later runs reuse the file in `models/`. The application code does not upload camera frames. Inference runs on the CPU in a separate process. The preview is compressed for local transfer; inference uses the original frames.

## PyCharm

1. Open the `posture-line` project directory.
2. Select the existing interpreter at `.venv/Scripts/python.exe` in **Settings → Project → Python Interpreter**. Re-select it if the project was moved or renamed.
3. Install the project using the command above if needed.
4. Create a Python run configuration with **Module name** `posture_line` and **Working directory** set to the project directory. A shared **Posture Line** configuration is also included.
5. Use **Run** or **Debug** to launch the application.

`main.py` is the untouched sample file created by PyCharm; use the **Posture Line** configuration to launch this application.

## Camera and model options

```powershell
.venv/Scripts/python.exe -m posture_line --camera 1
.venv/Scripts/python.exe -m posture_line --model C:/models/pose_landmarker_lite.task
```

Stopping or closing the window first requests a graceful shutdown. If the camera process does not exit within one second, the application requests termination, then force-kills it after another 0.5 seconds if necessary. These timers run without blocking the GUI. This also handles native camera calls that never return. Normal shutdown releases the camera explicitly; forced shutdown relies on operating-system process cleanup. If the camera cannot start, close other applications using it, check Windows camera permissions, and try another camera index.

## Project structure

- `src/posture_line/app.py`: PySide6 interface and OpenCV drawing.
- `src/posture_line/worker.py`: asynchronous process supervision, preview transfer, and bounded shutdown.
- `src/posture_line/camera_process.py`: camera capture and MediaPipe inference in an isolated process.
- `src/posture_line/geometry.py`: landmark selection and preliminary angle calculations.
- `src/posture_line/model.py`: model download.
- `tests/`: geometry and application lifecycle tests.
- `AGENTS.md`: project conventions, including the English-only project language policy.

## Validation

```powershell
.venv/Scripts/python.exe -m unittest discover -s tests -v
```

Tests cover reference angles, selected-side visibility, stale measurement clearing, and camera release after an inference failure. Subprocess regression tests cover a blocked camera read, blocked camera startup, immediate closure, GUI responsiveness, and restarting after a forced stop. These tests use simulated hardware inside actual child processes. Physical camera operation and measurements on a person are not covered by the automated tests.

`requirements-lock.txt` records the library versions used for validation on Windows with Python 3.12. Install with `python -m pip install -c requirements-lock.txt -e .` to reuse these versions.

API reference: [MediaPipe Pose Landmarker for Python](https://developers.google.com/edge/mediapipe/solutions/vision/pose_landmarker/python).
