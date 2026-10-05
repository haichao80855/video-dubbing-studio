import os
import shutil
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

# FFmpeg discovery
def find_binary(name: str) -> str:
    # 1. Prefer conda env with libass support, then Homebrew / Mac locations
    common_mac_paths = [
        f"/opt/miniconda3/envs/mlscreen311/bin/{name}",
        f"/opt/homebrew/bin/{name}",
        f"/usr/local/bin/{name}",
        f"/opt/miniconda3/bin/{name}",
    ]
    for p in common_mac_paths:
        if os.path.isfile(p) and os.access(p, os.X_OK):
            return p
    # 2. System PATH
    found = shutil.which(name)
    if found:
        return found
    return name

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
