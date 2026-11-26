"""Registry mapping engine IDs to concrete BaseVoiceCloningEngine instances."""

from __future__ import annotations

from functools import lru_cache

from app.engines.base import BaseVoiceCloningEngine
from app.engines.chatterbox_engine import ChatterboxComparisonEngine
from app.engines.cpu_fallback_engine import CpuFallbackVoiceCloningEngine
from app.engines.f5_engine import F5DualVoiceCloningEngine
from app.engines.indicf5_engine import IndicF5BengaliEngine
from app.engines.mock_engine import MockVoiceCloningEngine

_ENGINE_FACTORIES: dict[str, type[BaseVoiceCloningEngine]] = {
    "indicf5": IndicF5BengaliEngine,
    "f5": F5DualVoiceCloningEngine,
    "chatterbox": ChatterboxComparisonEngine,
    "cpu_fallback": CpuFallbackVoiceCloningEngine,
    "mock": MockVoiceCloningEngine,
}


@lru_cache(maxsize=8)
def get_engine(engine_id: str) -> BaseVoiceCloningEngine:
    """Return a cached engine instance for the configured engine ID."""
    normalized = engine_id.strip().lower()
    factory = _ENGINE_FACTORIES.get(normalized)
    if factory is None:
        supported = ", ".join(sorted(_ENGINE_FACTORIES.keys()))
        raise ValueError(f"Unknown VOICE_ENGINE '{engine_id}'. Supported values: {supported}")
    return factory()


def list_engines() -> list[BaseVoiceCloningEngine]:
    """Return all registered engines in priority order."""
    return [get_engine(key) for key in ("indicf5", "f5", "chatterbox", "cpu_fallback", "mock")]
