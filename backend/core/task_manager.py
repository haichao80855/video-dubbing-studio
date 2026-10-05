import os
import json
import uuid
import time
import asyncio
import logging
from typing import Dict, Any, List, Optional
from pathlib import Path
from backend.config import TASKS_DIR
from backend.services.downloader import VideoDownloader
from backend.services.asr import get_asr_engine
from backend.services.translator import DeepSeekTranslator
from backend.services.speaker_extractor import SpeakerExtractor
from backend.services.sentence_merger import SentenceMerger
from backend.services.continuous_flow_dubber import ContinuousFlowDubber
from backend.services.f5_tts_mlx import F5TTSMLXService
from backend.services.composer import VideoComposer

logger = logging.getLogger(__name__)

class TaskState:
    PENDING = "PENDING"
    DOWNLOADING = "DOWNLOADING"
    ASR = "ASR"
    TRANSLATING = "TRANSLATING"
    WAITING_REVIEW = "WAITING_REVIEW"
    TTS = "TTS"
    ALIGNING = "ALIGNING"
    COMPOSING = "COMPOSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"

class Task:
    def __init__(self, task_id: str, config: Dict[str, Any]):
        self.task_id = task_id
        self.config = config
        self.state = TaskState.PENDING
        self.progress = 0.0
        self.current_message = "任务已创建，等待开始"
        self.logs: List[Dict[str, Any]] = []
        self.subtitles: List[Dict[str, Any]] = []
        self.source_segments: List[Dict[str, Any]] = []
        self.result: Optional[Dict[str, Any]] = None
        self.error: Optional[str] = None
        self.created_at = time.time()
        self.task_dir = TASKS_DIR / task_id
        self.task_dir.mkdir(parents=True, exist_ok=True)
        self.video_info: Dict[str, Any] = {}
        self.speaker_ref: Dict[str, Any] = {}
        self.subscribers: List[asyncio.Queue] = []
        self.review_event = asyncio.Event()
        self.loop: Optional[asyncio.AbstractEventLoop] = None

    def add_log(self, message: str, stage: str, progress: float):
        self.state = stage
        self.progress = round(progress, 1)
        self.current_message = message
        entry = {
            "time": time.strftime("%H:%M:%S"),
            "stage": stage,
            "progress": self.progress,
            "message": message
        }
        self.logs.append(entry)
        self.save_state()

        # Push to all SSE subscribers safely across worker threads
        event_data = {
            "type": "progress",
            "task_id": self.task_id,
            "stage": self.state,
            "progress": self.progress,
            "message": message,
            "log": entry
        }
        for q in list(self.subscribers):
            try:
                if self.loop and self.loop.is_running():
                    self.loop.call_soon_threadsafe(q.put_nowait, event_data)
                else:
                    q.put_nowait(event_data)
            except Exception:
                pass

    def save_state(self):
        state_file = self.task_dir / "state.json"
        data = {
            "task_id": self.task_id,
            "state": self.state,
            "progress": self.progress,
            "message": self.current_message,
            "config": {k: v for k, v in self.config.items() if not k.endswith("_key")},
            "video_info": self.video_info,
            "speaker_ref": self.speaker_ref,
            "subtitles_count": len(self.subtitles),
            "result": self.result,
            "error": self.error,
            "created_at": self.created_at
        }
        with open(state_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def subscribe(self) -> asyncio.Queue:
        q = asyncio.Queue()
        self.subscribers.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue):
        if q in self.subscribers:
            self.subscribers.remove(q)

class TaskManager:
    """Singleton Manager for video dubbing workflows."""

    def __init__(self):
        self.tasks: Dict[str, Task] = {}

    def create_task(self, config: Dict[str, Any]) -> Task:
        task_id = str(uuid.uuid4())[:8]
        task = Task(task_id, config)
        self.tasks[task_id] = task
        task.save_state()
        return task

    def get_task(self, task_id: str) -> Optional[Task]:
        return self.tasks.get(task_id)

    def update_speaker_ref(self, task_id: str, segment_id: int) -> Optional[Dict[str, Any]]:
        task = self.get_task(task_id)
        if not task or not task.video_info.get("audio_wav_path"):
            return None
        extractor = SpeakerExtractor(task_dir=task.task_dir)
        segments = task.source_segments
        if not any(segment["id"] == segment_id for segment in segments):
            return None
        ref = extractor.prepare_speaker_reference(
            full_audio_path=task.video_info["audio_wav_path"],
            segments=segments,
            chosen_segment_id=segment_id
        )
        task.speaker_ref = ref
        task.save_state()
        return ref

    async def run_pipeline(self, task: Task):
        """Asynchronously executes the video dubbing pipeline."""
        try:
            loop = asyncio.get_running_loop()
            task.loop = loop
            cfg = task.config
            url = cfg.get("url", "").strip()
            if not url:
                raise ValueError("视频 URL 不能为空")

            # --- STAGE 1: DOWNLOAD ---
            task.add_log("开始下载视频并提取原声音频...", TaskState.DOWNLOADING, 5.0)
            
            downloader = VideoDownloader(
                task_dir=task.task_dir,
                progress_callback=lambda p, msg: task.add_log(msg, TaskState.DOWNLOADING, p)
            )
            # Run blocking yt-dlp in executor
            loop = asyncio.get_running_loop()
            video_info = await loop.run_in_executor(None, downloader.download, url)
            task.video_info = video_info
            task.save_state()
            task.add_log(f"视频下载成功: 《{video_info['title']}》 时长: {video_info['duration']}s", TaskState.DOWNLOADING, 100.0)

            # --- STAGE 2: ASR (MLX Whisper) ---
            task.add_log("启动 Apple Silicon MLX 硬件加速语音识别...", TaskState.ASR, 0.0)
            asr_engine = get_asr_engine(
                engine_type="mlx_whisper",
                model_name=cfg.get("asr_model")
            )
            asr_res = await loop.run_in_executor(
                None,
                lambda: asr_engine.transcribe(
                    video_info["audio_wav_path"],
                    progress_callback=lambda p, msg: task.add_log(msg, TaskState.ASR, p)
                )
            )
            raw_segments = asr_res["segments"]
            task.source_segments = raw_segments
            detected_lang = asr_res["language"]
            task.add_log(f"ASR 识别成功 (识别语言: {detected_lang}, 共 {len(raw_segments)} 句)", TaskState.ASR, 100.0)

            if not raw_segments:
                raise RuntimeError("视频中未识别出有效人声内容")

            # Merge fragmented ASR micro-segments into natural coherent semantic sentences (8~14s)
            merger = SentenceMerger()
            merged_segments = merger.merge_segments(raw_segments)
            task.add_log(f"语义长句合并完成：已将 {len(raw_segments)} 个碎句重整为 {len(merged_segments)} 个自然完整语流", TaskState.ASR, 90.0)

            # Extract representative speaker audio for voice cloning
            task.add_log("智能提取原人物音色参考切片 (3~6秒)...", TaskState.ASR, 95.0)
            extractor = SpeakerExtractor(task_dir=task.task_dir)
            speaker_ref = await loop.run_in_executor(
                None,
                lambda: extractor.prepare_speaker_reference(
                    full_audio_path=video_info["audio_wav_path"],
                    segments=raw_segments
                )
            )
            task.speaker_ref = speaker_ref
            task.save_state()
            task.add_log(f"已提取原人物音色样本 (片段 #{speaker_ref['segment_id']}: {speaker_ref['duration']}s)", TaskState.ASR, 100.0)

            # --- STAGE 3: TRANSLATION (DeepSeek 全文连贯意译) ---
            model_name = cfg.get("deepseek_model", "deepseek4.1flash")
            task.add_log(f"正在调用 DeepSeek ({model_name}) 结合全文上下文按原时间轴翻译...", TaskState.TRANSLATING, 0.0)
            deepseek_key = cfg.get("deepseek_api_key", "").strip()
            base_url = cfg.get("deepseek_base_url", "https://api.deepseek.com/v1")
            translator = DeepSeekTranslator(
                api_key=deepseek_key,
                base_url=base_url,
                model_name=model_name
            )

            dubber = ContinuousFlowDubber(task_dir=task.task_dir)
            narrative_info = dubber.extract_full_narrative(merged_segments)

            translated_subtitles = await loop.run_in_executor(
                None,
                lambda: dubber.translate_full_flow(
                    narrative_info=narrative_info,
                    translator=translator,
                    source_language=detected_lang,
                    speaking_rate=cfg.get("tts_speaking_rate", 3.8),
                    progress_callback=lambda p, msg: task.add_log(msg, TaskState.TRANSLATING, p)
                )
            )
            task.subtitles = translated_subtitles
            task.save_state()
            task.add_log("DeepSeek 全文通篇意译与连贯长段落生成完成！", TaskState.TRANSLATING, 100.0)

            # Save subtitles to json
            with open(task.task_dir / "subtitles.json", "w", encoding="utf-8") as f:
                json.dump(task.subtitles, f, ensure_ascii=False, indent=2)

            # --- STAGE 4: REVIEW GATE ---
            auto_mode = cfg.get("auto_pipeline", False)
            if not auto_mode:
                task.add_log("等待用户在前端校对和确认中文字幕...", TaskState.WAITING_REVIEW, 100.0)
                # Broadcast review event
                for q in list(task.subscribers):
                    try:
                        q.put_nowait({
                            "type": "review_ready",
                            "task_id": task.task_id,
                            "subtitles": task.subtitles,
                            "speaker_ref": task.speaker_ref
                        })
                    except Exception:
                        pass

                # Pause and wait for frontend confirmation
                await task.review_event.wait()
                task.add_log("用户确认校对完成，开始后续配音合成...", TaskState.WAITING_REVIEW, 100.0)

            # --- STAGE 5: TTS (F5-TTS MLX 连续连贯原声克隆) ---
            speed_mode = cfg.get("tts_speed_mode", "balanced")
            task.add_log("使用 F5-TTS MLX 按原句时间窗口进行自然语速声音克隆...", TaskState.TTS, 0.0)

            f5_service = F5TTSMLXService(
                ref_audio_path=task.speaker_ref.get("audio_path"),
                ref_audio_text=task.speaker_ref.get("ref_text")
            )

            total_video_dur = float(video_info.get("duration", 0.0))
            dubbed_audio_path, updated_subtitles = await loop.run_in_executor(
                None,
                lambda: dubber.synthesize_and_stitch_continuous(
                    subtitles=task.subtitles,
                    f5_service=f5_service,
                    global_start_sec=narrative_info.get("global_start", 0.0),
                    video_total_duration=total_video_dur,
                    speed_mode=speed_mode,
                    speaking_rate=cfg.get("tts_speaking_rate", 3.8),
                    progress_callback=lambda p, msg: task.add_log(msg, TaskState.TTS, p)
                )
            )
            task.subtitles = updated_subtitles
            task.save_state()
            task.add_log("原声克隆配音完成，已保留原视频逐句起点和停顿", TaskState.TTS, 100.0)

            # --- STAGE 6: COMPOSING DIRECTLY ---
            task.add_log("进行最终视频混流与中文字幕合成...", TaskState.COMPOSING, 0.0)
            composer = VideoComposer(task_dir=task.task_dir, task_id=task.task_id)
            comp_res = await loop.run_in_executor(
                None,
                lambda: composer.compose_video(
                    video_path=video_info["video_path"],
                    audio_path=dubbed_audio_path,
                    subtitles=task.subtitles,
                    hard_sub=cfg.get("hard_sub", True),
                    progress_callback=lambda p, msg: task.add_log(msg, TaskState.COMPOSING, p)
                )
            )

            # --- FINISHED ---
            task.result = comp_res
            task.add_log("🎉 视频翻译与配音已全部完成！可在前端预览与下载", TaskState.COMPLETED, 100.0)
            task.save_state()

            # Broadcast completed
            for q in list(task.subscribers):
                try:
                    q.put_nowait({
                        "type": "completed",
                        "task_id": task.task_id,
                        "result": comp_res
                    })
                except Exception:
                    pass

        except Exception as e:
            logger.exception(f"Task {task.task_id} failed: {e}")
            task.error = str(e)
            task.add_log(f"任务执行失败: {e}", TaskState.FAILED, task.progress)
            task.save_state()
            for q in list(task.subscribers):
                try:
                    q.put_nowait({
                        "type": "error",
                        "task_id": task.task_id,
                        "error": str(e)
                    })
                except Exception:
                    pass

task_manager = TaskManager()
