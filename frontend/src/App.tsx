import React, { useState, useEffect, useRef } from "react";
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
  const confirmedReviewTask = useRef<string | null>(null);
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
    let active = true;
    let latestStage: TaskStatus["state"] = "PENDING";
    let statusVersion = 0;
    let reviewLoaded = false;
    let reviewLoading = false;

    const canReview = () => active && latestStage === "WAITING_REVIEW" &&
      confirmedReviewTask.current !== currentTaskId;

    const updateStage = (stage: TaskStatus["state"]) => {
      if (!active || (stage === "WAITING_REVIEW" && confirmedReviewTask.current === currentTaskId)) return false;
      latestStage = stage;
      statusVersion += 1;
      if (["TTS", "ALIGNING", "COMPOSING", "COMPLETED", "FAILED"].includes(stage)) {
        confirmedReviewTask.current = currentTaskId;
        setIsReviewOpen(false);
      }
      return true;
    };

    const loadReview = async (subtitles?: SubtitleItem[]) => {
      if (!canReview() || reviewLoaded) return;
      // review_ready may supply data while the REST request is still in flight.
      if (subtitles) {
        reviewLoaded = true;
        setReviewSubtitles(subtitles);
        setIsReviewOpen(true);
        return;
      }
      if (reviewLoading) return;
      reviewLoading = true;
      try {
        const res = await fetchSubtitles(currentTaskId);
        if (!canReview() || reviewLoaded || res.state !== "WAITING_REVIEW") return;
        reviewLoaded = true;
        setReviewSubtitles(res.subtitles);
        setIsReviewOpen(true);
      } catch (err) {
        console.warn("Failed to load subtitles:", err);
      } finally {
        reviewLoading = false;
      }
    };

    const startStream = () => {
      unsub = connectTaskSSE(
        currentTaskId,
        (event) => {
          if (!active) return;
          if (event.type === "init") {
            if (!updateStage(event.state)) return;
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
            void loadReview();
          } else if (event.type === "progress") {
            if (!updateStage(event.stage)) return;
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

            void loadReview();
          } else if (event.type === "review_ready") {
            void loadReview(event.subtitles);
          } else if (event.type === "completed") {
            if (!updateStage("COMPLETED")) return;
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
            if (!updateStage("FAILED")) return;
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
      const requestVersion = statusVersion;
      try {
        const s = await fetchTaskStatus(currentTaskId);
        // SSE may have advanced the task while this polling request was in flight.
        if (!active || requestVersion !== statusVersion || !updateStage(s.state)) return;
        setTaskStatus(s);
        void loadReview();
        if (s.state === "COMPLETED" || s.state === "FAILED") {
          setIsLoading(false);
          clearInterval(interval);
        }
      } catch (e) {}
    }, 3000);

    return () => {
      active = false;
      if (unsub) unsub();
      clearInterval(interval);
    };
  }, [currentTaskId]);

  const handleStartTask = async (params: CreateTaskParams) => {
    try {
      setIsLoading(true);
      setLastSubmittedParams(params);
      const res = await createTask(params);
      confirmedReviewTask.current = null;
      setIsReviewOpen(false);
      setReviewSubtitles([]);
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
    confirmedReviewTask.current = null;
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
                F5-TTS MLX 原人物零样本声音克隆
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
              onOpenReviewModal={() => {
                if (taskStatus.state === "WAITING_REVIEW" && confirmedReviewTask.current !== currentTaskId) {
                  setIsReviewOpen(true);
                }
              }}
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
          settings={settings}
          onConfirmed={() => {
            confirmedReviewTask.current = currentTaskId;
            setIsReviewOpen(false);
            setTaskStatus((prev) => prev?.task_id === currentTaskId && prev.state === "WAITING_REVIEW"
              ? { ...prev, state: "TTS", progress: 0, message: "字幕已确认，开始原声克隆配音..." }
              : prev);
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
