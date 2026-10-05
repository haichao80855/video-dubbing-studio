import os
import json
import asyncio
import logging
from typing import Dict, Any, List, Optional
from pathlib import Path
from fastapi import FastAPI, HTTPException, Request, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import StreamingResponse, FileResponse, JSONResponse
from pydantic import BaseModel

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
    speed_mode: str = "balanced"


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
    return {
        "task_id": task.task_id,
        "speaker_ref": task.speaker_ref
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
        # If not waiting, just update subtitles
        pass

    # Update subtitles with user edits
    updated = [item.model_dump() for item in req.subtitles]
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
    preview_file = temp_preview_dir / f"preview_{abs(hash(req.text + str(req.task_id))) % 1000000}.wav"

    try:
        loop = asyncio.get_running_loop()
        ref_audio = req.ref_audio_path
        ref_text = req.ref_audio_text
        if req.task_id:
            task = task_manager.get_task(req.task_id)
            if task and task.speaker_ref:
                ref_audio = task.speaker_ref.get("audio_path")
                ref_text = task.speaker_ref.get("ref_text")

        if not ref_audio or not os.path.exists(ref_audio):
            raise ValueError("未找到用于克隆的声音参考切片，请确认任务是否已提取原声")

        service = F5TTSMLXService(ref_audio_path=ref_audio, ref_audio_text=ref_text)
        await loop.run_in_executor(
            None,
            lambda: service.synthesize(req.text, str(preview_file), speed_mode=req.speed_mode)
        )

        return FileResponse(str(preview_file), media_type="audio/wav")
    except Exception as e:
        logger.error(f"Preview TTS error: {e}")
        raise HTTPException(status_code=500, detail=f"试听生成失败: {str(e)}")

# Mount frontend build if exists
FRONTEND_DIST = PROJECT_ROOT / "frontend" / "dist"
if FRONTEND_DIST.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIST), html=True), name="frontend")
