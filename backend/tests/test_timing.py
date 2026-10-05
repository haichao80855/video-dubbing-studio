"""CPU regression tests; synthetic WAVs replace MLX inference and network calls."""

import asyncio
import importlib
import json
import math
import subprocess
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
from pydub import AudioSegment
from pydub.generators import Sine

from backend.services.aligner import AudioAligner
from backend.services.continuous_flow_dubber import ContinuousFlowDubber
from backend.services.f5_tts_mlx import F5TTSMLXService, F5TTSModelHolder
from backend.services.pacing import (
    duration_frames_for_speech, resolve_speech_duration, speech_character_count,
)
from backend.services.translator import DeepSeekTranslator


class SyntheticTTS:
    def __init__(self, milliseconds=None):
        self.milliseconds = milliseconds
        self.calls = []

    def synthesize(self, text, path, **kwargs):
        self.calls.append(kwargs)
        duration = resolve_speech_duration(
            text, kwargs.get("target_duration"), kwargs.get("speaking_rate", 3.8)
        )
        milliseconds = self.milliseconds if self.milliseconds is not None else round(duration * 1000)
        Sine(440, sample_rate=48000).to_audio_segment(duration=milliseconds).set_channels(2).export(path, format="wav")
        return milliseconds / 1000


def subtitle(segment_id, start, end, text="示例配音"):
    return {"id": segment_id, "start": start, "end": end,
            "original_text": "Original sentence.", "translated_text": text}


class TimingTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def test_short_clips_keep_source_starts_and_intermediate_silence(self):
        segments = [subtitle(1, 0, 4), subtitle(2, 5, 9), subtitle(3, 10, 14)]
        voice = SyntheticTTS(2000)
        audio, updated = ContinuousFlowDubber(self.root).synthesize_and_stitch_continuous(
            segments, voice, 0, 15
        )
        track = AudioSegment.from_wav(audio)
        self.assertEqual([(s["start"], s["end"]) for s in updated], [(0, 4), (5, 9), (10, 14)])
        self.assertEqual(len(track), 15000)
        self.assertEqual(track[2200:4900].rms, 0)
        self.assertGreater(track[5100:5300].rms, 0)
        self.assertEqual(track[7200:9900].rms, 0)
        self.assertGreater(track[10100:10300].rms, 0)
        self.assertEqual((track.frame_rate, track.channels), (48000, 2))
        self.assertEqual([call["target_duration"] for call in voice.calls], [4, 4, 4])

    def test_long_demo_pause_after_short_instruction_is_not_merged_away(self):
        from backend.services.sentence_merger import SentenceMerger
        source = [{"id": 1, "start": 0, "end": 2, "text": "Click this button."},
                  {"id": 2, "start": 12, "end": 16, "text": "Now continue to the next step."}]
        merged = SentenceMerger().merge_segments(source)
        self.assertEqual([(s["start"], s["end"]) for s in merged], [(0, 2), (12, 16)])

    def test_five_minute_timeline_has_no_cumulative_drift(self):
        segments = [subtitle(index + 1, 2 + index * 25, 4 + index * 25) for index in range(12)]
        audio, updated = ContinuousFlowDubber(self.root).synthesize_and_stitch_continuous(
            segments, SyntheticTTS(1000), 2, 300
        )
        track = AudioSegment.from_wav(audio)
        self.assertEqual(len(track), 300000)
        self.assertEqual(track[:1900].rms, 0)
        for expected, actual in zip(segments, updated):
            self.assertEqual(actual["start"], expected["start"])
            start = round(expected["start"] * 1000)
            self.assertEqual(track[start - 100:start].rms, 0)
            self.assertGreater(track[start + 50:start + 150].rms, 0)

    def test_overflow_fails_instead_of_cutting_speech_or_moving_next_sentence(self):
        engine = ContinuousFlowDubber(self.root)
        with self.assertRaisesRegex(RuntimeError, "不能截断句尾"):
            engine.synthesize_and_stitch_continuous(
                [subtitle(1, 0, 3), subtitle(2, 3, 6)], SyntheticTTS(4000), 0, 6
            )
        self.assertFalse((self.root / "dubbed_full_track.wav").exists())

    def test_small_overflow_uses_mild_ffmpeg_tempo_fit(self):
        path = self.root / "clip.wav"
        Sine(440, sample_rate=48000).to_audio_segment(duration=2100).export(path, format="wav")
        clip, _ = AudioAligner(self.root).prepare_clip(str(path), 2, 1)
        self.assertLessEqual(len(clip), 2000)
        self.assertGreater(len(clip), 1850)
        self.assertGreater(clip[-50:].rms, 0)

    def test_ffmpeg_failure_is_not_replaced_with_unaligned_audio(self):
        result = subprocess.CompletedProcess([], 1, b"", b"filter failed")
        with patch("backend.services.aligner.subprocess.run", return_value=result):
            with self.assertRaisesRegex(RuntimeError, "变速失败"):
                AudioAligner(self.root)._stretch_audio("input", "output", 1.05)

    def test_invalid_timeline_rejected_before_tts(self):
        voice = SyntheticTTS()
        invalid = [
            [subtitle(1, 0, 4), subtitle(2, 3, 5)],
            [subtitle(1, -1, 2)], [subtitle(1, 0, 16)],
            [subtitle(1, 0, 2), subtitle(1, 3, 4)],
            [subtitle(1, 0, float("nan"))], [],
        ]
        for segments in invalid:
            with self.subTest(segments=segments), self.assertRaises(ValueError):
                ContinuousFlowDubber(self.root).synthesize_and_stitch_continuous(segments, voice, 0, 15)
        self.assertEqual(voice.calls, [])

    def test_empty_and_silent_generated_audio_rejected(self):
        path = self.root / "silent.wav"
        AudioSegment.silent(duration=1000, frame_rate=48000).export(path, format="wav")
        with self.assertRaisesRegex(RuntimeError, "无声"):
            AudioAligner(self.root).prepare_clip(str(path), 2, 1)


class PacingTests(unittest.TestCase):
    def test_natural_chinese_duration_does_not_depend_on_english_reference_bytes(self):
        self.assertAlmostEqual(resolve_speech_duration("中文" * 15), 30 / 3.8)
        self.assertGreater(resolve_speech_duration("中文" * 15), 7.8)
        self.assertEqual(speech_character_count("你好，世界！ 123"), 7)

    def test_short_text_is_not_stretched_to_fill_long_scene(self):
        self.assertAlmostEqual(resolve_speech_duration("中文" * 5, 15), 10 / 3.8)

    def test_long_text_requires_shortening_instead_of_rushed_speech(self):
        with self.assertRaisesRegex(ValueError, "精简"):
            resolve_speech_duration("中文" * 15, 4)

    def test_reference_samples_are_included_in_f5_duration(self):
        self.assertEqual(duration_frames_for_speech(5 * 24000, 8), math.ceil(13 * 24000 / 256))

    def test_model_duration_limit_is_checked_before_silent_clamping(self):
        with self.assertRaisesRegex(ValueError, "拆分"):
            duration_frames_for_speech(5 * 24000, 50)

    def test_invalid_pacing_parameters(self):
        for rate in [0, -1, float("nan"), float("inf")]:
            with self.subTest(rate=rate), self.assertRaises(ValueError):
                resolve_speech_duration("中文", speaking_rate=rate)
        for window in [0, -1, float("nan")]:
            with self.subTest(window=window), self.assertRaises(ValueError):
                resolve_speech_duration("中文", target_duration=window)

    def test_f5_service_passes_explicit_total_frames_and_preserves_duration_when_resampling(self):
        mx = types.ModuleType("mlx.core")
        mx.expand_dims = np.expand_dims
        mx.eval = lambda value: None
        generate = types.ModuleType("f5_tts_mlx.generate")
        generate.convert_char_to_pinyin = lambda text: text
        model = MagicMock()
        model.sample.side_effect = lambda audio, **kw: (np.full(kw["duration"] * 256, 0.1), None)
        reference = np.full(5 * 24000, 0.1)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            (path / "reference.wav").touch()
            service = F5TTSMLXService(ref_audio_path=str(path / "reference.wav"), ref_audio_text="English reference.")
            with patch.dict(sys.modules, {"mlx": types.ModuleType("mlx"), "mlx.core": mx,
                                          "f5_tts_mlx.generate": generate}), \
                 patch.object(F5TTSModelHolder, "get_model", return_value=model), \
                 patch.object(service, "_load_reference_audio", return_value=reference):
                duration = service.synthesize("中文" * 15, str(path / "speech.wav"), target_duration=8)
            track = AudioSegment.from_wav(path / "speech.wav")
            self.assertAlmostEqual(duration, 30 / 3.8, delta=0.02)
            self.assertEqual(track.frame_rate, 48000)
            self.assertEqual(track.channels, 2)
            self.assertEqual(model.sample.call_args.kwargs["duration"], duration_frames_for_speech(len(reference), 30 / 3.8))
            self.assertEqual(model.sample.call_args.kwargs["speed"], 1.0)


class TranslationTests(unittest.TestCase):
    def translate(self, responses):
        client = MagicMock()
        client.__enter__.return_value = client
        client.post.side_effect = [types.SimpleNamespace(
            status_code=200, json=lambda result=result: {"choices": [{"message": {"content": json.dumps(result)}}]}
        ) for result in responses]
        segments = [{"id": 7, "start": 3, "end": 7, "text": "First source."},
                    {"id": 9, "start": 12, "end": 16, "text": "Second source."}]
        with patch("backend.services.translator.httpx.Client", return_value=client):
            translated = DeepSeekTranslator("test").translate_segments(segments, full_context="Complete source context.")
        return translated, client

    def test_translation_preserves_source_ids_times_and_full_context(self):
        translated, client = self.translate([[{"id": 9, "translated_text": "第二句"}, {"id": 7, "translated_text": "第一句"}]])
        self.assertEqual([(s["id"], s["start"], s["end"]) for s in translated], [(7, 3, 7), (9, 12, 16)])
        prompt = client.post.call_args.kwargs["json"]["messages"][1]["content"]
        self.assertIn("Complete source context.", prompt)
        self.assertEqual(translated[0]["original_text"], "First source.")

    def test_overlong_translation_is_corrected_once(self):
        translated, client = self.translate([
            [{"id": 7, "translated_text": "中文" * 30}, {"id": 9, "translated_text": "第二句"}],
            [{"id": 7, "translated_text": "精简后的第一句"}, {"id": 9, "translated_text": "第二句"}],
        ])
        self.assertEqual(client.post.call_count, 2)
        self.assertEqual(translated[0]["translated_text"], "精简后的第一句")

    def test_missing_translation_is_not_replaced_with_english(self):
        invalid = [{"id": 7, "translated_text": "第一句"}]
        with self.assertRaisesRegex(RuntimeError, "时间窗口"):
            self.translate([invalid, invalid])

    def test_duplicate_ids_rejected(self):
        invalid = [{"id": 7, "translated_text": "第一句"}, {"id": 7, "translated_text": "另一句"}]
        with self.assertRaises(RuntimeError):
            self.translate([invalid, invalid])


class MediaTests(unittest.TestCase):
    def test_download_uses_actual_video_duration_and_format_fallback(self):
        from backend.services.downloader import VideoDownloader
        for media, expected in [
            ({"streams": [{"duration": "12.345"}], "format": {"duration": "20"}}, 12.345),
            ({"streams": [{"duration": "N/A"}], "format": {"duration": "13.234"}}, 13.234),
        ]:
            with self.subTest(media=media), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                (root / "raw_video.mp4").touch()
                downloader = MagicMock()
                downloader.__enter__.return_value = downloader
                downloader.extract_info.return_value = {"title": "test", "duration": 20}
                probe = subprocess.CompletedProcess([], 0, json.dumps(media), "")
                extraction = subprocess.CompletedProcess([], 0, b"", b"")
                with patch("backend.services.downloader.yt_dlp.YoutubeDL", return_value=downloader), \
                     patch("backend.services.downloader.subprocess.run", side_effect=[probe, extraction]):
                    result = VideoDownloader(root).download("https://example.test/video")
                self.assertEqual(result["duration"], expected)

    def test_composition_failure_does_not_drop_timestamp_filters_and_subtitles(self):
        from backend.services.composer import VideoComposer
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            audio = root / "voice.wav"
            Sine(440, sample_rate=48000).to_audio_segment(duration=500).export(audio, format="wav")
            failure = subprocess.CompletedProcess([], 1, b"", b"subtitles filter failed")
            with patch("backend.services.composer.OUTPUTS_DIR", root), \
                 patch("backend.services.composer.select_composition_ffmpeg", return_value=("ffmpeg", True)), \
                 patch("backend.services.composer.subprocess.run", return_value=failure) as run:
                with self.assertRaisesRegex(RuntimeError, "合成失败"):
                    VideoComposer(root, "test").compose_video("video.mp4", str(audio), [subtitle(1, 0, 0.5)])
            self.assertEqual(run.call_count, 1)


class PipelineAndPreviewTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.manager_module = importlib.import_module("backend.core.task_manager")
        self.app_module = importlib.import_module("backend.app")
        self.directory_patch = patch.object(self.manager_module, "TASKS_DIR", self.root)
        self.directory_patch.start()
        self.addCleanup(self.directory_patch.stop)

    def test_real_pipeline_uses_merged_source_segments_and_keeps_scene_gaps(self):
        self.run_synthetic_pipeline(auto_pipeline=True)

    def test_reviewed_pipeline_does_not_reenter_waiting_review(self):
        self.run_synthetic_pipeline(auto_pipeline=False)

    def run_synthetic_pipeline(self, auto_pipeline):
        module = self.manager_module
        manager = module.TaskManager()
        task = manager.create_task({"url": "https://example.test/video", "auto_pipeline": auto_pipeline,
                                    "deepseek_api_key": "test", "tts_speaking_rate": 3.2})
        raw = [{"id": index + 1, "start": 2 + index * 8, "end": 8 + index * 8,
                "text": f"Complete source sentence {index}."} for index in range(3)]
        downloader = MagicMock()
        downloader.download.return_value = {"video_path": "video.mp4", "audio_wav_path": "source.wav",
                                             "title": "test", "duration": 28}
        asr = MagicMock()
        asr.transcribe.return_value = {"language": "en", "segments": raw}
        extractor = MagicMock()
        extractor.prepare_speaker_reference.return_value = {"audio_path": "reference.wav", "ref_text": raw[0]["text"], "segment_id": 1, "duration": 6}
        translator = MagicMock()
        translator.translate_segments.side_effect = lambda segments, **kw: [{**s, "original_text": s["text"], "translated_text": "示例配音"} for s in segments]
        voice = SyntheticTTS(2000)
        composer = MagicMock()
        composer.compose_video.return_value = {"filename": "test.mp4"}

        async def run():
            if auto_pipeline:
                await manager.run_pipeline(task)
                return
            pipeline = asyncio.create_task(manager.run_pipeline(task))
            try:
                while task.state != module.TaskState.WAITING_REVIEW and not pipeline.done():
                    await asyncio.sleep(0.01)
                self.assertFalse(pipeline.done(), task.error)
                with patch.object(self.app_module, "task_manager", manager):
                    await self.app_module.confirm_subtitles(task.task_id,
                        self.app_module.ConfirmSubtitlesRequest(subtitles=task.subtitles))
                accepted_log_index = len(task.logs) - 1
                await pipeline
                self.assertNotIn(module.TaskState.WAITING_REVIEW,
                                 [entry["stage"] for entry in task.logs[accepted_log_index:]])
            finally:
                if not pipeline.done():
                    pipeline.cancel()

        with patch.object(module, "VideoDownloader", return_value=downloader), \
             patch.object(module, "get_asr_engine", return_value=asr), \
             patch.object(module, "SpeakerExtractor", return_value=extractor), \
             patch.object(module, "DeepSeekTranslator", return_value=translator), \
             patch.object(module, "F5TTSMLXService", return_value=voice), \
             patch.object(module, "VideoComposer", return_value=composer):
            asyncio.run(asyncio.wait_for(run(), timeout=10))
        self.assertEqual(task.state, module.TaskState.COMPLETED, task.error)
        self.assertEqual([s["start"] for s in task.subtitles], [2, 10, 18])
        self.assertEqual(task.source_segments, raw)
        self.assertEqual(translator.translate_segments.call_args.kwargs["speaking_rate"], 3.2)
        self.assertTrue(all(call["speaking_rate"] == 3.2 for call in voice.calls))
        track = AudioSegment.from_wav(task.task_dir / "dubbed_full_track.wav")
        self.assertEqual(track[4500:9500].rms, 0)
        self.assertGreater(track[10100:10200].rms, 0)

    def make_review_task(self):
        manager = self.manager_module.TaskManager()
        task = manager.create_task({"tts_speaking_rate": 3.2, "tts_speed_mode": "quality"})
        task.state = self.manager_module.TaskState.WAITING_REVIEW
        task.subtitles = [subtitle(7, 5, 9)]
        task.source_segments = [{"id": 2, "start": 5, "end": 9, "text": "Exact original transcript."}]
        task.video_info = {"audio_wav_path": "source.wav"}
        reference = self.root / "reference.wav"
        reference.touch()
        task.speaker_ref = {"audio_path": str(reference), "ref_text": "Exact original transcript."}
        return manager, task

    def test_preview_uses_same_task_rate_quality_and_source_window(self):
        from fastapi.testclient import TestClient
        manager, task = self.make_review_task()
        voice = SyntheticTTS()
        with patch.object(self.app_module, "task_manager", manager), \
             patch.object(self.app_module, "TASKS_DIR", self.root), \
             patch.object(self.app_module, "F5TTSMLXService", return_value=voice):
            with TestClient(self.app_module.app) as client:
                response = client.post("/api/tts/preview", json={"task_id": task.task_id,
                    "subtitle_id": 7, "text": "试听配音", "target_duration": 99})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(voice.calls[0], {"speed_mode": "quality", "target_duration": 4, "speaking_rate": 3.2})

    def test_review_edits_preserve_source_anchors_and_metadata(self):
        from fastapi.testclient import TestClient
        manager, task = self.make_review_task()
        with patch.object(self.app_module, "task_manager", manager), TestClient(self.app_module.app) as client:
            response = client.post(f"/api/tasks/{task.task_id}/subtitles/confirm", json={"subtitles": [
                subtitle(7, 0, 99, "修改后的文案")
            ]})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual((task.subtitles[0]["start"], task.subtitles[0]["end"]), (5, 9))
        self.assertEqual(task.subtitles[0]["original_text"], "Original sentence.")
        self.assertTrue(task.review_event.is_set())
        self.assertEqual(task.state, self.manager_module.TaskState.TTS)
        saved = json.loads((task.task_dir / "subtitles.json").read_text())
        self.assertEqual(saved, task.subtitles)

    def test_repeated_confirmation_is_idempotent_after_pipeline_advances(self):
        from fastapi.testclient import TestClient
        manager, task = self.make_review_task()
        payload = {"subtitles": [subtitle(7, 5, 9, " 修改后的文案 ")]}
        with patch.object(self.app_module, "task_manager", manager), TestClient(self.app_module.app) as client:
            path = f"/api/tasks/{task.task_id}/subtitles/confirm"
            first = client.post(path, json=payload)
            self.assertEqual(first.status_code, 200, first.text)
            self.assertFalse(first.json()["already_confirmed"])
            for stage in ("TTS", "COMPOSING", "COMPLETED", "FAILED"):
                with self.subTest(stage=stage):
                    task.state = stage
                    # Synthesizing may add metadata; that must not change the accepted text.
                    task.subtitles[0]["audio_path"] = "already-generated.wav"
                    response = client.post(path, json=payload)
                    self.assertEqual(response.status_code, 200, response.text)
                    self.assertTrue(response.json()["already_confirmed"])
                    self.assertEqual(task.state, stage)
                    self.assertEqual(task.subtitles[0]["audio_path"], "already-generated.wav")

    def test_changed_text_after_confirmation_is_rejected_without_mutating(self):
        from fastapi.testclient import TestClient
        manager, task = self.make_review_task()
        with patch.object(self.app_module, "task_manager", manager), TestClient(self.app_module.app) as client:
            path = f"/api/tasks/{task.task_id}/subtitles/confirm"
            client.post(path, json={"subtitles": [subtitle(7, 5, 9, "确认文案")]})
            response = client.post(path, json={"subtitles": [subtitle(7, 5, 9, "再次修改")]})
        self.assertEqual(response.status_code, 409)
        self.assertIn("已确认", response.json()["detail"])
        self.assertEqual(task.subtitles[0]["translated_text"], "确认文案")

    def test_non_review_task_cannot_be_unblocked(self):
        from fastapi.testclient import TestClient
        manager, task = self.make_review_task()
        task.state = self.manager_module.TaskState.FAILED
        with patch.object(self.app_module, "task_manager", manager), TestClient(self.app_module.app) as client:
            response = client.post(f"/api/tasks/{task.task_id}/subtitles/confirm",
                                   json={"subtitles": task.subtitles})
        self.assertEqual(response.status_code, 409)
        self.assertFalse(task.review_event.is_set())
        self.assertIsNone(task.confirmed_review)

    def test_review_overflow_returns_actionable_error_without_unblocking(self):
        from fastapi.testclient import TestClient
        manager, task = self.make_review_task()
        with patch.object(self.app_module, "task_manager", manager), TestClient(self.app_module.app) as client:
            response = client.post(f"/api/tasks/{task.task_id}/subtitles/confirm", json={"subtitles": [
                subtitle(7, 5, 9, "中文" * 20)
            ]})
        self.assertEqual(response.status_code, 400)
        self.assertIn("精简", response.json()["detail"])
        self.assertFalse(task.review_event.is_set())

    def test_reference_switch_uses_raw_asr_transcript(self):
        manager, task = self.make_review_task()
        with patch.object(self.manager_module, "SpeakerExtractor") as extractor:
            extractor.return_value.prepare_speaker_reference.return_value = task.speaker_ref
            manager.update_speaker_ref(task.task_id, 2)
            self.assertEqual(extractor.return_value.prepare_speaker_reference.call_args.kwargs["segments"], task.source_segments)


if __name__ == "__main__":
    unittest.main()
