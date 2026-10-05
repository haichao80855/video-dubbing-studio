"""Speech timing shared by previews and the video dubbing pipeline."""

import math
from typing import Optional

DEFAULT_SPEAKING_RATE = 3.8
MAX_TEMPO_FACTOR = 1.1
SAMPLE_RATE = 24000
HOP_LENGTH = 256
MAX_DURATION_FRAMES = 4096


def speech_character_count(text: str) -> int:
    """Count letters/numbers, excluding whitespace and punctuation."""
    return sum(character.isalnum() for character in text)


def resolve_speech_duration(
    text: str,
    target_duration: Optional[float] = None,
    speaking_rate: float = DEFAULT_SPEAKING_RATE,
) -> float:
    if not math.isfinite(speaking_rate) or speaking_rate <= 0:
        raise ValueError("朗读语速必须为正数")
    characters = speech_character_count(text)
    if not characters:
        raise ValueError("配音文案必须包含有效文字")
    natural_duration = max(0.3, characters / speaking_rate)
    if target_duration is None:
        return natural_duration
    if not math.isfinite(target_duration) or target_duration <= 0:
        raise ValueError("配音时间窗口必须为正数")
    if natural_duration > target_duration * MAX_TEMPO_FACTOR:
        recommended = max(1, int(target_duration * speaking_rate))
        raise ValueError(
            f"文案有 {characters} 字，无法在 {target_duration:.2f} 秒内自然读完；"
            f"请精简到约 {recommended} 字，或调整朗读语速"
        )
    # Short sentences finish naturally; unused time remains at its original place.
    return min(natural_duration, target_duration)


def duration_frames_for_speech(reference_samples: int, speech_duration: float) -> int:
    """F5's duration includes the reference, not just the generated speech."""
    if reference_samples <= 0 or not math.isfinite(speech_duration) or speech_duration <= 0:
        raise ValueError("参考音频与生成时长必须有效")
    frames = math.ceil((reference_samples + speech_duration * SAMPLE_RATE) / HOP_LENGTH)
    if frames > MAX_DURATION_FRAMES:
        raise ValueError("配音段落过长，请拆分段落或缩短参考音频，避免模型截断句尾")
    return frames
