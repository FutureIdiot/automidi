from __future__ import annotations

import json
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional


@dataclass
class GameResult:
    status: str
    input_audio: Optional[str]
    tempo_used: Optional[float]
    midi_path: Optional[str]
    runner: str
    model_path: str
    output_dir: Optional[str]
    notes: list[str]


def find_uvr_vocals(song_dir: Path, audio_exts: tuple[str, ...]) -> Optional[Path]:
    uvr_dir = song_dir / "process" / "uvr5"
    if not uvr_dir.exists():
        return None

    candidates = []
    for f in uvr_dir.iterdir():
        if not f.is_file():
            continue
        name = f.name.lower()
        if "vocal" in name and f.suffix.lower() in set(audio_exts):
            candidates.append(f)

    if not candidates:
        return None

    return sorted(candidates)[0]


def load_tempo(song_dir: Path) -> Optional[float]:
    tempo_path = song_dir / "process" / "tempo.json"
    if not tempo_path.exists():
        return None

    data = json.loads(tempo_path.read_text(encoding="utf-8"))

    manual = data.get("manual_override")
    if manual is not None:
        return float(manual)

    estimated = data.get("estimated_bpm")
    if estimated is not None:
        return float(estimated)

    return None


def save_game_result(result: GameResult, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(asdict(result), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def find_generated_midi(output_dir: Path, midi_exts: tuple[str, ...]) -> Optional[Path]:
    if not output_dir.exists():
        return None

    for ext in midi_exts:
        midis = sorted(output_dir.rglob(f"*{ext}"))
        if midis:
            return midis[0]

    return None


def build_game_command(
    *,
    runner_command: list[str],
    input_audio: Path,
    output_dir: Path,
    model_path: Path,
    tempo: float,
    language: str,
    seg_threshold: float,
    est_threshold: float,
    batch_size: int,
    num_workers: int,
    precision: str,
) -> list[str]:
    cmd = [
        *runner_command,
        "extract",
        str(input_audio),
        "-m",
        str(model_path),
        "--output-dir",
        str(output_dir),
        "--output-formats",
        "mid",
        "--seg-threshold",
        str(seg_threshold),
        "--est-threshold",
        str(est_threshold),
        "--tempo",
        str(round(tempo, 3)),
        "--batch-size",
        str(batch_size),
        "--num-workers",
        str(num_workers),
        "--precision",
        precision,
    ]
    if language:
        cmd.extend(["--language", language])
    return cmd


def run_game_for_song(
    song_dir: Path,
    *,
    runner_command: list[str],
    repo_root: Path,
    model_path: str,
    language: str,
    seg_threshold: float,
    est_threshold: float,
    batch_size: int,
    num_workers: int,
    precision: str,
    audio_exts: tuple[str, ...],
    midi_exts: tuple[str, ...],
) -> GameResult:
    runner = " ".join(runner_command)
    input_audio = find_uvr_vocals(song_dir, audio_exts)
    if input_audio is None:
        return GameResult(
            status="error",
            input_audio=None,
            tempo_used=None,
            midi_path=None,
            runner=runner,
            model_path=model_path,
            output_dir=None,
            notes=["uvr_vocals_not_found"],
        )

    tempo = load_tempo(song_dir)
    if tempo is None:
        return GameResult(
            status="error",
            input_audio=str(input_audio),
            tempo_used=None,
            midi_path=None,
            runner=runner,
            model_path=model_path,
            output_dir=None,
            notes=["tempo_not_found"],
        )

    output_dir = song_dir / "output" / "game"
    output_dir.mkdir(parents=True, exist_ok=True)

    if not runner_command:
        return GameResult(
            status="error",
            input_audio=str(input_audio),
            tempo_used=tempo,
            midi_path=None,
            runner=runner,
            model_path=model_path,
            output_dir=str(output_dir),
            notes=["runner_command_not_configured"],
        )

    model = Path(model_path) if model_path else None
    if model is None:
        return GameResult(
            status="error",
            input_audio=str(input_audio),
            tempo_used=tempo,
            midi_path=None,
            runner=runner,
            model_path=model_path,
            output_dir=str(output_dir),
            notes=["model_path_not_configured"],
        )

    if not model.exists():
        return GameResult(
            status="error",
            input_audio=str(input_audio),
            tempo_used=tempo,
            midi_path=None,
            runner=runner,
            model_path=str(model),
            output_dir=str(output_dir),
            notes=["model_path_not_found"],
        )

    if not repo_root.exists():
        return GameResult(
            status="error",
            input_audio=str(input_audio),
            tempo_used=tempo,
            midi_path=None,
            runner=runner,
            model_path=str(model),
            output_dir=str(output_dir),
            notes=[f"repo_root_not_found: {repo_root}"],
        )

    cmd = build_game_command(
        runner_command=runner_command,
        input_audio=input_audio,
        output_dir=output_dir,
        model_path=model,
        tempo=tempo,
        language=language,
        seg_threshold=seg_threshold,
        est_threshold=est_threshold,
        batch_size=batch_size,
        num_workers=num_workers,
        precision=precision,
    )

    try:
        completed = subprocess.run(
            cmd,
            check=True,
            capture_output=True,
            text=True,
            cwd=repo_root,
        )
    except subprocess.CalledProcessError as e:
        err_text = (e.stderr or "") + "\n" + (e.stdout or "")
        return GameResult(
            status="error",
            input_audio=str(input_audio),
            tempo_used=tempo,
            midi_path=None,
            runner=runner,
            model_path=str(model),
            output_dir=str(output_dir),
            notes=[f"command_failed: {err_text[:1000].strip()}"],
        )
    except FileNotFoundError as e:
        return GameResult(
            status="error",
            input_audio=str(input_audio),
            tempo_used=tempo,
            midi_path=None,
            runner=runner,
            model_path=str(model),
            output_dir=str(output_dir),
            notes=[f"runner_not_found: {e}"],
        )

    midi_path = find_generated_midi(output_dir, midi_exts)

    notes: list[str] = []
    status = "ok"

    if midi_path is None:
        status = "partial"
        notes.append("midi_file_not_found")

    stdout_preview = (completed.stdout or "").strip()
    if stdout_preview:
        notes.append(f"stdout: {stdout_preview[:300]}")

    return GameResult(
        status=status,
        input_audio=str(input_audio),
        tempo_used=tempo,
        midi_path=str(midi_path) if midi_path else None,
        runner=runner,
        model_path=str(model),
        output_dir=str(output_dir),
        notes=notes,
    )
