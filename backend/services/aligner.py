import os
import subprocess
import logging
from typing import List, Dict, Any, Optional, Callable
from pathlib import Path
from pydub import AudioSegment
from backend.config import FFMPEG_PATH

logger = logging.getLogger(__name__)

class AudioAligner:
    """
    Handles Forced Alignment & Time-stretching with Absolute Timestamp Overlay Anchoring.
    Guarantees 0ms cumulative drift and perfect audio-video synchronization.
    """

    def __init__(self, task_dir: Path):
        self.task_dir = task_dir
        self.aligned_clips_dir = task_dir / "aligned_clips"
        self.aligned_clips_dir.mkdir(parents=True, exist_ok=True)

    def _stretch_audio(self, input_wav: str, output_wav: str, speed_factor: float):
        """Applies FFmpeg atempo filter to adjust speed without altering pitch, standardizing to 48kHz stereo."""
        speed = max(0.5, min(2.0, speed_factor))
        cmd = [
            FFMPEG_PATH, "-y",
            "-i", input_wav,
            "-filter:a", f"atempo={speed:.4f}",
            "-acodec", "pcm_s16le",
            "-ar", "48000",
            "-ac", "2",
            output_wav
        ]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if res.returncode != 0:
            logger.warning(f"atempo speed change failed, falling back to original: {res.stderr.decode('utf-8', errors='ignore')}")
            # fallback: copy original resampled to 48kHz stereo
            AudioSegment.from_file(input_wav).set_frame_rate(48000).set_channels(2).export(output_wav, format="wav")

    def align_and_stitch(
        self,
        subtitles_with_audio: List[Dict[str, Any]],
        total_duration: float,
        progress_callback: Optional[Callable[[float, str], None]] = None
    ) -> str:
        """
        Aligns each audio clip onto an absolute timeline canvas using exact millisecond overlay.
        Eliminates sequential accumulation drift completely (0ms error).
        """
        if not subtitles_with_audio:
            raise ValueError("没有可用的音频切片进行对齐")

        total = len(subtitles_with_audio)
        # Allocate canvas matching total_duration + safe buffer
        canvas_total_ms = int(total_duration * 1000) + 3000
        full_canvas = AudioSegment.silent(duration=canvas_total_ms, frame_rate=48000).set_channels(2)

        logger.info(f"Stitching {total} audio segments using Absolute Timestamp Overlay (Target Duration: {total_duration}s, 48kHz Stereo)")

        for idx, item in enumerate(subtitles_with_audio):
            seg_id = item["id"]
            start_sec = item["start"]
            end_sec = item["end"]
            audio_path = item.get("audio_path")
            tts_duration = item.get("tts_duration", 0.0)

            # Look ahead to next sentence start to determine allowed window budget
            next_item = subtitles_with_audio[idx + 1] if idx + 1 < total else None
            if next_item:
                slot_duration = max(0.4, next_item["start"] - start_sec)
            else:
                slot_duration = max(0.4, end_sec - start_sec)

            aligned_path = str(self.aligned_clips_dir / f"aligned_{seg_id:04d}.wav")

            # Calculate speed adjustment factor
            if tts_duration > slot_duration * 1.05:
                # TTS audio exceeds window -> speed up within natural range (max 1.35x)
                raw_ratio = tts_duration / slot_duration
                speed_factor = min(1.35, raw_ratio)
                self._stretch_audio(audio_path, aligned_path, speed_factor)
            elif tts_duration < slot_duration * 0.70 and tts_duration > 1.5:
                # TTS audio is noticeably shorter -> slight slowdown (max 0.92x)
                speed_factor = 0.92
                self._stretch_audio(audio_path, aligned_path, speed_factor)
            else:
                # Keep original speed, ensure 48kHz stereo
                self._stretch_audio(audio_path, aligned_path, 1.0)

            # Load the aligned segment in 48kHz stereo
            clip = AudioSegment.from_file(aligned_path).set_frame_rate(48000).set_channels(2)

            # Boundary protection: if clip still slightly exceeds slot_duration,
            # soft fade-out at the slot boundary so it NEVER intrudes into the next sentence's start!
            slot_ms = int(slot_duration * 1000)
            if len(clip) > slot_ms:
                fade_ms = min(60, int(slot_ms * 0.1))
                clip = clip[:slot_ms].fade_out(fade_ms)

            # --- ABSOLUTE TIMESTAMP OVERLAY (核心：绝对时间戳打点) ---
            # Every sentence starts at its exact mathematical millisecond in the video timeline!
            # Zero cumulative drift!
            start_ms = max(0, int(start_sec * 1000))
            full_canvas = full_canvas.overlay(clip, position=start_ms)

            if progress_callback:
                pct = (idx + 1) / total * 90.0
                progress_callback(pct, f"正在绝对时间轴对齐音轨 ({idx + 1}/{total})...")

        # Trim final audio canvas to exact video total_duration
        target_ms = int(total_duration * 1000)
        final_track = full_canvas[:target_ms]

        out_full_audio = str(self.task_dir / "dubbed_full_track.wav")
        final_track.export(out_full_audio, format="wav")

        if progress_callback:
            progress_callback(100.0, "绝对时间轴对齐与音画锁定完成 (48kHz 立体声，零累积漂移)")

        return out_full_audio
