import React from "react";
import { Sparkles, Settings, Cpu, Video } from "lucide-react";

interface HeaderProps {
  onOpenSettings: () => void;
  hasDeepSeekKey: boolean;
}

export const Header: React.FC<HeaderProps> = ({ onOpenSettings, hasDeepSeekKey }) => {
  return (
    <header className="border-b border-slate-800 bg-slate-900/60 backdrop-blur-md sticky top-0 z-40">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
        <div className="flex items-center space-x-3">
          <div className="w-10 h-10 rounded-xl bg-gradient-to-tr from-blue-600 via-indigo-600 to-purple-500 flex items-center justify-center shadow-lg shadow-blue-500/20">
            <Video className="w-5 h-5 text-white" />
          </div>
          <div>
            <div className="flex items-center space-x-2">
              <h1 className="font-bold text-lg text-white tracking-tight">
                Video Dubbing Studio
              </h1>
              <span className="px-2 py-0.5 text-xs font-semibold rounded-full bg-gradient-to-r from-blue-500/20 to-indigo-500/20 text-blue-300 border border-blue-500/30">
                v2.0 连贯流式版
              </span>
            </div>
            <p className="text-xs text-slate-400">
              Bilibili / YouTube → MLX ASR → DeepSeek 全文通篇意译 → F5-TTS 连续原声解说流 (消灭1秒死寂) → 48kHz 中文 MP4
            </p>
          </div>
        </div>

        <div className="flex items-center space-x-3">
          <div className="hidden sm:flex items-center space-x-2 px-3 py-1.5 rounded-lg bg-slate-800/80 border border-slate-700/60 text-xs text-slate-300">
            <Cpu className="w-3.5 h-3.5 text-emerald-400" />
            <span>Apple Silicon MLX 硬件加速</span>
          </div>

          <button
            onClick={onOpenSettings}
            className={`relative flex items-center space-x-2 px-3.5 py-2 rounded-xl text-xs font-medium transition-all ${
              hasDeepSeekKey
                ? "bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700"
                : "bg-amber-500/10 hover:bg-amber-500/20 text-amber-300 border border-amber-500/30 animate-pulse"
            }`}
          >
            <Settings className="w-4 h-4" />
            <span>API 密钥与模型设置</span>
            {!hasDeepSeekKey && (
              <span className="w-2 h-2 rounded-full bg-amber-400 absolute -top-1 -right-1" />
            )}
          </button>
        </div>
      </div>
    </header>
  );
};
