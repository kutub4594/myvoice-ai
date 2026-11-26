"""FastAPI entrypoint for MyVoice AI backend."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Annotated

from fastapi import (
    Depends,
    FastAPI,
    File,
    Form,
    Header,
    HTTPException,
    Query,
    Request,
    Response,
    UploadFile,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.engines.base import (
    EngineInferenceError,
    EngineInputError,
    EngineNotReadyError,
    EngineSynthesisInput,
)
from app.engines.indicf5_engine import probe_device_capability
from app.engines.registry import get_engine, list_engines
from app.security import (
    SecurityPolicyError,
    authenticate_request_token,
    enforce_https_transport,
    has_configured_auth,
    verify_gradio_credentials,
)
from app.schemas import (
    DiagnosticsResponse,
    EngineInfo,
    EngineStatus,
    HealthResponse,
    LanguageMode,
    OutputFormat,
    ProfileType,
    RemoteTrainingDeleteResponse,
    RemoteTrainingSummaryResponse,
    RemoteTrainingUploadResponse,
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
    validate_output_wav,
    validate_reference_wav,
)
from app.services.private_storage import (
    PrivateStorageConsentError,
    PrivateStorageError,
    delete_all_remote_training_data,
    delete_remote_dataset,
    list_remote_training_data,
    resolve_private_training_dir,
    store_training_dataset_zip,
)
from app.services.text_segmenter import segment_for_synthesis, segment_text


_UPLOAD_CHUNK_BYTES = 64 * 1024


async def read_upload_bounded(
    upload_file: UploadFile,
    max_bytes: int,
    *,
    label: str = "Uploaded file",
) -> bytes:
    """Read an UploadFile in bounded 64 KB chunks and fail immediately if max_bytes is exceeded."""
    buf = bytearray()
    while True:
        chunk = await upload_file.read(_UPLOAD_CHUNK_BYTES)
        if not chunk:
            break
        if len(buf) + len(chunk) > max_bytes:
            await upload_file.close()
            max_mb = max_bytes / (1024 * 1024)
            raise HTTPException(
                status_code=413,
                detail=f"{label} exceeds {max_mb:g} MB limit.",
            )
        buf.extend(chunk)
    await upload_file.close()
    if not buf:
        raise HTTPException(status_code=400, detail=f"{label} is empty.")
    return bytes(buf)


def enforce_https_dependency(request: Request) -> None:
    """Reject plain HTTP requests unless explicitly allowed on local development hosts."""
    cfg = get_settings()
    try:
        enforce_https_transport(
            scheme=request.url.scheme,
            forwarded_proto=request.headers.get("x-forwarded-proto"),
            host_header=request.headers.get("host"),
            url_hostname=request.url.hostname,
            client_host=request.client.host if request.client else None,
            settings=cfg,
        )
    except SecurityPolicyError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


def require_secure_owner(
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
    x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
) -> str:
    """Enforce HTTPS and validate bearer/API-key credentials, returning isolated owner_id."""
    enforce_https_dependency(request)
    cfg = get_settings()
    try:
        return authenticate_request_token(authorization, x_api_key, settings=cfg)
    except SecurityPolicyError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


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

    @app.get(
        "/health",
        response_model=HealthResponse,
        tags=["system"],
        dependencies=[Depends(enforce_https_dependency)],
    )
    def health_check() -> HealthResponse:
        engine = get_engine(settings.voice_engine)
        ffmpeg_ok = is_ffmpeg_available()
        status = "ok" if ffmpeg_ok and engine.info.status != EngineStatus.UNAVAILABLE else "degraded"
        runtime = probe_device_capability(
            requested_device=settings.device,
            max_concurrent_jobs=settings.max_concurrent_jobs,
        )
        details = engine.runtime_details()
        runtime.model_loaded = bool(details.get("model_loaded", False))
        runtime.active_inference_jobs = int(details.get("active_jobs", 0))
        return HealthResponse(
            status=status,
            app_name=settings.app_name,
            version=settings.app_version,
            active_engine=engine.info,
            ffmpeg_available=ffmpeg_ok,
            runtime=runtime,
        )

    @app.get("/api/v1/diagnostics", response_model=DiagnosticsResponse, tags=["system"])
    def diagnostics(owner_id: str = Depends(require_secure_owner)) -> DiagnosticsResponse:
        health = health_check()
        engine = get_engine(settings.voice_engine)
        details = dict(engine.runtime_details())
        details["authenticated_owner_id"] = owner_id
        return DiagnosticsResponse(
            health=health,
            runtime_details=details,
            implemented_stages=[
                "Stage 0: FastAPI contracts, consent gates, FFmpeg audio pipeline, script segmenter, Flutter vault",
                "Stage 1: Bengali zero-shot adapter (IndicF5), reference/output validation, long-text chunking, concurrency lock",
            ],
            experimental_stages=[
                "Stage 1 live GPU benchmark (requires Hugging Face IndicF5 access + CUDA GPU host)",
                "Stage 2: English zero-shot engine (Chatterbox MIT evaluation)",
                "Tier 2: Personal voice fine-tuning dataset studio + resumable Colab checkpoints",
            ],
        )

    @app.get(
        "/api/v1/engines",
        response_model=list[EngineInfo],
        tags=["engines"],
        dependencies=[Depends(enforce_https_dependency)],
    )
    def get_engines() -> list[EngineInfo]:
        return [engine.info for engine in list_engines()]

    @app.get(
        "/api/v1/segment-preview",
        response_model=list[SegmentPreview],
        tags=["text"],
        dependencies=[Depends(enforce_https_dependency)],
    )
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
        _owner_id: str = Depends(require_secure_owner),
    ) -> TranscribeResponse:
        if not consent_confirmed:
            raise HTTPException(
                status_code=403,
                detail="Explicit user consent is required before uploading or processing voice audio.",
            )

        raw_bytes = await read_upload_bounded(
            reference_audio,
            settings.max_reference_audio_bytes,
            label="Reference audio",
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
            except (EngineInputError, AudioProcessingError) as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc
            except EngineInferenceError as exc:
                raise HTTPException(status_code=500, detail=str(exc)) from exc

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
        _owner_id: str = Depends(require_secure_owner),
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
        segments = segment_for_synthesis(
            cleaned_text,
            mode=language_mode.value,
            base_pause_ms=max(0, base_pause),
            max_chunk_chars=settings.max_chunk_chars,
        )
        if not segments:
            raise HTTPException(status_code=400, detail="No speakable characters found in text.")

        raw_bytes = b""
        suffix = ".wav"
        if reference_audio is not None:
            raw_bytes = await read_upload_bounded(
                reference_audio,
                settings.max_reference_audio_bytes,
                label="Reference audio",
            )
            suffix = Path(reference_audio.filename or "sample.wav").suffix or ".wav"

        # Ephemeral processing directory guarantees uploaded voice clips are purged after response.
        output_metrics = None
        with tempfile.TemporaryDirectory(prefix="myvoice_syn_") as tmp:
            work_dir = Path(tmp)
            norm_ref: Path | None = None
            try:
                if raw_bytes:
                    raw_path = work_dir / f"upload{suffix}"
                    raw_path.write_bytes(raw_bytes)
                    norm_ref = normalize_reference_audio(raw_path, work_dir / "ref_norm.wav")
                    if not engine.info.is_mock:
                        validate_reference_wav(
                            norm_ref,
                            min_duration_sec=settings.min_reference_duration_sec,
                            max_duration_sec=settings.max_reference_duration_sec,
                        )

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
                    normalize_loudness=not engine.info.is_mock,
                )
                if not engine.info.is_mock:
                    output_metrics = validate_output_wav(stitched_wav)

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
            except (EngineInputError, AudioProcessingError) as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc
            except EngineInferenceError as exc:
                raise HTTPException(status_code=500, detail=str(exc)) from exc

        headers = {
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Voice-Engine": engine.info.id,
            "X-Engine-Is-Mock": str(engine.info.is_mock).lower(),
            "X-Segment-Count": str(len(segments)),
        }
        if output_metrics is not None:
            headers["X-Audio-Duration-Ms"] = str(int(round(output_metrics.duration_sec * 1000)))
            headers["X-Audio-Rms-Dbfs"] = f"{output_metrics.rms_dbfs:.2f}"

        return Response(
            content=audio_bytes,
            media_type=media_type,
            headers=headers,
        )

    @app.post(
        "/api/v1/training/upload",
        response_model=RemoteTrainingUploadResponse,
        tags=["training-privacy"],
    )
    async def upload_training_dataset(
        dataset_zip: UploadFile = File(...),
        consent_confirmed: bool = Form(False),
        dataset_id: str | None = Form(None),
        owner_id: str = Depends(require_secure_owner),
    ) -> RemoteTrainingUploadResponse:
        if not consent_confirmed:
            raise HTTPException(
                status_code=403,
                detail="Explicit user consent is mandatory for every training dataset upload.",
            )

        max_bytes = settings.max_training_dataset_mb * 1024 * 1024
        raw_zip = await read_upload_bounded(
            dataset_zip,
            max_bytes,
            label="Training dataset ZIP",
        )

        cfg = get_settings()
        try:
            private_root = resolve_private_training_dir(cfg.private_training_storage_dir)
            manifest = store_training_dataset_zip(
                private_root,
                raw_zip,
                owner_id=owner_id,
                consent_confirmed=consent_confirmed,
                dataset_id=dataset_id,
                max_entries=cfg.max_training_zip_entries,
                max_uncompressed_bytes=cfg.max_training_dataset_uncompressed_mb * 1024 * 1024,
                max_single_file_bytes=cfg.max_training_file_mb * 1024 * 1024,
            )
        except PrivateStorageConsentError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except PrivateStorageError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

        return RemoteTrainingUploadResponse(**manifest)

    @app.get(
        "/api/v1/training/data",
        response_model=RemoteTrainingSummaryResponse,
        tags=["training-privacy"],
    )
    def get_remote_training_data(
        owner_id: str = Depends(require_secure_owner),
    ) -> RemoteTrainingSummaryResponse:
        cfg = get_settings()
        try:
            private_root = resolve_private_training_dir(cfg.private_training_storage_dir)
            summary = list_remote_training_data(private_root, owner_id=owner_id)
        except PrivateStorageError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        return RemoteTrainingSummaryResponse(**summary)

    @app.delete(
        "/api/v1/training/data",
        response_model=RemoteTrainingDeleteResponse,
        tags=["training-privacy"],
    )
    def purge_remote_training_data(
        owner_id: str = Depends(require_secure_owner),
    ) -> RemoteTrainingDeleteResponse:
        cfg = get_settings()
        try:
            private_root = resolve_private_training_dir(cfg.private_training_storage_dir)
            result = delete_all_remote_training_data(private_root, owner_id=owner_id)
        except PrivateStorageError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        return RemoteTrainingDeleteResponse(**result)

    @app.delete("/api/v1/training/data/{dataset_id}", tags=["training-privacy"])
    def remove_remote_training_dataset(
        dataset_id: str,
        owner_id: str = Depends(require_secure_owner),
    ) -> dict:
        cfg = get_settings()
        try:
            private_root = resolve_private_training_dir(cfg.private_training_storage_dir)
            return delete_remote_dataset(private_root, dataset_id, owner_id=owner_id)
        except PrivateStorageError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    @app.middleware("http")
    async def guard_gradio_transport(request: Request, call_next):
        if request.url.path == "/gradio" or request.url.path.startswith("/gradio/"):
            cfg = get_settings()
            try:
                enforce_https_transport(
                    scheme=request.url.scheme,
                    forwarded_proto=request.headers.get("x-forwarded-proto"),
                    host_header=request.headers.get("host"),
                    url_hostname=request.url.hostname,
                    client_host=request.client.host if request.client else None,
                    settings=cfg,
                )
            except SecurityPolicyError as exc:
                return JSONResponse(status_code=exc.status_code, content={"detail": str(exc)})
            if not has_configured_auth(cfg):
                return JSONResponse(
                    status_code=503,
                    content={
                        "detail": "Gradio UI is disabled because backend authentication is not configured."
                    },
                )
        return await call_next(request)

    if settings.enable_gradio and has_configured_auth(settings):
        import gradio as gr
        from app.gradio_app import build_gradio_blocks

        def _gradio_auth(username: str, password: str) -> bool:
            return verify_gradio_credentials(username, password, settings=get_settings())

        app = gr.mount_gradio_app(
            app,
            build_gradio_blocks(),
            path="/gradio",
            auth=_gradio_auth,
        )

    return app


app = create_app()
