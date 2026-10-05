# 🎬 Video Dubbing Studio (视频智能翻译与原声克隆配音系统)

> 输入 **Bilibili / YouTube** 视频链接，通过 **MLX ASR → 保留源时间轴的 DeepSeek 意译 → F5-TTS MLX 显式时长声音克隆 → 逐句绝对时间定位 → FFmpeg (48kHz立体声)**，全自动或人机协同输出**原声克隆中文 MP4 视频**。

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
         ▼ (F5-TTS MLX 零样本声音克隆)
[复刻原作者声线与音色，合成 48kHz 高保真中文配音]
         │
         ▼ (原视频逐句时间轴 & atempo 轻微变速)
[独立定位每句 + 保留原停顿 + 全轨 48kHz 立体声时间对齐]
         │
         ▼ (FFmpeg libass 压制 + 48kHz AAC 混流)
[输出纯配音中文 MP4 视频与 SRT 字幕]
```

- **🎙️ 专注原人物零样本声音克隆 (Zero-Shot Voice Cloning)**：专为 Apple Silicon Metal 硬件加速优化的 `F5-TTS MLX`，自动截取原视频中 3~6 秒最清晰发言作为音色种子，将翻译出的中文完全以**原视频作者的声线、共鸣与说话韵律**朗读出来，实现真正的「原作者本人说地道中文」！
- **🌊 语义长句合并与连贯语流 (SentenceMerger)**：自动将 Whisper 切碎的 2~3 秒半截子短句聚合成 **8~14 秒的完整语义长句**，片段数从 80+ 缩减至 20~28 个完整语段；从源头消灭「一句一停」的机械断崖降调，不仅翻译逻辑更连贯，配音处理速度也同步翻倍！
- **⏱️ 保留原视频逐句时间轴**：全文作为翻译上下文，译文保持源分段 ID 与起止时间。每句音频独立放到原起点，保留停顿、演示和场景间隔，避免连续串接造成累积漂移。
- **🗣️ 独立朗读语速与显式生成时长**：默认约 **3.8 字/秒**，可在 **2.5~4.5 字/秒** 之间调节。试听和最终合成共用任务语速与时间窗口，不再按英文参考文本与中文文本的字节数比例估算语速。
- **极速流畅的 Web 界面**：React + Vite + Tailwind CSS，现代精致暗色风格，支持响应式设计与实时流水线进度监控。
- **前端直接输入 API 密钥 & 一键测试连通性**：在前端设置弹窗中直接输入 `DeepSeek API Key`、自定义 `API Base URL` 与模型名称（默认 `deepseek4.1flash`），内置「检测连通性」按钮即时显示响应延迟与状态诊断，密钥存储在用户浏览器本地（`localStorage`）。
- **Apple Silicon 硬件加速**：底层采用 Metal 优化的 `mlx-whisper` 与 `F5-TTS MLX`，在 M 系列 Mac 芯片上推理速度极快，自带精准词级时间戳。
- **配音级智能意译 (DeepSeek)**：每段根据时长与所选语速限制字数，校验翻译结果的 ID、缺失段落和长度，必要时要求模型修正一次。过长文案在校对时提示精简；音频仅允许至多约 **1.1 倍** 的轻微加速，不强行截断句尾。
- **人机协同在线校对 & 原声试听**：翻译完成后可暂停，支持在界面中试听截取的原人物音色样本（可一键切换更换其他发言片段作为音色种子），支持修改中文配音稿，并提供**单句克隆配音试听**功能。
- **广播级 48kHz 立体声音频管线**：全链路采用 48000Hz 立体声编码（`-c:a aac -b:a 192k -ar 48000 -ac 2`）并结合电平峰值归一化，彻底根治视频静音、单声道走空或声音微弱的问题。
- **字幕无缝压制与长句双行换行**：自动生成标准 `.srt` 字幕，长句自动在逗号处舒适拆分两行居中排版，支持硬字幕（画面内嵌烧录）与软字幕封装导出。

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
3. **选择流程模式**：
   - **朗读语速**：默认 3.8 字/秒；若觉得急促，可在创建任务前调低。生成模式的「飞速／平衡／高精」控制计算速度与采样方式，与朗读语速分开。
   - **配音引擎**：系统默认且唯一采用 **F5-TTS MLX (原人物零样本声音克隆)**；
   - **校对开关**：默认开启「翻译后暂停并在前端在线校对字幕与原声音色」（推荐）；
   - **字幕选项**：可选择是否压制硬字幕。
4. **启动流水线**：
   - 点击 **「开始原声克隆处理」**；
   - 界面将实时显示各阶段进度条与执行日志终端。
5. **在线校对与原声试听（若开启）**：
   - 当任务到达「人工校对」阶段时，自动弹出校对窗口；
   - 顶部可直接点击播放听取系统自动提取的原声切片，亦可下拉切换选用其他分句作为音色参考；
   - 每一句中文译文右侧均有「试听克隆原声」按钮，确认满意后点击「确认字幕并继续生成视频」。
6. **预览与下载**：
   - 任务完成后，直接在内置视频播放器中播放中文配音视频；
   - 点击「下载中文 MP4 视频」与「下载 SRT 字幕」。

---

## 📂 项目目录结构

```
vp/
├── backend/
│   ├── app.py                 # FastAPI 入口路由、SSE 事件流、静态资源托管
│   ├── config.py              # 路径配置、FFmpeg 探测、ASR 模型定义
│   ├── requirements.txt       # Python 核心依赖 (去除非必要外部引擎)
│   ├── test_pipeline.py       # 端到端核心流水线自动化测试用例 (48kHz立体声校验)
│   ├── core/
│   │   └── task_manager.py    # 异步任务状态机、进度广播与原声种子管理
│   ├── services/
│   │   ├── downloader.py      # yt-dlp 视频/音频下载服务
│   │   ├── asr.py             # mlx-whisper 硬件加速语音识别
│   │   ├── sentence_merger.py # 语义长句重整器 (碎句聚合成 8~14s 连贯长句)
│   │   ├── continuous_flow_dubber.py # 全篇连贯原声解说流引擎 (通篇意译与200ms微换气)
│   │   ├── translator.py      # DeepSeek 智能翻译与长句气口控制
│   │   ├── tts.py             # F5-TTS MLX 原声克隆批量调度器
│   │   ├── f5_tts_mlx.py      # F5-TTS MLX 模型加载、Euler加速与零样本推理服务
│   │   ├── speaker_extractor.py # 原人物音频切片智能提取与自选服务
│   │   ├── aligner.py         # 逐句绝对时间定位与轻微变速
│   │   ├── pacing.py          # 朗读语速、时间窗口与 F5 总生成帧数
│   │   └── composer.py        # FFmpeg 音画混流 (48kHz AAC, 字幕双行换行)
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
│   │       ├── SettingsModal.tsx # API Key 配置模态框 (纯净 DeepSeek 配置)
│   │       ├── UrlForm.tsx    # 视频链接输入与原声克隆专区
│   │       ├── Progress.tsx   # 7阶段可视化进度条与日志控制台
│   │       ├── SubtitleEditor.tsx # 在线字幕校对与音色种子试听/切换编辑器
│   │       └── VideoPlayer.tsx# 48kHz立体声成品播放器与下载面板
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
| `GET /api/config/options` | GET | 获取支持的 ASR 模型与 TTS 引擎信息 |
| `POST /api/config/test-llm` | POST | 测试 DeepSeek API 连通性与响应延迟 |
| `POST /api/tasks/create` | POST | 提交新视频链接并创建后台处理任务 |
| `GET /api/tasks/{task_id}/status` | GET | 获取任务当前执行状态、进度与日志 |
| `GET /api/tasks/{task_id}/events` | GET | SSE 实时事件流，推送当前阶段与日志条目 |
| `GET /api/tasks/{task_id}/speaker-ref` | GET | 获取当前任务提取的原声参考音频元数据 |
| `GET /api/tasks/{task_id}/speaker-ref/audio` | GET | 流式返回当前原声参考切片 WAV 音频用于播放 |
| `POST /api/tasks/{task_id}/speaker-ref/update` | POST | 切换选用其他分句作为原声克隆样本 |
| `GET /api/tasks/{task_id}/subtitles` | GET | 获取待校对的字幕分段与翻译文本 |
| `POST /api/tasks/{task_id}/subtitles/confirm` | POST | 提交校对修改后的字幕，继续执行克隆合成 |
| `POST /api/tts/preview` | POST | 使用当前原声种子生成单句克隆配音供前端试听 |
| `GET /outputs/{filename}` | GET | 获取已生成的最终 MP4 视频或 SRT 字幕 |

---

## ⚙️ 常见问题 (FAQ)

1. **是否需要网络代理？**
   - 若下载 YouTube 视频或访问外部服务，建议在终端设置网络代理：
     ```bash
     export HTTPS_PROXY=http://127.0.0.1:7890
     bash scripts/run.sh
     ```
2. **为什么生成的视频有声音且音质极高？**
   - 本系统采用全链路 48000Hz 立体声编码（`-c:a aac -b:a 192k -ar 48000 -ac 2`）并对 F5-TTS 的输出音频进行了电平峰值归一化，完全兼容 Safari、Chrome 及各类播放器，绝不走空或静音。
3. **MLX 模型首次下载缓存**：
   - 首次运行 ASR 与 F5-TTS 任务时，系统会自动从 HuggingFace 缓存模型权重，之后永久本地秒级加载。
4. **确认字幕提示不在校对阶段 / 窗口重复弹出**：
   - 确认后任务立即进入配音阶段，校对窗口会关闭；相同文案的重复确认返回成功。已确认后再改文案会被拒绝，避免覆盖正在生成的配音。后续合成错误显示在任务进度中。
5. **FFmpeg 报 `No such filter: 'subtitles'`**：
   - 该 FFmpeg 没有编译 `libass`。系统会检测可用版本；若均缺少滤镜，自动输出带可切换中文字幕的 MP4、SRT 和用于浏览器预览的 WebVTT，并在日志和结果页提示。配音与视频仍按原时间轴合成。
   - 如需画面内嵌硬字幕，在 Mac 终端运行 `brew install ffmpeg-full`，再重启服务。无需强制链接：系统会检测 Apple Silicon 的 `/opt/homebrew/opt/ffmpeg-full/bin/ffmpeg` 与 Intel 的 `/usr/local/opt/ffmpeg-full/bin/ffmpeg`。
   - 自定义安装位置可在启动前设置 `VDS_FFMPEG_PATH` 与 `VDS_FFPROBE_PATH`；修改后重启服务。

## 验证时间轴修复

安装项目依赖后，在项目根目录运行：

```bash
python -m unittest discover -s backend/tests -v
python backend/test_pipeline.py
cd frontend
npm run build
```

回归测试使用合成 WAV 和模拟的模型/API 响应，检查 5 分钟音轨无累积漂移、原停顿保留、超长文案与音频拒绝截尾、试听参数一致、重复确认与校对状态。字幕兼容测试实际模拟缺少字幕滤镜的 FFmpeg 并验证软字幕轨道、中文文本、时间戳和 48kHz 立体声；独立合成脚本检查硬字幕合成与 MP4 音频属性。

这些 CPU 测试不需要下载模型。Linux 上可只安装 `numpy scipy soundfile pydub httpx fastapi yt-dlp` 来运行；真实克隆音质仍需要在 Apple Silicon Mac 上试听。更新代码并重启后需要重新生成视频，已有输出不会自动改变。

浏览器校对流程回归（先构建前端）：

```bash
python -m pip install playwright
python -m playwright install chromium
python frontend/tests/test_review_flow.py
```

测试会自动启动本地静态服务并模拟 API 与状态事件，检查重复点击仅提交一次、等待中的文案不被轮询覆盖、延迟请求不重新打开已确认或失败的校对窗口，以及软字幕预览轨道。
