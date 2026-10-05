import os
import logging
import math
from typing import Optional
import numpy as np
import soundfile as sf
import scipy.signal as signal
from backend.services.pacing import (
    DEFAULT_SPEAKING_RATE, duration_frames_for_speech, resolve_speech_duration,
)

# Fix MLX 0.22+ nanobind compatibility with f5_tts_mlx:
# f5_tts_mlx passes (self.num_channels, dur) where dur is an mx.array(dtype=float32),
# but MLX 0.22+ strictly expects Sequence[int], raising TypeError: normal(): incompatible function arguments.
def _patch_random_shapes(mx):
    original = mx.random.normal
    if getattr(original, "_vds_integer_shapes", False):
        return
    def safe_normal(shape=None, *args, **kwargs):
        if shape is not None and isinstance(shape, (tuple, list)):
            shape = [int(x.item() if hasattr(x, "item") else x) for x in shape]
        return original(shape, *args, **kwargs)
    safe_normal._vds_integer_shapes = True
    mx.random.normal = safe_normal

logger = logging.getLogger(__name__)

# Constants matching f5_tts_mlx
SAMPLE_RATE = 24000
HOP_LENGTH = 256
FRAMES_PER_SEC = SAMPLE_RATE / HOP_LENGTH
TARGET_RMS = 0.1

class F5TTSModelHolder:
    """Singleton model cache to avoid reloading F5TTS weights on every generation."""
    _instance = None
    _model = None
    _model_name = "lucasnewman/f5-tts-mlx"

    @classmethod
    def get_model(cls, model_name: str = "lucasnewman/f5-tts-mlx"):
        import mlx.core as mx
        _patch_random_shapes(mx)
        if cls._model is None or cls._model_name != model_name:
            from f5_tts_mlx import F5TTS

            logger.info(f"Loading F5-TTS MLX model: {model_name}...")
            cls._model = F5TTS.from_pretrained(model_name)
            cls._model_name = model_name
            logger.info("F5-TTS MLX model loaded successfully into Apple Silicon unified memory.")
        return cls._model

class F5TTSMLXService:
    """Zero-shot voice cloning service using F5-TTS on Apple Silicon MLX with 3~5x acceleration."""

    def __init__(
        self,
        model_name: str = "lucasnewman/f5-tts-mlx",
        ref_audio_path: Optional[str] = None,
        ref_audio_text: Optional[str] = None
    ):
        self.model_name = model_name
        self.ref_audio_path = ref_audio_path
        self.ref_audio_text = ref_audio_text or ""
        self._cached_ref_audio = None
        self._cached_ref_path = None

    def update_reference(self, ref_audio_path: str, ref_audio_text: str):
        self.ref_audio_path = ref_audio_path
        self.ref_audio_text = ref_audio_text
        self._cached_ref_audio = None
        self._cached_ref_path = None

    def _load_reference_audio(self, ref_path: str):
        import mlx.core as mx
        if self._cached_ref_path == ref_path and self._cached_ref_audio is not None:
            return self._cached_ref_audio

        audio, sr = sf.read(ref_path)
        # Resample to 24kHz if needed using in-memory scipy resample
        if sr != SAMPLE_RATE:
            if len(audio.shape) > 1:
                audio = np.mean(audio, axis=1)
            # Rational resampling
            import math
            gcd = math.gcd(SAMPLE_RATE, sr)
            audio = signal.resample_poly(audio, SAMPLE_RATE // gcd, sr // gcd)

        # Convert to mono if stereo
        if len(audio.shape) > 1:
            audio = np.mean(audio, axis=1)

        audio = mx.array(audio)
        rms = mx.sqrt(mx.mean(mx.square(audio)))
        if float(rms) < TARGET_RMS and float(rms) > 0.001:
            audio = audio * TARGET_RMS / rms

        self._cached_ref_path = ref_path
        self._cached_ref_audio = audio
        return audio

    def synthesize(
        self,
        text: str,
        output_path: str,
        ref_audio_path: Optional[str] = None,
        ref_audio_text: Optional[str] = None,
        speed_mode: str = "balanced",
        steps: Optional[int] = None,
        speed: float = 1.0,
        target_duration: Optional[float] = None,
        speaking_rate: float = DEFAULT_SPEAKING_RATE,
    ) -> float:
        """
        Synthesizes text into cloned speech using Euler/Midpoint flow matching.
        Produces 48kHz Stereo 16-bit PCM WAV in memory (3~5x faster than RK4).
        """
        if not math.isfinite(speed) or speed <= 0:
            raise ValueError("朗读速度倍率必须为正数")
        clean_text = text.strip()
        speech_duration = resolve_speech_duration(
            clean_text, target_duration, speaking_rate * speed,
        )

        import mlx.core as mx
        from f5_tts_mlx.generate import convert_char_to_pinyin

        target_ref_path = ref_audio_path or self.ref_audio_path
        target_ref_text = ref_audio_text or self.ref_audio_text

        if not target_ref_path or not os.path.exists(target_ref_path):
            raise FileNotFoundError(f"声音克隆所需的参考音频不存在: {target_ref_path}")
        if not target_ref_text.strip():
            raise ValueError("参考音频需要对应的准确原文，不能使用空文本")

        f5tts = F5TTSModelHolder.get_model(self.model_name)
        ref_audio = self._load_reference_audio(target_ref_path)

        # Configure ODE solver and steps based on speed_mode
        # Euler 8 steps provides 3.5x speedup with near-identical audio fidelity
        # Euler 6 steps provides 5x speedup for blazing fast generation
        if speed_mode == "fast":
            ode_method = "euler"
            ode_steps = steps or 6
        elif speed_mode == "quality":
            ode_method = "midpoint"
            ode_steps = steps or 8
        else:  # "balanced" (default)
            ode_method = "euler"
            ode_steps = steps or 8

        duration_frames = duration_frames_for_speech(ref_audio.shape[0], speech_duration)
        full_text = convert_char_to_pinyin([target_ref_text + " " + clean_text])

        # Single-pass Flow Matching sampling
        wave, _ = f5tts.sample(
            mx.expand_dims(ref_audio, axis=0),
            text=full_text,
            duration=duration_frames,
            steps=ode_steps,
            method=ode_method,
            speed=1.0,  # Duration already accounts for the requested speaking rate.
            cfg_strength=2.0,
            sway_sampling_coef=-1.0,
        )
        # Remove reference audio portion from start
        wave = wave[ref_audio.shape[0] :]
        mx.eval(wave)
        output_audio = np.array(wave)

        # Ensure valid float values and apply Peak Normalization for loud, clear sound
        output_audio = np.nan_to_num(output_audio, nan=0.0, posinf=0.0, neginf=0.0)
        peak = float(np.max(np.abs(output_audio))) if len(output_audio) > 0 else 0.0

        if peak > 0.005:
            # Normalize peak to 0.92 (-0.7 dB) so speech is crisp, clear and loud
            output_audio = output_audio * (0.92 / peak)
        else:
            raise RuntimeError(f"F5-TTS 生成的音频为空或无声 (peak={peak})，请重新选择参考音频")

        # In-memory upsampling from 24kHz to 48kHz Stereo (< 5ms, zero subprocess overhead!)
        audio_48k = signal.resample_poly(output_audio, 2, 1)
        stereo_48k = np.stack([audio_48k, audio_48k], axis=-1)
        pcm16_stereo = (np.clip(stereo_48k, -1.0, 1.0) * 32767.0).astype(np.int16)

        # Write final 48kHz Stereo 16-bit PCM WAV directly
        sf.write(output_path, pcm16_stereo, 48000, subtype='PCM_16')
        duration_sec = round(len(pcm16_stereo) / 48000.0, 3)

        return duration_sec
