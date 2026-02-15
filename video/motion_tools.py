from __future__ import annotations

from pathlib import Path
from typing import Any

import cv2
import numpy as np


ROI_PRESETS: dict[str, tuple[float, float, float, float]] = {
    "Auto": (0.20, 0.35, 0.80, 0.95),
    "Lower Middle": (0.20, 0.35, 0.80, 0.95),
    "Lower Left": (0.00, 0.35, 0.60, 0.95),
    "Lower Right": (0.40, 0.35, 1.00, 0.95),
}


def _resolve_roi(
    frame_w: int,
    frame_h: int,
    roi: tuple[float, float, float, float] | str | None,
) -> tuple[int, int, int, int]:
    if roi is None:
        norm = ROI_PRESETS["Auto"]
    elif isinstance(roi, str):
        norm = ROI_PRESETS.get(roi, ROI_PRESETS["Auto"])
    else:
        norm = roi

    x1 = max(0, min(frame_w - 1, int(frame_w * norm[0])))
    y1 = max(0, min(frame_h - 1, int(frame_h * norm[1])))
    x2 = max(x1 + 1, min(frame_w, int(frame_w * norm[2])))
    y2 = max(y1 + 1, min(frame_h, int(frame_h * norm[3])))
    return x1, y1, x2, y2


def detect_release_time_by_motion(
    video_path: str | Path,
    catch_time: float,
    roi: tuple[float, float, float, float] | str | None = None,
    release_window_sec: float = 1.2,
) -> dict[str, Any]:
    path = str(Path(video_path))
    cap = cv2.VideoCapture(path, cv2.CAP_FFMPEG)
    if not cap.isOpened():
        cap.release()
        cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        raise RuntimeError("Unable to open video for release detection.")

    try:
        fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
        if fps <= 0:
            fps = 30.0
        frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        duration = (frame_count / fps) if frame_count > 0 else (catch_time + release_window_sec + 0.5)

        start = max(0.0, float(catch_time) + 0.05)
        end = min(duration, float(catch_time) + max(0.1, float(release_window_sec)))
        if end <= start:
            raise RuntimeError("Invalid release detection window.")

        cap.set(cv2.CAP_PROP_POS_MSEC, start * 1000.0)
        ok, prev = cap.read()
        if not ok or prev is None:
            raise RuntimeError("Unable to read starting frame for motion detection.")

        prev_gray = cv2.cvtColor(prev, cv2.COLOR_BGR2GRAY)
        frame_h, frame_w = prev_gray.shape[:2]
        x1, y1, x2, y2 = _resolve_roi(frame_w, frame_h, roi)
        prev_roi = prev_gray[y1:y2, x1:x2]

        scores: list[float] = []
        times: list[float] = []
        idx = 1
        frame_step = 2 if fps > 50 else 1
        sample_interval = frame_step / fps
        current_time = start

        while current_time <= end:
            ok, frame = cap.read()
            if not ok or frame is None:
                break
            current_time = start + idx * (1.0 / fps)
            idx += 1
            if (idx % frame_step) != 0:
                continue

            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            roi_frame = gray[y1:y2, x1:x2]
            diff = cv2.absdiff(roi_frame, prev_roi)
            score = float(np.sum(diff))
            scores.append(score)
            times.append(current_time)
            prev_roi = roi_frame

        if not scores:
            raise RuntimeError("No motion samples were produced in detection window.")

        scores_arr = np.asarray(scores, dtype=np.float64)
        times_arr = np.asarray(times, dtype=np.float64)
        top_idx = int(np.argmax(scores_arr))
        release_time = float(times_arr[top_idx])

        median_score = float(np.median(scores_arr)) + 1e-6
        max_score = float(scores_arr[top_idx])
        confidence = max_score / (max_score + median_score)

        order = np.argsort(scores_arr)[::-1][:5]
        candidates = [float(times_arr[i]) for i in order]
        return {
            "release_time": release_time,
            "confidence": float(max(0.0, min(1.0, confidence))),
            "candidates": candidates,
            "sample_interval": sample_interval,
        }
    finally:
        cap.release()
