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
    Handles Forced Alignment & Time-stretching with Smart Silence Compression and Absolute Timeline Anchoring.
    Eliminates awkward 1-second dead silences, creating a tight, fluid, human-like voiceover flow.
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
        Aligns each audio clip onto an absolute timeline canvas using smart silence compression.
        Eliminates the awkward 1s dead silences between sentences and guarantees zero cumulative drift.
        """
        if not subtitles_with_audio:
            raise ValueError("没有可用的音频切片进行对齐")

        total = len(subtitles_with_audio)
        canvas_total_ms = int(total_duration * 1000) + 4000
        full_canvas = AudioSegment.silent(duration=canvas_total_ms, frame_rate=48000).set_channels(2)

        logger.info(f"Stitching {total} merged sentences with Smart Silence Compression (Target Duration: {total_duration}s, 48kHz Stereo)")

        current_playhead_ms = 0
        NATURAL_BREATH_PAUSE_MS = 220  # 0.22s human-like breath pause between sentences

        for idx, item in enumerate(subtitles_with_audio):
            seg_id = item["id"]
            start_sec = item["start"]
            end_sec = item["end"]
            audio_path = item.get("audio_path")
            tts_duration = item.get("tts_duration", 0.0)

            # Look ahead to next sentence to determine slot budget
            next_item = subtitles_with_audio[idx + 1] if idx + 1 < total else None
            if next_item:
                slot_duration = max(0.4, next_item["start"] - start_sec)
            else:
                slot_duration = max(0.4, end_sec - start_sec)

            aligned_path = str(self.aligned_clips_dir / f"aligned_{seg_id:04d}.wav")

            # Calculate speed adjustment factor
            if tts_duration > slot_duration * 1.05:
                raw_ratio = tts_duration / slot_duration
                speed_factor = min(1.35, raw_ratio)
                self._stretch_audio(audio_path, aligned_path, speed_factor)
            elif tts_duration < slot_duration * 0.70 and tts_duration > 1.8:
                speed_factor = 0.92
                self._stretch_audio(audio_path, aligned_path, speed_factor)
            else:
                self._stretch_audio(audio_path, aligned_path, 1.0)

            # Load the aligned segment in 48kHz stereo
            clip = AudioSegment.from_file(aligned_path).set_frame_rate(48000).set_channels(2)

            # Boundary protection: soft fade-out if slightly overflowing
            slot_ms = int(slot_duration * 1000)
            if len(clip) > slot_ms:
                fade_ms = min(60, int(slot_ms * 0.1))
                clip = clip[:slot_ms].fade_out(fade_ms)

            # --- SMART SILENCE COMPRESSION & TIMELINE POSITIONING ---
            target_start_ms = max(0, int(start_sec * 1000))

            if idx == 0:
                # First sentence starts at its original timestamp
                actual_start_ms = target_start_ms
            else:
                # Calculate gap from previous sentence playhead
                gap_ms = target_start_ms - current_playhead_ms
                if gap_ms > 400 and gap_ms < 1800:
                    # Awkward speaking pause (0.4s ~ 1.8s): compress to natural breath pause
                    # Allows smooth flow while keeping anchor within a close bound of the scene
                    compressed_start = current_playhead_ms + NATURAL_BREATH_PAUSE_MS
                    # Blend slightly toward target_start to maintain visual anchor
                    actual_start_ms = max(compressed_start, target_start_ms - 400)
                else:
                    # Short gap or long scene cut (>1.8s): respect original anchor
                    actual_start_ms = max(current_playhead_ms + 100, target_start_ms)

            # Overlay clip onto canvas
            full_canvas = full_canvas.overlay(clip, position=actual_start_ms)
            current_playhead_ms = actual_start_ms + len(clip)

            if progress_callback:
                pct = (idx + 1) / total * 90.0
                progress_callback(pct, f"正在进行连贯语流对齐 ({idx + 1}/{total})...")

        # Trim final audio canvas to exact video total_duration
        target_ms = int(total_duration * 1000)
        final_track = full_canvas[:target_ms]

        out_full_audio = str(self.task_dir / "dubbed_full_track.wav")
        final_track.export(out_full_audio, format="wav")

        if progress_callback:
            progress_callback(100.0, "连贯语流与停顿压缩对齐完成 (48kHz 双声道，自然行云流水)")

        return out_full_audio
