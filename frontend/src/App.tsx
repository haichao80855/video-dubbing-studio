import React, { useState, useEffect } from "react";
import { Header } from "./components/Header";
import { SettingsModal, SettingsState } from "./components/SettingsModal";
import { UrlForm } from "./components/UrlForm";
import { Progress } from "./components/Progress";
import { SubtitleEditor } from "./components/SubtitleEditor";
import { VideoPlayer } from "./components/VideoPlayer";
import {
  ConfigOptions,
  TaskStatus,
  SubtitleItem,
  fetchOptions,
  createTask,
  fetchTaskStatus,
  fetchSubtitles,
  connectTaskSSE,
  CreateTaskParams,
} from "./api/client";

const DEFAULT_SETTINGS: SettingsState = {
  deepseekApiKey: "",
  deepseekBaseUrl: "https://api.deepseek.com/v1",
  deepseekModel: "deepseek4.1flash",
  dashscopeApiKey: "",
  cosyvoiceEndpoint: "",
  asrModel: "mlx-community/whisper-large-v3-turbo",
};

export const App: React.FC = () => {
  // Settings in localStorage
  const [settings, setSettings] = useState<SettingsState>(() => {
    try {
      const saved = localStorage.getItem("vp_deepseek_settings");
      if (saved) return { ...DEFAULT_SETTINGS, ...JSON.parse(saved) };
    } catch (e) {}
    return DEFAULT_SETTINGS;
  });

  const [isSettingsOpen, setIsSettingsOpen] = useState(false);
  const [options, setOptions] = useState<ConfigOptions | null>(null);

  // Active Task State
  const [currentTaskId, setCurrentTaskId] = useState<string | null>(null);
  const [taskStatus, setTaskStatus] = useState<TaskStatus | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  // Review Modal State
  const [isReviewOpen, setIsReviewOpen] = useState(false);
  const [reviewSubtitles, setReviewSubtitles] = useState<SubtitleItem[]>([]);
  const [lastSubmittedParams, setLastSubmittedParams] = useState<CreateTaskParams | null>(null);

  // Load config options on mount
  useEffect(() => {
    fetchOptions()
      .then(setOptions)
      .catch((err) => console.error("Failed to load options:", err));
  }, []);

  const handleSaveSettings = (newSettings: SettingsState) => {
    setSettings(newSettings);
    localStorage.setItem("vp_deepseek_settings", JSON.stringify(newSettings));
  };

  // SSE stream connection whenever currentTaskId changes
  useEffect(() => {
    if (!currentTaskId) return;

    let unsub: (() => void) | null = null;

    const startStream = () => {
      unsub = connectTaskSSE(
        currentTaskId,
        (event) => {
          if (event.type === "init") {
            setTaskStatus((prev) => ({
              ...prev,
              task_id: event.task_id,
              state: event.state,
              progress: event.progress,
              message: event.message,
              logs: event.logs || [],
              video_info: event.video_info || {},
              result: event.result,
              subtitles_count: (event.logs || []).length,
            }));
          } else if (event.type === "progress") {
            setTaskStatus((prev) => {
              if (!prev) return null;
              const newLogs = event.log ? [...prev.logs, event.log] : prev.logs;
              return {
                ...prev,
                state: event.stage,
                progress: event.progress,
                message: event.message,
                logs: newLogs,
              };
            });

            // If entering WAITING_REVIEW, fetch subtitles and open editor
            if (event.stage === "WAITING_REVIEW") {
              fetchSubtitles(currentTaskId).then((res) => {
                setReviewSubtitles(res.subtitles);
                setIsReviewOpen(true);
              });
            }
          } else if (event.type === "review_ready") {
            setReviewSubtitles(event.subtitles || []);
            setIsReviewOpen(true);
          } else if (event.type === "completed") {
            setTaskStatus((prev) =>
              prev
                ? {
                    ...prev,
                    state: "COMPLETED",
                    progress: 100,
                    message: "视频合成完毕！",
                    result: event.result,
                  }
                : null
            );
            setIsLoading(false);
          } else if (event.type === "error") {
            setTaskStatus((prev) =>
              prev
                ? {
                    ...prev,
                    state: "FAILED",
                    error: event.error,
                    message: `任务失败: ${event.error}`,
                  }
                : null
            );
            setIsLoading(false);
          }
        },
        (err) => {
          console.warn("SSE error, falling back to polling", err);
        }
      );
    };

    startStream();

    // Polling fallback every 3 seconds to guarantee freshness
    const interval = setInterval(async () => {
      try {
        const s = await fetchTaskStatus(currentTaskId);
        setTaskStatus(s);
        if (s.state === "WAITING_REVIEW" && reviewSubtitles.length === 0) {
          const subs = await fetchSubtitles(currentTaskId);
          setReviewSubtitles(subs.subtitles);
          setIsReviewOpen(true);
        }
        if (s.state === "COMPLETED" || s.state === "FAILED") {
          setIsLoading(false);
          clearInterval(interval);
        }
      } catch (e) {}
    }, 3000);

    return () => {
      if (unsub) unsub();
      clearInterval(interval);
    };
  }, [currentTaskId]);

  const handleStartTask = async (params: CreateTaskParams) => {
    try {
      setIsLoading(true);
      setLastSubmittedParams(params);
      const res = await createTask(params);
      setCurrentTaskId(res.task_id);
      setTaskStatus({
        task_id: res.task_id,
        state: "PENDING",
        progress: 0,
        message: "正在初始化任务与准备环境...",
        logs: [],
        subtitles_count: 0,
      });
    } catch (e: any) {
      alert("创建任务失败: " + e.message);
      setIsLoading(false);
    }
  };

  const handleReset = () => {
    setCurrentTaskId(null);
    setTaskStatus(null);
    setIsLoading(false);
    setIsReviewOpen(false);
    setReviewSubtitles([]);
  };

  return (
    <div className="min-h-full flex flex-col bg-slate-950 text-slate-100">
      {/* Top Header */}
      <Header
        onOpenSettings={() => setIsSettingsOpen(true)}
        hasDeepSeekKey={Boolean(settings.deepseekApiKey.trim())}
      />

      {/* Main Content Area */}
      <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-8">
        {/* If no task or task is failed / pending, show input form */}
        {!taskStatus || taskStatus.state === "FAILED" ? (
          <div className="space-y-6">
            <div className="text-center max-w-2xl mx-auto space-y-2">
              <h2 className="text-2xl sm:text-3xl font-extrabold tracking-tight text-white">
                将视频一键翻译配音为
                <span className="text-transparent bg-clip-text bg-gradient-to-r from-blue-400 via-indigo-400 to-purple-400">
                  {" "}
                  地道中文 MP4
                </span>
              </h2>
              <p className="text-sm text-slate-400">
                支持 Bilibili & YouTube · Apple Silicon MLX GPU 加速 · DeepSeek 智能意译 ·
                微软 Edge TTS / 阿里 CosyVoice 3
              </p>
            </div>

            <UrlForm
              options={options}
              settings={settings}
              onOpenSettings={() => setIsSettingsOpen(true)}
              onSubmit={handleStartTask}
              isLoading={isLoading}
            />

            {taskStatus?.state === "FAILED" && (
              <Progress taskStatus={taskStatus} />
            )}
          </div>
        ) : taskStatus.state === "COMPLETED" && taskStatus.result ? (
          /* When Completed, show VideoPlayer */
          <div className="space-y-6">
            <VideoPlayer
              taskStatus={taskStatus}
              result={taskStatus.result}
              onReset={handleReset}
            />
            <Progress taskStatus={taskStatus} />
          </div>
        ) : (
          /* In-Progress Stepper View */
          <div className="space-y-6">
            <Progress
              taskStatus={taskStatus}
              onOpenReviewModal={() => setIsReviewOpen(true)}
            />
          </div>
        )}
      </main>

      {/* Settings Modal */}
      <SettingsModal
        isOpen={isSettingsOpen}
        onClose={() => setIsSettingsOpen(false)}
        settings={settings}
        onSave={handleSaveSettings}
      />

      {/* Subtitle Reviewer Modal */}
      {currentTaskId && isReviewOpen && (
        <SubtitleEditor
          isOpen={isReviewOpen}
          onClose={() => setIsReviewOpen(false)}
          taskId={currentTaskId}
          initialSubtitles={reviewSubtitles}
          ttsEngine={lastSubmittedParams?.tts_engine || "edge_tts"}
          voiceName={lastSubmittedParams?.voice_name || "zh-CN-YunxiNeural"}
          settings={settings}
          onConfirmed={() => {
            setIsReviewOpen(false);
          }}
        />
      )}

      {/* Footer */}
      <footer className="border-t border-slate-900 py-6 text-center text-xs text-slate-400">
        <p>Video Dubbing Studio · 专为 Apple Silicon 设计 · 本地 Metal 加速推理与隐私安全</p>
      </footer>
    </div>
  );
};

export default App;
