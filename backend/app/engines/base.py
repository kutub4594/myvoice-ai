"""Abstract base interface for MyVoice AI voice cloning engines."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from app.schemas import EngineInfo, ProfileType, SpeakingStyle


class EngineNotReadyError(RuntimeError):
    """Raised when an engine lacks ML dependencies, weights, or implemented language support."""


class EngineInputError(ValueError):
    """Raised when caller inputs (reference audio, transcript, language) fail validation."""


class EngineInferenceError(RuntimeError):
    """Raised when real model loading or inference fails at runtime (never falls back to mock)."""


@dataclass(frozen=True)
class EngineSynthesisInput:
    """Normalized inputs passed to an engine for a single language-homogeneous segment."""

    text: str
    language: Literal["bn", "en"]
    output_wav_path: Path
    reference_wav_path: Path | None = None
    reference_text: str | None = None
    profile_type: ProfileType = ProfileType.ZERO_SHOT
    trained_checkpoint_id: str | None = None
    style: SpeakingStyle = SpeakingStyle.NEUTRAL
    speed: float = 1.0
    exaggeration: float = 0.5
    cfg_weight: float = 0.5


class BaseVoiceCloningEngine(ABC):
    """Contract all voice cloning engines (IndicF5, F5, Chatterbox, CPU fallback, Mock) implement."""

    @property
    @abstractmethod
    def info(self) -> EngineInfo:
        """Return engine metadata, license info, and readiness status."""

    def runtime_details(self) -> dict[str, Any]:
        """Return non-secret hardware/model runtime diagnostics."""
        return {
            "engine_id": self.info.id,
            "status": self.info.status.value,
            "is_mock": self.info.is_mock,
        }

    @abstractmethod
    def transcribe_reference(self, reference_wav_path: Path, language_hint: str | None = None) -> str:
        """Return a transcript for a reference clip (used by zero-shot F5 models)."""

    @abstractmethod
    def synthesize_segment(self, request: EngineSynthesisInput) -> Path:
        """Synthesize speech for one language segment to request.output_wav_path."""
