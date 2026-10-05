export interface VoiceOption {
  id: string;
  name: string;
  gender: string;
}

export interface ModelOption {
  id: string;
  name: string;
}

export interface ConfigOptions {
  asr_models: ModelOption[];
  tts_engine?: string;
  tts_name?: string;
}

export interface SubtitleItem {
  id: number;
  start: number;
  end: number;
  duration?: number;
  original_text?: string;
  translated_text: string;
}

export interface TaskLog {
  time: string;
  stage: string;
  progress: number;
  message: string;
}

export interface TaskResult {
  output_mp4: string;
  output_srt: string;
  filename: string;
  srt_filename: string;
  vtt_filename?: string;
  subtitle_mode?: "hard" | "soft";
  warnings?: string[];
}

export interface SpeakerRef {
  segment_id: number;
  start: number;
  end: number;
  duration: number;
  ref_text: string;
  audio_path: string;
}

export interface SpeakerCandidate {
  id: number;
  start: number;
  end: number;
  text: string;
}

export interface TaskStatus {
  task_id: string;
  state:
    | "PENDING"
    | "DOWNLOADING"
    | "ASR"
    | "TRANSLATING"
    | "WAITING_REVIEW"
    | "TTS"
    | "ALIGNING"
    | "COMPOSING"
    | "COMPLETED"
    | "FAILED";
  progress: number;
  message: string;
  video_info?: {
    title?: string;
    duration?: number;
    uploader?: string;
    thumbnail?: string;
  };
  speaker_ref?: SpeakerRef;
  logs: TaskLog[];
  subtitles_count: number;
  result?: TaskResult;
  error?: string;
}

export interface CreateTaskParams {
  url: string;
  hard_sub: boolean;
  auto_pipeline: boolean;
  asr_model?: string;
  deepseek_model?: string;
  deepseek_base_url?: string;
  deepseek_api_key: string;
  tts_speed_mode?: string;
  tts_speaking_rate?: number;
}

export interface LLMTestResult {
  status: "ok" | "error";
  latency_ms?: number;
  model?: string;
  reply?: string;
  message?: string;
  error?: string;
  status_code?: number;
}

const API_BASE = "";

export async function testLLMConnection(params: {
  api_key: string;
  base_url?: string;
  model?: string;
}): Promise<LLMTestResult> {
  const res = await fetch(`${API_BASE}/api/config/test-llm`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(params),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ error: "网络请求失败" }));
    return { status: "error", error: err.error || `HTTP ${res.status}` };
  }
  return res.json();
}

export async function fetchOptions(): Promise<ConfigOptions> {
  const res = await fetch(`${API_BASE}/api/config/options`);
  if (!res.ok) throw new Error("获取配置列表失败");
  return res.json();
}

export async function createTask(params: CreateTaskParams): Promise<{ task_id: string }> {
  const res = await fetch(`${API_BASE}/api/tasks/create`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(params),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "创建任务失败" }));
    throw new Error(err.detail || "创建任务失败");
  }
  return res.json();
}

export async function fetchTaskStatus(taskId: string): Promise<TaskStatus> {
  const res = await fetch(`${API_BASE}/api/tasks/${taskId}/status`);
  if (!res.ok) throw new Error("获取任务状态失败");
  return res.json();
}

export async function fetchSubtitles(taskId: string): Promise<{ state: TaskStatus["state"]; subtitles: SubtitleItem[] }> {
  const res = await fetch(`${API_BASE}/api/tasks/${taskId}/subtitles`);
  if (!res.ok) throw new Error("获取字幕失败");
  return res.json();
}

export async function confirmSubtitles(taskId: string, subtitles: SubtitleItem[]): Promise<void> {
  const res = await fetch(`${API_BASE}/api/tasks/${taskId}/subtitles/confirm`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ subtitles }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "确认字幕失败" }));
    throw new Error(err.detail || "确认字幕失败");
  }
}

export async function fetchSpeakerRef(taskId: string): Promise<{
  task_id: string;
  speaker_ref: SpeakerRef;
  segments: SpeakerCandidate[];
  tts_speaking_rate: number;
}> {
  const res = await fetch(`${API_BASE}/api/tasks/${taskId}/speaker-ref`);
  if (!res.ok) throw new Error("获取原声参考切片失败");
  return res.json();
}

export async function updateSpeakerRef(
  taskId: string,
  segmentId: number
): Promise<{ status: string; speaker_ref: SpeakerRef }> {
  const res = await fetch(`${API_BASE}/api/tasks/${taskId}/speaker-ref/update`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ segment_id: segmentId }),
  });
  if (!res.ok) throw new Error("切换原声参考切片失败");
  return res.json();
}

export async function previewTTSAudio(params: {
  text: string;
  task_id?: string;
  ref_audio_path?: string;
  ref_audio_text?: string;
  speed_mode?: string;
  subtitle_id?: number;
  target_duration?: number;
  speaking_rate?: number;
}): Promise<Blob> {
  const res = await fetch(`${API_BASE}/api/tts/preview`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(params),
  });
  if (!res.ok) {
    const error = await res.json().catch(() => ({ detail: "试听生成失败" }));
    throw new Error(error.detail || "试听生成失败");
  }
  return res.blob();
}

export function connectTaskSSE(
  taskId: string,
  onEvent: (event: any) => void,
  onError?: (err: any) => void
): () => void {
  const es = new EventSource(`${API_BASE}/api/tasks/${taskId}/events`);
  es.onmessage = (e) => {
    try {
      const data = JSON.parse(e.data);
      onEvent(data);
    } catch (err) {
      // ignore parse errors or ping
    }
  };
  es.onerror = (e) => {
    if (onError) onError(e);
  };
  return () => {
    es.close();
  };
}
