import os
import subprocess
import logging
from typing import List, Dict, Any, Optional, Callable
from pathlib import Path
from pydub import AudioSegment
from backend.config import FFMPEG_PATH

logger = logging.getLogger(__name__)

class AudioAligner:
    """Handles Forced Alignment & Time-stretching for video dubbing timeline matching."""

    def __init__(self, task_dir: Path):
        self.task_dir = task_dir
        self.aligned_clips_dir = task_dir / "aligned_clips"
        self.aligned_clips_dir.mkdir(parents=True, exist_ok=True)

    def _stretch_audio(self, input_wav: str, output_wav: str, speed_factor: float):
        """Applies FFmpeg atempo filter to adjust speed without altering pitch."""
        # atempo valid range in ffmpeg is 0.5 to 2.0 per filter instance
        speed = max(0.5, min(2.0, speed_factor))
        cmd = [
            FFMPEG_PATH, "-y",
            "-i", input_wav,
            "-filter:a", f"atempo={speed:.4f}",
            "-acodec", "pcm_s16le",
            "-ar", "16000",
            "-ac", "1",
            output_wav
        ]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if res.returncode != 0:
            logger.warning(f"atempo speed change failed, falling back to original: {res.stderr.decode('utf-8', errors='ignore')}")
            # fallback: copy original
            AudioSegment.from_file(input_wav).export(output_wav, format="wav")

    def align_and_stitch(
        self,
        subtitles_with_audio: List[Dict[str, Any]],
        total_duration: float,
        progress_callback: Optional[Callable[[float, str], None]] = None
    ) -> str:
        """
        Aligns each audio clip with original sentence slot using time-stretching,
        and stitches all segments into a complete continuous dubbing track.
        """
        if not subtitles_with_audio:
            raise ValueError("没有可用的音频切片进行对齐")

        total = len(subtitles_with_audio)
        full_track = AudioSegment.silent(duration=0, frame_rate=16000)
        current_ms = 0

        logger.info(f"Stitching {total} audio segments into timeline (Target Duration: {total_duration}s)")

        for idx, item in enumerate(subtitles_with_audio):
            seg_id = item["id"]
            start_sec = item["start"]
            end_sec = item["end"]
            target_duration = max(0.2, end_sec - start_sec)
            audio_path = item.get("audio_path")
            tts_duration = item.get("tts_duration", 0.0)

            aligned_path = str(self.aligned_clips_dir / f"aligned_{seg_id:04d}.wav")

            # Calculate speed adjustment factor
            if tts_duration > target_duration * 1.05:
                # TTS audio is longer than original slot -> speed up
                raw_ratio = tts_duration / target_duration
                # Cap speedup to 1.35x to maintain natural voice quality
                speed_factor = min(1.35, raw_ratio)
                self._stretch_audio(audio_path, aligned_path, speed_factor)
            elif tts_duration < target_duration * 0.70 and tts_duration > 1.5:
                # TTS audio is significantly shorter, slight slowdown (max 0.9x) or keep original
                speed_factor = 0.92
                self._stretch_audio(audio_path, aligned_path, speed_factor)
            else:
                # Keep original speed
                aligned_path = audio_path

            # Load the aligned segment
            clip = AudioSegment.from_file(aligned_path)
            target_start_ms = int(start_sec * 1000)

            # Insert silence if there is a gap before this segment
            if target_start_ms > current_ms:
                gap_ms = target_start_ms - current_ms
                full_track += AudioSegment.silent(duration=gap_ms, frame_rate=16000)
                current_ms = target_start_ms

            # Append audio clip
            full_track += clip
            current_ms += len(clip)

            if progress_callback:
                pct = (idx + 1) / total * 90.0
                progress_callback(pct, f"正在对齐时间轴与拼接音轨 ({idx + 1}/{total})...")

        # Fill remaining time with silence up to total_duration
        target_total_ms = int(total_duration * 1000)
        if target_total_ms > current_ms:
            tail_gap = target_total_ms - current_ms
            full_track += AudioSegment.silent(duration=tail_gap, frame_rate=16000)

        out_full_audio = str(self.task_dir / "dubbed_full_track.wav")
        full_track.export(out_full_audio, format="wav")

        if progress_callback:
            progress_callback(100.0, "完整中文配音轨对齐与缝合完成")

        return out_full_audio
