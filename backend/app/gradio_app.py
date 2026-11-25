"""Optional Gradio UI for Hugging Face Spaces / ZeroGPU compatibility."""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from app.config import get_settings
from app.engines.base import EngineNotReadyError, EngineSynthesisInput
from app.engines.registry import get_engine
from app.schemas import ProfileType, SpeakingStyle
from app.services.audio_processor import (
    AudioProcessingError,
    normalize_reference_audio,
    stitch_wav_segments,
)
from app.services.text_segmenter import segment_text


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
        segments = segment_text(
            target_text,
            mode=language_mode,
            base_pause_ms=settings.inter_segment_pause_ms,
        )
        if not segments:
            raise gr.Error("No speakable text found after normalization.")

        with tempfile.TemporaryDirectory(prefix="myvoice_gradio_") as tmp:
            work_dir = Path(tmp)
            norm_ref = normalize_reference_audio(Path(reference_audio_path), work_dir / "ref.wav")
            segment_outputs: list[tuple[Path, int]] = []
            try:
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
                )
            except (EngineNotReadyError, AudioProcessingError) as exc:
                raise gr.Error(str(exc)) from exc

            # Gradio reads the returned file path after the handler returns, so write to a named temp file.
            persistent_out = Path(tempfile.mkstemp(suffix=".wav", prefix="myvoice_out_")[1])
            shutil.copyfile(stitched, persistent_out)
            return str(persistent_out), f"Engine: {engine.info.name} (segments: {len(segments)})"

    with gr.Blocks(title="MyVoice AI - Personal Voice Cloning") as demo:
        gr.Markdown(
            "# MyVoice AI\n"
            f"Active Engine: **{settings.voice_engine}** (scaffold phase — no large weights loaded)"
        )
        with gr.Row():
            ref_audio = gr.Audio(sources=["microphone", "upload"], type="filepath", label="Reference Voice")
            ref_text = gr.Textbox(label="Reference Transcript (optional for F5 auto-transcribe)")
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
