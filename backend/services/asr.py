import os
import logging
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional, Callable
from pathlib import Path
from backend.config import DEFAULT_MLX_WHISPER_MODEL

logger = logging.getLogger(__name__)

class BaseASREngine(ABC):
    """Abstract Base Class for ASR Engines (MLX-Whisper, Qwen-Audio MLX, SenseVoice)."""

    @abstractmethod
    def transcribe(
        self,
        audio_path: str,
        progress_callback: Optional[Callable[[float, str], None]] = None
    ) -> Dict[str, Any]:
        """Transcribe audio into timestamped segments."""
        pass

class MLXWhisperEngine(BaseASREngine):
    """Apple Silicon Metal accelerated Whisper ASR using mlx-whisper."""

    def __init__(self, model_name: str = DEFAULT_MLX_WHISPER_MODEL):
        self.model_name = model_name

    def transcribe(
        self,
        audio_path: str,
        progress_callback: Optional[Callable[[float, str], None]] = None
    ) -> Dict[str, Any]:
        import mlx_whisper

        if progress_callback:
            progress_callback(10.0, f"加载 MLX ASR 模型 ({self.model_name})...")

        logger.info(f"Starting MLX ASR with model: {self.model_name} on {audio_path}")

        if progress_callback:
            progress_callback(30.0, "利用 Apple Silicon GPU 硬件加速进行高精度语音识别与词级时间戳提取...")

        # Run transcribe with word timestamps enabled
        result = mlx_whisper.transcribe(
            audio_path,
            path_or_hf_repo=self.model_name,
            word_timestamps=True,
            verbose=False
        )

        detected_lang = result.get("language", "en")
        raw_segments = result.get("segments", [])

        normalized_segments: List[Dict[str, Any]] = []
        for idx, seg in enumerate(raw_segments, 1):
            text = seg.get("text", "").strip()
            if not text:
                continue
            normalized_segments.append({
                "id": idx,
                "start": round(seg.get("start", 0.0), 3),
                "end": round(seg.get("end", 0.0), 3),
                "duration": round(seg.get("end", 0.0) - seg.get("start", 0.0), 3),
                "text": text,
                "words": seg.get("words", [])
            })

        if progress_callback:
            progress_callback(100.0, f"语音识别完成，共识别出 {len(normalized_segments)} 个语句片段 (语言: {detected_lang})")

        return {
            "language": detected_lang,
            "segments": normalized_segments
        }

def get_asr_engine(engine_type: str = "mlx_whisper", model_name: Optional[str] = None) -> BaseASREngine:
    """Factory to instantiate ASR engine."""
    model = model_name or DEFAULT_MLX_WHISPER_MODEL
    return MLXWhisperEngine(model_name=model)
