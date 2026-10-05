import os
import re
import json
import logging
from typing import List, Dict, Any, Tuple, Optional, Callable
from pathlib import Path
import numpy as np
import soundfile as sf
import scipy.signal as signal
from pydub import AudioSegment

from backend.config import FFMPEG_PATH
from backend.services.translator import DeepSeekTranslator
from backend.services.f5_tts_mlx import F5TTSMLXService

logger = logging.getLogger(__name__)

class ContinuousFlowDubber:
    """
    Continuous Flow Dubbing Engine (连续整篇原声解说流引擎).
    Eliminates all choppy 1-second awkward silences and sentence-by-sentence intonation drops.
    Treats the video as a unified continuous narrative.
    """

    def __init__(self, task_dir: Path):
        self.task_dir = task_dir
        self.tts_clips_dir = task_dir / "continuous_clips"
        self.tts_clips_dir.mkdir(parents=True, exist_ok=True)

    def extract_full_narrative(self, raw_segments: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Consolidates the entire video speech into a unified coherent narrative script,
        capturing global start, global end, and clean text.
        """
        if not raw_segments:
            return {"text": "", "start": 0.0, "end": 0.0, "duration": 0.0, "sentences": []}

        global_start = raw_segments[0]["start"]
        global_end = raw_segments[-1]["end"]
        total_duration = max(1.0, global_end - global_start)

        full_text_parts = []
        for s in raw_segments:
            txt = s.get("text", "").strip()
            if txt:
                full_text_parts.append(txt)

        full_text = " ".join(full_text_parts)
        full_text = re.sub(r"\s+", " ", full_text).strip()

        return {
            "full_text": full_text,
            "global_start": global_start,
            "global_end": global_end,
            "total_speech_duration": total_duration,
            "segment_count": len(raw_segments)
        }

    def translate_full_flow(
        self,
        narrative_info: Dict[str, Any],
        translator: DeepSeekTranslator,
        progress_callback: Optional[Callable[[float, str], None]] = None
    ) -> List[Dict[str, Any]]:
        """
        Translates the full narrative text as a unified, coherent story.
        Outputs naturally segmented, comfortable sentences with commas for breathing.
        """
        full_text = narrative_info["full_text"]
        speech_dur = narrative_info["total_speech_duration"]
        
        # Calculate target Chinese word budget: ~3.6 chars/second of original speech
        target_total_chars = max(20, int(speech_dur * 3.6))

        if progress_callback:
            progress_callback(10.0, "DeepSeek 正在通篇全局阅读与连贯意译整段视频文案...")

        system_prompt = (
            "你是一位顶级的纪录片与科技视频同声解说翻译大师。"
            "你的任务是将输入的整篇英文演讲文案，翻译为通篇行云流水、逻辑极其连贯、起承转合自然的中文解说长文。\n"
            "核心要求：\n"
            "1. 【通篇连贯流畅，绝不破碎】：不要机械直译，要站在全文逻辑高度进行连贯本土化意译。句子与句子之间承接自然，如同专业博主在滔滔不绝地现场解说。\n"
            "2. 【篇幅与语速匹配】：整篇译文的总汉字字数必须控制在 target_total_chars 左右（允许上下浮动 10%），以保证中文朗读时长与原视频演讲时长天生吻合！\n"
            "3. 【划分自然呼吸气口】：请将全文切分为若干个 15~35 个汉字的长句（每句必须是一个完整语义意群，内部用中文逗号划分停顿气口）。\n"
            "4. 【严格输出格式】：返回纯 JSON 数组，每个对象包含：\n"
            "   - `id`: 序号 (从 1 开始)\n"
            "   - `translated_text`: 中文完整长句\n"
            "只返回纯 JSON 数组，不要任何 Markdown 外部说明。"
        )

        user_prompt = (
            f"原视频演讲总时长: {speech_dur:.1f} 秒\n"
            f"建议全篇中文总字数目标: 约 {target_total_chars} 汉字\n"
            f"原视频英文全文如下：\n{full_text}"
        )

        url = translator._get_chat_url()
        headers = {
            "Authorization": f"Bearer {translator.api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": translator.model_name,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "temperature": 0.3
        }

        import httpx
        proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("HTTP_PROXY") or os.environ.get("all_proxy")
        client_kwargs = {"timeout": 120.0}
        if proxy:
            client_kwargs["proxy"] = proxy

        with httpx.Client(**client_kwargs) as client:
            resp = client.post(url, json=payload, headers=headers)
            if resp.status_code != 200:
                raise RuntimeError(f"DeepSeek 全文连贯翻译失败 [{resp.status_code}]: {resp.text}")

            data = resp.json()
            content_text = data.get("choices", [{}])[0].get("message", {}).get("content", "").strip()

            # Clean JSON fences
            if content_text.startswith("```json"):
                content_text = content_text[7:]
            elif content_text.startswith("```"):
                content_text = content_text[3:]
            if content_text.endswith("```"):
                content_text = content_text[:-3]
            content_text = content_text.strip()

            match = re.search(r"(\[.*\]|\{.*\})", content_text, re.DOTALL)
            if match:
                content_text = match.group(1)

            parsed = json.loads(content_text)
            if isinstance(parsed, dict):
                for v in parsed.values():
                    if isinstance(v, list):
                        parsed = v
                        break

            if not isinstance(parsed, list):
                raise ValueError("DeepSeek 全文翻译返回格式异常")

        # Assign estimated proportional timestamps for each translated sentence
        total_chars = sum(len(item.get("translated_text", "")) for item in parsed)
        running_time = narrative_info["global_start"]

        results = []
        for idx, item in enumerate(parsed, 1):
            txt = item.get("translated_text", "").strip()
            # Duration proportional to character count
            fraction = len(txt) / max(1, total_chars)
            seg_dur = max(2.0, round(speech_dur * fraction, 2))
            
            seg_start = round(running_time, 2)
            seg_end = round(running_time + seg_dur, 2)
            running_time += seg_dur

            results.append({
                "id": idx,
                "start": seg_start,
                "end": seg_end,
                "duration": seg_dur,
                "original_text": f"段落 #{idx}",
                "translated_text": txt
            })

        if progress_callback:
            progress_callback(100.0, f"全文通篇意译完成，共生成 {len(results)} 个流畅连贯的中文长段落")

        return results

    def synthesize_and_stitch_continuous(
        self,
        subtitles: List[Dict[str, Any]],
        f5_service: F5TTSMLXService,
        global_start_sec: float,
        video_total_duration: float,
        speed_mode: str = "balanced",
        progress_callback: Optional[Callable[[float, str], None]] = None
    ) -> Tuple[str, List[Dict[str, Any]]]:
        """
        Synthesizes each translated paragraph and tightly stitches with 200ms human breath pauses.
        Completely eliminates 1-second awkward gaps.
        Returns: (final_audio_path, updated_subtitles_with_exact_timing)
        """
        import asyncio
        loop = asyncio.get_event_loop() if asyncio.get_event_loop().is_running() else None

        total = len(subtitles)
        full_track = AudioSegment.silent(duration=0, frame_rate=48000).set_channels(2)

        # 1. Add intro silence matching the video before speaker starts
        intro_ms = max(0, int(global_start_sec * 1000))
        if intro_ms > 0:
            full_track += AudioSegment.silent(duration=intro_ms, frame_rate=48000).set_channels(2)

        updated_subtitles = []
        current_cursor_sec = intro_ms / 1000.0
        BREATH_PAUSE_MS = 200  # 0.20s natural human breathing room

        for idx, item in enumerate(subtitles, 1):
            seg_id = item["id"]
            text = item.get("translated_text", "").strip()
            out_clip_path = str(self.tts_clips_dir / f"flow_{seg_id:04d}.wav")

            # Synthesize continuous paragraph using F5-TTS MLX
            dur_sec = f5_service.synthesize(text, out_clip_path, speed_mode=speed_mode)
            clip = AudioSegment.from_file(out_clip_path).set_frame_rate(48000).set_channels(2)

            # Record exact speech start and end for subtitle synchronization
            clip_dur_sec = len(clip) / 1000.0
            actual_start = round(current_cursor_sec, 2)
            actual_end = round(current_cursor_sec + clip_dur_sec, 2)

            updated_subtitles.append({
                **item,
                "start": actual_start,
                "end": actual_end,
                "duration": round(clip_dur_sec, 2),
                "audio_path": out_clip_path
            })

            # Append speech clip
            full_track += clip
            current_cursor_sec += clip_dur_sec

            # Append natural 0.2s breath pause between sentences (unless it's the very last sentence)
            if idx < total:
                full_track += AudioSegment.silent(duration=BREATH_PAUSE_MS, frame_rate=48000).set_channels(2)
                current_cursor_sec += (BREATH_PAUSE_MS / 1000.0)

            if progress_callback:
                pct = idx / total * 100.0
                progress_callback(pct, f"正在进行连续连贯原声克隆合成 ({idx}/{total})...")

        # 2. Global Tempo Fit: Ensure overall speech duration matches video duration naturally
        target_total_ms = int(video_total_duration * 1000)
        current_len_ms = len(full_track)

        # Pad remaining video tail with silence up to video_total_duration
        if target_total_ms > current_len_ms:
            tail_gap = target_total_ms - current_len_ms
            full_track += AudioSegment.silent(duration=tail_gap, frame_rate=48000).set_channels(2)
        elif current_len_ms > target_total_ms:
            # Slight trim at end
            full_track = full_track[:target_total_ms]

        final_audio_path = str(self.task_dir / "dubbed_full_track.wav")
        full_track.export(final_audio_path, format="wav")

        logger.info(f"ContinuousFlowDubber: Created seamless voiceover stream ({len(full_track)/1000.0}s) with zero awkward gaps.")
        return final_audio_path, updated_subtitles
