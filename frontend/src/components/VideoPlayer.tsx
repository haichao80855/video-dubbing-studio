import React, { useRef } from "react";
import { Download, FileText, CheckCircle2, RotateCcw, Volume2, Film } from "lucide-react";
import { TaskResult, TaskStatus } from "../api/client";

interface VideoPlayerProps {
  taskStatus: TaskStatus;
  result: TaskResult;
  onReset: () => void;
}

export const VideoPlayer: React.FC<VideoPlayerProps> = ({ taskStatus, result, onReset }) => {
  const videoUrl = `/outputs/${result.filename}`;
  const srtUrl = `/outputs/${result.srt_filename}`;
  const videoRef = useRef<HTMLVideoElement>(null);

  return (
    <div className="bg-slate-900/90 border border-slate-800 rounded-3xl p-6 sm:p-8 shadow-2xl backdrop-blur-sm space-y-6 animate-fadeIn">
      {/* Title & Badge */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-slate-800/80 pb-4">
        <div className="flex items-center space-x-3">
          <div className="w-10 h-10 rounded-2xl bg-emerald-500/10 text-emerald-400 flex items-center justify-center border border-emerald-500/20">
            <CheckCircle2 className="w-5 h-5" />
          </div>
          <div>
            <h2 className="text-base font-bold text-white">🎉 中文配音视频制作完成！</h2>
            <p className="text-xs text-slate-400">
              视频画面、F5-TTS 原声克隆音轨与中文字幕已精确对齐并完成合成
            </p>
          </div>
        </div>

        <button
          onClick={onReset}
          className="flex items-center space-x-2 px-4 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-semibold border border-slate-700/80 transition self-start sm:self-auto"
        >
          <RotateCcw className="w-3.5 h-3.5" />
          <span>制作新视频</span>
        </button>
      </div>

      {/* Embedded Video Player */}
      <div className="rounded-2xl overflow-hidden bg-black border border-slate-800 shadow-inner max-w-4xl mx-auto aspect-video flex items-center justify-center relative group">
        <video
          ref={videoRef}
          controls
          preload="auto"
          className="w-full h-full object-contain"
          src={videoUrl}
        >
          您的浏览器不支持 HTML5 视频播放。
        </video>
      </div>

      {/* Audio Status Notice */}
      <div className="p-3 rounded-xl bg-blue-500/10 border border-blue-500/20 flex items-center space-x-2 text-xs text-blue-300">
        <Volume2 className="w-4 h-4 flex-shrink-0 text-blue-400" />
        <span>
          💡 <strong>声音提示</strong>：已混入标准 48kHz 高保真立体声中文原声克隆配音。若点击播放没有声音，请检查浏览器播放器右下角的音量滑块或静音开关是否已开启。
        </span>
      </div>

      {/* Details & Action Buttons */}
      <div className="flex flex-col sm:flex-row items-center justify-between gap-4 pt-2">
        <div className="text-xs text-slate-400">
          <p className="font-semibold text-slate-200 truncate max-w-md">
            {taskStatus.video_info?.title || result.filename}
          </p>
          <p className="mt-0.5">
            时长: {taskStatus.video_info?.duration ? `${taskStatus.video_info.duration}s` : "完整"} ·
            包含已压制的中文字幕与 48kHz 立体声原声克隆纯语音轨
          </p>
        </div>

        <div className="flex items-center space-x-3 w-full sm:w-auto">
          {/* Download SRT */}
          <a
            href={srtUrl}
            download={result.srt_filename}
            className="flex-1 sm:flex-none flex items-center justify-center space-x-2 px-4 py-3 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-semibold border border-slate-700 transition"
          >
            <FileText className="w-4 h-4 text-purple-400" />
            <span>下载 SRT 字幕</span>
          </a>

          {/* Download MP4 */}
          <a
            href={videoUrl}
            download={result.filename}
            className="flex-1 sm:flex-none flex items-center justify-center space-x-2 px-6 py-3 rounded-xl bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-500 hover:to-indigo-500 text-white text-xs font-semibold shadow-lg shadow-blue-600/30 transition"
          >
            <Download className="w-4 h-4" />
            <span>下载中文 MP4 视频</span>
          </a>
        </div>
      </div>
    </div>
  );
};
