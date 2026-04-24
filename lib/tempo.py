from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional

import librosa
import numpy as np


@dataclass
class TempoResult:
    estimated_bpm: float
    rounded_bpm: int
    candidates: list[float]
    confidence: float
    beat_count: int
    duration_sec: float
    method: str
    notes: list[str]
    manual_override: Optional[float] = None


def normalize_bpm(bpm: float, low: float = 45.0, high: float = 140.0) -> float:
    if bpm <= 0:
        return bpm
    while bpm < low:
        bpm *= 2
    while bpm > high:
        bpm /= 2
    return bpm


def compute_confidence(beat_times: np.ndarray) -> float:
    if len(beat_times) < 8:
        return 0.2

    intervals = np.diff(beat_times)
    mean = float(np.mean(intervals))
    std = float(np.std(intervals))

    if mean <= 1e-6:
        return 0.0

    cv = std / mean
    return round(max(0.0, 1.0 - min(cv, 1.0)), 3)


def estimate_tempo(
    audio_path: Path,
    sr: int = 22050,
    bpm_low: float = 45.0,
    bpm_high: float = 140.0,
) -> TempoResult:
    y, sr = librosa.load(audio_path, sr=sr, mono=True)
    duration = librosa.get_duration(y=y, sr=sr)

    notes: list[str] = []

    onset_env = librosa.onset.onset_strength(y=y, sr=sr)

    raw_tempo = librosa.feature.tempo(
        onset_envelope=onset_env,
        sr=sr,
        aggregate=np.median,
    )
    raw_tempo = float(np.asarray(raw_tempo).squeeze())

    tempo_bt, beat_frames = librosa.beat.beat_track(
        onset_envelope=onset_env,
        sr=sr,
    )
    beat_times = librosa.frames_to_time(beat_frames, sr=sr)

    tempo_bt = np.asarray(tempo_bt).squeeze()

    if np.size(tempo_bt) > 0 and float(tempo_bt) > 0:
        bpm = float(tempo_bt)
    else:
        bpm = raw_tempo
        notes.append("fallback_to_global_tempo")

    bpm = normalize_bpm(bpm, low=bpm_low, high=bpm_high)

    candidates = [
        round(bpm, 3),
        round(bpm / 2, 3),
        round(bpm * 2, 3),
    ]

    confidence = compute_confidence(beat_times)

    if len(beat_times) < 16:
        notes.append("few_beats")

    if duration < 30:
        notes.append("short_audio")

    return TempoResult(
        estimated_bpm=round(bpm, 3),
        rounded_bpm=round(bpm),
        candidates=candidates,
        confidence=confidence,
        beat_count=int(len(beat_times)),
        duration_sec=round(duration, 3),
        method="librosa",
        notes=notes,
    )

def save_result(result: TempoResult, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(asdict(result), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
