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

# TTS Voices
EDGE_TTS_VOICES = [
    {"id": "zh-CN-YunxiNeural", "name": "云希 (活力男声 - 视频解说推荐)", "gender": "Male"},
    {"id": "zh-CN-XiaoxiaoNeural", "name": "晓晓 (温柔女声 - 旁白推荐)", "gender": "Female"},
    {"id": "zh-CN-YunjianNeural", "name": "云健 (沉稳男声 - 科技/纪录片)", "gender": "Male"},
    {"id": "zh-CN-XiaoyiNeural", "name": "晓伊 (亲切女声)", "gender": "Female"},
    {"id": "zh-CN-YunyangNeural", "name": "云扬 (专业男播音)", "gender": "Male"},
    {"id": "zh-CN-liaoning-XiaobeiNeural", "name": "晓北 (辽宁风趣女声)", "gender": "Female"},
    {"id": "zh-CN-shaanxi-XiaoniNeural", "name": "晓妮 (陕西风趣女声)", "gender": "Female"},
]

COSYVOICE_VOICES = [
    {"id": "longxiaochun", "name": "龙小春 (自然女声)", "gender": "Female"},
    {"id": "longyuan", "name": "龙渊 (沉稳男声)", "gender": "Male"},
    {"id": "longyue", "name": "龙悦 (亲和女声)", "gender": "Female"},
]
