import os
import sys
import logging
import datetime
from pathlib import Path
from typing import Optional, List
import numpy as np
import soundfile as sf

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
        if cls._model is None or cls._model_name != model_name:
            import mlx.core as mx
            from f5_tts_mlx import F5TTS

            logger.info(f"Loading F5-TTS MLX model: {model_name}...")
            cls._model = F5TTS.from_pretrained(model_name)
            cls._model_name = model_name
            logger.info("F5-TTS MLX model loaded successfully into Apple Silicon unified memory.")
        return cls._model

class F5TTSMLXService:
    """Zero-shot voice cloning service using F5-TTS on Apple Silicon MLX."""

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
        # Resample to 24kHz if needed
        if sr != SAMPLE_RATE:
            import subprocess
            from backend.config import FFMPEG_PATH

            temp_24k = ref_path + ".24k.wav"
            cmd = [
                FFMPEG_PATH, "-y",
                "-i", ref_path,
                "-ar", str(SAMPLE_RATE),
                "-ac", "1",
                temp_24k
            ]
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
            audio, sr = sf.read(temp_24k)
            if os.path.exists(temp_24k):
                os.remove(temp_24k)

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
        steps: int = 8,
        speed: float = 1.0,
    ) -> float:
        """
        Synthesizes text into cloned speech using the reference audio,
        saving to output_path (wav) and returning duration in seconds.
        """
        import mlx.core as mx
        from f5_tts_mlx.generate import convert_char_to_pinyin, estimated_duration, split_sentences

        target_ref_path = ref_audio_path or self.ref_audio_path
        target_ref_text = ref_audio_text or self.ref_audio_text

        if not target_ref_path or not os.path.exists(target_ref_path):
            raise FileNotFoundError(f"声音克隆所需的参考音频不存在: {target_ref_path}")

        f5tts = F5TTSModelHolder.get_model(self.model_name)
        ref_audio = self._load_reference_audio(target_ref_path)

        clean_text = text.strip()
        if not clean_text:
            clean_text = "..."

        sentences = split_sentences(clean_text)
        is_single = len(sentences) <= 1

        if is_single:
            duration_frames = int(estimated_duration(ref_audio, target_ref_text, clean_text, speed) * FRAMES_PER_SEC)
            full_text = convert_char_to_pinyin([target_ref_text + " " + clean_text])

            wave, _ = f5tts.sample(
                mx.expand_dims(ref_audio, axis=0),
                text=full_text,
                duration=duration_frames,
                steps=steps,
                method="rk4",
                speed=speed,
                cfg_strength=2.0,
                sway_sampling_coef=-1.0,
            )
            # Remove reference audio portion from start
            wave = wave[ref_audio.shape[0] :]
            mx.eval(wave)
            output_audio = np.array(wave)
        else:
            # Multi-sentence stitching
            output_chunks = []
            for sentence in sentences:
                dur_frames = int(estimated_duration(ref_audio, target_ref_text, sentence, speed) * FRAMES_PER_SEC)
                pinyin_text = convert_char_to_pinyin([target_ref_text + " " + sentence])

                wave, _ = f5tts.sample(
                    mx.expand_dims(ref_audio, axis=0),
                    text=pinyin_text,
                    duration=dur_frames,
                    steps=steps,
                    method="rk4",
                    speed=speed,
                    cfg_strength=2.0,
                    sway_sampling_coef=-1.0,
                )
                wave = wave[ref_audio.shape[0] :]
                mx.eval(wave)
                output_chunks.append(np.array(wave))

            output_audio = np.concatenate(output_chunks, axis=0) if output_chunks else np.zeros((SAMPLE_RATE,))

        # Ensure valid float values and apply Peak Normalization for loud, clear sound
        output_audio = np.nan_to_num(output_audio, nan=0.0, posinf=0.0, neginf=0.0)
        peak = float(np.max(np.abs(output_audio))) if len(output_audio) > 0 else 0.0

        if peak > 0.005:
            # Normalize peak to 0.92 (-0.7 dB) so speech is crisp, clear and loud
            output_audio = output_audio * (0.92 / peak)
        else:
            logger.warning(f"Generated F5-TTS audio has near-zero amplitude (peak={peak})")

        # Convert to 16-bit PCM for universal player & ffmpeg compatibility
        output_audio_int16 = (np.clip(output_audio, -1.0, 1.0) * 32767.0).astype(np.int16)

        # Write output 24kHz 16-bit PCM WAV
        sf.write(output_path, output_audio_int16, SAMPLE_RATE, subtype='PCM_16')
        duration_sec = round(len(output_audio_int16) / SAMPLE_RATE, 3)

        # Resample to high-standard 48kHz PCM WAV for alignment and final video composition
        import subprocess
        from backend.config import FFMPEG_PATH
        temp_48k = output_path + ".48k.wav"
        cmd = [
            FFMPEG_PATH, "-y",
            "-i", output_path,
            "-acodec", "pcm_s16le",
            "-ar", "48000",
            "-ac", "2",
            temp_48k
        ]
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        if os.path.exists(temp_48k):
            os.replace(temp_48k, output_path)

        return duration_sec
