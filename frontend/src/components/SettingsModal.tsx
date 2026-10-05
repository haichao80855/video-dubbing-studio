import React, { useState, useEffect } from "react";
import {
  X,
  Key,
  CheckCircle,
  AlertCircle,
  Cpu,
  Radio,
  Activity,
  Globe,
  Loader2,
  Check,
  AlertTriangle,
} from "lucide-react";
import { testLLMConnection, LLMTestResult } from "../api/client";

export interface SettingsState {
  deepseekApiKey: string;
  deepseekBaseUrl: string;
  deepseekModel: string;
  dashscopeApiKey: string;
  cosyvoiceEndpoint: string;
  asrModel: string;
}

interface SettingsModalProps {
  isOpen: boolean;
  onClose: () => void;
  settings: SettingsState;
  onSave: (newSettings: SettingsState) => void;
}

export const SettingsModal: React.FC<SettingsModalProps> = ({
  isOpen,
  onClose,
  settings,
  onSave,
}) => {
  const [localSettings, setLocalSettings] = useState<SettingsState>(settings);
  const [savedNotice, setSavedNotice] = useState(false);
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<LLMTestResult | null>(null);

  useEffect(() => {
    setLocalSettings(settings);
    setTestResult(null);
  }, [settings, isOpen]);

  if (!isOpen) return null;

  const handleTestConnection = async () => {
    if (!localSettings.deepseekApiKey.trim()) {
      setTestResult({
        status: "error",
        error: "请先输入 DeepSeek API Key 再进行连通性测试",
      });
      return;
    }

    setTesting(true);
    setTestResult(null);
    try {
      const res = await testLLMConnection({
        api_key: localSettings.deepseekApiKey.trim(),
        base_url: localSettings.deepseekBaseUrl.trim() || "https://api.deepseek.com/v1",
        model: localSettings.deepseekModel.trim() || "deepseek4.1flash",
      });
      setTestResult(res);
    } catch (e: any) {
      setTestResult({
        status: "error",
        error: `请求发送失败: ${e.message}`,
      });
    } finally {
      setTesting(false);
    }
  };

  const handleSave = () => {
    onSave(localSettings);
    setSavedNotice(true);
    setTimeout(() => {
      setSavedNotice(false);
      onClose();
    }, 600);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm animate-fadeIn">
      <div className="bg-slate-900 border border-slate-800 rounded-2xl w-full max-w-lg shadow-2xl overflow-hidden flex flex-col max-h-[90vh]">
        {/* Header */}
        <div className="px-6 py-4 border-b border-slate-800 flex items-center justify-between">
          <div className="flex items-center space-x-2.5">
            <div className="p-2 rounded-lg bg-blue-500/10 text-blue-400">
              <Key className="w-5 h-5" />
            </div>
            <div>
              <h2 className="text-base font-semibold text-white">模型与 API 密钥设置</h2>
              <p className="text-xs text-slate-400">密钥仅存储在您的浏览器本地，不上传服务器</p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 transition"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Body */}
        <div className="p-6 space-y-5 overflow-y-auto flex-1">
          {/* DeepSeek API Key */}
          <div className="space-y-1.5">
            <div className="flex items-center justify-between">
              <label className="text-xs font-medium text-slate-200 flex items-center space-x-1.5">
                <span>DeepSeek API Key</span>
                <span className="text-red-400 font-bold">*</span>
              </label>
              <a
                href="https://platform.deepseek.com/"
                target="_blank"
                rel="noreferrer"
                className="text-xs text-blue-400 hover:underline"
              >
                DeepSeek 控制台 →
              </a>
            </div>
            <input
              type="password"
              placeholder="sk-..."
              value={localSettings.deepseekApiKey}
              onChange={(e) => {
                setLocalSettings({ ...localSettings, deepseekApiKey: e.target.value });
                setTestResult(null);
              }}
              className="w-full px-3.5 py-2.5 rounded-xl bg-slate-950 border border-slate-800 text-sm text-slate-100 placeholder-slate-600 focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 font-mono transition"
            />
            <p className="text-[11px] text-slate-400">
              支持 DeepSeek 官方 API 或第三方 OpenAI 兼容聚合平台（硅基流动、OpenRouter 等）
            </p>
          </div>

          {/* DeepSeek Model Name & Base URL */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3.5">
            <div className="space-y-1.5">
              <label className="text-xs font-medium text-slate-200 flex items-center space-x-1">
                <span>翻译模型名称</span>
                <span className="text-red-400 font-bold">*</span>
              </label>
              <input
                type="text"
                placeholder="deepseek4.1flash"
                value={localSettings.deepseekModel}
                onChange={(e) => {
                  setLocalSettings({ ...localSettings, deepseekModel: e.target.value });
                  setTestResult(null);
                }}
                className="w-full px-3 py-2 rounded-xl bg-slate-950 border border-slate-800 text-xs text-slate-100 placeholder-slate-600 focus:outline-none focus:border-blue-500 font-mono transition"
              />
              <p className="text-[10px] text-slate-500">
                默认 deepseek4.1flash (可填 deepseek-chat 等)
              </p>
            </div>

            <div className="space-y-1.5">
              <label className="text-xs font-medium text-slate-200 flex items-center space-x-1">
                <Globe className="w-3.5 h-3.5 text-slate-400" />
                <span>API Base URL</span>
              </label>
              <input
                type="text"
                placeholder="https://api.deepseek.com/v1"
                value={localSettings.deepseekBaseUrl}
                onChange={(e) => {
                  setLocalSettings({ ...localSettings, deepseekBaseUrl: e.target.value });
                  setTestResult(null);
                }}
                className="w-full px-3 py-2 rounded-xl bg-slate-950 border border-slate-800 text-xs text-slate-100 placeholder-slate-600 focus:outline-none focus:border-blue-500 font-mono transition"
              />
              <p className="text-[10px] text-slate-500">
                官方默认 https://api.deepseek.com/v1
              </p>
            </div>
          </div>

          {/* Connectivity Test Section */}
          <div className="p-3.5 rounded-xl bg-slate-950/80 border border-slate-800 space-y-2.5">
            <div className="flex items-center justify-between">
              <div className="flex items-center space-x-1.5 text-xs text-slate-300 font-medium">
                <Activity className="w-4 h-4 text-blue-400" />
                <span>API 连通性测试</span>
              </div>
              <button
                type="button"
                onClick={handleTestConnection}
                disabled={testing || !localSettings.deepseekApiKey.trim()}
                className={`px-3 py-1.5 rounded-lg text-xs font-semibold flex items-center space-x-1.5 transition ${
                  testing || !localSettings.deepseekApiKey.trim()
                    ? "bg-slate-800 text-slate-500 cursor-not-allowed"
                    : "bg-blue-600/20 hover:bg-blue-600/30 text-blue-300 border border-blue-500/30 active:scale-95"
                }`}
              >
                {testing ? (
                  <>
                    <Loader2 className="w-3.5 h-3.5 animate-spin" />
                    <span>正在测试连接...</span>
                  </>
                ) : (
                  <>
                    <Activity className="w-3.5 h-3.5" />
                    <span>检测连通性</span>
                  </>
                )}
              </button>
            </div>

            {/* Test Result Feedback */}
            {testResult && (
              <div
                className={`p-3 rounded-lg text-xs border transition-all ${
                  testResult.status === "ok"
                    ? "bg-emerald-500/10 border-emerald-500/30 text-emerald-300"
                    : "bg-rose-500/10 border-rose-500/30 text-rose-300"
                }`}
              >
                <div className="flex items-start space-x-2">
                  {testResult.status === "ok" ? (
                    <CheckCircle className="w-4 h-4 text-emerald-400 flex-shrink-0 mt-0.5" />
                  ) : (
                    <AlertTriangle className="w-4 h-4 text-rose-400 flex-shrink-0 mt-0.5" />
                  )}
                  <div className="flex-1 space-y-0.5">
                    <p className="font-semibold">
                      {testResult.status === "ok"
                        ? testResult.message
                        : "连通性测试未通过"}
                    </p>
                    {testResult.status === "ok" && testResult.latency_ms && (
                      <p className="text-[11px] text-emerald-400/80">
                        响应延迟: {testResult.latency_ms} ms · 模型回复:{" "}
                        <span className="font-mono bg-emerald-950/40 px-1 py-0.5 rounded">
                          "{testResult.reply}"
                        </span>
                      </p>
                    )}
                    {testResult.status === "error" && (
                      <p className="text-[11px] text-rose-300/90 break-words leading-relaxed">
                        {testResult.error}
                      </p>
                    )}
                  </div>
                </div>
              </div>
            )}
          </div>

          {/* CosyVoice Config */}
          <div className="border-t border-slate-800/80 pt-4 space-y-4">
            <h3 className="text-xs font-semibold text-slate-300 uppercase tracking-wider flex items-center space-x-1.5">
              <span>CosyVoice 3 扩展配置 (可选)</span>
              <span className="text-[10px] lowercase font-normal px-1.5 py-0.5 rounded bg-slate-800 text-slate-400">
                默认使用免费的 Edge-TTS，无需填写
              </span>
            </h3>

            {/* DashScope API Key */}
            <div className="space-y-1.5">
              <div className="flex items-center justify-between">
                <label className="text-xs font-medium text-slate-200">
                  阿里百炼 DashScope API Key (用于 CosyVoice 官方 API)
                </label>
                <a
                  href="https://bailian.console.aliyun.com/"
                  target="_blank"
                  rel="noreferrer"
                  className="text-xs text-blue-400 hover:underline"
                >
                  百炼控制台 →
                </a>
              </div>
              <input
                type="password"
                placeholder="sk-..."
                value={localSettings.dashscopeApiKey}
                onChange={(e) =>
                  setLocalSettings({ ...localSettings, dashscopeApiKey: e.target.value })
                }
                className="w-full px-3.5 py-2.5 rounded-xl bg-slate-950 border border-slate-800 text-sm text-slate-100 placeholder-slate-600 focus:outline-none focus:border-blue-500 font-mono transition"
              />
            </div>

            {/* Local CosyVoice Endpoint */}
            <div className="space-y-1.5">
              <label className="text-xs font-medium text-slate-200">
                本地 CosyVoice 服务端点 (可选)
              </label>
              <input
                type="text"
                placeholder="http://localhost:50000"
                value={localSettings.cosyvoiceEndpoint}
                onChange={(e) =>
                  setLocalSettings({ ...localSettings, cosyvoiceEndpoint: e.target.value })
                }
                className="w-full px-3.5 py-2.5 rounded-xl bg-slate-950 border border-slate-800 text-sm text-slate-100 placeholder-slate-600 focus:outline-none focus:border-blue-500 font-mono transition"
              />
              <p className="text-[11px] text-slate-400">
                若在本地部署了 CosyVoice 推理容器/脚本，填写本地服务地址
              </p>
            </div>
          </div>

          {/* MLX ASR Model */}
          <div className="border-t border-slate-800/80 pt-4 space-y-1.5">
            <label className="text-xs font-medium text-slate-200 flex items-center space-x-1.5">
              <Cpu className="w-3.5 h-3.5 text-emerald-400" />
              <span>Apple Silicon MLX ASR 模型</span>
            </label>
            <select
              value={localSettings.asrModel}
              onChange={(e) =>
                setLocalSettings({ ...localSettings, asrModel: e.target.value })
              }
              className="w-full px-3.5 py-2.5 rounded-xl bg-slate-950 border border-slate-800 text-sm text-slate-100 focus:outline-none focus:border-blue-500 transition"
            >
              <option value="mlx-community/whisper-large-v3-turbo">
                mlx-community/whisper-large-v3-turbo (推荐 / 极速高精)
              </option>
              <option value="mlx-community/whisper-base">
                mlx-community/whisper-base (轻量低资源)
              </option>
              <option value="mlx-community/whisper-small">
                mlx-community/whisper-small (均衡)
              </option>
            </select>
          </div>
        </div>

        {/* Footer */}
        <div className="px-6 py-4 bg-slate-950/80 border-t border-slate-800 flex items-center justify-between">
          <span className="text-xs text-slate-400 flex items-center space-x-1">
            {localSettings.deepseekApiKey ? (
              <>
                <CheckCircle className="w-3.5 h-3.5 text-emerald-400 inline" />
                <span>DeepSeek Key 已就绪</span>
              </>
            ) : (
              <>
                <AlertCircle className="w-3.5 h-3.5 text-amber-400 inline" />
                <span className="text-amber-300">请配置 DeepSeek API Key</span>
              </>
            )}
          </span>
          <div className="flex space-x-2">
            <button
              onClick={onClose}
              className="px-4 py-2 rounded-xl text-xs font-medium text-slate-400 hover:text-white hover:bg-slate-800 transition"
            >
              取消
            </button>
            <button
              onClick={handleSave}
              className="px-5 py-2 rounded-xl text-xs font-medium bg-blue-600 hover:bg-blue-500 text-white shadow-lg shadow-blue-600/30 transition flex items-center space-x-1.5"
            >
              {savedNotice ? (
                <>
                  <CheckCircle className="w-4 h-4 text-white" />
                  <span>已保存！</span>
                </>
              ) : (
                <span>保存设置</span>
              )}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
