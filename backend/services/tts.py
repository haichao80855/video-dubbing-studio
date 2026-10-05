import os
import asyncio
import subprocess
import logging
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional, Callable
from pathlib import Path
import httpx
import edge_tts
from pydub import AudioSegment
from backend.config import FFMPEG_PATH, FFPROBE_PATH

logger = logging.getLogger(__name__)

def get_audio_duration(file_path: str) -> float:
    """Return audio duration in seconds using pydub/ffprobe."""
    try:
        audio = AudioSegment.from_file(file_path)
        return round(len(audio) / 1000.0, 3)
    except Exception:
        # Fallback to ffprobe
        cmd = [
            FFPROBE_PATH, "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            file_path
        ]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if res.returncode == 0 and res.stdout.strip():
            return round(float(res.stdout.strip()), 3)
        return 0.0

def convert_to_pcm_wav(input_file: str, output_wav: str):
    """Convert any audio file to 16kHz mono 16-bit PCM WAV."""
    cmd = [
        FFMPEG_PATH, "-y",
        "-i", input_file,
        "-acodec", "pcm_s16le",
        "-ar", "16000",
        "-ac", "1",
        output_wav
    ]
    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if res.returncode != 0:
        raise RuntimeError(f"FFmpeg audio conversion error: {res.stderr.decode('utf-8', errors='ignore')}")

class BaseTTS(ABC):
    @abstractmethod
    async def synthesize(self, text: str, voice: str, output_path: str) -> float:
        """Synthesizes text to output_path (wav) and returns duration in seconds."""
        pass

class EdgeTTSService(BaseTTS):
    """High quality, free Microsoft Edge TTS."""

    async def synthesize(self, text: str, voice: str, output_path: str) -> float:
        voice_id = voice or "zh-CN-YunxiNeural"
        temp_mp3 = output_path + ".temp.mp3"
        
        # Clean text for TTS
        clean_text = text.strip()
        if not clean_text:
            clean_text = "..."

        comm = edge_tts.Communicate(clean_text, voice_id)
        await comm.save(temp_mp3)

        # Convert to standard 16kHz PCM wav
        convert_to_pcm_wav(temp_mp3, output_path)
        if os.path.exists(temp_mp3):
            os.remove(temp_mp3)

        return get_audio_duration(output_path)

class CosyVoiceService(BaseTTS):
    """CosyVoice 3 via DashScope API or local HTTP server."""

    def __init__(self, api_key: Optional[str] = None, endpoint: Optional[str] = None):
        self.api_key = (api_key or "").strip()
        self.endpoint = (endpoint or "").strip()

    async def synthesize(self, text: str, voice: str, output_path: str) -> float:
        clean_text = text.strip()
        if not clean_text:
            clean_text = "..."

        temp_out = output_path + ".temp.audio"

        # Case 1: Local CosyVoice endpoint
        if self.endpoint:
            url = f"{self.endpoint.rstrip('/')}/tts"
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.post(url, json={"text": clean_text, "voice": voice or "longxiaochun"})
                if resp.status_code != 200:
                    raise RuntimeError(f"Local CosyVoice error {resp.status_code}: {resp.text}")
                with open(temp_out, "wb") as f:
                    f.write(resp.content)
            convert_to_pcm_wav(temp_out, output_path)
            if os.path.exists(temp_out):
                os.remove(temp_out)
            return get_audio_duration(output_path)

        # Case 2: Alibaba Cloud DashScope API
        if not self.api_key:
            raise ValueError("使用 CosyVoice 需要提供 DashScope API Key 或本地端点地址")

        url = "https://dashscope.aliyuncs.com/api/v1/services/audio/text-to-speech/speech-synthesis"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": "cosyvoice-v1",
            "input": {
                "text": clean_text
            },
            "parameters": {
                "voice": voice or "longxiaochun",
                "format": "wav",
                "sample_rate": 16000
            }
        }

        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(url, json=payload, headers=headers)
            if resp.status_code != 200:
                raise RuntimeError(f"DashScope CosyVoice API error {resp.status_code}: {resp.text}")
            with open(temp_out, "wb") as f:
                f.write(resp.content)

        convert_to_pcm_wav(temp_out, output_path)
        if os.path.exists(temp_out):
            os.remove(temp_out)
        return get_audio_duration(output_path)


class TTSRunner:
    """Manages batch TTS generation for subtitle segments."""

    def __init__(
        self,
        engine_type: str = "edge_tts",
        voice_name: str = "zh-CN-YunxiNeural",
        api_key: Optional[str] = None,
        endpoint: Optional[str] = None
    ):
        self.engine_type = engine_type
        self.voice_name = voice_name
        if engine_type == "cosyvoice":
            self.service = CosyVoiceService(api_key=api_key, endpoint=endpoint)
        else:
            self.service = EdgeTTSService()

    async def generate_all(
        self,
        subtitles: List[Dict[str, Any]],
        task_dir: Path,
        progress_callback: Optional[Callable[[float, str], None]] = None
    ) -> List[Dict[str, Any]]:
        """
        Synthesizes audio for each subtitle item in parallel/sequence.
        Adds 'audio_path' and 'tts_duration' to each segment.
        """
        tts_dir = task_dir / "tts_clips"
        tts_dir.mkdir(parents=True, exist_ok=True)

        results = []
        total = len(subtitles)

        # Concurrency limit to prevent rate limits
        semaphore = asyncio.Semaphore(4)

        async def process_one(idx: int, item: Dict[str, Any]):
            async with semaphore:
                seg_id = item["id"]
                text = item.get("translated_text", "").strip() or item.get("text", "")
                out_path = str(tts_dir / f"clip_{seg_id:04d}.wav")
                try:
                    duration = await self.service.synthesize(text, self.voice_name, out_path)
                except Exception as e:
                    logger.error(f"TTS synthesis failed for segment {seg_id}: {e}")
                    # Create 0.5s silence as fallback
                    silence = AudioSegment.silent(duration=500, frame_rate=16000)
                    silence.export(out_path, format="wav")
                    duration = 0.5

                return {
                    **item,
                    "audio_path": out_path,
                    "tts_duration": duration
                }

        tasks = [process_one(i, item) for i, item in enumerate(subtitles)]

        completed = 0
        for fut in asyncio.as_completed(tasks):
            res = await fut
            results.append(res)
            completed += 1
            if progress_callback:
                pct = completed / total * 100
                progress_callback(pct, f"正在进行语音合成配音 ({completed}/{total})...")

        # Sort back by ID
        results.sort(key=lambda x: x["id"])
        return results
