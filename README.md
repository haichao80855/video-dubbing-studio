# 🎬 Video Dubbing Studio (视频智能翻译与原声克隆配音系统)

> 输入 **Bilibili / YouTube** 视频链接，通过 **MLX ASR → DeepSeek 意译 → F5-TTS MLX (原人物声音克隆) / Edge TTS → Forced Alignment → FFmpeg**，全自动或人机协同输出高质量**中文配音 MP4 视频**。

---

## 🌟 核心特性与架构

```
[Bilibili / YouTube URL]
         │
         ▼ (yt-dlp)
[原视频与 16kHz WAV 提取]
         │
         ▼ (mlx-whisper Apple Silicon GPU 加速)
[精准词级时间戳识别 + 自动截取原人物音色切片 (3~6秒)]
         │
         ▼ (DeepSeek 4.1 Flash / Chat API)
[口语化意译 + 语速时长匹配]
         │
         ▼ (现代化 Web 界面: 可选在线校对与原声试听/自选)
[在线听取/更换原声音色种子 + 校对中文字幕] ──► 用户确认
         │
         ▼ (F5-TTS MLX 零样本声音克隆 / Edge-TTS)
[复刻原作者声线与音色，合成中文配音 (Voice Cloned Audio)]
         │
         ▼ (Forced Alignment & atempo 智能变速)
[保调变速 + 静音填充 + 全轨时间对齐]
         │
         ▼ (FFmpeg libass 压制)
[输出纯配音中文 MP4 视频与 SRT 字幕]
```

- **🎙️ 原人物零样本声音克隆 (Zero-Shot Voice Cloning)**：专为 Apple Silicon Metal 硬件加速优化的 `F5-TTS MLX`，自动截取原视频中 3~6 秒最清晰发言作为音色种子，将翻译出的中文完全以**原视频作者的声线、共鸣与说话韵律**朗读出来，实现真正的「原作者本人说地道中文」！
- **极速流畅的 Web 界面**：React + Vite + Tailwind CSS，现代精致暗色风格，支持响应式设计与实时流水线进度监控。
- **前端直接输入 API 密钥 & 一键测试连通性**：在前端设置弹窗中直接输入 `DeepSeek API Key`、自定义 `API Base URL` 与模型名称（默认 `deepseek4.1flash`），内置「检测连通性」按钮即时显示响应延迟与状态诊断，密钥存储在用户浏览器本地（`localStorage`）。
- **Apple Silicon 硬件加速**：底层采用 Metal 优化的 `mlx-whisper` 与 `F5-TTS MLX`，在 M 系列 Mac 芯片上推理速度极快，自带精准词级时间戳。
- **配音级智能意译 (DeepSeek)**：Prompt 针对中文配音场景深度调优，严格根据原视频时长控制中文汉字数量（~3.5-4.5字/秒），告别冗长无法念完的机翻。
- **人机协同在线校对 & 原声试听**：翻译完成后可暂停，支持在界面中试听截取的原人物音色样本（可一键切换更换其他发言片段作为音色种子），支持修改中文配音稿，并提供**单句克隆配音试听**功能。
- **多引擎配音**：
  - **F5-TTS MLX (推荐 / 默认)**：完全本地离线、零 API 成本、极高还原度复刻原人物声音。
  - **Microsoft Edge TTS**：完全免费、零配置、极速合成，内置云希、晓晓、云健等数十种自然拟真音色。
  - **CosyVoice 3**：支持阿里百炼 DashScope 官方 API 及本地私有化部署端点，高表现力情感音色。
- **智能时间对齐 (Time-stretching)**：使用 FFmpeg `atempo` 滤镜进行保调变速（不改变音调音质），自动填充段落间自然停顿，确保中文配音与原视频口型和画面完全对齐。
- **字幕无缝压制**：自动生成标准 `.srt` 字幕，支持硬字幕（画面内嵌烧录）与软字幕封装导出。

---

## 🚀 快速启动

### 1. 一键启动服务（推荐）

打开终端，进入项目根目录执行：

```bash
cd /Users/donghaichao/Desktop/vp
bash scripts/run.sh
```

- 脚本会自动检测 Python 虚拟环境与依赖；
- 启动后自动在默认浏览器中打开 **`http://127.0.0.1:8000`**；
- 前后端已完成一体化打包，由 FastAPI 统一托管提供服务。

### 2. 开发模式（前后端热重载）

若需对前端界面或后端接口进行二次开发，可运行：

```bash
bash scripts/run.sh --dev
```

- 后端运行在 `http://127.0.0.1:8000`（代码保存自动热重启）；
- 前端运行在 `http://127.0.0.1:5173`（支持 Vite HMR 极速热更新，并内置 API 反向代理）。

---

## 📖 使用步骤指南

1. **配置 API Key 与连通性检测**：
   - 打开页面右上角 **「API 密钥与模型设置」** 按钮；
   - 输入您的 **DeepSeek API Key**；
   - 确认或修改模型名称（默认 `deepseek4.1flash`）与 Base URL（默认 `https://api.deepseek.com/v1`，支持硅基流动或第三方中转）；
   - 点击 **「检测连通性」** 按钮，验证网络与 Key 权限是否畅通并查看延迟；
   - 点击保存（浏览器会记住您的配置）。
2. **输入视频链接**：
   - 粘贴哔哩哔哩链接（如 `https://www.bilibili.com/video/BV1...`）或 YouTube 链接；
   - 系统会自动识别平台图标。
3. **选择配音与流程模式**：
   - **配音音色**：默认推荐 `云希 (活力男声)` 或 `晓晓 (温柔女声)`；
   - **校对开关**：默认开启「翻译后暂停并在前端在线校对字幕」（推荐）；
   - **字幕选项**：可选择是否烧录硬字幕。
4. **启动流水线**：
   - 点击 **「开始全流程处理」**；
   - 界面将实时显示各阶段进度条与执行日志终端。
5. **在线校对（若开启）**：
   - 当任务到达「人工校对」阶段时，自动弹出校对窗口；
   - 您可以微调翻译文案，点击「试听发音」实时听取单句配音效果；
   - 点击「确认字幕并继续生成视频」即可继续。
6. **预览与下载**：
   - 任务完成后，直接在内置视频播放器中播放中文配音视频；
   - 点击「下载中文 MP4 视频」与「下载 SRT 字幕」。

---

## 📂 项目目录结构

```
vp/
├── backend/
│   ├── app.py                 # FastAPI 入口路由、SSE 事件流、静态资源托管
│   ├── config.py              # 路径配置、FFmpeg 探测、模型与音色定义
│   ├── requirements.txt       # Python 核心依赖
│   ├── test_pipeline.py       # 端到端核心流水线自动化测试用例
│   ├── core/
│   │   └── task_manager.py    # 异步任务状态机、进度广播与事件管理
│   ├── services/
│   │   ├── downloader.py      # yt-dlp 视频/音频下载服务
│   │   ├── asr.py             # mlx-whisper 硬件加速语音识别
│   │   ├── translator.py      # DeepSeek 智能翻译与配音节奏控制
│   │   ├── tts.py             # Edge-TTS / CosyVoice 语音合成
│   │   ├── aligner.py         # Forced Alignment 时间对齐与 atempo 变速
│   │   └── composer.py        # FFmpeg 音画混流与字幕烧录
│   └── storage/               # 运行时临时数据与产物目录
│       ├── tasks/             # 任务执行切片缓存
│       └── outputs/           # 最终生成的 MP4 视频与 SRT 文件
├── frontend/
│   ├── package.json           # 前端依赖配置
│   ├── vite.config.ts         # Vite 构建与开发代理配置
│   ├── tailwind.config.js     # Tailwind CSS 样式配置
│   ├── src/
│   │   ├── App.tsx            # 主应用与状态流转
│   │   ├── api/client.ts      # REST API 与 SSE 客户端通信层
│   │   └── components/
│   │       ├── Header.tsx     # 顶部导航与设置入口
│   │       ├── SettingsModal.tsx # API Key 配置模态框 (localStorage)
│   │       ├── UrlForm.tsx    # 视频链接输入与参数面板
│   │       ├── Progress.tsx   # 7阶段可视化进度条与日志控制台
│   │       ├── SubtitleEditor.tsx # 在线字幕校对与单句配音试听编辑器
│   │       └── VideoPlayer.tsx# 成品播放器与下载面板
│   └── dist/                  # 前端静态编译产物（已打包供后端托管）
├── scripts/
│   ├── run.sh                 # 一键启动脚本（支持生产/开发双模式）
│   └── setup_env.sh           # 环境检测与依赖安装脚本
└── README.md                  # 项目使用与架构说明
```

---

## 🛠️ API 规范与端点说明

| 路径 | 方法 | 说明 |
| :--- | :--- | :--- |
| `GET /api/health` | GET | 服务健康检查 |
| `GET /api/config/options` | GET | 获取支持的 ASR 模型与 TTS 音色列表 |
| `POST /api/tasks/create` | POST | 提交新视频链接并创建后台处理任务 |
| `GET /api/tasks/{task_id}/status` | GET | 获取任务当前执行状态、进度与日志 |
| `GET /api/tasks/{task_id}/events` | GET | SSE 实时事件流，推送当前阶段与日志条目 |
| `GET /api/tasks/{task_id}/subtitles` | GET | 获取待校对的字幕分段与翻译文本 |
| `POST /api/tasks/{task_id}/subtitles/confirm` | POST | 提交校对修改后的字幕，继续执行后续合成 |
| `POST /api/tts/preview` | POST | 生成单句配音音频二进制切片以供前端试听 |
| `GET /outputs/{filename}` | GET | 获取已生成的最终 MP4 视频或 SRT 字幕 |

---

## ⚙️ 常见问题 (FAQ)

1. **是否需要网络代理？**
   - 若下载 YouTube 视频或调用 Google Gemini API，需要能够访问外网的网络环境。系统已原生支持 `HTTP_PROXY` 与 `HTTPS_PROXY` 环境变量，例如在启动前设置：
     ```bash
     export HTTPS_PROXY=http://127.0.0.1:7890
     bash scripts/run.sh
     ```
2. **Bilibili 高清画质说明**：
   - 默认 yt-dlp 支持免登录下载 720p/1080p 视频；如需下载 1080p 60fps 或大会员专享画质，可在 `yt-dlp` 设置中配置 Bilibili Cookie。
3. **MLX 模型首次下载缓存**：
   - 首次运行 ASR 任务时，`mlx-whisper` 会自动从 HuggingFace 缓存 `whisper-large-v3-turbo` 权重，后续运行无需重复下载，直接使用本地缓存极速推理。
