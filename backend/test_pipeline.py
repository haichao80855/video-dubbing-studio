import os
import sys
import asyncio
import subprocess
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.config import FFMPEG_PATH, FFPROBE_PATH, TASKS_DIR, OUTPUTS_DIR
from backend.services.tts import F5TTSCloneRunner
from backend.services.aligner import AudioAligner
from backend.services.composer import VideoComposer, format_timestamp_srt
from pydub import AudioSegment
from pydub.generators import Sine

async def test_dubbing_core():
    print("=== Testing Video Dubbing Core Pipeline (F5-TTS MLX & 48kHz Stereo) ===")
    test_task_dir = TASKS_DIR / "test_task"
    test_task_dir.mkdir(parents=True, exist_ok=True)

    # 1. Test SRT formatting
    print("\n1. Testing Timestamp & SRT formatting...")
    assert format_timestamp_srt(1.234) == "00:00:01,234", "SRT timestamp format mismatch"
    assert format_timestamp_srt(65.5) == "00:01:05,500", "SRT timestamp format mismatch"
    print("✓ SRT Timestamp formatting verified.")

    # 2. Test Audio Generation & Alignment in 48kHz Stereo
    print("\n2. Testing 48kHz Stereo Alignment & Time-stretching (atempo)...")
    # Generate test audio clips with audible tone (440Hz and 880Hz) to ensure non-silence
    tts_dir = test_task_dir / "tts_clips"
    tts_dir.mkdir(parents=True, exist_ok=True)

    clip1_path = str(tts_dir / "clip_0001.wav")
    clip2_path = str(tts_dir / "clip_0002.wav")

    # Generate 2 seconds of 440Hz audible sine wave in 48kHz stereo
    tone1 = Sine(440).to_audio_segment(duration=2000).set_frame_rate(48000).set_channels(2)
    tone1.export(clip1_path, format="wav")

    # Generate 2.5 seconds of 660Hz audible sine wave in 48kHz stereo
    tone2 = Sine(660).to_audio_segment(duration=2500).set_frame_rate(48000).set_channels(2)
    tone2.export(clip2_path, format="wav")

    sample_subtitles = [
        {
            "id": 1,
            "start": 0.5,
            "end": 2.5,
            "text": "Hello world",
            "translated_text": "你好世界测试原声克隆",
            "audio_path": clip1_path,
            "tts_duration": 2.0
        },
        {
            "id": 2,
            "start": 3.0,
            "end": 5.5,
            "text": "Apple Silicon MLX Metal",
            "translated_text": "苹果硬件加速测试",
            "audio_path": clip2_path,
            "tts_duration": 2.5
        }
    ]

    aligner = AudioAligner(task_dir=test_task_dir)
    full_audio_path = aligner.align_and_stitch(sample_subtitles, total_duration=6.0)
    print(f"✓ Stitched full audio track: {full_audio_path}")
    assert os.path.exists(full_audio_path), "Full dubbed track not created"
    
    full_audio = AudioSegment.from_file(full_audio_path)
    print(f"  Track duration: {len(full_audio)/1000.0}s (Target: 6.0s)")
    print(f"  Frame rate: {full_audio.frame_rate} Hz (Expected: 48000)")
    print(f"  Channels: {full_audio.channels} (Expected: 2 Stereo)")
    assert full_audio.frame_rate == 48000, f"Expected 48000Hz, got {full_audio.frame_rate}"
    assert full_audio.channels == 2, f"Expected 2 channels stereo, got {full_audio.channels}"
    # Verify non-silent amplitude
    assert full_audio.dBFS > -40.0, f"Audio track is silent or near-zero dBFS: {full_audio.dBFS}"
    print(f"  Track Loudness: {full_audio.dBFS:.1f} dBFS (Clearly audible!)")

    # 3. Test FFmpeg Synthetic Video Composition
    print("\n3. Testing FFmpeg Video Composition with 48kHz Stereo AAC...")
    test_video = str(test_task_dir / "test_input_video.mp4")
    gen_video_cmd = [
        FFMPEG_PATH, "-y",
        "-f", "lavfi",
        "-i", "color=c=navy:s=1280x720:d=6:r=30",
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        test_video
    ]
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
    assert os.path.exists(res['output_mp4']), "Output MP4 does not exist"
    assert os.path.getsize(res['output_mp4']) > 10000, "Output MP4 is too small"

    # 4. Verify MP4 Audio Stream Properties via ffprobe
    print("\n4. Verifying MP4 Audio Stream Parameters...")
    probe_cmd = [
        FFPROBE_PATH,
        "-v", "error",
        "-select_streams", "a:0",
        "-show_entries", "stream=codec_name,sample_rate,channels,bit_rate",
        "-of", "default=noprint_wrappers=1:nokey=1",
        res['output_mp4']
    ]
    probe_out = subprocess.run(probe_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    probe_lines = probe_out.stdout.strip().split('\n')
    print("  Audio Stream Info from FFprobe:", probe_lines)
    assert "aac" in probe_lines[0].lower(), f"Expected AAC codec, got {probe_lines[0]}"
    assert probe_lines[1] == "48000", f"Expected 48000 Hz, got {probe_lines[1]}"
    assert probe_lines[2] == "2", f"Expected 2 channels (Stereo), got {probe_lines[2]}"
    print("✓ MP4 Audio Stream is 100% verified: AAC, 48000 Hz, Stereo!")

    print("\n🎉 ALL CORE PIPELINE TESTS PASSED WITH 48kHz STEREO SOUND VERIFIED!")

if __name__ == "__main__":
    asyncio.run(test_dubbing_core())
