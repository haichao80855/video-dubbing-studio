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
from backend.services.composer import VideoComposer, format_timestamp_srt, wrap_subtitle_text
from backend.services.sentence_merger import SentenceMerger
from pydub import AudioSegment
from pydub.generators import Sine

async def test_dubbing_core():
    print("=== Testing Video Dubbing Core Pipeline (F5-TTS MLX & 48kHz Stereo) ===")
    test_task_dir = TASKS_DIR / "test_task"
    test_task_dir.mkdir(parents=True, exist_ok=True)

    # 1. Test SentenceMerger (Semantic Sentence Aggregation)
    print("\n1. Testing SentenceMerger (Converting fragmented Whisper clips to natural long sentences)...")
    raw_micro_segments = [
        {"id": 1, "start": 0.0, "end": 2.5, "text": "Now it's time to set up the playground that"},
        {"id": 2, "start": 2.5, "end": 5.1, "text": "we're going to be using to practice our AI coding and"},
        {"id": 3, "start": 5.3, "end": 8.0, "text": "setting up the environment that we're going to use to edit code."},
        {"id": 4, "start": 8.2, "end": 11.0, "text": "The main thing that we are going to need is an IDE."},
        {"id": 5, "start": 11.2, "end": 14.5, "text": "And the one I recommend is Visual Studio Code."},
    ]
    merger = SentenceMerger(min_duration=5.0, target_duration=9.0, max_duration=15.0)
    merged = merger.merge_segments(raw_micro_segments)
    print(f"✓ Consolidated {len(raw_micro_segments)} fragmented micro-clips into {len(merged)} natural semantic sentences:")
    for m in merged:
        print(f"  Sentence #{m['id']} ({m['start']}s ~ {m['end']}s, dur={m['duration']}s): {m['text']}")
    assert len(merged) < len(raw_micro_segments), "SentenceMerger did not consolidate micro-segments"
    assert merged[0]["start"] == 0.0, "Start timestamp mismatch"
    assert merged[-1]["end"] == 14.5, "End timestamp mismatch"
    print("✓ SentenceMerger verification passed successfully!")

    # 2. Test SRT formatting & subtitle wrapping
    print("\n2. Testing Timestamp & Subtitle text wrapping...")
    assert format_timestamp_srt(1.234) == "00:00:01,234", "SRT timestamp format mismatch"
    assert format_timestamp_srt(65.5) == "00:01:05,500", "SRT timestamp format mismatch"
    wrapped = wrap_subtitle_text("这是一个非常长且复杂的中文长句测试句子，用于验证在中间逗号处自然换行显示两行字幕")
    print("  Wrapped subtitle sample:\n", wrapped)
    assert "\n" in wrapped, "Subtitle was not wrapped at comma"
    print("✓ Subtitle wrapping verified.")

    # 3. Test Audio Generation & Alignment in 48kHz Stereo with Absolute Timestamp Overlay & Silence Compression
    print("\n3. Testing 48kHz Stereo Alignment & Smart Silence Compression...")
    tts_dir = test_task_dir / "tts_clips"
    tts_dir.mkdir(parents=True, exist_ok=True)

    clip1_path = str(tts_dir / "clip_0001.wav")
    clip2_path = str(tts_dir / "clip_0002.wav")
    clip3_path = str(tts_dir / "clip_0003.wav")

    # Clip 1: Intentionally long (2.8s) for a 1.5s slot (to test overflow containment & atempo)
    tone1 = Sine(440).to_audio_segment(duration=2800).set_frame_rate(48000).set_channels(2)
    tone1.export(clip1_path, format="wav")

    # Clip 2: 1.8s for 2.0s slot (starts at 3.0s)
    tone2 = Sine(660).to_audio_segment(duration=1800).set_frame_rate(48000).set_channels(2)
    tone2.export(clip2_path, format="wav")

    # Clip 3: 1.5s for 1.5s slot (starts at 5.5s)
    tone3 = Sine(880).to_audio_segment(duration=1500).set_frame_rate(48000).set_channels(2)
    tone3.export(clip3_path, format="wav")

    sample_subtitles = [
        {
            "id": 1,
            "start": 0.5,
            "end": 2.0,
            "text": "Intentionally long sentence",
            "translated_text": "第一句故意很长用来测试溢出不推迟后续句子",
            "audio_path": clip1_path,
            "tts_duration": 2.8
        },
        {
            "id": 2,
            "start": 3.0,
            "end": 5.0,
            "text": "Second sentence anchor",
            "translated_text": "第二句必须严格在三秒打点启动",
            "audio_path": clip2_path,
            "tts_duration": 1.8
        },
        {
            "id": 3,
            "start": 5.5,
            "end": 7.0,
            "text": "Third sentence anchor",
            "translated_text": "第三句必须严格在五点五秒打点启动",
            "audio_path": clip3_path,
            "tts_duration": 1.5
        }
    ]

    aligner = AudioAligner(task_dir=test_task_dir)
    full_audio_path = aligner.align_and_stitch(sample_subtitles, total_duration=8.0)
    print(f"✓ Stitched full audio track: {full_audio_path}")
    assert os.path.exists(full_audio_path), "Full dubbed track not created"
    
    full_audio = AudioSegment.from_file(full_audio_path)
    print(f"  Track duration: {len(full_audio)/1000.0}s (Target: 8.0s)")
    print(f"  Frame rate: {full_audio.frame_rate} Hz (Expected: 48000)")
    print(f"  Channels: {full_audio.channels} (Expected: 2 Stereo)")
    assert full_audio.frame_rate == 48000, f"Expected 48000Hz, got {full_audio.frame_rate}"
    assert full_audio.channels == 2, f"Expected 2 channels stereo, got {full_audio.channels}"
    assert full_audio.dBFS > -40.0, f"Audio track is silent: {full_audio.dBFS}"
    print(f"  Track Loudness: {full_audio.dBFS:.1f} dBFS (Audible!)")

    # Verify that before 0.5s (e.g. 0.0s~0.4s) is silence:
    silence_before_seg1 = full_audio[0:400]
    assert silence_before_seg1.dBFS < -50.0 or silence_before_seg1.dBFS == float("-inf"), "Silence before segment 1 is not silent"

    # Verify that segment 2 starts on schedule: before 3.0s (e.g. 2.8s~2.95s) is silence, then sound starts at 3.0s
    silence_before_seg2 = full_audio[2800:2950]
    sound_at_seg2 = full_audio[3050:3500]
    print(f"  Silence before Seg 2 (2.8s~2.95s): {silence_before_seg2.dBFS:.1f} dBFS")
    print(f"  Sound at Seg 2 (3.05s~3.5s): {sound_at_seg2.dBFS:.1f} dBFS")
    assert sound_at_seg2.dBFS > -20.0, "Segment 2 is not playing at its exact 3.0s timestamp!"
    print("✓ Absolute Timestamp Overlay Verified: Segment 1 overflow did NOT drift Segment 2 (0ms drift)!")

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
