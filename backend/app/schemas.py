"""API schemas and domain enums for MyVoice AI."""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal

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


class DeviceCapabilityInfo(BaseModel):
    """Hardware and runtime inference diagnostics (never includes secrets)."""

    selected_device: str
    torch_installed: bool
    transformers_installed: bool
    cuda_available: bool
    mps_available: bool = False
    gpu_name: str | None = None
    gpu_vram_mb: int | None = None
    model_loaded: bool = False
    active_inference_jobs: int = 0
    max_concurrent_jobs: int = 1


class AudioQualityMetrics(BaseModel):
    """Objective audio validation metrics for WAV clips."""

    duration_sec: float
    sample_rate: int
    channels: int
    rms_dbfs: float
    peak_dbfs: float
    clipping_ratio: float


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
    runtime: DeviceCapabilityInfo | None = None


class DiagnosticsResponse(BaseModel):
    """Detailed non-secret system and engine diagnostics."""

    health: HealthResponse
    runtime_details: dict[str, Any] = Field(default_factory=dict)
    implemented_stages: list[str] = Field(default_factory=list)
    experimental_stages: list[str] = Field(default_factory=list)


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


class RemoteTrainingUploadResponse(BaseModel):
    """Response returned after user-consented upload of training dataset to external private storage."""

    owner_id: str
    dataset_id: str
    uploaded_at_utc: str
    file_count: int
    total_bytes: int
    outside_git_repo: bool
    privacy_notice: str = (
        "Stored strictly in private owner-isolated external backend storage outside the Git repository."
    )


class RemoteTrainingSummaryResponse(BaseModel):
    """Summary of remote training datasets, embeddings, checkpoints, and generated audio."""

    owner_id: str
    storage_scope: str
    outside_git_repo: bool
    datasets: list[dict[str, Any]]
    categories: dict[str, dict[str, int]]


class RemoteTrainingDeleteResponse(BaseModel):
    """Result of user-initiated deletion of remote training data."""

    owner_id: str
    storage_scope: str = "private_external_owner_isolated"
    deleted_items: int
    freed_bytes: int
