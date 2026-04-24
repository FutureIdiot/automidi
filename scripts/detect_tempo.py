from pathlib import Path

import argparse
import json
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from lib.config import load_config
from lib.tempo import estimate_tempo, save_result
from lib.worktree import iter_song_dirs


def find_audio(song_dir: Path, audio_exts: tuple[str, ...]):
    input_dir = song_dir / "input"
    if not input_dir.exists():
        return None

    for ext in audio_exts:
        files = sorted(input_dir.glob(f"*{ext}"))
        if files:
            return files[0]
    return None


def has_tempo_result(song_dir: Path) -> bool:
    result_path = song_dir / "process" / "tempo.json"
    if not result_path.exists():
        return False

    try:
        data = json.loads(result_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False

    return data.get("estimated_bpm") is not None


def run(
    work_root: Path,
    batch_name: str | None = None,
    force_tempo: bool = False,
    sample_rate: int = 22050,
    bpm_low: float = 45.0,
    bpm_high: float = 140.0,
    audio_exts: tuple[str, ...] = (".wav", ".mp3"),
):
    for batch_dir, song_dir in iter_song_dirs(work_root, batch_name):
        if has_tempo_result(song_dir) and not force_tempo:
            print(f"[SKIP] {batch_dir.name}/{song_dir.name} | existing tempo.json")
            continue

        audio = find_audio(song_dir, audio_exts)
        if not audio:
            print(f"[SKIP] no audio: {batch_dir.name}/{song_dir.name}")
            continue

        try:
            result = estimate_tempo(
                audio,
                sr=sample_rate,
                bpm_low=bpm_low,
                bpm_high=bpm_high,
            )

            out_path = song_dir / "process" / "tempo.json"
            save_result(result, out_path)

            print(
                f"[OK] {batch_dir.name}/{song_dir.name} | "
                f"{result.estimated_bpm} BPM | conf={result.confidence}"
            )

        except Exception as e:
            print(f"[ERR] {batch_dir.name}/{song_dir.name}: {e}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch", type=str, default=None)
    parser.add_argument("--config", type=str, default=None)
    parser.add_argument("--force-tempo", action="store_true")
    args = parser.parse_args()

    config = load_config(args.config)
    run(
        config.paths.work_root,
        args.batch,
        args.force_tempo,
        config.tempo.sample_rate,
        config.tempo.bpm_low,
        config.tempo.bpm_high,
        config.extensions.tempo_audio,
    )
