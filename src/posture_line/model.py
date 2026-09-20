"""Download the same Lite model used by the HTML prototype."""
from pathlib import Path
from urllib.request import urlopen

MODEL_URL = "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/1/pose_landmarker_lite.task"


def ensure_model(path: Path, cancelled=lambda: False):
    if path.is_file() and path.stat().st_size > 0:
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".part")
    try:
        with urlopen(MODEL_URL, timeout=15) as source, temporary.open("wb") as target:
            while True:
                if cancelled():
                    raise InterruptedError("Download cancelled")
                chunk = source.read(256 * 1024)
                if not chunk:
                    break
                target.write(chunk)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)
    return path
