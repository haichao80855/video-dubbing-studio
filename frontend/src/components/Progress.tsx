import React, { useState, useRef, useEffect } from "react";
import {
  Download,
  Mic,
  Languages,
  CheckSquare,
  Volume2,
  SlidersHorizontal,
  Film,
  CheckCircle2,
  AlertCircle,
  Terminal,
  ChevronDown,
  ChevronUp,
} from "lucide-react";
import { TaskStatus } from "../api/client";

interface ProgressProps {
  taskStatus: TaskStatus;
  onOpenReviewModal?: () => void;
}

const STAGES = [
  { key: "DOWNLOADING", label: "下载视频", icon: Download },
  { key: "ASR", label: "MLX语音识别", icon: Mic },
  { key: "TRANSLATING", label: "DeepSeek翻译", icon: Languages },
  { key: "WAITING_REVIEW", label: "人工校对", icon: CheckSquare },
  { key: "TTS", label: "TTS配音", icon: Volume2 },
  { key: "ALIGNING", label: "时间轴对齐", icon: SlidersHorizontal },
  { key: "COMPOSING", label: "FFmpeg合成", icon: Film },
];

export const Progress: React.FC<ProgressProps> = ({ taskStatus, onOpenReviewModal }) => {
  const [showLogs, setShowLogs] = useState(true);
  const logContainerRef = useRef<HTMLDivElement>(null);

  // Auto-scroll logs
  useEffect(() => {
    if (logContainerRef.current) {
      logContainerRef.current.scrollTop = logContainerRef.current.scrollHeight;
    }
  }, [taskStatus.logs]);

  const currentStageIndex = STAGES.findIndex((s) => s.key === taskStatus.state);
  const isFailed = taskStatus.state === "FAILED";
  const isCompleted = taskStatus.state === "COMPLETED";

  return (
    <div className="bg-slate-900/80 border border-slate-800 rounded-3xl p-6 sm:p-8 shadow-xl backdrop-blur-sm space-y-6">
      {/* Video Info Card (if downloaded) */}
      {taskStatus.video_info?.title && (
        <div className="flex flex-col sm:flex-row items-start sm:items-center space-y-3 sm:space-y-0 sm:space-x-4 p-4 rounded-2xl bg-slate-950/60 border border-slate-800/80">
          {taskStatus.video_info.thumbnail ? (
            <img
              src={taskStatus.video_info.thumbnail}
              alt="cover"
              className="w-24 h-16 object-cover rounded-xl border border-slate-800"
            />
          ) : (
            <div className="w-24 h-16 bg-slate-800 rounded-xl flex items-center justify-center text-slate-500">
              <Film className="w-6 h-6" />
            </div>
          )}
          <div className="flex-1 min-w-0">
            <h3 className="text-sm font-semibold text-white truncate">
              {taskStatus.video_info.title}
            </h3>
            <p className="text-xs text-slate-400 mt-0.5">
              UP主/作者: {taskStatus.video_info.uploader || "未知"} · 视频时长:{" "}
              {taskStatus.video_info.duration ? `${taskStatus.video_info.duration} 秒` : "未知"}
            </p>
          </div>
        </div>
      )}

      {/* Stepper Pipeline */}
      <div className="py-2">
        <div className="grid grid-cols-2 sm:grid-cols-4 md:grid-cols-7 gap-2">
          {STAGES.map((stage, idx) => {
            const Icon = stage.icon;
            const isPast =
              isCompleted || (currentStageIndex !== -1 && idx < currentStageIndex);
            const isCurrent = taskStatus.state === stage.key;

            return (
              <div
                key={stage.key}
                className={`flex flex-col items-center p-3 rounded-2xl border transition-all ${
                  isCurrent
                    ? "bg-blue-600/10 border-blue-500/50 shadow-md shadow-blue-500/10"
                    : isPast
                    ? "bg-slate-950/40 border-emerald-500/20 text-emerald-400"
                    : "bg-slate-950/20 border-slate-800/60 text-slate-500"
                }`}
              >
                <div
                  className={`w-8 h-8 rounded-xl flex items-center justify-center mb-1.5 transition-all ${
                    isCurrent
                      ? "bg-blue-600 text-white animate-pulse"
                      : isPast
                      ? "bg-emerald-500/20 text-emerald-400"
                      : "bg-slate-800 text-slate-500"
                  }`}
                >
                  {isPast ? <CheckCircle2 className="w-4 h-4" /> : <Icon className="w-4 h-4" />}
                </div>
                <span
                  className={`text-[11px] font-medium text-center ${
                    isCurrent
                      ? "text-blue-400 font-semibold"
                      : isPast
                      ? "text-emerald-400"
                      : "text-slate-400"
                  }`}
                >
                  {stage.label}
                </span>
              </div>
            );
          })}
        </div>
      </div>

      {/* Progress Bar & Current Message */}
      <div className="space-y-2">
        <div className="flex items-center justify-between text-xs">
          <div className="flex items-center space-x-2">
            {isFailed ? (
              <AlertCircle className="w-4 h-4 text-rose-400" />
            ) : isCompleted ? (
              <CheckCircle2 className="w-4 h-4 text-emerald-400" />
            ) : (
              <div className="w-2.5 h-2.5 rounded-full bg-blue-500 animate-ping" />
            )}
            <span
              className={`font-medium ${
                isFailed ? "text-rose-400" : isCompleted ? "text-emerald-400" : "text-slate-200"
              }`}
            >
              {taskStatus.message}
            </span>
          </div>
          <span className="font-mono text-slate-400 font-semibold">
            {taskStatus.progress.toFixed(0)}%
          </span>
        </div>

        <div className="w-full h-2.5 bg-slate-950 rounded-full overflow-hidden p-0.5 border border-slate-800">
          <div
            className={`h-full rounded-full transition-all duration-300 ${
              isFailed
                ? "bg-rose-500"
                : isCompleted
                ? "bg-emerald-500"
                : "bg-gradient-to-r from-blue-600 to-indigo-500"
            }`}
            style={{ width: `${Math.max(3, taskStatus.progress)}%` }}
          />
        </div>
      </div>

      {/* Review Banner if WAITING_REVIEW */}
      {taskStatus.state === "WAITING_REVIEW" && onOpenReviewModal && (
        <div className="p-4 rounded-2xl bg-amber-500/10 border border-amber-500/30 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 animate-fadeIn">
          <div>
            <h4 className="text-sm font-semibold text-amber-300">
              ✍️ 字幕已翻译完毕，正在等待人工在线校对
            </h4>
            <p className="text-xs text-amber-200/80 mt-0.5">
              您可以预览和修改每句中文译文、试听单句发音，确认后再一键生成最终视频。
            </p>
          </div>
          <button
            onClick={onOpenReviewModal}
            className="px-4 py-2 rounded-xl text-xs font-semibold bg-amber-500 hover:bg-amber-400 text-slate-950 shadow-md shadow-amber-500/20 transition flex-shrink-0"
          >
            打开在线校对窗口 →
          </button>
        </div>
      )}

      {/* Live Logs Terminal */}
      <div className="rounded-2xl bg-slate-950 border border-slate-800 overflow-hidden">
        <button
          type="button"
          onClick={() => setShowLogs(!showLogs)}
          className="w-full px-4 py-2.5 bg-slate-900/60 border-b border-slate-800 flex items-center justify-between text-xs text-slate-400 hover:text-slate-200 transition"
        >
          <div className="flex items-center space-x-2">
            <Terminal className="w-3.5 h-3.5 text-blue-400" />
            <span className="font-mono">实时执行日志 ({taskStatus.logs.length})</span>
          </div>
          {showLogs ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
        </button>

        {showLogs && (
          <div
            ref={logContainerRef}
            className="p-4 max-h-52 overflow-y-auto font-mono text-xs space-y-1.5 scroll-smooth"
          >
            {taskStatus.logs.map((log, i) => (
              <div key={i} className="flex items-start space-x-2 text-slate-400 leading-relaxed">
                <span className="text-slate-600 select-none">[{log.time}]</span>
                <span className="text-blue-400 font-medium select-none">
                  [{log.stage}]
                </span>
                <span className="text-slate-300">{log.message}</span>
              </div>
            ))}
            {taskStatus.logs.length === 0 && (
              <p className="text-slate-600 italic">正在初始化流水线...</p>
            )}
          </div>
        )}
      </div>
    </div>
  );
};
