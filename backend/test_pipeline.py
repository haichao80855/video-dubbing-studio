import os
import sys
import asyncio
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.config import FFMPEG_PATH, TASKS_DIR, OUTPUTS_DIR
from backend.services.tts import TTSRunner
from backend.services.aligner import AudioAligner
from backend.services.composer import VideoComposer, format_timestamp_srt
from pydub import AudioSegment

async def test_dubbing_core():
    print("=== Testing Video Dubbing Core Pipeline ===")
    test_task_dir = TASKS_DIR / "test_task"
    test_task_dir.mkdir(parents=True, exist_ok=True)

    # 1. Test SRT formatting
    print("\n1. Testing Timestamp & SRT formatting...")
    assert format_timestamp_srt(1.234) == "00:00:01,234", "SRT timestamp format mismatch"
    assert format_timestamp_srt(65.5) == "00:01:05,500", "SRT timestamp format mismatch"
    print("✓ SRT Timestamp formatting verified.")

    # 2. Test Edge-TTS Synthesis
    print("\n2. Testing Edge-TTS Chinese Audio Generation...")
    sample_subtitles = [
        {
            "id": 1,
            "start": 0.5,
            "end": 2.5,
            "text": "Hello world",
            "translated_text": "你好，世界，欢迎来到智能视频配音系统！"
        },
        {
            "id": 2,
            "start": 3.0,
            "end": 5.5,
            "text": "This is a test of Apple Silicon MLX.",
            "translated_text": "这是基于苹果芯片的硬件加速测试。"
        }
    ]

    tts_runner = TTSRunner(engine_type="edge_tts", voice_name="zh-CN-YunxiNeural")
    synthesized = await tts_runner.generate_all(sample_subtitles, test_task_dir)
    print(f"✓ Generated {len(synthesized)} TTS audio clips:")
    for item in synthesized:
        print(f"  Clip #{item['id']}: duration={item['tts_duration']}s, path={item['audio_path']}")
        assert os.path.exists(item['audio_path']), f"Missing file {item['audio_path']}"
        assert item['tts_duration'] > 0

    # 3. Test Alignment & Time-stretching & Stitching
    print("\n3. Testing Forced Alignment & Time-stretching (atempo)...")
    aligner = AudioAligner(task_dir=test_task_dir)
    full_audio_path = aligner.align_and_stitch(synthesized, total_duration=6.0)
    print(f"✓ Stitched full audio track: {full_audio_path}")
    assert os.path.exists(full_audio_path), "Full dubbed track not created"
    full_audio = AudioSegment.from_file(full_audio_path)
    print(f"  Total audio track duration: {len(full_audio)/1000.0}s (Target: 6.0s)")

    # 4. Test FFmpeg Synthetic Video Composition
    print("\n4. Testing FFmpeg Video Composition...")
    # Generate a dummy 6s test video with color test pattern
    test_video = str(test_task_dir / "test_input_video.mp4")
    gen_video_cmd = [
        FFMPEG_PATH, "-y",
        "-f", "lavfi",
        "-i", "color=c=navy:s=1280x720:d=6:r=30",
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        test_video
    ]
    import subprocess
    subprocess.run(gen_video_cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print("  Created 6-second synthetic test video.")

    composer = VideoComposer(task_dir=test_task_dir, task_id="test_task")
    res = composer.compose_video(
        video_path=test_video,
        audio_path=full_audio_path,
        subtitles=sample_subtitles,
        hard_sub=True
    )
    print(f"✓ Video Composition Completed successfully!")
    print(f"  Output MP4: {res['output_mp4']}")
    print(f"  Output SRT: {res['output_srt']}")
    assert os.path.exists(res['output_mp4']), "Output MP4 does not exist"
    assert os.path.exists(res['output_srt']), "Output SRT does not exist"
    print(f"  Output MP4 size: {os.path.getsize(res['output_mp4'])} bytes")

    print("\n🎉 ALL CORE PIPELINE TESTS PASSED!")

if __name__ == "__main__":
    asyncio.run(test_dubbing_core())
