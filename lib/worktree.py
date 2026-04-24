from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path


def _is_song_dir(path: Path) -> bool:
    return path.is_dir() and (path / "input").is_dir()


def _iter_flat_layout(work_root: Path) -> Iterator[tuple[Path, Path]]:
    for song_dir in sorted(work_root.iterdir()):
        if _is_song_dir(song_dir):
            yield work_root, song_dir


def _iter_batch_layout(batch_dir: Path) -> Iterator[tuple[Path, Path]]:
    for song_dir in sorted(batch_dir.iterdir()):
        if _is_song_dir(song_dir):
            yield batch_dir, song_dir


def iter_song_dirs(
    work_root: Path,
    batch_name: str | None = None,
) -> Iterator[tuple[Path, Path]]:
    if batch_name:
        batch_dir = work_root / batch_name
        if batch_dir.exists() and batch_dir.is_dir():
            yield from _iter_batch_layout(batch_dir)
            return

        yield from _iter_flat_layout(work_root)
        return

    for entry in sorted(work_root.iterdir()):
        if _is_song_dir(entry):
            yield work_root, entry
        elif entry.is_dir():
            yield from _iter_batch_layout(entry)
