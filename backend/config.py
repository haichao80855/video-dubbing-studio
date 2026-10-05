import os
import shutil
import subprocess
from functools import lru_cache
from pathlib import Path

# Paths
BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent
STORAGE_DIR = BASE_DIR / "storage"
DOWNLOADS_DIR = STORAGE_DIR / "downloads"
TASKS_DIR = STORAGE_DIR / "tasks"
OUTPUTS_DIR = STORAGE_DIR / "outputs"

for p in [STORAGE_DIR, DOWNLOADS_DIR, TASKS_DIR, OUTPUTS_DIR]:
    p.mkdir(parents=True, exist_ok=True)

# FFmpeg discovery: full Homebrew builds are keg-only, so also check their opt paths.
def binary_candidates(name: str) -> list[str]:
    override = os.environ.get(f"VDS_{name.upper()}_PATH")
    paths = ([override] if override else []) + [
        f"/opt/homebrew/opt/ffmpeg-full/bin/{name}",
        f"/usr/local/opt/ffmpeg-full/bin/{name}",
        f"/opt/miniconda3/envs/mlscreen311/bin/{name}",
        f"/opt/homebrew/bin/{name}",
        f"/usr/local/bin/{name}",
        f"/opt/miniconda3/bin/{name}",
    ]
    found = shutil.which(name)
    if found:
        paths.append(found)
    return list(dict.fromkeys(p for p in paths if os.path.isfile(p) and os.access(p, os.X_OK)))


def find_binary(name: str) -> str:
    candidates = binary_candidates(name)
    return candidates[0] if candidates else name


@lru_cache(maxsize=16)
def ffmpeg_has_filter(binary: str, filter_name: str) -> bool:
    """Inspect actual capabilities rather than assuming an installation has libass."""
    try:
        result = subprocess.run(
            [binary, "-hide_banner", "-filters"], capture_output=True, text=True, timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0 and any(
        len(fields := line.split()) >= 2 and fields[1] == filter_name
        for line in result.stdout.splitlines()
    )


def select_composition_ffmpeg(preferred: str, hard_sub: bool) -> tuple[str, bool]:
    if not hard_sub:
        return preferred, False
    for candidate in dict.fromkeys([preferred, *binary_candidates("ffmpeg")]):
        if ffmpeg_has_filter(candidate, "subtitles"):
            return candidate, True
    return preferred, False

FFMPEG_PATH = find_binary("ffmpeg")
FFPROBE_PATH = find_binary("ffprobe")

# ASR Models
DEFAULT_MLX_WHISPER_MODEL = "mlx-community/whisper-large-v3-turbo"
AVAILABLE_WHISPER_MODELS = [
    {"id": "mlx-community/whisper-large-v3-turbo", "name": "Whisper Large V3 Turbo (推荐/极速准确)"},
    {"id": "mlx-community/whisper-base", "name": "Whisper Base (轻量)"},
    {"id": "mlx-community/whisper-small", "name": "Whisper Small (均衡)"},
]

# TTS Engine
DEFAULT_TTS_MODEL = "lucasnewman/f5-tts-mlx"
