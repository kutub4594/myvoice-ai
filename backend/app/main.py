"""FastAPI entrypoint for MyVoice AI backend."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, File, Form, HTTPException, Query, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.engines.base import EngineNotReadyError, EngineSynthesisInput
from app.engines.registry import get_engine, list_engines
from app.schemas import (
    EngineInfo,
    EngineStatus,
    HealthResponse,
    LanguageMode,
    OutputFormat,
    ProfileType,
    SegmentPreview,
    SpeakingStyle,
    TranscribeResponse,
)
from app.services.audio_processor import (
    AudioProcessingError,
    convert_wav_to_mp3,
    is_ffmpeg_available,
    normalize_reference_audio,
    stitch_wav_segments,
)
from app.services.text_segmenter import segment_text


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description=(
            "Stateless Python backend for MyVoice AI supporting Bengali, English, and "
            "mixed-script voice cloning pipelines."
        ),
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.allowed_origins),
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health", response_model=HealthResponse, tags=["system"])
    def health_check() -> HealthResponse:
        engine = get_engine(settings.voice_engine)
        ffmpeg_ok = is_ffmpeg_available()
        status = "ok" if ffmpeg_ok and engine.info.status != EngineStatus.UNAVAILABLE else "degraded"
        return HealthResponse(
            status=status,
            app_name=settings.app_name,
            version=settings.app_version,
            active_engine=engine.info,
            ffmpeg_available=ffmpeg_ok,
        )

    @app.get("/api/v1/engines", response_model=list[EngineInfo], tags=["engines"])
    def get_engines() -> list[EngineInfo]:
        return [engine.info for engine in list_engines()]

    @app.get("/api/v1/segment-preview", response_model=list[SegmentPreview], tags=["text"])
    def preview_segments(
        text: Annotated[str, Query(min_length=1, max_length=2000)],
        language_mode: LanguageMode = LanguageMode.AUTO,
    ) -> list[SegmentPreview]:
        segments = segment_text(
            text,
            mode=language_mode.value,
            base_pause_ms=settings.inter_segment_pause_ms,
        )
        return [
            SegmentPreview(
                index=seg.index,
                language=seg.language,
                text=seg.text,
                pause_after_ms=seg.pause_after_ms,
            )
            for seg in segments
        ]

    @app.post("/api/v1/transcribe", response_model=TranscribeResponse, tags=["audio"])
    async def transcribe_sample(
        reference_audio: UploadFile = File(...),
        language_hint: str = Form("auto"),
        consent_confirmed: bool = Form(False),
    ) -> TranscribeResponse:
        if not consent_confirmed:
            raise HTTPException(
                status_code=403,
                detail="Explicit user consent is required before uploading or processing voice audio.",
            )

        raw_bytes = await reference_audio.read()
        if not raw_bytes:
            raise HTTPException(status_code=400, detail="Uploaded reference audio is empty.")
        if len(raw_bytes) > settings.max_reference_audio_bytes:
            raise HTTPException(
                status_code=413,
                detail=f"Reference audio exceeds {settings.max_reference_audio_mb} MB limit.",
            )

        engine = get_engine(settings.voice_engine)
        suffix = Path(reference_audio.filename or "sample.wav").suffix or ".wav"

        with tempfile.TemporaryDirectory(prefix="myvoice_tr_") as tmp:
            work_dir = Path(tmp)
            raw_path = work_dir / f"upload{suffix}"
            raw_path.write_bytes(raw_bytes)
            norm_path = work_dir / "normalized.wav"
            try:
                normalize_reference_audio(raw_path, norm_path)
                transcript = engine.transcribe_reference(norm_path, language_hint=language_hint)
            except EngineNotReadyError as exc:
                raise HTTPException(status_code=501, detail=str(exc)) from exc
            except AudioProcessingError as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc

        return TranscribeResponse(
            transcript=transcript,
            language_hint=language_hint,
            is_mock=engine.info.is_mock,
        )

    @app.post("/api/v1/synthesize", tags=["synthesis"])
    async def synthesize_speech(
        text: str = Form(...),
        language_mode: LanguageMode = Form(LanguageMode.AUTO),
        output_format: OutputFormat = Form(OutputFormat.WAV),
        profile_type: ProfileType = Form(ProfileType.ZERO_SHOT),
        style: SpeakingStyle = Form(SpeakingStyle.NEUTRAL),
        speed: float = Form(1.0),
        exaggeration: float = Form(0.5),
        cfg_weight: float = Form(0.5),
        pause_ms: int | None = Form(None),
        reference_text: str | None = Form(None),
        trained_checkpoint_id: str | None = Form(None),
        consent_confirmed: bool = Form(False),
        reference_audio: UploadFile | None = File(None),
    ) -> Response:
        if not consent_confirmed:
            raise HTTPException(
                status_code=403,
                detail="Explicit user consent is required before processing voice recordings.",
            )

        cleaned_text = text.strip()
        if not cleaned_text:
            raise HTTPException(status_code=400, detail="Input text cannot be empty.")
        if len(cleaned_text) > settings.max_text_length:
            raise HTTPException(
                status_code=400,
                detail=f"Input text exceeds maximum length of {settings.max_text_length} characters.",
            )
        if not (0.5 <= speed <= 1.75):
            raise HTTPException(status_code=400, detail="Speed must be between 0.5 and 1.75.")

        if profile_type == ProfileType.ZERO_SHOT and reference_audio is None:
            raise HTTPException(
                status_code=400,
                detail="A reference audio clip is required for zero-shot voice cloning.",
            )
        if profile_type == ProfileType.TRAINED_MODEL and not (trained_checkpoint_id or "").strip():
            raise HTTPException(
                status_code=400,
                detail="trained_checkpoint_id is required when profile_type is trained_model.",
            )

        engine = get_engine(settings.voice_engine)
        base_pause = pause_ms if pause_ms is not None else settings.inter_segment_pause_ms
        segments = segment_text(cleaned_text, mode=language_mode.value, base_pause_ms=max(0, base_pause))
        if not segments:
            raise HTTPException(status_code=400, detail="No speakable characters found in text.")

        raw_bytes = b""
        suffix = ".wav"
        if reference_audio is not None:
            raw_bytes = await reference_audio.read()
            if not raw_bytes:
                raise HTTPException(status_code=400, detail="Uploaded reference audio is empty.")
            if len(raw_bytes) > settings.max_reference_audio_bytes:
                raise HTTPException(
                    status_code=413,
                    detail=f"Reference audio exceeds {settings.max_reference_audio_mb} MB limit.",
                )
            suffix = Path(reference_audio.filename or "sample.wav").suffix or ".wav"

        # Ephemeral processing directory guarantees uploaded voice clips are purged after response.
        with tempfile.TemporaryDirectory(prefix="myvoice_syn_") as tmp:
            work_dir = Path(tmp)
            norm_ref: Path | None = None
            try:
                if raw_bytes:
                    raw_path = work_dir / f"upload{suffix}"
                    raw_path.write_bytes(raw_bytes)
                    norm_ref = normalize_reference_audio(raw_path, work_dir / "ref_norm.wav")

                segment_outputs: list[tuple[Path, int]] = []
                for seg in segments:
                    seg_out = work_dir / f"seg_{seg.index}.wav"
                    engine.synthesize_segment(
                        EngineSynthesisInput(
                            text=seg.text,
                            language=seg.language,
                            output_wav_path=seg_out,
                            reference_wav_path=norm_ref,
                            reference_text=(reference_text or "").strip() or None,
                            profile_type=profile_type,
                            trained_checkpoint_id=(trained_checkpoint_id or "").strip() or None,
                            style=style,
                            speed=speed,
                            exaggeration=exaggeration,
                            cfg_weight=cfg_weight,
                        )
                    )
                    segment_outputs.append((seg_out, seg.pause_after_ms))

                stitched_wav = stitch_wav_segments(
                    segment_outputs,
                    output_wav_path=work_dir / "stitched.wav",
                    work_dir=work_dir,
                    crossfade_ms=settings.crossfade_ms,
                )

                if output_format == OutputFormat.MP3:
                    final_path = convert_wav_to_mp3(stitched_wav, work_dir / "output.mp3")
                    media_type = "audio/mpeg"
                    filename = "myvoice_output.mp3"
                else:
                    final_path = stitched_wav
                    media_type = "audio/wav"
                    filename = "myvoice_output.wav"

                audio_bytes = final_path.read_bytes()
            except EngineNotReadyError as exc:
                raise HTTPException(status_code=501, detail=str(exc)) from exc
            except AudioProcessingError as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc

        return Response(
            content=audio_bytes,
            media_type=media_type,
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "X-Voice-Engine": engine.info.id,
                "X-Engine-Is-Mock": str(engine.info.is_mock).lower(),
                "X-Segment-Count": str(len(segments)),
            },
        )

    if settings.enable_gradio:
        import gradio as gr
        from app.gradio_app import build_gradio_blocks

        app = gr.mount_gradio_app(app, build_gradio_blocks(), path="/gradio")

    return app


app = create_app()
