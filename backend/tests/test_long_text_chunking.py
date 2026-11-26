"""Unit tests for long-text chunking and objective WAV validation helpers."""

from __future__ import annotations

import math
import shutil
import struct
import tempfile
import unittest
import wave
from pathlib import Path

from app.services.audio_processor import (
    AudioProcessingError,
    adjust_wav_speed,
    inspect_wav_quality,
    is_ffmpeg_available,
    validate_output_wav,
    validate_reference_wav,
)
from app.services.text_segmenter import chunk_long_text, segment_for_synthesis


def _write_sine_wav(path: Path, duration_sec: float = 2.0, sample_rate: int = 24000, amp: float = 0.25) -> None:
    frames = int(duration_sec * sample_rate)
    samples = [
        int(max(-1.0, min(1.0, amp * math.sin(2.0 * math.pi * 220.0 * (i / sample_rate)))) * 32767.0)
        for i in range(frames)
    ]
    raw = struct.pack(f"<{frames}h", *samples)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(raw)


def _write_silent_wav(path: Path, duration_sec: float = 2.0, sample_rate: int = 24000) -> None:
    frames = int(duration_sec * sample_rate)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(b"\x00\x00" * frames)


class LongTextChunkingTests(unittest.TestCase):
    def test_leading_punctuation_inherits_next_script(self) -> None:
        segments = segment_for_synthesis('"আমি বাংলায় বলছি।" Hello world!', mode="auto", max_chunk_chars=160)
        self.assertGreaterEqual(len(segments), 2)
        self.assertEqual(segments[0].language, "bn")
        self.assertEqual(segments[1].language, "en")

    def test_long_bengali_paragraph_splits_cleanly_at_danda_and_clauses(self) -> None:
        long_bn = (
            "আজ সকাল থেকেই আকাশটা একটু মেঘলা, তবে বাতাসটা বেশ ঠান্ডা এবং আরামদায়ক লাগছে। "
            "আমরা সবাই মিলে নদীর ধারে হাঁটতে গিয়েছিলাম, সেখানে অনেক পাখি দেখলাম এবং ছবি তুললাম। "
            "দুপুরের দিকে রোদ উঠলে বাড়ি ফিরে এসে গরম চা আর মুড়ি খেয়ে গল্প করলাম।"
        )
        chunks = chunk_long_text(long_bn, language="bn", base_pause_ms=110, max_chars=90)
        self.assertGreaterEqual(len(chunks), 3)
        for chunk in chunks:
            self.assertEqual(chunk.language, "bn")
            self.assertLessEqual(len(chunk.text), 110)
            self.assertTrue(chunk.text.strip())
        # Last chunk should terminate cleanly with zero trailing pause
        self.assertEqual(chunks[-1].pause_after_ms, 0)
        # Earlier sentence boundaries preserve natural pause
        self.assertGreater(chunks[0].pause_after_ms, 0)

    def test_mixed_long_text_keeps_sequential_indices(self) -> None:
        text = (
            "আমাদের নতুন ভয়েস ক্লোনিং সিস্টেম এখন দীর্ঘ বাংলা অনুচ্ছেদ সুন্দরভাবে ভাগ করতে পারে। "
            "Meanwhile, English sentences stay separate so they do not get routed to a Bengali-only model."
        )
        segments = segment_for_synthesis(text, mode="auto", base_pause_ms=100, max_chunk_chars=70)
        self.assertGreaterEqual(len(segments), 3)
        self.assertEqual([seg.index for seg in segments], list(range(len(segments))))
        self.assertEqual(segments[0].language, "bn")
        self.assertEqual(segments[-1].language, "en")


class AudioValidationTests(unittest.TestCase):
    def test_validate_reference_wav_accepts_clean_speech_like_clip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            wav_path = Path(tmp) / "ref.wav"
            _write_sine_wav(wav_path, duration_sec=3.0, amp=0.2)
            metrics = validate_reference_wav(wav_path, min_duration_sec=1.5, max_duration_sec=30.0)
            self.assertAlmostEqual(metrics.duration_sec, 3.0, places=2)
            self.assertGreater(metrics.rms_dbfs, -30.0)
            self.assertEqual(metrics.clipping_ratio, 0.0)

    def test_validate_reference_wav_rejects_short_and_silent_clips(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            short_wav = Path(tmp) / "short.wav"
            _write_sine_wav(short_wav, duration_sec=0.4, amp=0.2)
            with self.assertRaises(AudioProcessingError):
                validate_reference_wav(short_wav, min_duration_sec=1.5, max_duration_sec=30.0)

            silent_wav = Path(tmp) / "silent.wav"
            _write_silent_wav(silent_wav, duration_sec=3.0)
            with self.assertRaises(AudioProcessingError):
                validate_reference_wav(silent_wav, min_duration_sec=1.5, max_duration_sec=30.0)

    def test_validate_output_wav_detects_silence_and_passes_valid_audio(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ok_wav = Path(tmp) / "ok.wav"
            _write_sine_wav(ok_wav, duration_sec=1.2, amp=0.15)
            metrics = validate_output_wav(ok_wav)
            self.assertGreater(metrics.duration_sec, 1.0)
            self.assertGreater(metrics.rms_dbfs, -35.0)

            silent_wav = Path(tmp) / "bad.wav"
            _write_silent_wav(silent_wav, duration_sec=1.0)
            with self.assertRaises(AudioProcessingError):
                validate_output_wav(silent_wav)

    def test_inspect_and_speed_adjustment_behavior(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            in_wav = Path(tmp) / "in.wav"
            out_wav = Path(tmp) / "out.wav"
            _write_sine_wav(in_wav, duration_sec=1.5, amp=0.25)
            metrics = inspect_wav_quality(in_wav)
            self.assertEqual(metrics.sample_rate, 24000)

            with self.assertRaises(AudioProcessingError):
                adjust_wav_speed(in_wav, out_wav, speed=3.0)

            if is_ffmpeg_available() and shutil.which("ffmpeg"):
                adjust_wav_speed(in_wav, out_wav, speed=1.25)
                sped = inspect_wav_quality(out_wav)
                self.assertLess(sped.duration_sec, metrics.duration_sec)


if __name__ == "__main__":
    unittest.main()
