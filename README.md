# AutoMIDI

AutoMIDI is a local batch pipeline for turning song assets into MIDI files.

Current pipeline:

`inbox -> pair -> work -> tempo -> UVR5 -> GAME -> exports`

Implemented stages:

- Pair audio and lyric files
- Create an isolated workspace for each song
- Detect tempo with `librosa`
- Extract vocals with `audio-separator / UVR5`
- Generate MIDI with `GAME`
- Copy final MIDI files into a batch export folder

## Conventions

- The default input directory is `paths.inbox_root` from `config.json`
- Each batch is a folder placed under `inbox/`
- Each song is expected to have one audio file and one lyric file
- Supported extensions for each stage are managed in `config.json -> extensions`
- `pipeline.py --run` executes the full chain: `pair -> tempo -> uvr5 -> game -> export`

## Project Layout

```text
automidi/
├── inbox/                # input batches
├── work/                 # per-batch / per-song workspace
├── exports/              # aggregated MIDI exports per batch
├── logs/                 # pipeline reports
├── lib/                  # core logic
├── scripts/              # CLI entrypoints
├── tools/
│   ├── ffmpeg/           # bundled FFmpeg
│   └── uvr5-models/      # local UVR5 model cache
├── config.json           # local machine config, not committed
├── config.example.json   # config template
├── pyproject.toml
├── requirements.txt
├── setup_uv_env.ps1
└── run_pipeline.ps1
```

## Workspace Layout

Each song is processed under `work/<batch>/<song>/`:

```text
work/<batch>/<song>/
├── input/
├── process/
│   ├── tempo.json
│   ├── uvr5_result.json
│   ├── game_result.json
│   └── uvr5/
└── output/
    └── game/
```

After the full pipeline finishes, final MIDI files are also copied to:

```text
exports/<batch>/
```

## Configuration

Copy `config.example.json` to `config.json` and adjust it for the current machine.

Example:

```json
{
  "paths": {
    "work_root": "work",
    "log_root": "logs",
    "inbox_root": "inbox",
    "export_root": "exports"
  },
  "tools": {
    "ffmpeg_bin_dir": "tools/ffmpeg/bin"
  },
  "extensions": {
    "pair_audio": [".mp3", ".wav"],
    "pair_lyric": [".txt", ".doc", ".docx"],
    "tempo_audio": [".wav", ".mp3"],
    "uvr5_audio": [".wav", ".mp3", ".flac", ".m4a"],
    "game_audio": [".wav", ".mp3", ".flac", ".m4a"],
    "game_midi": [".mid", ".midi"]
  },
  "uvr5": {
    "runner_command": ["uv", "run", "--python", "3.12", "audio-separator"],
    "device": "cpu",
    "model_file_dir": "tools/uvr5-models",
    "model": "vocals_mel_band_roformer.ckpt",
    "single_stem": "Vocals",
    "output_format": "WAV",
    "extra_args": []
  },
  "tempo": {
    "sample_rate": 22050,
    "bpm_low": 45.0,
    "bpm_high": 140.0
  },
  "game": {
    "repo_root": "../GAME",
    "runner_command": [
      "uv",
      "run",
      "--python",
      "3.12",
      "--with-requirements",
      "requirements.txt",
      "--with",
      "torch",
      "python",
      "infer.py"
    ],
    "model_path": "",
    "language": "zh",
    "seg_threshold": 0.6,
    "est_threshold": 0.6,
    "batch_size": 1,
    "num_workers": 0,
    "precision": "32-true"
  }
}
```

Important fields:

- `paths.work_root`: workspace root
- `paths.log_root`: pipeline reports
- `paths.inbox_root`: input batch root
- `paths.export_root`: aggregated batch export root
- `tools.ffmpeg_bin_dir`: bundled FFmpeg `bin` directory
- `extensions.pair_audio`: audio extensions used during pairing
- `extensions.pair_lyric`: lyric extensions used during pairing
- `extensions.tempo_audio`: audio lookup order for the tempo stage
- `extensions.uvr5_audio`: audio lookup order for the UVR5 stage
- `extensions.game_audio`: allowed vocal file extensions under `process/uvr5/`
- `extensions.game_midi`: MIDI lookup order under `output/game/`
- `uvr5.runner_command`: UVR5 launch command
- `uvr5.device`: `cpu` or `cuda`
- `uvr5.model_file_dir`: UVR5 model cache directory
- `uvr5.model`: UVR5 model filename
- `tempo.*`: sample rate and BPM search range
- `game.repo_root`: path to the external `GAME` repository
- `game.runner_command`: GAME launch command
- `game.model_path`: path to the GAME `.pt` model

## Requirements

You need:

- `uv`
- The sibling `GAME` repository
- FFmpeg under `tools/ffmpeg/bin`
- A valid GAME model file
- A valid `config.json`

Recommended FFmpeg files:

```text
tools/ffmpeg/bin/ffmpeg.exe
tools/ffmpeg/bin/ffprobe.exe
```

For Windows builds, see the official FFmpeg download page:
https://ffmpeg.org/download.html#build-windows

## Environment Setup

Use `uv`:

```powershell
uv sync --python 3.12
```

Shortcut script:

```powershell
.\setup_uv_env.ps1
```

Notes:

- You do not need to manually activate `.venv`
- `uv run ...` uses the project environment for you
- On a new machine, dependency installation still depends on local network and permissions

## Running

Default full pipeline:

```powershell
uv run --python 3.12 python scripts\pipeline.py --run
```

Shortcut script:

```powershell
.\run_pipeline.ps1
```

Full run and clear the input batch afterward:

```powershell
uv run --python 3.12 python scripts\pipeline.py --run --delete-source
```

Skip a stage:

```powershell
uv run --python 3.12 python scripts\pipeline.py --run --skip-game
uv run --python 3.12 python scripts\pipeline.py --run --skip-uvr5
uv run --python 3.12 python scripts\pipeline.py --run --skip-tempo
```

Force rerun a stage:

```powershell
uv run --python 3.12 python scripts\pipeline.py --run --force-tempo
uv run --python 3.12 python scripts\pipeline.py --run --force-uvr5
uv run --python 3.12 python scripts\pipeline.py --run --force-game
```

Run individual stages:

```powershell
uv run --python 3.12 python scripts\run_uvr5.py --batch inbox --force-uvr5
uv run --python 3.12 python scripts\run_game.py --batch inbox --force-game
uv run --python 3.12 python scripts\detect_tempo.py --batch inbox --force-tempo
```

## Behavior

### Pairing

- Recursively scans `inbox`
- Matches audio and lyric files by normalized stem
- Removes trailing ` demo` from audio names before matching
- Uses `extensions.pair_audio` and `extensions.pair_lyric`
- Duplicate audio or duplicate lyric files are reported as errors

### Batch Naming

- `batch_name = input_dir.name`
- If `work/<batch_name>` already exists and is not empty, the pipeline aborts

### Stage Skip Rules

- If `process/tempo.json` already exists, tempo is skipped by default
- If `process/uvr5_result.json` already exists with `status=ok`, UVR5 is skipped
- If `process/game_result.json` already exists with `status=ok`, GAME is skipped

### Cleanup

- Input files are only removed when `--delete-source` is used
- Cleanup only happens when the batch has no missing files, duplicates, or ignored files

### Exports

- Per-song GAME output stays in `work/<batch>/<song>/output/game/`
- The pipeline also copies each final MIDI into `exports/<batch>/`
- Export filenames are based on the song workspace directory name

## Reports

Each run writes:

```text
logs/pipeline_report_<batch>.json
```

The report includes:

- Overall `status`
- `failure_count`
- `failures`
- Pairing results
- Tempo / UVR5 / GAME stage results
- Exported file list

If any pipeline failure is recorded, the process exits with a non-zero code.

## Migration To Another Machine

This project is portable, but not fully self-contained.

To run it on another machine:

1. Copy this repository
2. Clone or copy the sibling `GAME` repository
3. Install `uv`
4. Run `uv sync --python 3.12`
5. Prepare FFmpeg and model files
6. Adjust `config.json` paths for the new machine

You do not need to manually create or activate a separate virtual environment if you use `uv run`.

## Notes

- The first UVR5 run may download model files unless they already exist locally
- `tools/uvr5-models/` can be very large and should not be committed
- `config.json` is machine-local and should not be committed
- The system `python` launcher is not required if `uv` is available and working
