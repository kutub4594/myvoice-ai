"""Dual F5 Engine: Delegates Bengali to IndicF5; English F5-TTS remains gated.

License & deployment note:
- ai4bharat/IndicF5 (Bengali): MIT License (gated Hugging Face repo). Delegated to
  IndicF5BengaliEngine for Stage 1 real Bengali cloning.
- SWivid/F5-TTS (English): Code MIT, pre-trained weights CC-BY-NC-4.0 (Non-Commercial).
  Do NOT deploy pre-trained F5-TTS weights in a public production service without
  appropriate permission. Stage 2 evaluates MIT-licensed Chatterbox for English.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.config import Settings, get_settings
from app.engines.base import BaseVoiceCloningEngine, EngineNotReadyError, EngineSynthesisInput
from app.engines.indicf5_engine import IndicF5BengaliEngine
from app.schemas import EngineInfo, EngineStatus


class F5DualVoiceCloningEngine(BaseVoiceCloningEngine):
    """Routes Bengali synthesis to IndicF5 while keeping non-commercial F5-TTS English gated."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._bengali_engine = IndicF5BengaliEngine(settings=self._settings)

    @property
    def info(self) -> EngineInfo:
        bn_info = self._bengali_engine.info
        return EngineInfo(
            id="f5",
            name="IndicF5 (Bengali) + F5-TTS (English Pending)",
            status=EngineStatus.PLACEHOLDER if bn_info.status != EngineStatus.READY else EngineStatus.READY,
            is_mock=False,
            supports_bengali=True,
            supports_english=False,
            supports_style_controls=False,
            supports_trained_checkpoints=False,
            requires_gpu=True,
            models=["ai4bharat/IndicF5", "SWivid/F5-TTS (not deployed)"],
            licenses=[
                "ai4bharat/IndicF5: MIT (gated HF repo)",
                "SWivid/F5-TTS: Code MIT / Weights CC-BY-NC-4.0 (Non-Commercial)",
            ],
            notes=(
                "Bengali routes to real IndicF5BengaliEngine when ML dependencies are installed. "
                "English F5-TTS is intentionally disabled due to CC-BY-NC-4.0 weight licensing."
            ),
        )

    def runtime_details(self) -> dict[str, Any]:
        details = self._bengali_engine.runtime_details()
        details["engine_id"] = "f5"
        details["english_status"] = "disabled_non_commercial_weights"
        return details

    def transcribe_reference(self, reference_wav_path: Path, language_hint: str | None = None) -> str:
        return self._bengali_engine.transcribe_reference(
            reference_wav_path,
            language_hint=language_hint,
        )

    def synthesize_segment(self, request: EngineSynthesisInput) -> Path:
        if request.language == "bn":
            return self._bengali_engine.synthesize_segment(request)
        raise EngineNotReadyError(
            "English F5-TTS is not enabled: SWivid/F5-TTS pre-trained weights are CC-BY-NC-4.0 "
            "(Non-Commercial). Stage 2 will evaluate MIT-licensed Chatterbox for English."
        )
