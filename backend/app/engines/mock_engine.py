"""Deterministic mock engine for offline API and Flutter UI integration testing.

Generates audible synthetic sine-wave tones proportional to text length so the full
upload -> segment -> stitch -> WAV/MP3 download pipeline can be verified without ML weights.
"""

from __future__ import annotations

import math
import struct
import wave
from pathlib import Path

from app.engines.base import BaseVoiceCloningEngine, EngineSynthesisInput
from app.schemas import EngineInfo, EngineStatus, SpeakingStyle


class MockVoiceCloningEngine(BaseVoiceCloningEngine):
    """Offline placeholder engine for pipeline testing only (NOT real voice cloning)."""

    SAMPLE_RATE = 24000

    @property
    def info(self) -> EngineInfo:
        return EngineInfo(
            id="mock",
            name="Mock Pipeline Test Engine",
            status=EngineStatus.READY,
            is_mock=True,
            supports_bengali=True,
            supports_english=True,
            supports_style_controls=True,
            supports_trained_checkpoints=True,
            requires_gpu=False,
            models=["synthetic-tone-generator"],
            licenses=["MIT (internal test utility)"],
            notes=(
                "Generates synthetic test audio to validate API, segmentation, FFmpeg stitching, "
                "and Flutter playback/download without downloading AI weights. Not real voice cloning."
            ),
        )

    def transcribe_reference(self, reference_wav_path: Path, language_hint: str | None = None) -> str:
        return f"[mock-transcript:{language_hint or 'auto'}]"

    def synthesize_segment(self, request: EngineSynthesisInput) -> Path:
        base_freq = 330.0 if request.language == "bn" else 440.0
        style_multiplier = {
            SpeakingStyle.NEUTRAL: 1.0,
            SpeakingStyle.CONVERSATIONAL: 1.06,
            SpeakingStyle.EXPRESSIVE: 1.15,
            SpeakingStyle.CALM: 0.92,
        }.get(request.style, 1.0)
        freq = base_freq * style_multiplier

        duration_sec = max(0.55, min(4.0, len(request.text) * 0.045 / max(0.5, request.speed)))
        total_frames = int(self.SAMPLE_RATE * duration_sec)
        fade_frames = int(self.SAMPLE_RATE * 0.03)

        frames = bytearray()
        for i in range(total_frames):
            env = 1.0
            if i < fade_frames:
                env = i / max(1, fade_frames)
            elif i > total_frames - fade_frames:
                env = (total_frames - i) / max(1, fade_frames)
            sample = int(10000 * env * math.sin(2.0 * math.pi * freq * i / self.SAMPLE_RATE))
            frames.extend(struct.pack("<h", sample))

        with wave.open(str(request.output_wav_path), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(self.SAMPLE_RATE)
            wf.writeframes(bytes(frames))

        return request.output_wav_path
