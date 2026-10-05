import React, { useState, useEffect, useRef } from "react";
import {
  X,
  Volume2,
  CheckCircle,
  Play,
  RotateCcw,
  Sparkles,
  Clock,
  Type,
  FileCheck,
  Mic,
  RefreshCw,
} from "lucide-react";
import {
  SubtitleItem,
  SpeakerRef,
  SpeakerCandidate,
  previewTTSAudio,
  confirmSubtitles,
  fetchSpeakerRef,
  updateSpeakerRef,
} from "../api/client";
import { SettingsState } from "./SettingsModal";

interface SubtitleEditorProps {
  isOpen: boolean;
  onClose: () => void;
  taskId: string;
  initialSubtitles: SubtitleItem[];
  settings: SettingsState;
  onConfirmed: () => void;
}

export const SubtitleEditor: React.FC<SubtitleEditorProps> = ({
  isOpen,
  onClose,
  taskId,
  initialSubtitles,
  settings,
  onConfirmed,
}) => {
  const [subtitles, setSubtitles] = useState<SubtitleItem[]>(initialSubtitles);
  const [speakerRef, setSpeakerRef] = useState<SpeakerRef | null>(null);
  const [speakerCandidates, setSpeakerCandidates] = useState<SpeakerCandidate[]>([]);
  const [speakingRate, setSpeakingRate] = useState(3.8);
  const [audioVersion, setAudioVersion] = useState(0);
  const [previewingId, setPreviewingId] = useState<number | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const submitting = useRef(false);
  const [isUpdatingRef, setIsUpdatingRef] = useState(false);
  const [audioPlayer, setAudioPlayer] = useState<HTMLAudioElement | null>(null);

  useEffect(() => {
    setSubtitles(initialSubtitles);
  }, [initialSubtitles]);

  useEffect(() => {
    if (isOpen && taskId) {
      fetchSpeakerRef(taskId)
        .then((res) => {
          setSpeakerRef(res.speaker_ref);
          setSpeakerCandidates(res.segments);
          setSpeakingRate(res.tts_speaking_rate);
        })
        .catch((err) => console.warn("Fetch speaker ref error:", err));
    }
  }, [isOpen, taskId]);

  if (!isOpen) return null;

  const handleSwitchSpeakerRef = async (segId: number) => {
    try {
      setIsUpdatingRef(true);
      const res = await updateSpeakerRef(taskId, segId);
      setSpeakerRef(res.speaker_ref);
      setAudioVersion((v) => v + 1);
    } catch (e: any) {
      alert("切换参考切片失败: " + e.message);
    } finally {
      setIsUpdatingRef(false);
    }
  };

  const handleTextChange = (id: number, newText: string) => {
    setSubtitles((prev) =>
      prev.map((item) => (item.id === id ? { ...item, translated_text: newText } : item))
    );
  };

  const handlePreview = async (item: SubtitleItem) => {
    try {
      if (audioPlayer) {
        audioPlayer.pause();
      }
      setPreviewingId(item.id);
      const blob = await previewTTSAudio({
        text: item.translated_text || item.original_text || "",
        task_id: taskId,
        subtitle_id: item.id,
      });
      const url = URL.createObjectURL(blob);
      const audio = new Audio(url);
      setAudioPlayer(audio);
      audio.onended = () => setPreviewingId(null);
      audio.onerror = () => setPreviewingId(null);
      await audio.play();
    } catch (e: any) {
      alert("克隆试听失败: " + e.message);
      setPreviewingId(null);
    }
  };

  const handleConfirm = async () => {
    if (submitting.current) return;
    submitting.current = true;
    try {
      setIsSubmitting(true);
      await confirmSubtitles(taskId, subtitles);
      onConfirmed();
    } catch (e: any) {
      alert("保存字幕并继续失败: " + e.message);
    } finally {
      submitting.current = false;
      setIsSubmitting(false);
    }
  };

  const handleReset = () => {
    if (confirm("确定重置所有修改为初始 AI 翻译结果吗？")) {
      setSubtitles(initialSubtitles);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-3 sm:p-6 bg-black/80 backdrop-blur-md animate-fadeIn">
      <div className="bg-slate-900 border border-slate-800 rounded-3xl w-full max-w-5xl shadow-2xl overflow-hidden flex flex-col max-h-[92vh]">
        {/* Header */}
        <div className="px-6 py-4 border-b border-slate-800 flex items-center justify-between bg-slate-900/90">
          <div className="flex items-center space-x-3">
            <div className="p-2 rounded-xl bg-blue-600/10 text-blue-400">
              <FileCheck className="w-5 h-5" />
            </div>
            <div>
              <div className="flex items-center space-x-2">
                <h2 className="text-base font-bold text-white">在线校对中文字幕与时间轴</h2>
                <span className="px-2 py-0.5 rounded-full text-xs bg-slate-800 text-slate-300 font-mono">
                  共 {subtitles.length} 句
                </span>
              </div>
              <p className="text-xs text-slate-400">
                可微调中文翻译文案、试听配音发音；确认后系统将立即按此文案进行 F5-TTS 声音克隆合成。
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-2 rounded-xl text-slate-400 hover:text-white hover:bg-slate-800 transition"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Toolbar info */}
        <div className="px-6 py-2.5 bg-slate-950/60 border-b border-slate-800 flex items-center justify-between text-xs text-slate-400">
          <div className="flex items-center space-x-4">
            <span className="flex items-center space-x-1">
              <Volume2 className="w-3.5 h-3.5 text-blue-400" />
              <span>配音引擎: ✨ F5-TTS MLX (原人物零样本声音克隆)</span>
            </span>
          </div>
          <button
            type="button"
            onClick={handleReset}
            className="flex items-center space-x-1 text-slate-400 hover:text-slate-200 transition"
          >
            <RotateCcw className="w-3.5 h-3.5" />
            <span>重置所有修改</span>
          </button>
        </div>

        {/* Voice Clone Reference Card */}
        <div className="mx-6 my-4 p-4 rounded-2xl bg-gradient-to-r from-blue-950/40 via-indigo-950/30 to-purple-950/40 border border-blue-500/30 space-y-3 shadow-md">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
            <div className="flex items-center space-x-2.5">
              <div className="p-2 rounded-xl bg-blue-500/20 text-blue-400">
                <Mic className="w-4 h-4" />
              </div>
              <div>
                <h4 className="text-xs font-bold text-white flex items-center space-x-2">
                  <span>🎙️ 原人物声音克隆参考切片 (音色种子)</span>
                  <span className="px-2 py-0.5 rounded-full text-[10px] bg-blue-500/20 text-blue-300 font-semibold">
                    Metal 硬件加速
                  </span>
                </h4>
                <p className="text-[11px] text-slate-400">
                  系统已自动截取原视频中最佳发言；所有中文配音将完全以该音色与共鸣感朗读
                </p>
              </div>
            </div>

            {/* Segment switcher */}
            <div className="flex items-center space-x-2">
              <span className="text-[11px] text-slate-300 whitespace-nowrap">更换参考切片:</span>
              <select
                disabled={isUpdatingRef}
                value={speakerRef?.segment_id || ""}
                onChange={(e) => handleSwitchSpeakerRef(Number(e.target.value))}
                className="px-2.5 py-1.5 rounded-xl bg-slate-900 border border-slate-700 text-xs text-slate-100 focus:outline-none focus:border-blue-500 transition max-w-[220px]"
              >
                {speakerCandidates.map((s) => (
                  <option key={s.id} value={s.id}>
                    #{s.id} ({(s.end - s.start).toFixed(1)}s): {s.text.slice(0, 18)}...
                  </option>
                ))}
              </select>
            </div>
          </div>

          {/* Audio player for the reference clip */}
          {speakerRef && (
            <div className="flex flex-col sm:flex-row items-center justify-between gap-3 p-3 rounded-xl bg-slate-950/80 border border-slate-800">
              <div className="text-xs text-slate-300 flex-1 min-w-0">
                <p className="truncate text-slate-200">
                  <span className="text-slate-500 mr-1.5 font-medium">当前音色样本原声:</span>
                  <span className="italic">"{speakerRef.ref_text}"</span>
                </p>
                <p className="text-[10px] text-slate-400 mt-0.5 font-mono">
                  片段 #{speakerRef.segment_id} · {speakerRef.start.toFixed(2)}s ~{" "}
                  {speakerRef.end.toFixed(2)}s (时长: {speakerRef.duration.toFixed(2)}s)
                </p>
              </div>

              <audio
                key={audioVersion}
                controls
                src={`/api/tasks/${taskId}/speaker-ref/audio?v=${audioVersion}`}
                className="h-8 max-w-xs w-full"
              />
            </div>
          )}
        </div>

        {/* Subtitles List Table */}
        <div className="flex-1 overflow-y-auto p-6 space-y-3 bg-slate-950/40">
          {subtitles.map((item) => {
            const duration = Math.max(0.1, item.end - item.start);
            const maxChars = Math.max(1, Math.floor(duration * speakingRate));
            const charCount = Array.from(item.translated_text || "").filter((char) => /[\p{L}\p{N}]/u.test(char)).length;
            const charsPerSec = charCount / duration;
            const isSevereOverflow = charCount > maxChars * 1.25;
            const isWarningOverflow = charCount > maxChars && !isSevereOverflow;

            return (
              <div
                key={item.id}
                className={`p-4 rounded-2xl bg-slate-900/90 border transition space-y-3 ${
                  isSevereOverflow
                    ? "border-rose-500/50 bg-rose-950/10"
                    : isWarningOverflow
                    ? "border-amber-500/40 bg-amber-950/10"
                    : "border-slate-800 hover:border-slate-700"
                }`}
              >
                {/* Meta row */}
                <div className="flex items-center justify-between text-xs text-slate-400">
                  <div className="flex items-center space-x-3 font-mono">
                    <span className="px-2 py-0.5 rounded-md bg-slate-800 text-slate-300 font-bold">
                      #{item.id}
                    </span>
                    <span className="flex items-center space-x-1 text-slate-300">
                      <Clock className="w-3 h-3 text-slate-500" />
                      <span>
                        {item.start.toFixed(2)}s ~ {item.end.toFixed(2)}s
                      </span>
                    </span>
                    <span className="text-slate-400 font-semibold">
                      时长: {duration.toFixed(2)}s · 建议 ≤ {maxChars} 字
                    </span>
                  </div>

                  <div className="flex items-center space-x-3">
                    {/* Speed pace indicator */}
                    <span
                      className={`text-[11px] px-2 py-0.5 rounded-full font-medium ${
                        isSevereOverflow
                          ? "bg-rose-500/20 text-rose-300 border border-rose-500/40 font-semibold"
                          : isWarningOverflow
                          ? "bg-amber-500/20 text-amber-300 border border-amber-500/40"
                          : "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20"
                      }`}
                    >
                      {charCount} / {maxChars} 字 ({charsPerSec.toFixed(1)} 字/秒)
                      {isSevereOverflow
                        ? " · 严重超字 (将引发脱节)"
                        : isWarningOverflow
                        ? " · 偏多 (配音略急促)"
                        : " · 字数合适"}
                    </span>

                    {/* Audition Button */}
                    <button
                      type="button"
                      onClick={() => handlePreview(item)}
                      disabled={previewingId === item.id}
                      className="flex items-center space-x-1 px-2.5 py-1 rounded-lg bg-blue-600/10 hover:bg-blue-600/20 text-blue-400 border border-blue-500/20 transition text-xs font-medium"
                    >
                      {previewingId === item.id ? (
                        <div className="w-3 h-3 border-2 border-blue-400 border-t-transparent rounded-full animate-spin" />
                      ) : (
                        <Play className="w-3 h-3 fill-current" />
                      )}
                      <span>{previewingId === item.id ? "克隆生成中..." : "试听克隆原声"}</span>
                    </button>
                  </div>
                </div>

                {/* Original transcript */}
                <div className="text-xs text-slate-400 bg-slate-950/70 p-2.5 rounded-xl border border-slate-800/80">
                  <span className="text-slate-500 select-none mr-1.5 font-medium">原文:</span>
                  <span>{item.original_text || "无原文"}</span>
                </div>

                {/* Editable Chinese Dubbing Line */}
                <div>
                  <textarea
                    rows={2}
                    value={item.translated_text}
                    onChange={(e) => handleTextChange(item.id, e.target.value)}
                    placeholder="输入中文配音译文..."
                    className="w-full px-3.5 py-2.5 rounded-xl bg-slate-950 border border-slate-800 text-sm text-white placeholder-slate-600 focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 transition resize-none leading-relaxed"
                  />
                </div>
              </div>
            );
          })}
        </div>

        {/* Footer */}
        <div className="px-6 py-4 bg-slate-900 border-t border-slate-800 flex items-center justify-between">
          <span className="text-xs text-slate-400">
            提示：每句保留原视频起点；文案过长时请精简，避免急促朗读或超出时间窗口
          </span>
          <div className="flex space-x-3">
            <button
              onClick={onClose}
              className="px-4 py-2.5 rounded-xl text-xs font-medium text-slate-400 hover:text-white hover:bg-slate-800 transition"
            >
              稍后再说
            </button>
            <button
              onClick={handleConfirm}
              disabled={isSubmitting}
              className="px-6 py-2.5 rounded-xl text-xs font-semibold bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-500 hover:to-indigo-500 text-white shadow-lg shadow-blue-600/30 transition flex items-center space-x-2"
            >
              {isSubmitting ? (
                <>
                  <div className="w-3.5 h-3.5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                  <span>正在提交并启动配音...</span>
                </>
              ) : (
                <>
                  <CheckCircle className="w-4 h-4" />
                  <span>确认字幕并继续生成视频 →</span>
                </>
              )}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
