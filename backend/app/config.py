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
    app_version: str = "0.2.0-indicf5"
    app_env: str = "development"
    host: str = "0.0.0.0"
    port: int = 8000
    voice_engine: str = "mock"
    device: str = "auto"
    enable_gradio: bool = False
    indicf5_model_id: str = "ai4bharat/IndicF5"
    enable_auto_transcribe: bool = False
    whisper_model_size: str = "small"
    max_reference_audio_mb: int = 15
    min_reference_duration_sec: float = 1.5
    max_reference_duration_sec: float = 30.0
    max_text_length: int = 2000
    max_chunk_chars: int = 160
    max_concurrent_jobs: int = 1
    max_training_dataset_mb: int = 250
    max_training_dataset_uncompressed_mb: int = 500
    max_training_zip_entries: int = 5000
    max_training_file_mb: int = 100
    private_training_storage_dir: str | None = None
    api_auth_token: str | None = None
    owner_tokens_raw: str | None = None
    allow_local_http_dev: bool = False
    trusted_proxy_ips_raw: str = "127.0.0.1,::1"
    crossfade_ms: int = 60
    inter_segment_pause_ms: int = 110
    model_cache_dir: str | None = None
    hf_token: str | None = None
    allowed_origins: tuple[str, ...] = ("*",)

    @property
    def max_reference_audio_bytes(self) -> int:
        return self.max_reference_audio_mb * 1024 * 1024


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached runtime settings from environment variables."""
    raw_origins = os.getenv("ALLOWED_ORIGINS", "*")
    origins = tuple(item.strip() for item in raw_origins.split(",") if item.strip()) or ("*",)
    hf_token = (os.getenv("HF_TOKEN") or "").strip() or None
    cache_dir = (os.getenv("MODEL_CACHE_DIR") or "").strip() or None

    return Settings(
        app_name=os.getenv("APP_NAME", "MyVoice AI Backend"),
        app_version=os.getenv("APP_VERSION", "0.2.0-indicf5"),
        app_env=os.getenv("APP_ENV", "development"),
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", "8000")),
        voice_engine=os.getenv("VOICE_ENGINE", "mock").strip().lower(),
        device=os.getenv("INFERENCE_DEVICE", "auto").strip().lower(),
        enable_gradio=_parse_bool(os.getenv("ENABLE_GRADIO"), default=False),
        indicf5_model_id=os.getenv("INDICF5_MODEL_ID", "ai4bharat/IndicF5").strip(),
        enable_auto_transcribe=_parse_bool(os.getenv("ENABLE_AUTO_TRANSCRIBE"), default=False),
        whisper_model_size=os.getenv("WHISPER_MODEL_SIZE", "small").strip(),
        max_reference_audio_mb=int(os.getenv("MAX_REFERENCE_AUDIO_MB", "15")),
        min_reference_duration_sec=float(os.getenv("MIN_REFERENCE_DURATION_SEC", "1.5")),
        max_reference_duration_sec=float(os.getenv("MAX_REFERENCE_DURATION_SEC", "30.0")),
        max_text_length=int(os.getenv("MAX_TEXT_LENGTH", "2000")),
        max_chunk_chars=int(os.getenv("MAX_CHUNK_CHARS", "160")),
        max_concurrent_jobs=max(1, int(os.getenv("MAX_CONCURRENT_JOBS", "1"))),
        max_training_dataset_mb=int(os.getenv("MAX_TRAINING_DATASET_MB", "250")),
        max_training_dataset_uncompressed_mb=int(
            os.getenv("MAX_TRAINING_DATASET_UNCOMPRESSED_MB", "500")
        ),
        max_training_zip_entries=max(1, int(os.getenv("MAX_TRAINING_ZIP_ENTRIES", "5000"))),
        max_training_file_mb=max(1, int(os.getenv("MAX_TRAINING_FILE_MB", "100"))),
        private_training_storage_dir=(os.getenv("PRIVATE_TRAINING_STORAGE_DIR") or "").strip() or None,
        api_auth_token=(os.getenv("MYVOICE_API_TOKEN") or "").strip() or None,
        owner_tokens_raw=(os.getenv("MYVOICE_OWNER_TOKENS") or "").strip() or None,
        allow_local_http_dev=_parse_bool(os.getenv("ALLOW_LOCAL_HTTP_DEV"), default=False),
        trusted_proxy_ips_raw=os.getenv("TRUSTED_PROXY_IPS", "127.0.0.1,::1").strip(),
        crossfade_ms=int(os.getenv("CROSSFADE_MS", "60")),
        inter_segment_pause_ms=int(os.getenv("INTER_SEGMENT_PAUSE_MS", "110")),
        model_cache_dir=cache_dir,
        hf_token=hf_token,
        allowed_origins=origins,
    )
