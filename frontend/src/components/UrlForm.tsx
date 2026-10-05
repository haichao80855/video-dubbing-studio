import React, { useState } from "react";
import {
  Link as LinkIcon,
  Play,
  Mic,
  Subtitles,
  Sliders,
  CheckCircle2,
  AlertTriangle,
  Sparkles,
  Cpu,
  Zap,
} from "lucide-react";
import { ConfigOptions, CreateTaskParams } from "../api/client";
import { SettingsState } from "./SettingsModal";

interface UrlFormProps {
  options: ConfigOptions | null;
  settings: SettingsState;
  onOpenSettings: () => void;
  onSubmit: (params: CreateTaskParams) => void;
  isLoading: boolean;
}

export const UrlForm: React.FC<UrlFormProps> = ({
  options,
  settings,
  onOpenSettings,
  onSubmit,
  isLoading,
}) => {
  const [url, setUrl] = useState("");
  const [hardSub, setHardSub] = useState(true);
  const [autoPipeline, setAutoPipeline] = useState(false); // default: pause for review as requested
  const [ttsSpeedMode, setTtsSpeedMode] = useState("balanced"); // balanced (Euler 8) vs fast (Euler 6) vs quality (Midpoint 8)

  // Detect platform
  const isBilibili = url.includes("bilibili.com") || url.includes("b23.tv");
  const isYoutube = url.includes("youtube.com") || url.includes("youtu.be");

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!url.trim()) return;

    if (!settings.deepseekApiKey.trim()) {
      onOpenSettings();
      return;
    }

    onSubmit({
      url: url.trim(),
      hard_sub: hardSub,
      auto_pipeline: autoPipeline,
      asr_model: settings.asrModel,
      deepseek_model: settings.deepseekModel,
      deepseek_base_url: settings.deepseekBaseUrl,
      deepseek_api_key: settings.deepseekApiKey,
      tts_speed_mode: ttsSpeedMode,
    });
  };

  return (
    <div className="bg-slate-900/80 border border-slate-800 rounded-3xl p-6 sm:p-8 shadow-xl backdrop-blur-sm">
      <form onSubmit={handleSubmit} className="space-y-6">
        {/* URL Input */}
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <label className="text-sm font-semibold text-slate-200 flex items-center space-x-2">
              <LinkIcon className="w-4 h-4 text-blue-400" />
              <span>视频链接 (Bilibili / YouTube)</span>
            </label>
            <div className="flex items-center space-x-2">
              {isBilibili && (
                <span className="px-2 py-0.5 rounded-full text-[11px] font-medium bg-pink-500/10 text-pink-400 border border-pink-500/20">
                  哔哩哔哩 (Bilibili)
                </span>
              )}
              {isYoutube && (
                <span className="px-2 py-0.5 rounded-full text-[11px] font-medium bg-red-500/10 text-red-400 border border-red-500/20">
                  YouTube
                </span>
              )}
            </div>
          </div>
          <div className="relative">
            <input
              type="text"
              required
              placeholder="例如: https://www.bilibili.com/video/BV1xx411c7mD 或 https://www.youtube.com/watch?v=..."
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              className="w-full px-4 py-3.5 rounded-2xl bg-slate-950 border border-slate-800 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20 transition font-mono"
            />
          </div>
        </div>

        {/* Configurations Grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-5 pt-2">
          {/* F5-TTS Voice Clone & Speed Mode Card */}
          <div className="space-y-3 p-4 rounded-2xl bg-slate-950/60 border border-blue-500/20">
            <div className="flex items-center justify-between">
              <label className="text-xs font-semibold text-white flex items-center space-x-1.5">
                <Mic className="w-4 h-4 text-blue-400" />
                <span>原人物声音克隆 (F5-TTS MLX)</span>
              </label>
              <span className="px-2 py-0.5 rounded-full text-[10px] bg-blue-500/20 text-blue-300 font-semibold border border-blue-500/30">
                Metal 硬件加速
              </span>
            </div>

            {/* Speed Mode Selector */}
            <div className="space-y-1.5 pt-1">
              <label className="text-[11px] text-slate-300 font-medium flex items-center space-x-1">
                <Zap className="w-3.5 h-3.5 text-amber-400" />
                <span>推理速度模式 (Flow Matching ODE)</span>
              </label>
              <div className="grid grid-cols-3 gap-1.5 p-1 rounded-xl bg-slate-900 border border-slate-800 text-[11px]">
                <button
                  type="button"
                  onClick={() => setTtsSpeedMode("balanced")}
                  className={`py-1.5 px-2 rounded-lg transition text-center ${
                    ttsSpeedMode === "balanced"
                      ? "bg-blue-600 text-white font-semibold shadow-sm"
                      : "text-slate-400 hover:text-white"
                  }`}
                >
                  ⚡️ 极速平衡
                </button>
                <button
                  type="button"
                  onClick={() => setTtsSpeedMode("fast")}
                  className={`py-1.5 px-2 rounded-lg transition text-center ${
                    ttsSpeedMode === "fast"
                      ? "bg-blue-600 text-white font-semibold shadow-sm"
                      : "text-slate-400 hover:text-white"
                  }`}
                >
                  🚀 飞速模式
                </button>
                <button
                  type="button"
                  onClick={() => setTtsSpeedMode("quality")}
                  className={`py-1.5 px-2 rounded-lg transition text-center ${
                    ttsSpeedMode === "quality"
                      ? "bg-blue-600 text-white font-semibold shadow-sm"
                      : "text-slate-400 hover:text-white"
                  }`}
                >
                  🎯 高精模式
                </button>
              </div>
              <p className="text-[10px] text-slate-400 leading-relaxed">
                {ttsSpeedMode === "fast"
                  ? "🚀 飞速 (Euler 6步)：5分钟视频仅需约2~2.5分钟，性能提升5倍！"
                  : ttsSpeedMode === "quality"
                  ? "🎯 高精 (Midpoint 8步)：极佳细节平滑度，5分钟视频约3.5~4分钟。"
                  : "⚡️ 极速平衡 (Euler 8步·推荐)：音质与速度兼顾，相比旧版提速3.5倍！"}
              </p>
            </div>
          </div>

          {/* Subtitle & Pipeline Mode */}
          <div className="space-y-3 p-4 rounded-2xl bg-slate-950/60 border border-slate-800/80">
            <label className="text-xs font-semibold text-slate-300 flex items-center space-x-1.5">
              <Sliders className="w-4 h-4 text-purple-400" />
              <span>流程与字幕选项</span>
            </label>

            <div className="space-y-2 pt-0.5">
              {/* Review switch */}
              <label className="flex items-center justify-between cursor-pointer group">
                <span className="text-xs text-slate-300 group-hover:text-white transition">
                  翻译后暂停并在前端在线校对字幕与原声音色
                </span>
                <input
                  type="checkbox"
                  checked={!autoPipeline}
                  onChange={(e) => setAutoPipeline(!e.target.checked)}
                  className="w-4 h-4 rounded text-blue-600 bg-slate-900 border-slate-700 focus:ring-blue-500"
                />
              </label>

              {/* Hard sub switch */}
              <label className="flex items-center justify-between cursor-pointer group">
                <span className="text-xs text-slate-300 group-hover:text-white transition">
                  压制中文字幕到画面中 (硬字幕)
                </span>
                <input
                  type="checkbox"
                  checked={hardSub}
                  onChange={(e) => setHardSub(e.target.checked)}
                  className="w-4 h-4 rounded text-blue-600 bg-slate-900 border-slate-700 focus:ring-blue-500"
                />
              </label>
            </div>
            <p className="text-[11px] text-slate-400">
              开启校对可在生成配音前试听原声音色种子、微调文案，并在线试听单句发音
            </p>
          </div>
        </div>

        {/* Warning if DeepSeek Key missing */}
        {!settings.deepseekApiKey && (
          <div className="p-3.5 rounded-2xl bg-amber-500/10 border border-amber-500/20 flex items-center justify-between">
            <div className="flex items-center space-x-2 text-xs text-amber-300">
              <AlertTriangle className="w-4 h-4 flex-shrink-0" />
              <span>尚未配置 DeepSeek API Key，无法进行意译与配音节奏适配</span>
            </div>
            <button
              type="button"
              onClick={onOpenSettings}
              className="text-xs text-amber-300 font-semibold underline hover:text-amber-200"
            >
              立即配置 →
            </button>
          </div>
        )}

        {/* Action Button */}
        <div className="pt-2">
          <button
            type="submit"
            disabled={isLoading || !url.trim()}
            className={`w-full py-4 rounded-2xl text-sm font-semibold flex items-center justify-center space-x-2 shadow-lg transition-all ${
              isLoading || !url.trim()
                ? "bg-slate-800 text-slate-500 cursor-not-allowed"
                : "bg-gradient-to-r from-blue-600 via-indigo-600 to-purple-600 hover:from-blue-500 hover:to-purple-500 text-white shadow-blue-600/25 active:scale-[0.99]"
            }`}
          >
            {isLoading ? (
              <>
                <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                <span>正在执行全篇连贯解说流式克隆流水线...</span>
              </>
            ) : (
              <>
                <Sparkles className="w-4 h-4" />
                <span>开始全篇连贯解说 (URL → 全文意译 → 连续流式原声克隆 → 48kHz MP4)</span>
              </>
            )}
          </button>
        </div>
      </form>
    </div>
  );
};
