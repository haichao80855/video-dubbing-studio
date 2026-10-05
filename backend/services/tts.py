import os
import asyncio
import subprocess
import logging
from typing import List, Dict, Any, Optional, Callable
from pathlib import Path
from pydub import AudioSegment
from backend.config import FFMPEG_PATH, FFPROBE_PATH
from backend.services.f5_tts_mlx import F5TTSMLXService

logger = logging.getLogger(__name__)

def get_audio_duration(file_path: str) -> float:
    """Return audio duration in seconds using pydub/ffprobe."""
    try:
        audio = AudioSegment.from_file(file_path)
        return round(len(audio) / 1000.0, 3)
    except Exception:
        # Fallback to ffprobe
        cmd = [
            FFPROBE_PATH, "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            file_path
        ]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if res.returncode == 0 and res.stdout.strip():
            return round(float(res.stdout.strip()), 3)
        return 0.0

class F5TTSCloneRunner:
    """Manages zero-shot voice cloning using F5-TTS MLX for all subtitle segments."""

    def __init__(
        self,
        ref_audio_path: Optional[str] = None,
        ref_audio_text: Optional[str] = None,
        model_name: str = "lucasnewman/f5-tts-mlx"
    ):
        self.ref_audio_path = ref_audio_path
        self.ref_audio_text = ref_audio_text
        self.service = F5TTSMLXService(
            model_name=model_name,
            ref_audio_path=ref_audio_path,
            ref_audio_text=ref_audio_text
        )

    async def generate_all(
        self,
        subtitles: List[Dict[str, Any]],
        task_dir: Path,
        progress_callback: Optional[Callable[[float, str], None]] = None
    ) -> List[Dict[str, Any]]:
        """
        Synthesizes cloned speech for each subtitle item in sequence.
        Adds 'audio_path' and 'tts_duration' to each segment.
        """
        tts_dir = task_dir / "tts_clips"
        tts_dir.mkdir(parents=True, exist_ok=True)

        results = []
        total = len(subtitles)
        loop = asyncio.get_running_loop()
        failed_count = 0

        for idx, item in enumerate(subtitles):
            seg_id = item["id"]
            text = (item.get("translated_text", "").strip() or item.get("text", "")).strip()
            out_path = str(tts_dir / f"clip_{seg_id:04d}.wav")

            try:
                # F5-TTS MLX runs sequentially to maximize Apple Silicon Metal throughput
                duration = await loop.run_in_executor(
                    None,
                    lambda: self.service.synthesize(text, out_path)
                )

                # Validate generated audio file
                if not os.path.exists(out_path) or os.path.getsize(out_path) < 1000 or duration <= 0.05:
                    raise RuntimeError(f"切片 #{seg_id} 生成的音频文件异常或过小 (大小: {os.path.getsize(out_path) if os.path.exists(out_path) else 0} 字节)")

            except Exception as e:
                logger.error(f"F5-TTS 声音克隆分句 #{seg_id} 失败: {e}")
                failed_count += 1
                # If too many fail, fail the task directly rather than generating silent video!
                if failed_count > max(3, int(total * 0.4)):
                    raise RuntimeError(f"F5-TTS 声音克隆连续失败达到阈值 ({failed_count}/{total})，已终止以防止生成无声音频。最新错误: {e}")

                # Fallback: short silence for this single failed sentence
                silence = AudioSegment.silent(duration=500, frame_rate=48000)
                silence.export(out_path, format="wav")
                duration = 0.5

            results.append({
                **item,
                "audio_path": out_path,
                "tts_duration": duration
            })

            if progress_callback:
                pct = (idx + 1) / total * 100
                progress_callback(pct, f"F5-TTS 正在克隆合成原声配音 ({idx + 1}/{total})...")

        return results

# Backward compatibility alias
TTSRunner = F5TTSCloneRunner
