from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from lib.config import load_config
from lib.uvr5_runner import run_uvr_for_song, save_uvr_result
from lib.worktree import iter_song_dirs


def has_ok_uvr5_result(song_dir: Path) -> bool:
    result_path = song_dir / "process" / "uvr5_result.json"
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
    parser.add_argument("--model", type=str, default=None)
    parser.add_argument("--device", choices=["cpu", "cuda"], default=None)
    parser.add_argument("--single-stem", type=str, default=None)
    parser.add_argument("--output-format", type=str, default=None)
    parser.add_argument("--force-uvr5", action="store_true")
    args = parser.parse_args()

    config = load_config(args.config)
    runner_command = args.runner_command or (
        [args.runner_exe] if args.runner_exe else config.uvr5.runner_command
    )
    device = args.device or config.uvr5.device
    model = args.model or config.uvr5.model
    single_stem = args.single_stem or config.uvr5.single_stem
    output_format = args.output_format or config.uvr5.output_format

    if not runner_command:
        raise SystemExit("[ERROR] UVR5 runner_command is not configured")

    for batch_dir, song_dir in iter_song_dirs(config.paths.work_root, args.batch):
        if has_ok_uvr5_result(song_dir) and not args.force_uvr5:
            print(f"[SKIP] {batch_dir.name}/{song_dir.name} | existing uvr5_result.json status=ok")
            continue

        print(f"[RUN] {batch_dir.name}/{song_dir.name}")

        result = run_uvr_for_song(
            song_dir,
            runner_command=runner_command,
            device=device,
            model_file_dir=config.uvr5.model_file_dir,
            model_name=model,
            single_stem=single_stem,
            output_format=output_format,
            extra_args=config.uvr5.extra_args,
            audio_exts=config.extensions.uvr5_audio,
            ffmpeg_bin_dir=config.tools.ffmpeg_bin_dir,
        )

        out_json = song_dir / "process" / "uvr5_result.json"
        save_uvr_result(result, out_json)

        print(
            f"[{result.status.upper()}] "
            f"{batch_dir.name}/{song_dir.name} | "
            f"vocals={result.vocals_path}"
        )


if __name__ == "__main__":
    main()
