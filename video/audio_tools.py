from __future__ import annotations

import subprocess
import wave
from pathlib import Path
from typing import Any

import numpy as np


def _resolve_ffmpeg_executable() -> str | None:
    # Prefer system ffmpeg if available.
    try:
        check = subprocess.run(
            ["ffmpeg", "-version"],
            check=False,
            capture_output=True,
            text=True,
        )
        if check.returncode == 0:
            return "ffmpeg"
    except FileNotFoundError:
        pass

    # Fallback to bundled binary from imageio-ffmpeg.
    try:
        from imageio_ffmpeg import get_ffmpeg_exe  # type: ignore

        exe = get_ffmpeg_exe()
        return str(exe) if exe else None
    except Exception:
        return None


def extract_audio_wav(video_path: str | Path, wav_out_path: str | Path) -> bool:
    video = str(Path(video_path))
    wav_out = str(Path(wav_out_path))
    ffmpeg_exe = _resolve_ffmpeg_executable()
    if not ffmpeg_exe:
        return False
    cmd = [
        ffmpeg_exe,
        "-y",
        "-i",
        video,
        "-ac",
        "1",
        "-ar",
        "44100",
        wav_out,
    ]
    try:
        result = subprocess.run(cmd, check=False, capture_output=True, text=True)
    except FileNotFoundError:
        return False
    return result.returncode == 0


def _load_wav_mono(wav_path: str | Path) -> tuple[int, np.ndarray]:
    path = Path(wav_path)

    try:
        from scipy.io import wavfile  # type: ignore

        sample_rate, data = wavfile.read(str(path))
        arr = np.asarray(data)
        if arr.ndim > 1:
            arr = arr.mean(axis=1)
        if np.issubdtype(arr.dtype, np.integer):
            info = np.iinfo(arr.dtype)
            max_abs = float(max(abs(info.min), abs(info.max))) or 1.0
            arr = arr.astype(np.float32) / max_abs
        else:
            arr = arr.astype(np.float32)
            peak = float(np.max(np.abs(arr))) if arr.size else 1.0
            if peak > 0:
                arr = arr / peak
        return int(sample_rate), arr
    except Exception:
        with wave.open(str(path), "rb") as wav:
            sample_rate = wav.getframerate()
            channels = wav.getnchannels()
            sample_width = wav.getsampwidth()
            frame_count = wav.getnframes()
            raw = wav.readframes(frame_count)

        if sample_width == 1:
            arr = np.frombuffer(raw, dtype=np.uint8).astype(np.float32)
            arr = (arr - 128.0) / 128.0
        elif sample_width == 2:
            arr = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
        elif sample_width == 4:
            arr = np.frombuffer(raw, dtype=np.int32).astype(np.float32) / 2147483648.0
        else:
            raise RuntimeError("Unsupported WAV sample width for detection.")

        if channels > 1:
            arr = arr.reshape(-1, channels).mean(axis=1)
        return int(sample_rate), arr


def _moving_average(values: np.ndarray, window: int) -> np.ndarray:
    if window <= 1:
        return values
    kernel = np.ones(window, dtype=np.float32) / float(window)
    return np.convolve(values, kernel, mode="same")


def detect_catch_candidates_from_audio(
    wav_path: str | Path,
    max_reps: int = 12,
    min_spacing_seconds: float = 1.5,
) -> dict[str, Any]:
    sample_rate, signal = _load_wav_mono(wav_path)
    if signal.size == 0:
        raise RuntimeError("Audio track is empty; cannot auto-detect catches.")

    envelope_window = max(1, int(sample_rate * 0.010))
    envelope = _moving_average(np.abs(signal), envelope_window)
    baseline = float(np.median(envelope)) if envelope.size else 0.0

    # Peak sampling spacing for raw candidate extraction, then a secondary spacing
    # pass in seconds for cleaner catch events across reps.
    raw_peak_spacing = max(1, int(sample_rate * 0.120))
    peaks: np.ndarray
    prominences: np.ndarray
    try:
        from scipy.signal import find_peaks  # type: ignore

        min_height = baseline + float(np.std(envelope)) * 1.0
        peaks, props = find_peaks(envelope, distance=raw_peak_spacing, height=min_height)
        prominences = np.asarray(props.get("peak_heights", []), dtype=np.float64)
    except Exception:
        min_height = baseline + float(np.std(envelope)) * 1.2
        candidates: list[int] = []
        last = -raw_peak_spacing
        for idx in range(1, envelope.size - 1):
            if envelope[idx] <= min_height:
                continue
            if envelope[idx] >= envelope[idx - 1] and envelope[idx] >= envelope[idx + 1]:
                if idx - last >= raw_peak_spacing:
                    candidates.append(idx)
                    last = idx
                elif envelope[idx] > envelope[last]:
                    candidates[-1] = idx
                    last = idx
        peaks = np.asarray(candidates, dtype=np.int64)
        prominences = envelope[peaks] if peaks.size else np.asarray([], dtype=np.float64)

    if peaks.size == 0:
        return {"candidates": []}

    max_prom = float(np.max(prominences)) if prominences.size else 0.0
    if max_prom <= 0:
        max_prom = 1.0

    raw_candidates: list[dict[str, float]] = []
    for idx, prom in zip(peaks.tolist(), prominences.tolist()):
        t = float(idx) / float(sample_rate)
        conf = float(max(0.0, min(1.0, float(prom) / max_prom)))
        raw_candidates.append({"time": t, "confidence": conf, "strength": float(prom)})

    raw_candidates.sort(key=lambda c: c["time"])

    # De-dup close catches: keep higher confidence if within min spacing.
    min_spacing = max(0.1, float(min_spacing_seconds))
    deduped: list[dict[str, float]] = []
    for cand in raw_candidates:
        if not deduped:
            deduped.append(cand)
            continue
        last = deduped[-1]
        if cand["time"] - last["time"] < min_spacing:
            if cand["confidence"] > last["confidence"]:
                deduped[-1] = cand
        else:
            deduped.append(cand)

    selected = deduped[: max(1, int(max_reps))]
    return {"candidates": selected}


def detect_catch_time_from_audio(wav_path: str | Path) -> dict[str, Any]:
    result = detect_catch_candidates_from_audio(wav_path, max_reps=10, min_spacing_seconds=0.12)
    candidates = result.get("candidates", [])
    if not candidates:
        raise RuntimeError("No catch candidate found in audio.")
    strongest = max(candidates, key=lambda c: float(c.get("confidence", 0.0)))
    top_times = [float(c.get("time", 0.0)) for c in sorted(candidates, key=lambda c: float(c.get("confidence", 0.0)), reverse=True)[:5]]
    return {
        "catch_time": float(strongest.get("time", 0.0)),
        "confidence": float(strongest.get("confidence", 0.0)),
        "candidates": top_times,
    }
