"""Primary Experimental Engine Scaffold: IndicF5 (Bengali) + F5-TTS (English).

Model verification notes:
- IndicF5 (ai4bharat/IndicF5): MIT License, gated Hugging Face repo (requires free HF token),
  supports 11 Indic languages including Bengali (no native English).
- F5-TTS (SWivid/F5-TTS): Code MIT, pre-trained weights CC-BY-NC-4.0 (Non-Commercial).
- Reference transcription helper: faster-whisper (MIT).

Supports both Tier 1 (Zero-Shot multi-reference clips) and Tier 2 (personal fine-tuned
checkpoints trained via Colab). Inference is intentionally NOT wired during scaffolding.
"""

from __future__ import annotations

from pathlib import Path

from app.engines.base import BaseVoiceCloningEngine, EngineNotReadyError, EngineSynthesisInput
from app.schemas import EngineInfo, EngineStatus


class F5DualVoiceCloningEngine(BaseVoiceCloningEngine):
    """Placeholder scaffold for IndicF5 (Bengali) + F5-TTS (English)."""

    @property
    def info(self) -> EngineInfo:
        return EngineInfo(
            id="f5",
            name="IndicF5 (Bengali) + F5-TTS (English)",
            status=EngineStatus.PLACEHOLDER,
            is_mock=False,
            supports_bengali=True,
            supports_english=True,
            supports_style_controls=False,
            supports_trained_checkpoints=True,
            requires_gpu=True,
            models=["ai4bharat/IndicF5", "SWivid/F5-TTS", "faster-whisper"],
            licenses=[
                "ai4bharat/IndicF5: MIT (gated HF repo)",
                "SWivid/F5-TTS: Code MIT / Weights CC-BY-NC-4.0",
                "faster-whisper: MIT",
            ],
            notes=(
                "Primary experimental scaffold. Supports zero-shot reference conditioning and "
                "fine-tuned checkpoint hooks. Model weights are not downloaded yet."
            ),
        )

    def transcribe_reference(self, reference_wav_path: Path, language_hint: str | None = None) -> str:
        raise EngineNotReadyError(
            "F5 auto-transcription (faster-whisper) is not enabled in the scaffold phase."
        )

    def synthesize_segment(self, request: EngineSynthesisInput) -> Path:
        model_name = "ai4bharat/IndicF5" if request.language == "bn" else "SWivid/F5-TTS"
        raise EngineNotReadyError(
            f"{model_name} inference is not implemented yet. Switch VOICE_ENGINE=mock for API testing."
        )
