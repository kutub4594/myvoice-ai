"""API schemas and domain enums for MyVoice AI."""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class LanguageMode(str, Enum):
    """Input language selection mode."""

    BENGALI = "bn"
    ENGLISH = "en"
    MIXED = "mixed"
    AUTO = "auto"


class OutputFormat(str, Enum):
    """Supported audio export formats."""

    WAV = "wav"
    MP3 = "mp3"


class ProfileType(str, Enum):
    """Distinguishes instant zero-shot reference cloning from fine-tuned checkpoints."""

    ZERO_SHOT = "zero_shot"
    TRAINED_MODEL = "trained_model"


class SpeakingStyle(str, Enum):
    """Supported speaking styles for multi-reference or parameter-guided synthesis."""

    NEUTRAL = "neutral"
    CONVERSATIONAL = "conversational"
    EXPRESSIVE = "expressive"
    CALM = "calm"


class EngineStatus(str, Enum):
    """Runtime readiness of a TTS/cloning engine."""

    READY = "ready"
    PLACEHOLDER = "placeholder"
    UNAVAILABLE = "unavailable"


class EngineInfo(BaseModel):
    """Metadata describing a registered voice cloning engine."""

    id: str
    name: str
    status: EngineStatus
    is_mock: bool = False
    supports_bengali: bool
    supports_english: bool
    supports_style_controls: bool = False
    supports_trained_checkpoints: bool = False
    requires_gpu: bool
    models: list[str]
    licenses: list[str]
    notes: str


class TranscribeResponse(BaseModel):
    """Transcript returned for an uploaded voice sample."""

    transcript: str
    language_hint: str
    is_mock: bool = False


class HealthResponse(BaseModel):
    """Health check response returned by GET /health."""

    status: Literal["ok", "degraded"]
    app_name: str
    version: str
    active_engine: EngineInfo
    ffmpeg_available: bool
    privacy_mode: str = "ephemeral_stateless"


class SegmentPreview(BaseModel):
    """Represents a segmented Bengali or English clause."""

    index: int
    language: Literal["bn", "en"]
    text: str
    pause_after_ms: int = Field(ge=0)


class ErrorDetail(BaseModel):
    """Structured API error response."""

    code: str
    message: str
