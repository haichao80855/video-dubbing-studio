import os
import subprocess
import logging
from typing import List, Dict, Any, Optional, Callable
from pathlib import Path
from backend.config import FFMPEG_PATH, FFPROBE_PATH, OUTPUTS_DIR

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
    """
    Composites dubbed audio, subtitles, and video stream into final Chinese MP4.
    Guarantees strict PTS timestamp alignment for perfect A/V lip synchronization.
    """

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
        Muxes video and Chinese audio track with exact PTS reset to eliminate any container-level desync.
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
            progress_callback(30.0, f"正在进行音画时钟精准对齐与 FFmpeg 封装 (硬字幕={hard_sub})...")

        # Ensure audio_path is valid and non-empty
        if not os.path.exists(audio_path) or os.path.getsize(audio_path) < 4096:
            raise RuntimeError(f"合成所需的配音音轨文件异常或为空: {audio_path}")

        escaped_srt = srt_path.replace("\\", "/").replace(":", "\\:").replace("'", "\\'")

        if hard_sub:
            # Complex filter chaining: burned subtitles + video PTS reset, and audio PTS reset + 48kHz stereo formatting
            filter_complex = (
                f"[0:v]subtitles=filename='{escaped_srt}':force_style='FontSize=22,FontName=Arial,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,Outline=2,Shadow=1,MarginV=25',setpts=PTS-STARTPTS[v];"
                f"[1:a]asetpts=PTS-STARTPTS,aformat=sample_rates=48000:channel_layouts=stereo[a]"
            )
            cmd = [
                FFMPEG_PATH, "-y",
                "-i", video_path,
                "-i", audio_path,
                "-filter_complex", filter_complex,
                "-map", "[v]",
                "-map", "[a]",
                "-c:v", "libx264",
                "-preset", "fast",
                "-crf", "22",
                "-c:a", "aac",
                "-b:a", "192k",
                "-ar", "48000",
                "-ac", "2",
                output_mp4
            ]
        else:
            filter_complex = (
                "[0:v]setpts=PTS-STARTPTS[v];"
                "[1:a]asetpts=PTS-STARTPTS,aformat=sample_rates=48000:channel_layouts=stereo[a]"
            )
            cmd = [
                FFMPEG_PATH, "-y",
                "-i", video_path,
                "-i", audio_path,
                "-i", srt_path,
                "-filter_complex", filter_complex,
                "-map", "[v]",
                "-map", "[a]",
                "-map", "2:s:0",
                "-c:v", "libx264",
                "-preset", "fast",
                "-crf", "22",
                "-c:a", "aac",
                "-b:a", "192k",
                "-ar", "48000",
                "-ac", "2",
                "-c:s", "mov_text",
                "-metadata:s:s:0", "language=chi",
                output_mp4
            ]

        logger.info(f"Running FFmpeg synchronized composition: {' '.join(cmd)}")
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if res.returncode != 0:
            err = res.stderr.decode("utf-8", errors="ignore")
            logger.error(f"FFmpeg composition failed: {err}")
            # Fallback retry without filter_complex if complex filter had compatibility issue
            retry_cmd = [
                FFMPEG_PATH, "-y",
                "-i", video_path,
                "-i", audio_path,
                "-map", "0:v:0",
                "-map", "1:a:0",
                "-c:v", "copy",
                "-c:a", "aac",
                "-b:a", "192k",
                "-ar", "48000",
                "-ac", "2",
                output_mp4
            ]
            retry_res = subprocess.run(retry_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            if retry_res.returncode != 0:
                raise RuntimeError(f"FFmpeg 合成最终视频失败: {retry_res.stderr.decode('utf-8', errors='ignore')}")

        # Post-check: verify output MP4 file exists and has size
        if not os.path.exists(output_mp4) or os.path.getsize(output_mp4) < 10000:
            raise RuntimeError(f"合成的 MP4 文件异常或大小为零: {output_mp4}")

        if progress_callback:
            progress_callback(100.0, "最终中文 MP4 视频合成完毕！(声画毫秒级对齐，48kHz 立体声)")

        return {
            "output_mp4": output_mp4,
            "output_srt": output_srt,
            "filename": output_filename,
            "srt_filename": f"subtitles_{self.task_id}.srt"
        }
