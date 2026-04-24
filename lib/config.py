from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config.json"


@dataclass(frozen=True)
class PathConfig:
    work_root: Path
    log_root: Path
    inbox_root: Path
    export_root: Path


@dataclass(frozen=True)
class UVR5Config:
    runner_command: list[str]
    device: str
    model_file_dir: Path
    model: str
    single_stem: str
    output_format: str
    extra_args: list[str]


@dataclass(frozen=True)
class TempoConfig:
    sample_rate: int
    bpm_low: float
    bpm_high: float


@dataclass(frozen=True)
class ExtensionsConfig:
    pair_audio: tuple[str, ...]
    pair_lyric: tuple[str, ...]
    tempo_audio: tuple[str, ...]
    uvr5_audio: tuple[str, ...]
    game_audio: tuple[str, ...]
    game_midi: tuple[str, ...]


@dataclass(frozen=True)
class ToolsConfig:
    ffmpeg_bin_dir: Path


@dataclass(frozen=True)
class GameConfig:
    repo_root: Path
    runner_command: list[str]
    model_path: str
    language: str
    seg_threshold: float
    est_threshold: float
    batch_size: int
    num_workers: int
    precision: str


@dataclass(frozen=True)
class AppConfig:
    project_root: Path
    paths: PathConfig
    uvr5: UVR5Config
    tempo: TempoConfig
    extensions: ExtensionsConfig
    tools: ToolsConfig
    game: GameConfig


def _resolve_path(value: str, project_root: Path) -> Path:
    path = Path(value).expanduser()
    if path.is_absolute():
        return path
    return project_root / path


def _looks_like_path(value: str) -> bool:
    return (
        "/" in value
        or "\\" in value
        or value.startswith(".")
        or value.startswith("~")
    )


def _resolve_command_part(value: str, project_root: Path) -> str:
    if _looks_like_path(value):
        return str(_resolve_path(value, project_root))
    return value


def _resolve_command(value: Any, project_root: Path) -> list[str]:
    if isinstance(value, list):
        return [str(_resolve_command_part(str(part), project_root)) for part in value]
    if isinstance(value, str) and value:
        return [str(_resolve_command_part(value, project_root))]
    return []


def _normalize_extensions(values: Any, defaults: tuple[str, ...]) -> tuple[str, ...]:
    if not isinstance(values, list) or not values:
        values = list(defaults)

    normalized: list[str] = []
    for value in values:
        ext = str(value).strip().lower()
        if not ext:
            continue
        if not ext.startswith("."):
            ext = f".{ext}"
        if ext not in normalized:
            normalized.append(ext)

    return tuple(normalized or defaults)


def _read_config(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(
            f"Config file not found: {path}. Create config.json in the project root."
        )

    return json.loads(path.read_text(encoding="utf-8"))


def load_config(config_path: str | Path | None = None) -> AppConfig:
    path = Path(config_path).resolve() if config_path else DEFAULT_CONFIG_PATH
    data = _read_config(path)

    paths = data.get("paths", {})
    tools = data.get("tools", {})
    uvr5 = data.get("uvr5", {})
    tempo = data.get("tempo", {})
    extensions = data.get("extensions", {})
    game = data.get("game", {})
    game_repo_root = _resolve_path(game.get("repo_root", "../GAME"), PROJECT_ROOT)
    game_model_path = game.get("model_path", "")

    return AppConfig(
        project_root=PROJECT_ROOT,
        paths=PathConfig(
            work_root=_resolve_path(paths.get("work_root", "work"), PROJECT_ROOT),
            log_root=_resolve_path(paths.get("log_root", "logs"), PROJECT_ROOT),
            inbox_root=_resolve_path(paths.get("inbox_root", "inbox"), PROJECT_ROOT),
            export_root=_resolve_path(paths.get("export_root", "exports"), PROJECT_ROOT),
        ),
        uvr5=UVR5Config(
            runner_command=_resolve_command(
                uvr5.get("runner_command", uvr5.get("runner_exe", "")),
                PROJECT_ROOT,
            ),
            device=uvr5.get("device", "cpu"),
            model_file_dir=_resolve_path(
                uvr5.get("model_file_dir", "tools/uvr5-models"),
                PROJECT_ROOT,
            ),
            model=uvr5.get("model", "vocals_mel_band_roformer.ckpt"),
            single_stem=uvr5.get("single_stem", "Vocals"),
            output_format=uvr5.get("output_format", "WAV"),
            extra_args=[str(arg) for arg in uvr5.get("extra_args", [])],
        ),
        tempo=TempoConfig(
            sample_rate=int(tempo.get("sample_rate", 22050)),
            bpm_low=float(tempo.get("bpm_low", 45.0)),
            bpm_high=float(tempo.get("bpm_high", 140.0)),
        ),
        extensions=ExtensionsConfig(
            pair_audio=_normalize_extensions(
                extensions.get("pair_audio"),
                (".mp3", ".wav"),
            ),
            pair_lyric=_normalize_extensions(
                extensions.get("pair_lyric"),
                (".txt", ".doc", ".docx"),
            ),
            tempo_audio=_normalize_extensions(
                extensions.get("tempo_audio"),
                (".wav", ".mp3"),
            ),
            uvr5_audio=_normalize_extensions(
                extensions.get("uvr5_audio"),
                (".wav", ".mp3", ".flac", ".m4a"),
            ),
            game_audio=_normalize_extensions(
                extensions.get("game_audio"),
                (".wav", ".mp3", ".flac", ".m4a"),
            ),
            game_midi=_normalize_extensions(
                extensions.get("game_midi"),
                (".mid", ".midi"),
            ),
        ),
        tools=ToolsConfig(
            ffmpeg_bin_dir=_resolve_path(
                tools.get("ffmpeg_bin_dir", "tools/ffmpeg/bin"),
                PROJECT_ROOT,
            ),
        ),
        game=GameConfig(
            repo_root=game_repo_root,
            runner_command=_resolve_command(
                game.get("runner_command", game.get("runner_exe", "")),
                game_repo_root,
            ),
            model_path=str(_resolve_path(game_model_path, game_repo_root))
            if game_model_path
            else "",
            language=game.get("language", "zh"),
            seg_threshold=float(game.get("seg_threshold", 0.6)),
            est_threshold=float(game.get("est_threshold", 0.6)),
            batch_size=int(game.get("batch_size", 1)),
            num_workers=int(game.get("num_workers", 0)),
            precision=game.get("precision", "32-true"),
        ),
    )
