import os
import subprocess
import logging
from typing import List, Dict, Any, Optional, Callable
from pathlib import Path
from backend.config import FFMPEG_PATH, OUTPUTS_DIR

logger = logging.getLogger(__name__)

def format_timestamp_srt(seconds: float) -> str:
    """Converts seconds float to SRT timestamp format: HH:MM:SS,mmm"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int(round((seconds - int(seconds)) * 1000))
    if millis >= 1000:
        secs += 1
        millis -= 1000
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"

class VideoComposer:
    """Composites dubbed audio, subtitles, and video stream into final Chinese MP4."""

    def __init__(self, task_dir: Path, task_id: str):
        self.task_dir = task_dir
        self.task_id = task_id

    def generate_srt(self, subtitles: List[Dict[str, Any]]) -> str:
        """Generates standard SRT subtitle file."""
        srt_path = self.task_dir / "subtitles.srt"
        with open(srt_path, "w", encoding="utf-8") as f:
            for idx, item in enumerate(subtitles, 1):
                start_str = format_timestamp_srt(item["start"])
                end_str = format_timestamp_srt(item["end"])
                text = item.get("translated_text", "").strip() or item.get("text", "").strip()
                f.write(f"{idx}\n")
                f.write(f"{start_str} --> {end_str}\n")
                f.write(f"{text}\n\n")
        return str(srt_path)

    def compose_video(
        self,
        video_path: str,
        audio_path: str,
        subtitles: List[Dict[str, Any]],
        hard_sub: bool = True,
        progress_callback: Optional[Callable[[float, str], None]] = None
    ) -> Dict[str, str]:
        """
        Muxes video and Chinese audio track, embeds or burns subtitles,
        producing the final Chinese MP4.
        """
        if progress_callback:
            progress_callback(10.0, "生成中文字幕文件...")

        srt_path = self.generate_srt(subtitles)

        output_filename = f"dubbed_{self.task_id}.mp4"
        output_mp4 = str(OUTPUTS_DIR / output_filename)
        output_srt = str(OUTPUTS_DIR / f"subtitles_{self.task_id}.srt")

        # Copy SRT to public outputs directory as well
        with open(srt_path, "r", encoding="utf-8") as src, open(output_srt, "w", encoding="utf-8") as dst:
            dst.write(src.read())

        if progress_callback:
            progress_callback(30.0, f"正在进行 FFmpeg 封装与视频合成 (硬字幕={hard_sub})...")

        if hard_sub:
            # Burn subtitles into video stream
            # Escaping subtitle filename for FFmpeg filter syntax
            escaped_srt = srt_path.replace("\\", "/").replace(":", "\\:").replace("'", "\\'")
            sub_filter = f"subtitles=filename='{escaped_srt}':force_style='FontSize=22,FontName=Arial,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,Outline=2,Shadow=1,MarginV=25'"
            
            cmd = [
                FFMPEG_PATH, "-y",
                "-i", video_path,
                "-i", audio_path,
                "-vf", sub_filter,
                "-map", "0:v:0",
                "-map", "1:a:0",
                "-c:v", "libx264",
                "-preset", "fast",
                "-crf", "22",
                "-c:a", "aac",
                "-b:a", "192k",
                "-shortest",
                output_mp4
            ]
        else:
            # Soft subtitles or stream copy (very fast)
            cmd = [
                FFMPEG_PATH, "-y",
                "-i", video_path,
                "-i", audio_path,
                "-i", srt_path,
                "-map", "0:v:0",
                "-map", "1:a:0",
                "-map", "2:s:0",
                "-c:v", "copy",
                "-c:a", "aac",
                "-b:a", "192k",
                "-c:s", "mov_text",
                "-metadata:s:s:0", "language=chi",
                "-shortest",
                output_mp4
            ]

        logger.info(f"Running FFmpeg composition: {' '.join(cmd)}")
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if res.returncode != 0:
            err = res.stderr.decode("utf-8", errors="ignore")
            logger.error(f"FFmpeg composition failed: {err}")
            # If hardsub failed (e.g. font issue), retry with copy mode
            if hard_sub:
                logger.info("Retrying with copy mode without hard subtitles...")
                retry_cmd = [
                    FFMPEG_PATH, "-y",
                    "-i", video_path,
                    "-i", audio_path,
                    "-map", "0:v:0",
                    "-map", "1:a:0",
                    "-c:v", "copy",
                    "-c:a", "aac",
                    "-b:a", "192k",
                    "-shortest",
                    output_mp4
                ]
                retry_res = subprocess.run(retry_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                if retry_res.returncode != 0:
                    raise RuntimeError(f"FFmpeg 合成最终视频失败: {retry_res.stderr.decode('utf-8', errors='ignore')}")
            else:
                raise RuntimeError(f"FFmpeg 合成最终视频失败: {err}")

        if progress_callback:
            progress_callback(100.0, "最终中文 MP4 视频合成完毕！")

        return {
            "output_mp4": output_mp4,
            "output_srt": output_srt,
            "filename": output_filename,
            "srt_filename": f"subtitles_{self.task_id}.srt"
        }
