from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path


def iter_song_dirs(
    work_root: Path,
    batch_name: str | None = None,
) -> Iterator[tuple[Path, Path]]:
    batches = [work_root / batch_name] if batch_name else sorted(work_root.iterdir())

    for batch_dir in batches:
        if not batch_dir.exists() or not batch_dir.is_dir():
            continue

        for song_dir in sorted(batch_dir.iterdir()):
            if song_dir.is_dir():
                yield batch_dir, song_dir
