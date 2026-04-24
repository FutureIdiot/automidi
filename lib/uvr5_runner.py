from __future__ import annotations

import json
import os
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional


@dataclass
class UVRResult:
    status: str
    input_audio: str
    vocals_path: Optional[str]
    instrumental_path: Optional[str]
    model: str
    runner: str
    notes: list[str]


def find_audio_in_input(song_dir: Path, audio_exts: tuple[str, ...]) -> Optional[Path]:
    input_dir = song_dir / "input"
    if not input_dir.exists():
        return None

    for ext in audio_exts:
        files = sorted(input_dir.glob(f"*{ext}"))
        if files:
            return files[0]
    return None


def save_uvr_result(result: UVRResult, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(asdict(result), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def find_vocals_file(uvr_out_dir: Path) -> Optional[Path]:
    if not uvr_out_dir.exists():
        return None

    candidates = []
    for f in uvr_out_dir.iterdir():
        if not f.is_file():
            continue
        name = f.name.lower()
        if "vocal" in name:
            candidates.append(f)

    if not candidates:
        return None

    return sorted(candidates)[0]


def find_instrumental_file(
    uvr_out_dir: Path,
    audio_exts: tuple[str, ...],
) -> Optional[Path]:
    if not uvr_out_dir.exists():
        return None

    preferred = []
    fallback = []
    allowed_exts = set(audio_exts)

    for f in uvr_out_dir.iterdir():
        if not f.is_file():
            continue
        name = f.name.lower()
        if f.suffix.lower() not in allowed_exts or "vocal" in name:
            continue
        if "instrument" in name:
            preferred.append(f)
        else:
            fallback.append(f)

    if preferred:
        return sorted(preferred)[0]
    if fallback:
        return sorted(fallback)[0]
    return None


def run_uvr_for_song(
    song_dir: Path,
    *,
    runner_command: list[str],
    device: str,
    model_file_dir: Path,
    model_name: str,
    single_stem: str,
    output_format: str,
    extra_args: list[str],
    audio_exts: tuple[str, ...],
    ffmpeg_bin_dir: Optional[Path] = None,
) -> UVRResult:
    runner = " ".join(runner_command)
    audio_path = find_audio_in_input(song_dir, audio_exts)
    if audio_path is None:
        return UVRResult(
            status="skip",
            input_audio="",
            vocals_path=None,
            instrumental_path=None,
            model=model_name,
            runner=runner,
            notes=["no_audio_found"],
        )

    uvr_out_dir = song_dir / "process" / "uvr5"
    uvr_out_dir.mkdir(parents=True, exist_ok=True)
    model_file_dir.mkdir(parents=True, exist_ok=True)

    cmd = [
        *runner_command,
        str(audio_path),
        "-m",
        model_name,
        "--model_file_dir",
        str(model_file_dir),
        "--single_stem",
        single_stem,
        "--output_format",
        output_format,
        "--output_dir",
        str(uvr_out_dir),
        *extra_args,
    ]
    if device == "cuda":
        cmd.append("--use_autocast")

    try:
        env = os.environ.copy()
        if ffmpeg_bin_dir and ffmpeg_bin_dir.exists():
            env["PATH"] = str(ffmpeg_bin_dir) + os.pathsep + env.get("PATH", "")

        completed = subprocess.run(
            cmd,
            check=True,
            capture_output=True,
            text=True,
            env=env,
        )
    except subprocess.CalledProcessError as e:
        err_text = (e.stderr or "") + "\n" + (e.stdout or "")
        return UVRResult(
            status="error",
            input_audio=str(audio_path),
            vocals_path=None,
            instrumental_path=None,
            model=model_name,
            runner=runner,
            notes=[f"command_failed: {err_text[:1000].strip()}"],
        )
    except FileNotFoundError as e:
        return UVRResult(
            status="error",
            input_audio=str(audio_path),
            vocals_path=None,
            instrumental_path=None,
            model=model_name,
            runner=runner,
            notes=[f"runner_not_found: {e}"],
        )

    vocals = find_vocals_file(uvr_out_dir)
    instrumental = find_instrumental_file(uvr_out_dir, audio_exts)
    notes: list[str] = []

    if vocals is None:
        notes.append("vocals_file_not_found")
        status = "partial"
    else:
        status = "ok"

    stdout_preview = (completed.stdout or "").strip()
    if stdout_preview:
        notes.append(f"stdout: {stdout_preview[:300]}")

    return UVRResult(
        status=status,
        input_audio=str(audio_path),
        vocals_path=str(vocals) if vocals else None,
        instrumental_path=str(instrumental) if instrumental else None,
        model=model_name,
        runner=runner,
        notes=notes,
    )
