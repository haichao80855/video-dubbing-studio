"""Translate with full context and dub on the source video's absolute timeline."""

import logging
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple, TYPE_CHECKING

from pydub import AudioSegment

from backend.services.aligner import AudioAligner
from backend.services.pacing import DEFAULT_SPEAKING_RATE

if TYPE_CHECKING:
    from backend.services.translator import DeepSeekTranslator
    from backend.services.f5_tts_mlx import F5TTSMLXService

logger = logging.getLogger(__name__)


class ContinuousFlowDubber:
    def __init__(self, task_dir: Path):
        self.task_dir = task_dir
        self.tts_clips_dir = task_dir / "continuous_clips"
        self.tts_clips_dir.mkdir(parents=True, exist_ok=True)

    def extract_full_narrative(self, raw_segments: List[Dict[str, Any]]) -> Dict[str, Any]:
        start = raw_segments[0]["start"] if raw_segments else 0.0
        end = raw_segments[-1]["end"] if raw_segments else 0.0
        return {
            "full_text": " ".join(s.get("text", "").strip() for s in raw_segments).strip(),
            "global_start": start,
            "global_end": end,
            "total_speech_duration": end - start,
            "segment_count": len(raw_segments),
            "segments": raw_segments,
        }

    def translate_full_flow(
        self,
        narrative_info: Dict[str, Any],
        translator: "DeepSeekTranslator",
        progress_callback: Optional[Callable[[float, str], None]] = None,
        source_language: str = "auto",
        speaking_rate: float = DEFAULT_SPEAKING_RATE,
    ) -> List[Dict[str, Any]]:
        # Give the translator the full narrative without losing source segment IDs.
        return translator.translate_segments(
            narrative_info["segments"],
            source_language=source_language,
            progress_callback=progress_callback,
            full_context=narrative_info["full_text"],
            speaking_rate=speaking_rate,
        )

    def synthesize_and_stitch_continuous(
        self,
        subtitles: List[Dict[str, Any]],
        f5_service: "F5TTSMLXService",
        global_start_sec: float,
        video_total_duration: float,
        speed_mode: str = "balanced",
        progress_callback: Optional[Callable[[float, str], None]] = None,
        speaking_rate: float = DEFAULT_SPEAKING_RATE,
    ) -> Tuple[str, List[Dict[str, Any]]]:
        # global_start_sec is retained for callers; every segment has its own anchor.
        aligner = AudioAligner(self.task_dir)
        aligner.validate_timeline(subtitles, video_total_duration)
        canvas = AudioSegment.silent(
            duration=round(video_total_duration * 1000), frame_rate=48000
        ).set_channels(2)
        updated = []
        for index, item in enumerate(subtitles, 1):
            slot_duration = item["end"] - item["start"]
            output = str(self.tts_clips_dir / f"flow_{item['id']:04d}.wav")
            try:
                f5_service.synthesize(
                    item.get("translated_text", "").strip(), output,
                    speed_mode=speed_mode, target_duration=slot_duration,
                    speaking_rate=speaking_rate,
                )
                clip, aligned_path = aligner.prepare_clip(output, slot_duration, item["id"])
            except (ValueError, RuntimeError) as error:
                raise RuntimeError(f"配音段落 #{item['id']}: {error}") from error
            start_ms = round(item["start"] * 1000)
            canvas = canvas.overlay(clip, position=start_ms)
            updated.append({
                **item,
                "audio_path": aligned_path,
                "tts_duration": len(clip) / 1000.0,
                "audio_end": round(item["start"] + len(clip) / 1000.0, 3),
            })
            if progress_callback:
                progress_callback(
                    index / len(subtitles) * 100,
                    f"按原时间轴生成原声克隆配音 ({index}/{len(subtitles)})...",
                )
        final_audio = str(self.task_dir / "dubbed_full_track.wav")
        canvas.export(final_audio, format="wav")
        logger.info("Dubbed %d source segments on a %.3fs timeline", len(updated), video_total_duration)
        return final_audio, updated
