"""Stage 2 Evaluation Placeholder: ResembleAI Chatterbox (English-only).

Audit findings:
- ResembleAI/chatterbox is archived/retired by Resemble AI, but remains publicly accessible
  on GitHub and Hugging Face under the permissive MIT License.
- Official Chatterbox does NOT support Bengali (do not claim Bengali support for Chatterbox).
- Pinned dependency stack: Python 3.10-3.13 (tested on 3.11), torch==2.6.0, torchaudio==2.6.0,
  transformers, librosa, diffusers, resemble-perth, safetensors, omegaconf.
- Isolated behind this modular adapter for Stage 2 English integration.
"""

from __future__ import annotations

from pathlib import Path

from app.engines.base import BaseVoiceCloningEngine, EngineNotReadyError, EngineSynthesisInput
from app.schemas import EngineInfo, EngineStatus


class ChatterboxComparisonEngine(BaseVoiceCloningEngine):
    """Modular placeholder for Stage 2 English voice cloning via ResembleAI/chatterbox."""

    @property
    def info(self) -> EngineInfo:
        return EngineInfo(
            id="chatterbox",
            name="Chatterbox (Stage 2 English Evaluation)",
            status=EngineStatus.PLACEHOLDER,
            is_mock=False,
            supports_bengali=False,
            supports_english=True,
            supports_style_controls=True,
            supports_trained_checkpoints=False,
            requires_gpu=True,
            models=["ResembleAI/chatterbox"],
            licenses=[
                "ResembleAI/chatterbox: MIT (archived/retired repo; embeds PerTh neural watermark)",
            ],
            notes=(
                "Stage 2 English-only candidate (does NOT support Bengali). Pinned to torch==2.6.0; "
                "not wired yet in Stage 1."
            ),
        )

    def transcribe_reference(self, reference_wav_path: Path, language_hint: str | None = None) -> str:
        return ""

    def synthesize_segment(self, request: EngineSynthesisInput) -> Path:
        if request.language != "en":
            raise EngineNotReadyError(
                "Chatterbox does not support Bengali. Use VOICE_ENGINE=indicf5 for Bengali."
            )
        raise EngineNotReadyError(
            "Stage 2 English Chatterbox inference is not implemented yet. "
            "Use VOICE_ENGINE=indicf5 for Bengali or VOICE_ENGINE=mock for API testing."
        )
