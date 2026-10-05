import os
import subprocess
import logging
from typing import List, Dict, Any, Optional
from pathlib import Path
from backend.config import FFMPEG_PATH

logger = logging.getLogger(__name__)

class SpeakerExtractor:
    """Extracts a clean, representative speech segment from the video audio as reference voice."""

    def __init__(self, task_dir: Path):
        self.task_dir = task_dir

    def find_best_reference_segment(self, segments: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """
        Scans ASR segments to find the best candidate for voice cloning:
        - Duration ideally between 3.5s and 6.5s
        - Clear speech without error markers
        - Good word count and natural pace
        """
        if not segments:
            return None

        # Filter candidates: duration between 3.0s and 8.0s
        valid_candidates = []
        for seg in segments:
            dur = seg.get("end", 0.0) - seg.get("start", 0.0)
            text = seg.get("text", "").strip()
            if 3.0 <= dur <= 8.0 and len(text) > 5 and not text.startswith("["):
                valid_candidates.append(seg)

        if not valid_candidates:
            # Fallback: look for 2.0s to 10.0s
            for seg in segments:
                dur = seg.get("end", 0.0) - seg.get("start", 0.0)
                text = seg.get("text", "").strip()
                if 2.0 <= dur <= 10.0 and len(text) > 3:
                    valid_candidates.append(seg)

        if not valid_candidates:
            # Ultimate fallback: return first segment
            return segments[0]

        # Score candidates: optimal duration is around 4.5s
        def score_segment(s):
            dur = s["end"] - s["start"]
            # Distance from ideal 4.5s duration
            dur_score = 10.0 - abs(dur - 4.5)
            # Length of text
            text_len = len(s.get("text", "").strip())
            return dur_score + min(text_len * 0.1, 5.0)

        valid_candidates.sort(key=score_segment, reverse=True)
        return valid_candidates[0]

    def extract_audio_clip(
        self,
        full_audio_path: str,
        start_sec: float,
        end_sec: float,
        output_wav_path: str,
        sample_rate: int = 24000
    ) -> str:
        """
        Extracts high quality mono PCM WAV clip from full_audio_path.
        24kHz is native for F5-TTS.
        """
        duration = max(0.5, end_sec - start_sec)
        cmd = [
            FFMPEG_PATH, "-y",
            "-ss", f"{start_sec:.3f}",
            "-t", f"{duration:.3f}",
            "-i", full_audio_path,
            "-acodec", "pcm_s16le",
            "-ar", str(sample_rate),
            "-ac", "1",
            output_wav_path
        ]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if res.returncode != 0:
            err = res.stderr.decode("utf-8", errors="ignore")
            logger.error(f"FFmpeg extract speaker clip failed: {err}")
            raise RuntimeError(f"提取参考原声音频失败: {err}")

        return output_wav_path

    def prepare_speaker_reference(
        self,
        full_audio_path: str,
        segments: List[Dict[str, Any]],
        chosen_segment_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Prepares and exports ref_speaker.wav.
        Returns metadata: segment_id, start, end, duration, ref_text, audio_path.
        """
        best_seg = None
        if chosen_segment_id is not None:
            for s in segments:
                if s["id"] == chosen_segment_id:
                    best_seg = s
                    break

        if not best_seg:
            best_seg = self.find_best_reference_segment(segments)

        if not best_seg:
            raise ValueError("未能找到有效的原声参考片段")

        ref_wav = str(self.task_dir / "ref_speaker.wav")
        self.extract_audio_clip(
            full_audio_path=full_audio_path,
            start_sec=best_seg["start"],
            end_sec=best_seg["end"],
            output_wav_path=ref_wav,
            sample_rate=24000
        )

        return {
            "segment_id": best_seg["id"],
            "start": best_seg["start"],
            "end": best_seg["end"],
            "duration": round(best_seg["end"] - best_seg["start"], 3),
            "ref_text": best_seg.get("text", "").strip(),
            "audio_path": ref_wav
        }
