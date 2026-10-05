import React, { useState } from "react";
import {
  Link as LinkIcon,
  Play,
  Volume2,
  Subtitles,
  Sliders,
  CheckCircle2,
  AlertTriangle,
  Sparkles,
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
  const [ttsEngine, setTtsEngine] = useState("edge_tts");
  const [voiceName, setVoiceName] = useState("zh-CN-YunxiNeural");
  const [hardSub, setHardSub] = useState(true);
  const [autoPipeline, setAutoPipeline] = useState(false); // default: pause for review as requested

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
      tts_engine: ttsEngine,
      voice_name: voiceName,
      hard_sub: hardSub,
      auto_pipeline: autoPipeline,
      asr_model: settings.asrModel,
      deepseek_model: settings.deepseekModel,
      deepseek_base_url: settings.deepseekBaseUrl,
      deepseek_api_key: settings.deepseekApiKey,
      dashscope_api_key: settings.dashscopeApiKey,
      cosyvoice_endpoint: settings.cosyvoiceEndpoint,
    });
  };

  const currentVoices =
    ttsEngine === "cosyvoice"
      ? options?.cosyvoice_voices || []
      : options?.edge_tts_voices || [];

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
          {/* TTS Engine & Voice */}
          <div className="space-y-3 p-4 rounded-2xl bg-slate-950/60 border border-slate-800/80">
            <div className="flex items-center justify-between">
              <label className="text-xs font-semibold text-slate-300 flex items-center space-x-1.5">
                <Volume2 className="w-4 h-4 text-blue-400" />
                <span>中文配音引擎与音色</span>
              </label>
              <div className="flex rounded-lg bg-slate-900 p-0.5 border border-slate-800 text-xs">
                <button
                  type="button"
                  onClick={() => {
                    setTtsEngine("edge_tts");
                    setVoiceName("zh-CN-YunxiNeural");
                  }}
                  className={`px-2.5 py-1 rounded-md transition ${
                    ttsEngine === "edge_tts"
                      ? "bg-blue-600 text-white font-medium"
                      : "text-slate-400 hover:text-white"
                  }`}
                >
                  Edge TTS (免费)
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setTtsEngine("cosyvoice");
                    setVoiceName("longxiaochun");
                  }}
                  className={`px-2.5 py-1 rounded-md transition ${
                    ttsEngine === "cosyvoice"
                      ? "bg-blue-600 text-white font-medium"
                      : "text-slate-400 hover:text-white"
                  }`}
                >
                  CosyVoice 3
                </button>
              </div>
            </div>

            <select
              value={voiceName}
              onChange={(e) => setVoiceName(e.target.value)}
              className="w-full px-3 py-2 rounded-xl bg-slate-900 border border-slate-800 text-xs text-slate-200 focus:outline-none focus:border-blue-500 transition"
            >
              {currentVoices.map((v) => (
                <option key={v.id} value={v.id}>
                  {v.name}
                </option>
              ))}
            </select>
            <p className="text-[11px] text-slate-400">
              {ttsEngine === "edge_tts"
                ? "微软神经语音库，无需配置 Key，支持极速多线程合成"
                : "CosyVoice 3 自然情感表现力音色（需配置百炼 Key 或本地端点）"}
            </p>
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
                  翻译后暂停并在前端在线校对字幕
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
              开启校对可在生成配音前微调文案与时间轴并在线试听单句发音
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
                <span>正在执行翻译与配音流水线...</span>
              </>
            ) : (
              <>
                <Sparkles className="w-4 h-4" />
                <span>开始全流程处理 (URL → MLX → Gemini → TTS → MP4)</span>
              </>
            )}
          </button>
        </div>
      </form>
    </div>
  );
};
