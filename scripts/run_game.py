from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from lib.config import load_config
from lib.game_runner import run_game_for_song, save_game_result
from lib.worktree import iter_song_dirs


def has_ok_game_result(song_dir: Path) -> bool:
    result_path = song_dir / "process" / "game_result.json"
    if not result_path.exists():
        return False

    try:
        data = json.loads(result_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False

    return data.get("status") == "ok"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch", type=str, default=None)
    parser.add_argument("--config", type=str, default=None)
    parser.add_argument("--runner-exe", type=str, default=None)
    parser.add_argument("--runner-command", nargs="+", default=None)
    parser.add_argument("--model-path", type=str, default=None)
    parser.add_argument("--force-game", action="store_true")
    args = parser.parse_args()

    config = load_config(args.config)
    runner_command = args.runner_command or (
        [args.runner_exe] if args.runner_exe else config.game.runner_command
    )
    model_path = args.model_path or config.game.model_path

    if not runner_command:
        raise SystemExit("[ERROR] GAME runner_command is not configured")

    for batch_dir, song_dir in iter_song_dirs(config.paths.work_root, args.batch):
        if has_ok_game_result(song_dir) and not args.force_game:
            print(f"[SKIP] {batch_dir.name}/{song_dir.name} | existing game_result.json status=ok")
            continue

        print(f"[RUN] {batch_dir.name}/{song_dir.name}")

        result = run_game_for_song(
            song_dir,
            runner_command=runner_command,
            repo_root=config.game.repo_root,
            model_path=model_path,
            language=config.game.language,
            seg_threshold=config.game.seg_threshold,
            est_threshold=config.game.est_threshold,
            batch_size=config.game.batch_size,
            num_workers=config.game.num_workers,
            precision=config.game.precision,
            audio_exts=config.extensions.game_audio,
            midi_exts=config.extensions.game_midi,
        )

        out_json = song_dir / "process" / "game_result.json"
        save_game_result(result, out_json)

        print(
            f"[{result.status.upper()}] "
            f"{batch_dir.name}/{song_dir.name} | "
            f"midi={result.midi_path}"
        )


if __name__ == "__main__":
    main()
