"""Capability detection and real soft-subtitle muxing without a libass filter."""
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pydub.generators import Sine

from backend import config
from backend.services.composer import VideoComposer


class FFmpegCapabilityTests(unittest.TestCase):
    def setUp(self):
        config.ffmpeg_has_filter.cache_clear()
        self.addCleanup(config.ffmpeg_has_filter.cache_clear)

    def test_filter_detection_uses_actual_filter_name(self):
        for output, expected in [(" ... subtitles V->V Render text\n", True),
                                 (" ... drawtext V->V subtitles are unavailable\n", False)]:
            with self.subTest(output=output), patch.object(config.subprocess, "run", return_value=
                    subprocess.CompletedProcess([], 0, output, "")) as run:
                config.ffmpeg_has_filter.cache_clear()
                self.assertEqual(config.ffmpeg_has_filter("ffmpeg", "subtitles"), expected)
                self.assertEqual(run.call_args.kwargs["timeout"], 5)

    def test_selects_installed_build_with_subtitles(self):
        with patch.object(config, "binary_candidates", return_value=["lean", "full"]), \
             patch.object(config, "ffmpeg_has_filter", side_effect=lambda binary, name: binary == "full"):
            self.assertEqual(config.select_composition_ffmpeg("lean", True), ("full", True))

    def test_missing_filter_selects_soft_subtitles(self):
        with patch.object(config, "binary_candidates", return_value=["lean"]), \
             patch.object(config, "ffmpeg_has_filter", return_value=False):
            self.assertEqual(config.select_composition_ffmpeg("lean", True), ("lean", False))

    def test_explicit_soft_mode_does_not_require_libass(self):
        with patch.object(config, "ffmpeg_has_filter") as check:
            self.assertEqual(config.select_composition_ffmpeg("lean", False), ("lean", False))
            check.assert_not_called()

    def test_capability_check_has_bounded_timeout(self):
        with patch.object(config.subprocess, "run", side_effect=subprocess.TimeoutExpired("ffmpeg", 5)):
            self.assertFalse(config.ffmpeg_has_filter("unresponsive", "subtitles"))

    @unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "requires FFmpeg")
    def test_real_fallback_preserves_subtitle_track_and_normalizes_timestamps(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            video = root / "video.mp4"
            audio = root / "voice.wav"
            Sine(440, sample_rate=48000).to_audio_segment(duration=2000).set_channels(2).export(audio, format="wav")
            subprocess.run([shutil.which("ffmpeg"), "-y", "-f", "lavfi", "-i",
                            "color=c=navy:s=320x180:d=2:r=25", "-vf", "setpts=PTS+3/TB",
                            "-c:v", "libx264", "-pix_fmt", "yuv420p", str(video)],
                           check=True, capture_output=True, timeout=20)
            # This executable really advertises no subtitles filter; other invocations
            # use the installed FFmpeg so the fallback is tested with actual media.
            lean = root / "ffmpeg-lean"
            lean.write_text("#!/usr/bin/env python3\nimport os,sys\n"
                            "if '-filters' in sys.argv:\n"
                            "    print(' ... setpts V->V Set timestamps')\n"
                            "else:\n"
                            f"    os.execv({shutil.which('ffmpeg')!r}, [{shutil.which('ffmpeg')!r}, *sys.argv[1:]])\n")
            lean.chmod(0o755)
            subtitles = [{"id": 1, "start": 0.2, "end": 1.5, "translated_text": "保留中文字幕"}]
            messages = []
            with patch("backend.services.composer.FFMPEG_PATH", str(lean)), \
                 patch("backend.services.composer.OUTPUTS_DIR", root), \
                 patch.object(config, "binary_candidates", return_value=[str(lean)]):
                result = VideoComposer(root, "fallback").compose_video(
                    str(video), str(audio), subtitles, hard_sub=True,
                    progress_callback=lambda p, text: messages.append(text))
            self.assertEqual(result["subtitle_mode"], "soft")
            self.assertTrue(result["warnings"])
            self.assertTrue(any("软字幕" in message for message in messages))
            vtt = (root / result["vtt_filename"]).read_text()
            self.assertIn("WEBVTT", vtt)
            self.assertIn("00:00:00.200 --> 00:00:01.500", vtt)
            self.assertIn("保留中文字幕", vtt)
            probe = subprocess.run([shutil.which("ffprobe"), "-v", "error", "-show_streams",
                                    "-show_format", "-of", "json", result["output_mp4"]],
                                   check=True, capture_output=True, text=True, timeout=10)
            media = json.loads(probe.stdout)
            streams = {s["codec_type"]: s for s in media["streams"]}
            self.assertEqual(streams["subtitle"]["codec_name"], "mov_text")
            self.assertEqual(streams["subtitle"]["tags"]["language"], "chi")
            self.assertEqual(streams["subtitle"]["disposition"]["default"], 1)
            self.assertEqual(streams["audio"]["sample_rate"], "48000")
            self.assertEqual(streams["audio"]["channels"], 2)
            for kind in ("audio", "video"):
                self.assertAlmostEqual(float(streams[kind]["start_time"]), 0, places=2)
            self.assertAlmostEqual(float(media["format"]["duration"]), 2, places=1)
            exported = subprocess.run([shutil.which("ffmpeg"), "-v", "error", "-i", result["output_mp4"],
                                       "-map", "0:s:0", "-f", "srt", "-"],
                                      check=True, capture_output=True, text=True, timeout=10)
            self.assertIn("保留中文字幕", exported.stdout)
            self.assertIn("00:00:00,200 --> 00:00:01,500", exported.stdout)


if __name__ == "__main__":
    unittest.main()
