"""Place speech at source timestamps without accumulating timing drift."""

import math
import subprocess
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from pydub import AudioSegment

from backend.config import FFMPEG_PATH
from backend.services.pacing import MAX_TEMPO_FACTOR


class AudioAligner:
    def __init__(self, task_dir: Path):
        self.aligned_clips_dir = task_dir / "aligned_clips"
        self.aligned_clips_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def validate_timeline(subtitles: List[Dict[str, Any]], total_duration: float):
        if not subtitles:
            raise ValueError("没有可用的配音段落")
        if not math.isfinite(total_duration) or total_duration <= 0:
            raise ValueError("视频时长无效")
        previous_end = 0.0
        seen_ids = set()
        for item in subtitles:
            start, end = float(item["start"]), float(item["end"])
            if not all(math.isfinite(t) for t in (start, end)) or start < 0 or end <= start:
                raise ValueError(f"段落 #{item['id']} 的时间窗口无效")
            if end > total_duration + 0.001:
                raise ValueError(f"段落 #{item['id']} 超出视频时长")
            if start < previous_end - 0.001:
                raise ValueError(f"段落 #{item['id']} 的时间窗口重叠或顺序错误")
            if item["id"] in seen_ids:
                raise ValueError("配音段落 ID 重复")
            seen_ids.add(item["id"])
            previous_end = end

    def _stretch_audio(self, input_wav: str, output_wav: str, speed_factor: float):
        if not 1.0 <= speed_factor <= MAX_TEMPO_FACTOR:
            raise ValueError("变速幅度超出自然朗读范围")
        result = subprocess.run(
            [FFMPEG_PATH, "-y", "-i", input_wav,
             "-filter:a", f"atempo={speed_factor:.8f}",
             "-acodec", "pcm_s16le", "-ar", "48000", "-ac", "2", output_wav],
            capture_output=True, timeout=60,
        )
        if result.returncode:
            raise RuntimeError(f"音频变速失败: {result.stderr.decode('utf-8', errors='replace')[-1000:]}")

    def prepare_clip(self, audio_path: str, slot_duration: float, segment_id: int) -> Tuple[AudioSegment, str]:
        if not math.isfinite(slot_duration) or slot_duration <= 0:
            raise ValueError("配音时间窗口无效")
        clip = AudioSegment.from_file(audio_path).set_frame_rate(48000).set_channels(2)
        if len(clip) < 50 or clip.rms == 0:
            raise RuntimeError("生成的配音为空或无声")
        slot_ms = round(slot_duration * 1000)
        if slot_ms < 1:
            raise ValueError("配音时间窗口过短")
        aligned_path = str(self.aligned_clips_dir / f"aligned_{segment_id:04d}.wav")
        if len(clip) > slot_ms:
            ratio = len(clip) / slot_ms
            if ratio > MAX_TEMPO_FACTOR:
                raise ValueError(
                    f"配音长 {len(clip)/1000:.2f} 秒，超过 {slot_duration:.2f} 秒窗口；"
                    "请精简文案或重新生成，不能截断句尾"
                )
            # Small headroom accounts for FFmpeg's tempo-filter frame rounding.
            self._stretch_audio(audio_path, aligned_path, min(MAX_TEMPO_FACTOR, ratio * 1.01))
            clip = AudioSegment.from_file(aligned_path).set_frame_rate(48000).set_channels(2)
            if len(clip) > slot_ms:
                # Only discard genuine trailing silence, never spoken content.
                if clip[slot_ms:].rms != 0:
                    raise RuntimeError("轻微变速后仍超出窗口，请精简文案或重新生成")
                clip = clip[:slot_ms]
        clip.export(aligned_path, format="wav")
        return clip, aligned_path

    def align_and_stitch(
        self, subtitles_with_audio: List[Dict[str, Any]], total_duration: float,
        progress_callback: Optional[Callable[[float, str], None]] = None,
    ) -> str:
        self.validate_timeline(subtitles_with_audio, total_duration)
        canvas = AudioSegment.silent(duration=round(total_duration * 1000), frame_rate=48000).set_channels(2)
        for index, item in enumerate(subtitles_with_audio, 1):
            clip, _ = self.prepare_clip(item["audio_path"], item["end"] - item["start"], item["id"])
            canvas = canvas.overlay(clip, position=round(item["start"] * 1000))
            if progress_callback:
                progress_callback(index / len(subtitles_with_audio) * 100, f"按原时间轴对齐 ({index}/{len(subtitles_with_audio)})...")
        output = str(self.aligned_clips_dir.parent / "dubbed_full_track.wav")
        canvas.export(output, format="wav")
        return output
