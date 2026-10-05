import os
import json
import asyncio
import logging
import uuid
from typing import Dict, Any, List, Optional
from pathlib import Path
from fastapi import FastAPI, HTTPException, Request, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import StreamingResponse, FileResponse, JSONResponse
from pydantic import BaseModel, Field

from backend.config import (
    OUTPUTS_DIR,
    TASKS_DIR,
    AVAILABLE_WHISPER_MODELS,
    BASE_DIR,
    PROJECT_ROOT
)
from backend.core.task_manager import task_manager, TaskState
from backend.services.translator import DeepSeekTranslator
from backend.services.f5_tts_mlx import F5TTSMLXService
from backend.services.aligner import AudioAligner
from backend.services.pacing import DEFAULT_SPEAKING_RATE, resolve_speech_duration

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("app")

app = FastAPI(title="Video Dubbing System API", version="1.0.0")

# Enable CORS for local dev & production
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve generated video and audio outputs
app.mount("/outputs", StaticFiles(directory=str(OUTPUTS_DIR)), name="outputs")

# Request schemas
class CreateTaskRequest(BaseModel):
    url: str
    hard_sub: bool = True
    auto_pipeline: bool = False
    asr_model: Optional[str] = None
    deepseek_model: str = "deepseek4.1flash"
    deepseek_base_url: str = "https://api.deepseek.com/v1"
    deepseek_api_key: str
    tts_speed_mode: str = "balanced"
    tts_speaking_rate: float = Field(default=DEFAULT_SPEAKING_RATE, ge=2.5, le=4.5)

class TestLLMRequest(BaseModel):
    api_key: str
    base_url: str = "https://api.deepseek.com/v1"
    model: str = "deepseek4.1flash"

class SubtitleItem(BaseModel):
    id: int
    start: float
    end: float
    duration: Optional[float] = None
    original_text: Optional[str] = ""
    translated_text: str

class ConfirmSubtitlesRequest(BaseModel):
    subtitles: List[SubtitleItem]

class UpdateSpeakerRefRequest(BaseModel):
    segment_id: int

class PreviewTTSRequest(BaseModel):
    text: str
    task_id: Optional[str] = None
    ref_audio_path: Optional[str] = None
    ref_audio_text: Optional[str] = None
    subtitle_id: Optional[int] = None
    speed_mode: Optional[str] = None
    target_duration: Optional[float] = Field(default=None, gt=0)
    speaking_rate: Optional[float] = Field(default=None, ge=2.5, le=4.5)


@app.get("/api/health")
async def health():
    return {"status": "ok", "app": "video-dubbing-system"}

@app.get("/api/config/options")
async def get_options():
    """Returns available ASR models and default TTS engine."""
    return {
        "asr_models": AVAILABLE_WHISPER_MODELS,
        "tts_engine": "f5_tts_mlx",
        "tts_name": "F5-TTS MLX (原人物声音克隆)"
    }

@app.post("/api/config/test-llm")
async def test_llm_connection(req: TestLLMRequest):
    """Tests connectivity to DeepSeek / OpenAI-compatible endpoint."""
    loop = asyncio.get_running_loop()
    res = await loop.run_in_executor(
        None,
        lambda: DeepSeekTranslator.test_connection(
            api_key=req.api_key,
            base_url=req.base_url,
            model_name=req.model
        )
    )
    return res

@app.post("/api/tasks/create")
async def create_task(req: CreateTaskRequest, background_tasks: BackgroundTasks):
    if not req.url or not req.url.strip():
        raise HTTPException(status_code=400, detail="视频 URL 不能为空")
    if not req.deepseek_api_key or not req.deepseek_api_key.strip():
        raise HTTPException(status_code=400, detail="DeepSeek API Key 不能为空，请在设置中配置")

    task = task_manager.create_task(req.model_dump())
    # Start pipeline in asyncio background task
    asyncio.create_task(task_manager.run_pipeline(task))

    return {
        "status": "success",
        "task_id": task.task_id,
        "message": "任务已创建并开始执行"
    }

@app.get("/api/tasks/{task_id}/status")
async def get_task_status(task_id: str):
    task = task_manager.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    return {
        "task_id": task.task_id,
        "state": task.state,
        "progress": task.progress,
        "message": task.current_message,
        "video_info": task.video_info,
        "logs": task.logs,
        "subtitles_count": len(task.subtitles),
        "result": task.result,
        "error": task.error,
        "created_at": task.created_at
    }

@app.get("/api/tasks/{task_id}/events")
async def task_events(task_id: str, request: Request):
    """Server-Sent Events endpoint for real-time progress updates."""
    task = task_manager.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    async def event_generator():
        q = task.subscribe()
        try:
            # Yield initial status
            initial_event = {
                "type": "init",
                "task_id": task.task_id,
                "state": task.state,
                "progress": task.progress,
                "message": task.current_message,
                "logs": task.logs,
                "video_info": task.video_info,
                "result": task.result
            }
            yield f"data: {json.dumps(initial_event, ensure_ascii=False)}\n\n"

            while True:
                # Check client disconnected
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(q.get(), timeout=15.0)
                    yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                    if event.get("type") in ("completed", "error"):
                        break
                except asyncio.TimeoutError:
                    # Keep-alive ping
                    yield f": ping\n\n"
        finally:
            task.unsubscribe(q)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )

@app.get("/api/tasks/{task_id}/subtitles")
async def get_subtitles(task_id: str):
    task = task_manager.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    return {
        "task_id": task.task_id,
        "state": task.state,
        "subtitles": task.subtitles
    }

@app.get("/api/tasks/{task_id}/speaker-ref")
async def get_speaker_ref(task_id: str):
    task = task_manager.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    candidates = [s for s in task.source_segments if 3 <= s["end"] - s["start"] <= 8]
    if not candidates:
        candidates = [s for s in task.source_segments if 2 <= s["end"] - s["start"] <= 10]
    if not candidates:
        candidates = task.source_segments[:1]
    return {
        "task_id": task.task_id,
        "speaker_ref": task.speaker_ref,
        "segments": [{key: s[key] for key in ("id", "start", "end", "text")} for s in candidates],
        "tts_speaking_rate": task.config.get("tts_speaking_rate", DEFAULT_SPEAKING_RATE),
    }

@app.get("/api/tasks/{task_id}/speaker-ref/audio")
async def get_speaker_ref_audio(task_id: str):
    task = task_manager.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    audio_path = task.speaker_ref.get("audio_path")
    if not audio_path or not os.path.exists(audio_path):
        raise HTTPException(status_code=404, detail="参考原声音频文件不存在")
    return FileResponse(audio_path, media_type="audio/wav")

@app.post("/api/tasks/{task_id}/speaker-ref/update")
async def update_speaker_ref(task_id: str, req: UpdateSpeakerRefRequest):
    new_ref = task_manager.update_speaker_ref(task_id, req.segment_id)
    if not new_ref:
        raise HTTPException(status_code=400, detail="更新参考音频切片失败")
    return {
        "status": "success",
        "speaker_ref": new_ref
    }

@app.post("/api/tasks/{task_id}/subtitles/confirm")
async def confirm_subtitles(task_id: str, req: ConfirmSubtitlesRequest):
    task = task_manager.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    if task.state != TaskState.WAITING_REVIEW:
        raise HTTPException(status_code=409, detail="任务当前不处于字幕校对阶段")

    # Update subtitles with user edits
    edited = {item.id: item for item in req.subtitles}
    if len(edited) != len(req.subtitles) or set(edited) != {item["id"] for item in task.subtitles}:
        raise HTTPException(status_code=400, detail="字幕段落不能重复或遗漏")
    updated = []
    for original in task.subtitles:
        text = edited[original["id"]].translated_text.strip()
        try:
            resolve_speech_duration(
                text, original["end"] - original["start"],
                task.config.get("tts_speaking_rate", DEFAULT_SPEAKING_RATE),
            )
        except ValueError as error:
            raise HTTPException(status_code=400, detail=f"段落 #{original['id']}: {error}") from error
        # Preserve source anchors, transcript and subsegments when saving edits.
        updated.append({**original, "translated_text": text})
    task.subtitles = updated
    task.save_state()

    # Unblock review waiting event
    task.review_event.set()

    return {
        "status": "success",
        "message": "字幕已确认，流水线继续进行配音合成"
    }

@app.post("/api/tts/preview")
async def preview_tts(req: PreviewTTSRequest):
    """Generates a small audio snippet for audition in the web UI using F5-TTS voice clone."""
    temp_preview_dir = TASKS_DIR / "previews"
    temp_preview_dir.mkdir(parents=True, exist_ok=True)
    preview_dir = temp_preview_dir / uuid.uuid4().hex
    preview_dir.mkdir()
    preview_file = preview_dir / "preview.wav"

    try:
        loop = asyncio.get_running_loop()
        ref_audio = req.ref_audio_path
        ref_text = req.ref_audio_text
        target_duration = req.target_duration
        speaking_rate = req.speaking_rate
        speed_mode = req.speed_mode
        if req.task_id:
            task = task_manager.get_task(req.task_id)
            if not task:
                raise HTTPException(status_code=404, detail="任务不存在")
            speaking_rate = speaking_rate if speaking_rate is not None else task.config.get("tts_speaking_rate", DEFAULT_SPEAKING_RATE)
            speed_mode = speed_mode or task.config.get("tts_speed_mode", "balanced")
            if task.speaker_ref:
                ref_audio = task.speaker_ref.get("audio_path")
                ref_text = task.speaker_ref.get("ref_text")
            if req.subtitle_id is not None:
                segment = next((s for s in task.subtitles if s["id"] == req.subtitle_id), None)
                if not segment:
                    raise HTTPException(status_code=404, detail="字幕段落不存在")
                target_duration = segment["end"] - segment["start"]

        if not ref_audio or not os.path.exists(ref_audio):
            raise ValueError("未找到用于克隆的声音参考切片，请确认任务是否已提取原声")

        service = F5TTSMLXService(ref_audio_path=ref_audio, ref_audio_text=ref_text)
        await loop.run_in_executor(
            None,
            lambda: service.synthesize(
                req.text, str(preview_file), speed_mode=speed_mode or "balanced",
                target_duration=target_duration,
                speaking_rate=speaking_rate if speaking_rate is not None else DEFAULT_SPEAKING_RATE,
            )
        )

        if target_duration is not None:
            _, fitted_path = await loop.run_in_executor(
                None, lambda: AudioAligner(preview_dir).prepare_clip(str(preview_file), target_duration, 0)
            )
            return FileResponse(fitted_path, media_type="audio/wav")
        return FileResponse(str(preview_file), media_type="audio/wav")
    except HTTPException:
        raise
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except Exception as e:
        logger.error(f"Preview TTS error: {e}")
        raise HTTPException(status_code=500, detail=f"试听生成失败: {str(e)}")

# Mount frontend build if exists
FRONTEND_DIST = PROJECT_ROOT / "frontend" / "dist"
if FRONTEND_DIST.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIST), html=True), name="frontend")
