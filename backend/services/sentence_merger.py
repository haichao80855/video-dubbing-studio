import re
import logging
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

class SentenceMerger:
    """
    Merges fragmented ASR micro-segments into complete, natural semantic long sentences (8~14s).
    Eliminates choppy sentence-by-sentence intonation and awkward 1s pauses.
    """

    def __init__(self, min_duration: float = 6.0, target_duration: float = 11.0, max_duration: float = 15.5):
        self.min_duration = min_duration
        self.target_duration = target_duration
        self.max_duration = max_duration

    def _is_terminal_punctuation(self, text: str) -> bool:
        """Checks if text ends with a strong sentence terminator (. ! ? 。 ！ ？)."""
        stripped = text.strip()
        if not stripped:
            return False
        last_char = stripped[-1]
        return last_char in {".", "!", "?", "。", "！", "？"}

    def _ends_with_conjunction(self, text: str) -> bool:
        """Checks if text ends with a dangling conjunction/preposition that should flow into next segment."""
        stripped = text.strip().lower()
        dangling_words = {
            "and", "but", "or", "so", "because", "which", "that", "to",
            "with", "for", "as", "if", "when", "where", "while", "then",
            "is", "are", "was", "were", "be", "been", "the", "a", "an"
        }
        tokens = re.findall(r"\b\w+\b", stripped)
        if tokens and tokens[-1] in dangling_words:
            return True
        return False

    def merge_segments(self, raw_segments: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Merges Whisper micro-segments into natural semantic sentences.
        Reduces 80+ fragmented clips into 20~30 coherent speech blocks.
        """
        if not raw_segments:
            return []

        merged: List[Dict[str, Any]] = []
        current_group: List[Dict[str, Any]] = []
        current_start = raw_segments[0]["start"]

        for idx, seg in enumerate(raw_segments):
            current_group.append(seg)
            accumulated_dur = seg["end"] - current_start
            text = seg.get("text", "").strip()

            is_terminal = self._is_terminal_punctuation(text)
            is_dangling = self._ends_with_conjunction(text)
            is_last = (idx == len(raw_segments) - 1)

            # Check next segment distance
            next_seg = raw_segments[idx + 1] if not is_last else None
            gap_to_next = (next_seg["start"] - seg["end"]) if next_seg else 0.0

            should_split = False

            if is_last:
                should_split = True
            elif accumulated_dur >= self.max_duration:
                # Exceeds max comfortable duration for diffusion TTS
                should_split = True
            elif accumulated_dur >= self.min_duration and is_terminal and not is_dangling:
                # Strong sentence ending with sufficient length
                should_split = True
            elif accumulated_dur >= self.target_duration and (is_terminal or gap_to_next > 0.6):
                # Reached target length at natural pause or clause
                should_split = True
            elif gap_to_next > 1.2:
                # Keep scene/demo pauses even after a short instruction.
                should_split = True

            if should_split and current_group:
                merged_text = " ".join(s.get("text", "").strip() for s in current_group)
                # Clean up spaces
                merged_text = re.sub(r"\s+", " ", merged_text).strip()

                merged_item = {
                    "id": len(merged) + 1,
                    "start": round(current_start, 3),
                    "end": round(seg["end"], 3),
                    "duration": round(seg["end"] - current_start, 3),
                    "text": merged_text,
                    "sub_segments": [
                        {
                            "id": s.get("id"),
                            "start": s.get("start"),
                            "end": s.get("end"),
                            "text": s.get("text")
                        }
                        for s in current_group
                    ]
                }
                merged.append(merged_item)

                # Reset for next group
                current_group = []
                if next_seg:
                    current_start = next_seg["start"]

        logger.info(f"SentenceMerger: Consolidated {len(raw_segments)} fragmented clips into {len(merged)} natural semantic sentences (Reduced by {(1 - len(merged)/len(raw_segments))*100:.1f}%)")
        return merged
