"""Environment-driven configuration for MyVoice AI backend."""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache


def _parse_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    """Application settings loaded from environment variables without hardcoded secrets."""

    app_name: str = "MyVoice AI Backend"
    app_version: str = "0.1.0-scaffold"
    app_env: str = "development"
    host: str = "0.0.0.0"
    port: int = 8000
    voice_engine: str = "mock"
    enable_gradio: bool = False
    max_reference_audio_mb: int = 15
    max_text_length: int = 1000
    crossfade_ms: int = 60
    inter_segment_pause_ms: int = 110
    allowed_origins: tuple[str, ...] = ("*",)

    @property
    def max_reference_audio_bytes(self) -> int:
        return self.max_reference_audio_mb * 1024 * 1024


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached runtime settings from environment variables."""
    raw_origins = os.getenv("ALLOWED_ORIGINS", "*")
    origins = tuple(item.strip() for item in raw_origins.split(",") if item.strip()) or ("*",)

    return Settings(
        app_name=os.getenv("APP_NAME", "MyVoice AI Backend"),
        app_version=os.getenv("APP_VERSION", "0.1.0-scaffold"),
        app_env=os.getenv("APP_ENV", "development"),
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", "8000")),
        voice_engine=os.getenv("VOICE_ENGINE", "mock").strip().lower(),
        enable_gradio=_parse_bool(os.getenv("ENABLE_GRADIO"), default=False),
        max_reference_audio_mb=int(os.getenv("MAX_REFERENCE_AUDIO_MB", "15")),
        max_text_length=int(os.getenv("MAX_TEXT_LENGTH", "1000")),
        crossfade_ms=int(os.getenv("CROSSFADE_MS", "60")),
        inter_segment_pause_ms=int(os.getenv("INTER_SEGMENT_PAUSE_MS", "110")),
        allowed_origins=origins,
    )
