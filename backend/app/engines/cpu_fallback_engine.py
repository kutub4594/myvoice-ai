"""Modular CPU Fallback Engine Scaffold: MMS-TTS (Bengali) + Piper (English) + OpenVoice v2.

Model verification notes:
- facebook/mms-tts-ben: CC-BY-NC-4.0 (Non-Commercial), native Bengali base TTS.
- rhasspy/piper: MIT code (check individual English voice dataset licenses).
- myshell-ai/OpenVoice v2: MIT code & weights. ToneColorConverter is acoustic/language-agnostic,
  though cross-lingual speaker conversion quality on Bengali MMS-TTS requires empirical testing.
"""

from __future__ import annotations

from pathlib import Path

from app.engines.base import BaseVoiceCloningEngine, EngineNotReadyError, EngineSynthesisInput
from app.schemas import EngineInfo, EngineStatus


class CpuFallbackVoiceCloningEngine(BaseVoiceCloningEngine):
    """Placeholder scaffold for CPU-friendly MMS-TTS + Piper + OpenVoice v2 pipeline."""

    @property
    def info(self) -> EngineInfo:
        return EngineInfo(
            id="cpu_fallback",
            name="MMS-TTS + Piper + OpenVoice v2 (CPU Fallback)",
            status=EngineStatus.PLACEHOLDER,
            is_mock=False,
            supports_bengali=True,
            supports_english=True,
            supports_style_controls=False,
            supports_trained_checkpoints=False,
            requires_gpu=False,
            models=["facebook/mms-tts-ben", "rhasspy/piper", "myshell-ai/OpenVoice-v2"],
            licenses=[
                "facebook/mms-tts-ben: CC-BY-NC-4.0",
                "rhasspy/piper: MIT (voice cards vary)",
                "myshell-ai/OpenVoice v2: MIT",
            ],
            notes=(
                "Modular CPU fallback scaffold only. Lower vocal identity fidelity expected compared "
                "to GPU F5/Chatterbox models; weights are not downloaded yet."
            ),
        )

    def transcribe_reference(self, reference_wav_path: Path, language_hint: str | None = None) -> str:
        return ""

    def synthesize_segment(self, request: EngineSynthesisInput) -> Path:
        base_tts = "facebook/mms-tts-ben" if request.language == "bn" else "rhasspy/piper"
        raise EngineNotReadyError(
            f"CPU fallback ({base_tts} -> OpenVoice v2) is not implemented yet. "
            "Switch VOICE_ENGINE=mock for API testing."
        )
