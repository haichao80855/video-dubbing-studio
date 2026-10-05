import os
import subprocess
import logging
from typing import List, Dict, Any, Optional, Callable
from pathlib import Path
from backend.config import FFMPEG_PATH, OUTPUTS_DIR, select_composition_ffmpeg

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

def wrap_subtitle_text(text: str) -> str:
    """Splits long sentences at comma/period into comfortable 2-line subtitles."""
    clean = text.strip()
    if len(clean) > 28 and ("，" in clean or " " in clean):
        mid = len(clean) // 2
        punctuation_indices = [i for i, ch in enumerate(clean) if ch in {"，", "、", " ", "；"}]
        if punctuation_indices:
            best_idx = min(punctuation_indices, key=lambda i: abs(i - mid))
            return clean[:best_idx + 1].strip() + "\n" + clean[best_idx + 1:].strip()
    return clean

class VideoComposer:
    """
    Composites dubbed audio, subtitles, and video stream into final Chinese MP4.
    Normalizes stream timestamps after speech has been aligned to source segments.
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
                raw_text = item.get("translated_text", "").strip() or item.get("text", "").strip()
                formatted_text = wrap_subtitle_text(raw_text)
                f.write(f"{idx}\n")
                f.write(f"{start_str} --> {end_str}\n")
                f.write(f"{formatted_text}\n\n")
        return str(srt_path)

    def compose_video(
        self,
        video_path: str,
        audio_path: str,
        subtitles: List[Dict[str, Any]],
        hard_sub: bool = True,
        progress_callback: Optional[Callable[[float, str], None]] = None
    ) -> Dict[str, Any]:
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

        # Ensure audio_path is valid and non-empty
        if not os.path.exists(audio_path) or os.path.getsize(audio_path) < 4096:
            raise RuntimeError(f"合成所需的配音音轨文件异常或为空: {audio_path}")

        ffmpeg_path, use_hard_sub = select_composition_ffmpeg(FFMPEG_PATH, hard_sub)
        warnings = []
        if hard_sub and not use_hard_sub:
            warning = "FFmpeg 缺少字幕压制滤镜，已改为可切换软字幕；请用支持字幕轨道的播放器打开 MP4，或下载 SRT 字幕。"
            warnings.append(warning)
            logger.warning(warning)
            if progress_callback:
                progress_callback(20.0, warning)
        if progress_callback:
            progress_callback(30.0, f"正在进行音画时钟精准对齐与 FFmpeg 封装 ({'硬' if use_hard_sub else '软'}字幕)...")

        # Browsers often cannot display an MP4 mov_text track. Supply WebVTT for preview.
        vtt_filename = f"subtitles_{self.task_id}.vtt" if not use_hard_sub else None
        if vtt_filename:
            with open(OUTPUTS_DIR / vtt_filename, "w", encoding="utf-8") as vtt:
                vtt.write("WEBVTT\n\n")
                for item in subtitles:
                    start = format_timestamp_srt(item["start"]).replace(",", ".")
                    end = format_timestamp_srt(item["end"]).replace(",", ".")
                    text = item.get("translated_text", "").strip() or item.get("text", "").strip()
                    vtt.write(f"{start} --> {end}\n{wrap_subtitle_text(text)}\n\n")

        escaped_srt = srt_path.replace("\\", "/").replace(":", "\\:").replace("'", "\\'")

        if use_hard_sub:
            # Complex filter chaining: burned subtitles + video PTS reset, and audio PTS reset + 48kHz stereo formatting
            filter_complex = (
                f"[0:v]setpts=PTS-STARTPTS,subtitles=filename='{escaped_srt}':force_style='FontSize=22,FontName=Arial,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,Outline=2,Shadow=1,MarginV=25'[v];"
                f"[1:a]asetpts=PTS-STARTPTS,aformat=sample_rates=48000:channel_layouts=stereo[a]"
            )
            cmd = [
                ffmpeg_path, "-y",
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
                ffmpeg_path, "-y",
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
                "-disposition:s:0", "default",
                output_mp4
            ]

        logger.info(f"Running FFmpeg synchronized composition: {' '.join(cmd)}")
        try:
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=3600)
        except subprocess.TimeoutExpired as error:
            raise RuntimeError("FFmpeg 合成超时（60 分钟），请检查视频长度与编码性能") from error
        if res.returncode != 0:
            err = res.stderr.decode("utf-8", errors="ignore")
            logger.error(f"FFmpeg composition failed: {err}")
            # A fallback without these filters would lose timestamp normalization/subtitles.
            raise RuntimeError(f"FFmpeg 合成失败，请检查字幕滤镜与编码器: {err[-2000:]}")

        # Post-check: verify output MP4 file exists and has size
        if not os.path.exists(output_mp4) or os.path.getsize(output_mp4) < 10000:
            raise RuntimeError(f"合成的 MP4 文件异常或大小为零: {output_mp4}")

        if progress_callback:
            progress_callback(100.0, "中文 MP4 合成完成，配音已按原句时间轴定位 (48kHz 立体声)")

        return {
            "output_mp4": output_mp4,
            "output_srt": output_srt,
            "filename": output_filename,
            "srt_filename": f"subtitles_{self.task_id}.srt",
            "vtt_filename": vtt_filename,
            "subtitle_mode": "hard" if use_hard_sub else "soft",
            "warnings": warnings,
        }
