"""Tests for FFmpeg-based audio normalization, stitching, and MP3 export."""

from __future__ import annotations

import math
import struct
import sys
import tempfile
import unittest
import wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.audio_processor import (
    convert_wav_to_mp3,
    is_ffmpeg_available,
    normalize_reference_audio,
    stitch_wav_segments,
    write_silence_wav,
)


def _write_sine_wav(path: Path, freq_hz: float = 440.0, duration_sec: float = 0.5, sample_rate: int = 24000) -> None:
    total = int(sample_rate * duration_sec)
    frames = bytearray()
    for i in range(total):
        sample = int(9000 * math.sin(2.0 * math.pi * freq_hz * i / sample_rate))
        frames.extend(struct.pack("<h", sample))
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(bytes(frames))


@unittest.skipUnless(is_ffmpeg_available(), "ffmpeg binary not available on PATH")
class AudioProcessorTests(unittest.TestCase):
    def test_write_silence_and_stitch_and_mp3_export(self) -> None:
        with tempfile.TemporaryDirectory(prefix="myvoice_audio_test_") as tmp:
            work_dir = Path(tmp)
            seg1 = work_dir / "seg1.wav"
            seg2 = work_dir / "seg2.wav"
            _write_sine_wav(seg1, freq_hz=330.0, duration_sec=0.4)
            _write_sine_wav(seg2, freq_hz=440.0, duration_sec=0.4)

            silence = write_silence_wav(work_dir / "silence.wav", duration_ms=100)
            self.assertTrue(silence.exists())
            self.assertGreater(silence.stat().st_size, 44)

            norm = normalize_reference_audio(seg1, work_dir / "norm.wav")
            self.assertTrue(norm.exists())

            stitched = stitch_wav_segments(
                [(seg1, 110), (seg2, 0)],
                output_wav_path=work_dir / "stitched.wav",
                work_dir=work_dir,
                crossfade_ms=50,
            )
            self.assertTrue(stitched.exists())
            with wave.open(str(stitched), "rb") as wf:
                self.assertEqual(wf.getnchannels(), 1)
                self.assertEqual(wf.getframerate(), 24000)
                self.assertGreater(wf.getnframes(), 12000)

            mp3_out = convert_wav_to_mp3(stitched, work_dir / "out.mp3")
            self.assertTrue(mp3_out.exists())
            self.assertGreater(mp3_out.stat().st_size, 500)


if __name__ == "__main__":
    unittest.main()
