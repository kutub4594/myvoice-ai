"""Abstract base interface for MyVoice AI voice cloning engines."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from app.schemas import EngineInfo, ProfileType, SpeakingStyle


class EngineNotReadyError(RuntimeError):
    """Raised when a scaffolded engine does not have model weights/inference wired yet."""


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
    """Contract all voice cloning engines (F5, CPU fallback, Mock) must implement."""

    @property
    @abstractmethod
    def info(self) -> EngineInfo:
        """Return engine metadata, license info, and readiness status."""

    @abstractmethod
    def transcribe_reference(self, reference_wav_path: Path, language_hint: str | None = None) -> str:
        """Return a transcript for a reference clip (used by zero-shot F5 models)."""

    @abstractmethod
    def synthesize_segment(self, request: EngineSynthesisInput) -> Path:
        """Synthesize speech for one language segment to request.output_wav_path."""
