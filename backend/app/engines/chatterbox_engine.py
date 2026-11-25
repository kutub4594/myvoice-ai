"""Optional Comparison Engine Scaffold: Chatterbox (English) + Bangla Adaptation.

Model verification notes:
- ResembleAI/chatterbox: MIT License (code and weights). Supports English with explicit
  exaggeration (0.25-2.0) and cfg_weight (0.0-1.0) controls; embeds PerTh watermark.
- Banglabox/chatterbox-bangla-tts: MIT License community adaptation adding Bangladeshi
  Bengali tokenizer and dual-loss fine-tuning. Requires direct listening tests before use.
"""

from __future__ import annotations

from pathlib import Path

from app.engines.base import BaseVoiceCloningEngine, EngineNotReadyError, EngineSynthesisInput
from app.schemas import EngineInfo, EngineStatus


class ChatterboxComparisonEngine(BaseVoiceCloningEngine):
    """Placeholder scaffold for Chatterbox expressive voice cloning comparison."""

    @property
    def info(self) -> EngineInfo:
        return EngineInfo(
            id="chatterbox",
            name="Chatterbox (English) + Bangla Adaptation",
            status=EngineStatus.PLACEHOLDER,
            is_mock=False,
            supports_bengali=True,
            supports_english=True,
            supports_style_controls=True,
            supports_trained_checkpoints=True,
            requires_gpu=True,
            models=["ResembleAI/chatterbox", "Banglabox/chatterbox-bangla-tts"],
            licenses=[
                "ResembleAI/chatterbox: MIT (includes PerTh neural watermark)",
                "Banglabox/chatterbox-bangla-tts: MIT",
            ],
            notes=(
                "Optional comparison scaffold with exaggeration/CFG style controls. "
                "Model weights are not downloaded and bilingual quality has not been tested yet."
            ),
        )

    def transcribe_reference(self, reference_wav_path: Path, language_hint: str | None = None) -> str:
        # Chatterbox does not require a reference transcript for zero-shot audio prompting.
        return ""

    def synthesize_segment(self, request: EngineSynthesisInput) -> Path:
        model_name = (
            "Banglabox/chatterbox-bangla-tts"
            if request.language == "bn"
            else "ResembleAI/chatterbox"
        )
        raise EngineNotReadyError(
            f"{model_name} inference is not implemented yet. Switch VOICE_ENGINE=mock for API testing."
        )
