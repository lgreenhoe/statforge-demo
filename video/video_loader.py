from __future__ import annotations

import importlib.util
import warnings
from pathlib import Path
from typing import Generator

import cv2
import numpy as np

SUPPORTED_EXTENSIONS = {".mov", ".mp4", ".m4v"}


def _ensure_supported_extension(filepath: str | Path) -> Path:
    path = Path(filepath)
    ext = path.suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise ValueError(
            f"Unsupported video format '{ext}'. Supported: {', '.join(sorted(SUPPORTED_EXTENSIONS))}"
        )
    return path


def _warn_if_ffmpeg_missing() -> None:
    ffmpeg_python_installed = importlib.util.find_spec("ffmpeg") is not None
    build_info = cv2.getBuildInformation()
    ffmpeg_enabled = "FFMPEG:                      YES" in build_info or "FFMPEG: YES" in build_info

    if not ffmpeg_python_installed:
        warnings.warn(
            "ffmpeg-python not installed. Install with: pip install ffmpeg-python",
            RuntimeWarning,
            stacklevel=2,
        )
    if not ffmpeg_enabled:
        warnings.warn(
            "OpenCV build may lack FFmpeg support. Some .mov/.m4v files may not decode.",
            RuntimeWarning,
            stacklevel=2,
        )


def _open_capture(filepath: str | Path) -> cv2.VideoCapture:
    path = _ensure_supported_extension(filepath)
    _warn_if_ffmpeg_missing()

    cap = cv2.VideoCapture(str(path), cv2.CAP_FFMPEG)
    if not cap.isOpened():
        # Fallback to default backend in case FFmpeg backend is unavailable.
        cap.release()
        cap = cv2.VideoCapture(str(path))

    if not cap.isOpened():
        raise RuntimeError(
            f"Unable to open video file: {path}. Codec/backend may be unsupported on this system."
        )

    try:
        backend = cap.getBackendName()
    except Exception:
        backend = "UNKNOWN"

    if backend.upper() != "FFMPEG":
        warnings.warn(
            f"Video opened with backend '{backend}', not FFmpeg. Decoding compatibility may vary.",
            RuntimeWarning,
            stacklevel=2,
        )
    return cap


def load_video_metadata(filepath: str | Path) -> dict[str, float | int]:
    cap = _open_capture(filepath)
    try:
        fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
        frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
        duration = (frame_count / fps) if fps > 0 else 0.0
        return {
            "fps": fps,
            "frame_count": frame_count,
            "duration": duration,
            "width": width,
            "height": height,
        }
    finally:
        cap.release()


def get_frame_at_time(filepath: str | Path, time_seconds: float) -> np.ndarray:
    if time_seconds < 0:
        raise ValueError("time_seconds must be >= 0")

    cap = _open_capture(filepath)
    try:
        cap.set(cv2.CAP_PROP_POS_MSEC, float(time_seconds) * 1000.0)
        ok, frame = cap.read()
        if not ok or frame is None:
            raise RuntimeError(
                f"Unable to decode frame at {time_seconds:.3f}s. Time may exceed duration or codec failed."
            )
        return frame
    finally:
        cap.release()


def extract_all_frames_generator(filepath: str | Path) -> Generator[np.ndarray, None, None]:
    cap = _open_capture(filepath)
    try:
        while True:
            ok, frame = cap.read()
            if not ok or frame is None:
                break
            yield frame
    finally:
        cap.release()
