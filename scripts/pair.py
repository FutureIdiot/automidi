from pathlib import Path
import argparse
import shutil
import sys
import json
import re
from datetime import datetime

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from lib.config import load_config


def safe_name(name):
    name = name.strip()
    name = re.sub(r'[<>:"/\\|?*]', "_", name)
    name = re.sub(r"\s+", " ", name)
    return name.rstrip(". ")


def copy_file(src, dst):
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


def normalize_audio_stem(stem):
    s = stem.strip().lower()
    if s.endswith(" demo"):
        s = s[:-5].strip()
    return s


def normalize_lyric_stem(stem):
    return stem.strip().lower()


def scan_pairs(input_dir, *, audio_exts, lyric_exts):
    audio_exts = {ext.lower() for ext in audio_exts}
    lyric_exts = {ext.lower() for ext in lyric_exts}
    files = [p for p in input_dir.rglob("*") if p.is_file()]

    audio_map = {}
    lyric_map = {}
    ignored_files = []

    for f in files:
        stem = f.stem
        ext = f.suffix.lower()

        if ext in audio_exts:
            norm = normalize_audio_stem(stem)
            audio_map.setdefault(norm, []).append(f)
        elif ext in lyric_exts:
            norm = normalize_lyric_stem(stem)
            lyric_map.setdefault(norm, []).append(f)
        else:
            ignored_files.append(str(f))

    all_stems = sorted(set(audio_map.keys()) | set(lyric_map.keys()))

    paired = []
    missing_audio = []
    missing_lyric = []
    duplicate_audio = []
    duplicate_lyric = []

    for stem in all_stems:
        audio_files = audio_map.get(stem, [])
        lyric_files = lyric_map.get(stem, [])

        if len(audio_files) > 1:
            duplicate_audio.append({
                "song_id": stem,
                "audio": [str(p) for p in audio_files],
            })

        if len(lyric_files) > 1:
            duplicate_lyric.append({
                "song_id": stem,
                "lyric": [str(p) for p in lyric_files],
            })

        if len(audio_files) > 1 or len(lyric_files) > 1:
            continue

        audio = audio_files[0] if audio_files else None
        lyric = lyric_files[0] if lyric_files else None

        if audio is not None and lyric is not None:
            paired.append({
                "song_id": stem,
                "audio": str(audio),
                "lyric": str(lyric),
            })
        elif audio is not None and lyric is None:
            missing_lyric.append({
                "song_id": stem,
                "audio": str(audio),
            })
        elif lyric is not None and audio is None:
            missing_audio.append({
                "song_id": stem,
                "lyric": str(lyric),
            })

    return paired, missing_audio, missing_lyric, duplicate_audio, duplicate_lyric, ignored_files


def resolve_work_dir(input_dir, inbox_root, work_root):
    if input_dir.resolve() == inbox_root.resolve():
        return work_root
    return work_root / input_dir.name


def build_worktree(work_dir, items, dry_run, log_root):
    log_root.mkdir(parents=True, exist_ok=True)

    created = []

    for item in items:
        song_id = safe_name(item["song_id"])
        song_root = work_dir / song_id

        input_dir = song_root / "input"
        process_dir = song_root / "process"
        output_dir = song_root / "output"

        audio_src = Path(item["audio"])
        lyric_value = item.get("lyric")
        lyric_src = Path(lyric_value) if lyric_value else None

        audio_dst = input_dir / audio_src.name
        lyric_dst = input_dir / lyric_src.name if lyric_src else None
        workspace_existed = song_root.exists()
        audio_dst_existed = audio_dst.exists()
        lyric_dst_existed = lyric_dst.exists() if lyric_dst else False
        overwritten = audio_dst_existed or lyric_dst_existed

        created.append({
            "song_id": song_id,
            "song_root": str(song_root),
            "audio_src": str(audio_src),
            "lyric_src": str(lyric_src) if lyric_src else None,
            "audio_dst": str(audio_dst),
            "lyric_dst": str(lyric_dst) if lyric_dst else None,
            "workspace_existed": workspace_existed,
            "audio_dst_existed": audio_dst_existed,
            "lyric_dst_existed": lyric_dst_existed,
            "overwritten": overwritten,
        })

        if not dry_run:
            input_dir.mkdir(parents=True, exist_ok=True)
            process_dir.mkdir(parents=True, exist_ok=True)
            output_dir.mkdir(parents=True, exist_ok=True)

            copy_file(audio_src, audio_dst)
            if lyric_src and lyric_dst:
                copy_file(lyric_src, lyric_dst)

    return created


def clear_input_dir(input_dir):
    deleted_files = []
    removed_dirs = []

    for path in sorted(input_dir.rglob("*"), reverse=True):
        if path.is_file():
            path.unlink()
            deleted_files.append(str(path))

    for path in sorted(input_dir.rglob("*"), reverse=True):
        if path.is_dir():
            try:
                path.rmdir()
                removed_dirs.append(str(path))
            except OSError:
                pass

    return deleted_files, removed_dirs


def has_existing_batch(work_root, batch_name):
    work_batch_dir = work_root / batch_name
    return work_batch_dir.exists() and any(p.name != ".gitkeep" for p in work_batch_dir.iterdir())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("input_dir", type=str)
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--delete-source", action="store_true")
    parser.add_argument("--config", type=str, default=None)
    args = parser.parse_args()

    config = load_config(args.config)

    input_dir = Path(args.input_dir).resolve()
    dry_run = not args.run

    if not input_dir.exists() or not input_dir.is_dir():
        print(f"[ERROR] Input directory not found: {input_dir}")
        sys.exit(1)

    if input_dir.parent.name == "inbox":
        base_dir = input_dir.parent.parent
    else:
        base_dir = input_dir.parent

    batch_name = input_dir.name
    work_dir = resolve_work_dir(input_dir, config.paths.inbox_root, config.paths.work_root)
    if not dry_run and work_dir.exists() and any(p.name != ".gitkeep" for p in work_dir.iterdir()):
        print(f"[ERROR] Work target already exists and is not empty: {work_dir}")
        sys.exit(1)

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
    work_items = paired + missing_lyric
    created = build_worktree(
        work_dir,
        work_items,
        dry_run,
        config.paths.log_root,
    )
    existing_workspace_count = sum(1 for item in created if item["workspace_existed"])
    overwritten_input_count = sum(1 for item in created if item["overwritten"])
    input_cleaned = False
    deleted_source_files = []
    removed_source_dirs = []

    cleanup_blockers = (
        missing_audio
        or duplicate_audio
        or duplicate_lyric
        or ignored_files
    )
    if args.delete_source and not dry_run and not cleanup_blockers:
        deleted_source_files, removed_source_dirs = clear_input_dir(input_dir)
        input_cleaned = True

    report = {
        "time": datetime.now().isoformat(timespec="seconds"),
        "input_dir": str(input_dir),
        "base_dir": str(base_dir),
        "batch_name": batch_name,
        "mode": "DRY_RUN" if dry_run else "RUN",
        "paired_count": len(paired),
        "missing_audio_count": len(missing_audio),
        "missing_lyric_count": len(missing_lyric),
        "duplicate_audio_count": len(duplicate_audio),
        "duplicate_lyric_count": len(duplicate_lyric),
        "ignored_file_count": len(ignored_files),
        "existing_workspace_count": existing_workspace_count,
        "overwritten_input_count": overwritten_input_count,
        "delete_source": args.delete_source,
        "input_cleaned": input_cleaned,
        "deleted_source_file_count": len(deleted_source_files),
        "removed_source_dir_count": len(removed_source_dirs),
        "paired": paired,
        "missing_audio": missing_audio,
        "missing_lyric": missing_lyric,
        "duplicate_audio": duplicate_audio,
        "duplicate_lyric": duplicate_lyric,
        "ignored_files": ignored_files,
        "deleted_source_files": deleted_source_files,
        "removed_source_dirs": removed_source_dirs,
        "created_work_items": created,
    }

    config.paths.log_root.mkdir(parents=True, exist_ok=True)
    report_path = config.paths.log_root / f"pipeline_v1_report_{batch_name}.json"

    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print(f"Input: {input_dir}")
    print(f"Base: {base_dir}")
    print(f"Batch: {batch_name}")
    print(f"Mode: {'DRY_RUN' if dry_run else 'RUN'}")
    print(f"Paired: {len(paired)}")
    print(f"Missing audio: {len(missing_audio)}")
    print(f"Missing lyric: {len(missing_lyric)}")
    print(f"Duplicate audio: {len(duplicate_audio)}")
    print(f"Duplicate lyric: {len(duplicate_lyric)}")
    print(f"Ignored files: {len(ignored_files)}")
    print(f"Existing workspace: {existing_workspace_count}")
    print(f"Overwritten input: {overwritten_input_count}")
    print(f"Delete source: {args.delete_source}")
    print(f"Input cleaned: {input_cleaned}")
    print(f"Report: {report_path}")

    if paired:
        print("\n[PAIRED]")
        for item in created:
            marker = "WARN overwrite" if item["overwritten"] else "OK"
            print(f"  {marker}  {item['song_id']}")

    if missing_audio:
        print("\n[MISSING AUDIO]")
        for item in missing_audio:
            print(f"  NO AUDIO  {item['song_id']}")

    if missing_lyric:
        print("\n[MISSING LYRIC]")
        for item in missing_lyric:
            print(f"  NO LYRIC  {item['song_id']}")

    if duplicate_audio:
        print("\n[DUPLICATE AUDIO]")
        for item in duplicate_audio:
            print(f"  DUP AUDIO  {item['song_id']}")

    if duplicate_lyric:
        print("\n[DUPLICATE LYRIC]")
        for item in duplicate_lyric:
            print(f"  DUP LYRIC  {item['song_id']}")

    if ignored_files:
        print("\n[IGNORED FILES]")
        for item in ignored_files:
            print(f"  IGNORED  {item}")

    if args.delete_source and not dry_run and cleanup_blockers:
        print("\nInput cleanup skipped because not all files were safely processed.")

    if dry_run:
        print("\nDry run only. Add --run to actually create work folders and copy files.")
        if args.delete_source:
            print("Input folder is not cleaned in dry-run mode.")


if __name__ == "__main__":
    main()
