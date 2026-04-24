from __future__ import annotations

import argparse
import json
import shutil
import sys
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from lib.config import load_config
from lib.game_runner import run_game_for_song, save_game_result
from lib.tempo import estimate_tempo, save_result as save_tempo_result
from lib.uvr5_runner import run_uvr_for_song, save_uvr_result
from scripts.detect_tempo import find_audio, has_tempo_result
from scripts.pair import build_worktree, clear_input_dir, has_existing_batch, scan_pairs
from scripts.run_game import has_ok_game_result
from scripts.run_uvr5 import has_ok_uvr5_result


def _base_dir_for(input_dir: Path) -> Path:
    if input_dir.parent.name == "inbox":
        return input_dir.parent.parent
    return input_dir.parent


def _song_dirs_from_created(created: list[dict[str, str]]) -> list[Path]:
    return [Path(item["song_root"]) for item in created]


def run_tempo_stage(
    song_dirs: list[Path],
    *,
    force: bool,
    sample_rate: int,
    bpm_low: float,
    bpm_high: float,
    audio_exts: tuple[str, ...],
) -> list[dict]:
    results = []

    for song_dir in song_dirs:
        if has_tempo_result(song_dir) and not force:
            result_path = song_dir / "process" / "tempo.json"
            results.append({
                "song_root": str(song_dir),
                "result_json": str(result_path),
                "status": "skip",
                "notes": ["existing_tempo_result"],
            })
            print(f"[TEMPO SKIP] {song_dir.name} | existing tempo.json")
            continue

        audio = find_audio(song_dir, audio_exts)
        if audio is None:
            results.append({
                "song_root": str(song_dir),
                "status": "skip",
                "notes": ["no_audio_found"],
            })
            print(f"[TEMPO SKIP] {song_dir.name} | no audio")
            continue

        try:
            result = estimate_tempo(
                audio,
                sr=sample_rate,
                bpm_low=bpm_low,
                bpm_high=bpm_high,
            )
            out_path = song_dir / "process" / "tempo.json"
            save_tempo_result(result, out_path)

            results.append({
                "song_root": str(song_dir),
                "status": "ok",
                "audio": str(audio),
                "tempo_json": str(out_path),
                "result": asdict(result),
            })
            print(
                f"[TEMPO OK] {song_dir.name} | "
                f"{result.estimated_bpm} BPM | conf={result.confidence}"
            )
        except Exception as e:
            results.append({
                "song_root": str(song_dir),
                "status": "error",
                "audio": str(audio),
                "notes": [str(e)],
            })
            print(f"[TEMPO ERR] {song_dir.name} | {e}")

    return results


def run_uvr5_stage(
    song_dirs: list[Path],
    *,
    runner_command: list[str],
    device: str,
    model_file_dir: Path,
    model_name: str,
    single_stem: str,
    output_format: str,
    extra_args: list[str],
    ffmpeg_bin_dir: Path,
    force: bool,
    audio_exts: tuple[str, ...],
) -> list[dict]:
    results = []

    for song_dir in song_dirs:
        if has_ok_uvr5_result(song_dir) and not force:
            result_path = song_dir / "process" / "uvr5_result.json"
            results.append({
                "song_root": str(song_dir),
                "result_json": str(result_path),
                "status": "skip",
                "notes": ["existing_uvr5_result_ok"],
                "result": None,
            })
            print(f"[UVR5 SKIP] {song_dir.name} | existing uvr5_result.json status=ok")
            continue

        result = run_uvr_for_song(
            song_dir,
            runner_command=runner_command,
            device=device,
            model_file_dir=model_file_dir,
            model_name=model_name,
            single_stem=single_stem,
            output_format=output_format,
            extra_args=extra_args,
            audio_exts=audio_exts,
            ffmpeg_bin_dir=ffmpeg_bin_dir,
        )
        out_path = song_dir / "process" / "uvr5_result.json"
        save_uvr_result(result, out_path)

        results.append({
            "song_root": str(song_dir),
            "result_json": str(out_path),
            "status": result.status,
            "result": asdict(result),
        })
        print(f"[UVR5 {result.status.upper()}] {song_dir.name} | vocals={result.vocals_path}")

    return results


def run_game_stage(
    song_dirs: list[Path],
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
    force: bool,
    audio_exts: tuple[str, ...],
    midi_exts: tuple[str, ...],
) -> list[dict]:
    results = []

    for song_dir in song_dirs:
        if has_ok_game_result(song_dir) and not force:
            result_path = song_dir / "process" / "game_result.json"
            results.append({
                "song_root": str(song_dir),
                "result_json": str(result_path),
                "status": "skip",
                "notes": ["existing_game_result_ok"],
                "result": None,
            })
            print(f"[GAME SKIP] {song_dir.name} | existing game_result.json status=ok")
            continue

        result = run_game_for_song(
            song_dir,
            runner_command=runner_command,
            repo_root=repo_root,
            model_path=model_path,
            language=language,
            seg_threshold=seg_threshold,
            est_threshold=est_threshold,
            batch_size=batch_size,
            num_workers=num_workers,
            precision=precision,
            audio_exts=audio_exts,
            midi_exts=midi_exts,
        )
        out_path = song_dir / "process" / "game_result.json"
        save_game_result(result, out_path)

        results.append({
            "song_root": str(song_dir),
            "result_json": str(out_path),
            "status": result.status,
            "result": asdict(result),
        })
        print(f"[GAME {result.status.upper()}] {song_dir.name} | midi={result.midi_path}")

    return results


def write_report(report: dict, log_root: Path, batch_name: str) -> Path:
    log_root.mkdir(parents=True, exist_ok=True)
    report_path = log_root / f"pipeline_report_{batch_name}.json"
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return report_path


def collect_batch_exports(
    song_dirs: list[Path],
    *,
    export_root: Path,
    batch_name: str,
) -> list[dict]:
    export_batch_dir = export_root / batch_name
    exported: list[dict] = []

    for song_dir in song_dirs:
        result_path = song_dir / "process" / "game_result.json"
        if not result_path.exists():
            continue

        try:
            data = json.loads(result_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue

        midi_path = data.get("midi_path")
        if not midi_path:
            continue

        src = Path(midi_path)
        if not src.exists() or not src.is_file():
            continue

        export_batch_dir.mkdir(parents=True, exist_ok=True)
        dst = export_batch_dir / f"{song_dir.name}{src.suffix.lower()}"
        shutil.copy2(src, dst)
        exported.append({
            "song_root": str(song_dir),
            "source_midi": str(src),
            "export_midi": str(dst),
        })

    return exported


def collect_failures(
    *,
    missing_audio: list,
    missing_lyric: list,
    duplicate_audio: list,
    duplicate_lyric: list,
    ignored_files: list,
    tempo_results: list[dict],
    uvr5_results: list[dict],
    game_results: list[dict],
    delete_source_requested: bool,
    input_cleaned: bool,
) -> list[dict[str, str]]:
    failures = []

    for key, items in (
        ("missing_audio", missing_audio),
        ("missing_lyric", missing_lyric),
        ("duplicate_audio", duplicate_audio),
        ("duplicate_lyric", duplicate_lyric),
        ("ignored_files", ignored_files),
    ):
        if items:
            failures.append({
                "stage": "pair",
                "reason": key,
                "count": str(len(items)),
            })

    for item in tempo_results:
        status = item.get("status")
        if status not in {"ok", "skip"}:
            failures.append({
                "stage": "tempo",
                "reason": status or "unknown",
                "song_root": item.get("song_root", ""),
            })
        elif status == "skip" and "no_audio_found" in item.get("notes", []):
            failures.append({
                "stage": "tempo",
                "reason": "no_audio_found",
                "song_root": item.get("song_root", ""),
            })

    for item in uvr5_results:
        status = item.get("status")
        if status not in {"ok", "skip"}:
            failures.append({
                "stage": "uvr5",
                "reason": status or "unknown",
                "song_root": item.get("song_root", ""),
            })

    for item in game_results:
        status = item.get("status")
        if status not in {"ok", "skip"}:
            failures.append({
                "stage": "game",
                "reason": status or "unknown",
                "song_root": item.get("song_root", ""),
            })

    if delete_source_requested and not input_cleaned:
        failures.append({
            "stage": "cleanup",
            "reason": "input_not_cleaned",
            "song_root": "",
        })

    return failures


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input_dir", nargs="?", default=None)
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--delete-source", action="store_true")
    parser.add_argument("--skip-tempo", action="store_true")
    parser.add_argument("--skip-uvr5", action="store_true")
    parser.add_argument("--skip-game", action="store_true")
    parser.add_argument("--force-tempo", action="store_true")
    parser.add_argument("--force-uvr5", action="store_true")
    parser.add_argument("--force-game", action="store_true")
    parser.add_argument("--config", type=str, default=None)
    parser.add_argument("--runner-exe", type=str, default=None)
    parser.add_argument("--runner-command", nargs="+", default=None)
    parser.add_argument("--uvr5-device", choices=["cpu", "cuda"], default=None)
    parser.add_argument("--model", type=str, default=None)
    parser.add_argument("--uvr5-single-stem", type=str, default=None)
    parser.add_argument("--uvr5-output-format", type=str, default=None)
    parser.add_argument("--game-runner-command", nargs="+", default=None)
    parser.add_argument("--game-model-path", type=str, default=None)
    args = parser.parse_args()

    config = load_config(args.config)
    input_dir = Path(args.input_dir).resolve() if args.input_dir else config.paths.inbox_root
    dry_run = not args.run

    if not input_dir.exists() or not input_dir.is_dir():
        raise SystemExit(f"[ERROR] Input directory not found: {input_dir}")

    runner_command = args.runner_command or (
        [args.runner_exe] if args.runner_exe else config.uvr5.runner_command
    )
    uvr5_device = args.uvr5_device or config.uvr5.device
    model = args.model or config.uvr5.model
    uvr5_single_stem = args.uvr5_single_stem or config.uvr5.single_stem
    uvr5_output_format = args.uvr5_output_format or config.uvr5.output_format
    game_runner_command = args.game_runner_command or config.game.runner_command
    game_model_path = args.game_model_path or config.game.model_path

    if not dry_run and not args.skip_uvr5 and not runner_command:
        raise SystemExit("[ERROR] UVR5 runner_command is not configured")
    if not dry_run and not args.skip_game and not game_runner_command:
        raise SystemExit("[ERROR] GAME runner_command is not configured")

    batch_name = input_dir.name
    base_dir = _base_dir_for(input_dir)
    if not dry_run and has_existing_batch(config.paths.work_root, batch_name):
        raise SystemExit(
            f"[ERROR] Work batch already exists and is not empty: {config.paths.work_root / batch_name}"
        )

    print(f"[PIPELINE] input={input_dir}")
    print(f"[PIPELINE] batch={batch_name}")
    print(f"[PIPELINE] mode={'DRY_RUN' if dry_run else 'RUN'}")

    (
        paired,
        missing_audio,
        missing_lyric,
        duplicate_audio,
        duplicate_lyric,
        ignored_files,
    ) = scan_pairs(
        input_dir,
        audio_exts=config.extensions.pair_audio,
        lyric_exts=config.extensions.pair_lyric,
    )
    created = build_worktree(
        batch_name,
        paired,
        dry_run,
        config.paths.work_root,
        config.paths.log_root,
    )
    existing_workspace_count = sum(1 for item in created if item["workspace_existed"])
    overwritten_input_count = sum(1 for item in created if item["overwritten"])
    input_cleaned = False
    deleted_source_files = []
    removed_source_dirs = []

    print(
        "[PAIR] "
        f"paired={len(paired)} "
        f"missing_audio={len(missing_audio)} "
        f"missing_lyric={len(missing_lyric)} "
        f"duplicate_audio={len(duplicate_audio)} "
        f"duplicate_lyric={len(duplicate_lyric)} "
        f"ignored_files={len(ignored_files)} "
        f"existing_workspace={existing_workspace_count} "
        f"overwritten_input={overwritten_input_count}"
    )
    for item in created:
        if item["overwritten"]:
            print(f"[PAIR WARN] existing input overwritten: {item['song_id']}")

    tempo_results = []
    uvr5_results = []
    game_results = []
    exported_results = []
    song_dirs = _song_dirs_from_created(created)

    if dry_run:
        print("[PIPELINE] dry-run only; tempo, UVR5 and GAME stages were not executed")
    else:
        if args.skip_tempo:
            print("[TEMPO] skipped by flag")
        else:
            tempo_results = run_tempo_stage(
                song_dirs,
                force=args.force_tempo,
                sample_rate=config.tempo.sample_rate,
                bpm_low=config.tempo.bpm_low,
                bpm_high=config.tempo.bpm_high,
                audio_exts=config.extensions.tempo_audio,
            )

        if args.skip_uvr5:
            print("[UVR5] skipped by flag")
        else:
            uvr5_results = run_uvr5_stage(
                song_dirs,
                runner_command=runner_command,
                device=uvr5_device,
                model_file_dir=config.uvr5.model_file_dir,
                model_name=model,
                single_stem=uvr5_single_stem,
                output_format=uvr5_output_format,
                extra_args=config.uvr5.extra_args,
                ffmpeg_bin_dir=config.tools.ffmpeg_bin_dir,
                force=args.force_uvr5,
                audio_exts=config.extensions.uvr5_audio,
            )

        if args.skip_game:
            print("[GAME] skipped by flag")
        else:
            game_results = run_game_stage(
                song_dirs,
                runner_command=game_runner_command,
                repo_root=config.game.repo_root,
                model_path=game_model_path,
                language=config.game.language,
                seg_threshold=config.game.seg_threshold,
                est_threshold=config.game.est_threshold,
                batch_size=config.game.batch_size,
                num_workers=config.game.num_workers,
                precision=config.game.precision,
                force=args.force_game,
                audio_exts=config.extensions.game_audio,
                midi_exts=config.extensions.game_midi,
            )

        cleanup_blockers = (
            missing_audio
            or missing_lyric
            or duplicate_audio
            or duplicate_lyric
            or ignored_files
        )
        if args.delete_source and not cleanup_blockers:
            deleted_source_files, removed_source_dirs = clear_input_dir(input_dir)
            input_cleaned = True
            print(f"[CLEANUP] input cleared: {input_dir}")
        elif args.delete_source:
            print("[CLEANUP SKIP] input was not cleared because not all files were safely processed")

        exported_results = collect_batch_exports(
            song_dirs,
            export_root=config.paths.export_root,
            batch_name=batch_name,
        )
        if exported_results:
            print(
                f"[EXPORT] count={len(exported_results)} "
                f"dir={config.paths.export_root / batch_name}"
            )

    failures = collect_failures(
        missing_audio=missing_audio,
        missing_lyric=missing_lyric,
        duplicate_audio=duplicate_audio,
        duplicate_lyric=duplicate_lyric,
        ignored_files=ignored_files,
        tempo_results=tempo_results,
        uvr5_results=uvr5_results,
        game_results=game_results,
        delete_source_requested=args.delete_source and not dry_run,
        input_cleaned=input_cleaned,
    )
    status = "error" if failures else "ok"

    report = {
        "time": datetime.now().isoformat(timespec="seconds"),
        "status": status,
        "failure_count": len(failures),
        "failures": failures,
        "input_dir": str(input_dir),
        "base_dir": str(base_dir),
        "batch_name": batch_name,
        "mode": "DRY_RUN" if dry_run else "RUN",
        "delete_source": args.delete_source,
        "export_root": str(config.paths.export_root),
        "export_batch_dir": str(config.paths.export_root / batch_name),
        "input_cleaned": input_cleaned,
        "deleted_source_file_count": len(deleted_source_files),
        "removed_source_dir_count": len(removed_source_dirs),
        "stages": {
            "pair": True,
            "tempo": not dry_run and not args.skip_tempo,
            "uvr5": not dry_run and not args.skip_uvr5,
            "game": not dry_run and not args.skip_game,
        },
        "paired_count": len(paired),
        "missing_audio_count": len(missing_audio),
        "missing_lyric_count": len(missing_lyric),
        "duplicate_audio_count": len(duplicate_audio),
        "duplicate_lyric_count": len(duplicate_lyric),
        "ignored_file_count": len(ignored_files),
        "existing_workspace_count": existing_workspace_count,
        "overwritten_input_count": overwritten_input_count,
        "paired": paired,
        "missing_audio": missing_audio,
        "missing_lyric": missing_lyric,
        "duplicate_audio": duplicate_audio,
        "duplicate_lyric": duplicate_lyric,
        "ignored_files": ignored_files,
        "deleted_source_files": deleted_source_files,
        "removed_source_dirs": removed_source_dirs,
        "created_work_items": created,
        "tempo_results": tempo_results,
        "uvr5_results": uvr5_results,
        "game_results": game_results,
        "exported_results": exported_results,
    }

    report_path = write_report(report, config.paths.log_root, batch_name)
    print(f"[PIPELINE] report={report_path}")
    if failures:
        print(f"[PIPELINE ERROR] failures={len(failures)}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
