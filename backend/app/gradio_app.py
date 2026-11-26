"""Optional Gradio UI for Hugging Face Spaces / ZeroGPU compatibility."""

from __future__ import annotations

import atexit
import shutil
import tempfile
import time
from pathlib import Path

from app.config import get_settings

_GRADIO_TEMP_PREFIX = "myvoice_out_"
_GRADIO_OUTPUT_FILES: list[Path] = []


def _cleanup_gradio_outputs(*, max_age_seconds: int = 300) -> None:
    """Remove stale Gradio temporary WAV outputs so audio does not accumulate on disk."""
    now = time.time()
    kept: list[Path] = []
    for path in list(_GRADIO_OUTPUT_FILES):
        try:
            if not path.exists():
                continue
            if max_age_seconds <= 0 or (now - path.stat().st_mtime) >= max_age_seconds:
                path.unlink(missing_ok=True)
            else:
                kept.append(path)
        except OSError:
            pass
    _GRADIO_OUTPUT_FILES[:] = kept


atexit.register(_cleanup_gradio_outputs, max_age_seconds=0)
from app.engines.base import (
    EngineInferenceError,
    EngineInputError,
    EngineNotReadyError,
    EngineSynthesisInput,
)
from app.engines.registry import get_engine
from app.schemas import ProfileType, SpeakingStyle
from app.services.audio_processor import (
    AudioProcessingError,
    normalize_reference_audio,
    stitch_wav_segments,
    validate_output_wav,
    validate_reference_wav,
)
from app.services.text_segmenter import segment_for_synthesis


def build_gradio_blocks():
    """Construct a Gradio Blocks interface wired to the active voice engine."""
    import gradio as gr

    settings = get_settings()

    def _synthesize_ui(
        reference_audio_path: str | None,
        reference_text: str,
        target_text: str,
        language_mode: str,
        style: str,
        speed: float,
        consent: bool,
    ):
        if not consent:
            raise gr.Error("Explicit user consent is required before processing any voice sample.")
        if not reference_audio_path:
            raise gr.Error("Please upload or record a reference voice sample.")
        if not target_text or not target_text.strip():
            raise gr.Error("Please enter Bengali, English, or mixed text.")

        engine = get_engine(settings.voice_engine)
        segments = segment_for_synthesis(
            target_text,
            mode=language_mode,
            base_pause_ms=settings.inter_segment_pause_ms,
            max_chunk_chars=settings.max_chunk_chars,
        )
        if not segments:
            raise gr.Error("No speakable text found after normalization.")

        with tempfile.TemporaryDirectory(prefix="myvoice_gradio_") as tmp:
            work_dir = Path(tmp)
            segment_outputs: list[tuple[Path, int]] = []
            try:
                norm_ref = normalize_reference_audio(Path(reference_audio_path), work_dir / "ref.wav")
                if not engine.info.is_mock:
                    validate_reference_wav(
                        norm_ref,
                        min_duration_sec=settings.min_reference_duration_sec,
                        max_duration_sec=settings.max_reference_duration_sec,
                    )
                for seg in segments:
                    out_path = work_dir / f"seg_{seg.index}.wav"
                    engine.synthesize_segment(
                        EngineSynthesisInput(
                            text=seg.text,
                            language=seg.language,
                            reference_wav_path=norm_ref,
                            reference_text=reference_text.strip() or None,
                            output_wav_path=out_path,
                            profile_type=ProfileType.ZERO_SHOT,
                            style=SpeakingStyle(style),
                            speed=speed,
                        )
                    )
                    segment_outputs.append((out_path, seg.pause_after_ms))
                stitched = stitch_wav_segments(
                    segment_outputs,
                    work_dir / "final.wav",
                    work_dir=work_dir,
                    crossfade_ms=settings.crossfade_ms,
                    normalize_loudness=not engine.info.is_mock,
                )
                if not engine.info.is_mock:
                    validate_output_wav(stitched)
            except (EngineNotReadyError, EngineInputError, EngineInferenceError, AudioProcessingError) as exc:
                raise gr.Error(str(exc)) from exc

            # Gradio reads the returned file path after the handler returns; track for bounded TTL cleanup.
            _cleanup_gradio_outputs(max_age_seconds=300)
            persistent_out = Path(tempfile.mkstemp(suffix=".wav", prefix=_GRADIO_TEMP_PREFIX)[1])
            shutil.copyfile(stitched, persistent_out)
            _GRADIO_OUTPUT_FILES.append(persistent_out)
            return str(persistent_out), f"Engine: {engine.info.name} (segments: {len(segments)})"

    with gr.Blocks(title="MyVoice AI - Personal Voice Cloning") as demo:
        gr.Markdown(
            "# MyVoice AI\n"
            f"Active Engine: **{settings.voice_engine}** (Stage 1 Bengali IndicF5 + modular adapters)"
        )
        with gr.Row():
            ref_audio = gr.Audio(sources=["microphone", "upload"], type="filepath", label="Reference Voice")
            ref_text = gr.Textbox(
                label="Reference Transcript (required for IndicF5 unless auto-transcribe is enabled)"
            )
        text_in = gr.Textbox(lines=4, label="Text (Bengali, English, or Mixed)")
        with gr.Row():
            lang_dd = gr.Dropdown(["auto", "bn", "en", "mixed"], value="auto", label="Language Mode")
            style_dd = gr.Dropdown(
                ["neutral", "conversational", "expressive", "calm"],
                value="neutral",
                label="Speaking Style",
            )
            speed_sl = gr.Slider(0.75, 1.35, value=1.0, step=0.05, label="Speed")
        consent_cb = gr.Checkbox(
            label="I confirm I own or have permission to process this voice recording.",
            value=False,
        )
        run_btn = gr.Button("Generate Speech", variant="primary")
        out_audio = gr.Audio(type="filepath", label="Generated Output")
        status_md = gr.Textbox(label="Status", interactive=False)

        run_btn.click(
            fn=_synthesize_ui,
            inputs=[ref_audio, ref_text, text_in, lang_dd, style_dd, speed_sl, consent_cb],
            outputs=[out_audio, status_md],
        )

    return demo
