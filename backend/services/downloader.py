import os
import subprocess
import json
import logging
from typing import Dict, Any, Callable, Optional
from pathlib import Path
import yt_dlp
from backend.config import FFMPEG_PATH, FFPROBE_PATH

logger = logging.getLogger(__name__)

class VideoDownloader:
    """Downloader supporting Bilibili & YouTube via yt-dlp, with audio/video extraction."""

    def __init__(self, task_dir: Path, progress_callback: Optional[Callable[[float, str], None]] = None):
        self.task_dir = task_dir
        self.progress_callback = progress_callback

    def _progress_hook(self, d: Dict[str, Any]):
        if self.progress_callback and d.get('status') == 'downloading':
            total = d.get('total_bytes') or d.get('total_bytes_estimate') or 0
            downloaded = d.get('downloaded_bytes') or 0
            percent = (downloaded / total * 100) if total > 0 else 0
            speed = d.get('speed') or 0
            speed_mb = (speed / 1024 / 1024) if speed else 0
            self.progress_callback(min(percent, 99.0), f"正在下载视频... {percent:.1f}% ({speed_mb:.1f} MB/s)")
        elif self.progress_callback and d.get('status') == 'finished':
            self.progress_callback(99.0, "下载完成，正在处理音视频轨道...")

    def download(self, url: str) -> Dict[str, Any]:
        """
        Download video and extract:
        - raw_video_path (mp4/mkv)
        - audio_wav_path (16kHz 16-bit mono wav for ASR)
        - metadata (title, duration, uploader, thumbnail)
        """
        if self.progress_callback:
            self.progress_callback(5.0, "解析视频链接与元数据...")

        out_template = str(self.task_dir / "raw_video.%(ext)s")

        ydl_opts = {
            'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
            'outtmpl': out_template,
            'progress_hooks': [self._progress_hook],
            'ffmpeg_location': FFMPEG_PATH,
            'quiet': True,
            'no_warnings': True,
            # Bilibili & YouTube compatibility headers
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Referer': 'https://www.bilibili.com/',
            }
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            video_title = info.get('title', 'video')
            duration = info.get('duration', 0)
            thumbnail = info.get('thumbnail', '')
            uploader = info.get('uploader', '') or info.get('channel', '')

        # Locate downloaded video file
        downloaded_files = list(self.task_dir.glob("raw_video.*"))
        if not downloaded_files:
            raise FileNotFoundError("未能找到下载的视频文件")
        
        raw_video_path = downloaded_files[0]
        audio_wav_path = self.task_dir / "audio_16k.wav"

        if self.progress_callback:
            self.progress_callback(95.0, "提取 16kHz 高保真语音轨...")

        # Extract 16kHz mono 16-bit PCM WAV using FFmpeg
        cmd = [
            FFMPEG_PATH, "-y",
            "-i", str(raw_video_path),
            "-vn",
            "-acodec", "pcm_s16le",
            "-ar", "16000",
            "-ac", "1",
            str(audio_wav_path)
        ]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if res.returncode != 0:
            logger.error(f"FFmpeg audio extraction error: {res.stderr.decode('utf-8', errors='ignore')}")
            raise RuntimeError(f"提取音频失败: {res.stderr.decode('utf-8', errors='ignore')}")

        if self.progress_callback:
            self.progress_callback(100.0, "视频与音频提取完成")

        return {
            "title": video_title,
            "duration": duration,
            "uploader": uploader,
            "thumbnail": thumbnail,
            "video_path": str(raw_video_path),
            "audio_wav_path": str(audio_wav_path)
        }
