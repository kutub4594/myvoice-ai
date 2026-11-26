"""Real Bengali Zero-Shot Voice Cloning Engine powered by AI4Bharat IndicF5.

Model verification notes:
- Repository: ai4bharat/IndicF5 (Hugging Face gated model; MIT License).
- Languages: 11 Indic languages including Bengali (no native English support).
- Zero-shot inputs: Requires a clean reference audio clip AND its accurate transcript.
- No multi-GB model weights are bundled in the repo or downloaded at import time; the
  model is loaded lazily on first real synthesis/load request on a GPU/CPU host.
"""

from __future__ import annotations

import importlib.util
import struct
import threading
import wave
from pathlib import Path
from typing import Any

from app.config import Settings, get_settings
from app.engines.base import (
    BaseVoiceCloningEngine,
    EngineInferenceError,
    EngineInputError,
    EngineNotReadyError,
    EngineSynthesisInput,
)
from app.schemas import DeviceCapabilityInfo, EngineInfo, EngineStatus, ProfileType
from app.services.audio_processor import (
    AudioProcessingError,
    adjust_wav_speed,
    validate_output_wav,
    validate_reference_wav,
)


def probe_device_capability(
    requested_device: str = "auto",
    model_loaded: bool = False,
    active_jobs: int = 0,
    max_concurrent_jobs: int = 1,
) -> DeviceCapabilityInfo:
    """Inspect installed ML runtime and GPU/CPU hardware without exposing secrets."""
    torch_installed = importlib.util.find_spec("torch") is not None
    transformers_installed = importlib.util.find_spec("transformers") is not None
    cuda_available = False
    mps_available = False
    gpu_name: str | None = None
    gpu_vram_mb: int | None = None

    if torch_installed:
        import torch  # type: ignore

        cuda_available = bool(torch.cuda.is_available())
        mps_backend = getattr(torch.backends, "mps", None)
        mps_available = bool(mps_backend is not None and mps_backend.is_available())
        if cuda_available:
            gpu_name = torch.cuda.get_device_name(0)
            props = torch.cuda.get_device_properties(0)
            gpu_vram_mb = int(props.total_memory // (1024 * 1024))

    req = requested_device.strip().lower()
    if req in {"cuda", "cpu", "mps"}:
        selected = req
    elif cuda_available:
        selected = "cuda"
    elif mps_available:
        selected = "mps"
    else:
        selected = "cpu"

    return DeviceCapabilityInfo(
        selected_device=selected,
        torch_installed=torch_installed,
        transformers_installed=transformers_installed,
        cuda_available=cuda_available,
        mps_available=mps_available,
        gpu_name=gpu_name,
        gpu_vram_mb=gpu_vram_mb,
        model_loaded=model_loaded,
        active_inference_jobs=active_jobs,
        max_concurrent_jobs=max_concurrent_jobs,
    )


class IndicF5BengaliEngine(BaseVoiceCloningEngine):
    """Production-structured Bengali zero-shot adapter for ai4bharat/IndicF5."""

    SAMPLE_RATE = 24000

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._model: Any = None
        self._whisper_model: Any = None
        self._load_lock = threading.Lock()
        self._infer_semaphore = threading.BoundedSemaphore(
            max(1, self._settings.max_concurrent_jobs)
        )
        self._active_jobs_lock = threading.Lock()
        self._active_jobs = 0

    def _dependencies_present(self) -> tuple[bool, list[str]]:
        required = ("torch", "transformers", "numpy", "soundfile")
        missing = [pkg for pkg in required if importlib.util.find_spec(pkg) is None]
        return (len(missing) == 0, missing)

    def _capability(self) -> DeviceCapabilityInfo:
        with self._active_jobs_lock:
            active = self._active_jobs
        return probe_device_capability(
            requested_device=self._settings.device,
            model_loaded=self._model is not None,
            active_jobs=active,
            max_concurrent_jobs=self._settings.max_concurrent_jobs,
        )

    @property
    def info(self) -> EngineInfo:
        deps_ok, missing = self._dependencies_present()
        status = EngineStatus.READY if deps_ok else EngineStatus.UNAVAILABLE
        note = (
            "Real Bengali zero-shot cloning via ai4bharat/IndicF5. Requires reference audio + "
            "accurate Bengali transcript. No English support."
        )
        if not deps_ok:
            note += f" Missing ML packages in this environment: {', '.join(missing)}."

        return EngineInfo(
            id="indicf5",
            name="IndicF5 (Bengali Zero-Shot)",
            status=status,
            is_mock=False,
            supports_bengali=True,
            supports_english=False,
            supports_style_controls=False,
            supports_trained_checkpoints=False,
            requires_gpu=True,
            models=[self._settings.indicf5_model_id, "faster-whisper (optional)"],
            licenses=[
                "ai4bharat/IndicF5: MIT (gated HF repo; requires user-accepted terms + HF_TOKEN)",
                "faster-whisper: MIT",
            ],
            notes=note,
        )

    def runtime_details(self) -> dict[str, Any]:
        cap = self._capability()
        deps_ok, missing = self._dependencies_present()
        return {
            "engine_id": "indicf5",
            "model_id": self._settings.indicf5_model_id,
            "dependencies_installed": deps_ok,
            "missing_dependencies": missing,
            "hf_token_configured": self._settings.hf_token is not None,
            "auto_transcribe_enabled": self._settings.enable_auto_transcribe,
            "device": cap.model_dump(),
        }

    def _ensure_model_loaded(self) -> tuple[Any, str]:
        deps_ok, missing = self._dependencies_present()
        if not deps_ok:
            raise EngineNotReadyError(
                f"IndicF5 ML dependencies are not installed ({', '.join(missing)}). "
                "Install backend/requirements-ml.txt on a GPU/CPU Python 3.10-3.12 host."
            )

        cap = self._capability()
        device = cap.selected_device

        with self._load_lock:
            if self._model is not None:
                return self._model, device

            from transformers import AutoModel  # type: ignore

            kwargs: dict[str, Any] = {"trust_remote_code": True}
            if self._settings.hf_token:
                kwargs["token"] = self._settings.hf_token
            if self._settings.model_cache_dir:
                kwargs["cache_dir"] = self._settings.model_cache_dir

            try:
                loaded = AutoModel.from_pretrained(self._settings.indicf5_model_id, **kwargs)
                self._model = loaded.to(device)
            except Exception as exc:
                raise EngineInferenceError(
                    f"Failed to load '{self._settings.indicf5_model_id}' on {device}. "
                    "Verify Hugging Face gated access terms and HF_TOKEN."
                ) from exc

            return self._model, device

    def transcribe_reference(self, reference_wav_path: Path, language_hint: str | None = None) -> str:
        if importlib.util.find_spec("faster_whisper") is None:
            raise EngineNotReadyError(
                "Automatic reference transcription requires 'faster-whisper'. "
                "Provide reference_text directly or install faster-whisper."
            )
        if not reference_wav_path.exists():
            raise EngineInputError("Reference audio file does not exist for transcription.")

        from faster_whisper import WhisperModel  # type: ignore

        cap = self._capability()
        whisper_device = "cuda" if cap.selected_device == "cuda" else "cpu"
        compute_type = "float16" if whisper_device == "cuda" else "int8"

        with self._load_lock:
            if self._whisper_model is None:
                self._whisper_model = WhisperModel(
                    self._settings.whisper_model_size,
                    device=whisper_device,
                    compute_type=compute_type,
                )

        lang_arg = "bn" if language_hint in {None, "", "auto", "bn"} else language_hint
        segments, _ = self._whisper_model.transcribe(str(reference_wav_path), language=lang_arg)
        transcript = " ".join(seg.text.strip() for seg in segments if seg.text.strip()).strip()
        if not transcript:
            raise EngineInputError(
                "Auto-transcription produced an empty transcript. Enter reference_text manually."
            )
        return transcript

    def _resolve_reference_text(self, request: EngineSynthesisInput) -> str:
        provided = (request.reference_text or "").strip()
        if provided:
            return provided
        if self._settings.enable_auto_transcribe and request.reference_wav_path is not None:
            return self.transcribe_reference(request.reference_wav_path, language_hint="bn")
        raise EngineInputError(
            "IndicF5 requires an accurate Bengali transcript of the reference audio (reference_text). "
            "Provide reference_text or enable ENABLE_AUTO_TRANSCRIBE=true with faster-whisper."
        )

    @staticmethod
    def _write_array_to_wav(audio: Any, out_path: Path, sample_rate: int = 24000) -> None:
        if hasattr(audio, "detach"):
            audio = audio.detach().cpu().numpy()

        import numpy as np  # type: ignore

        arr = np.asarray(audio)
        arr = np.squeeze(arr)
        if arr.ndim != 1 or arr.size == 0:
            raise EngineInferenceError(f"IndicF5 returned invalid audio array shape: {arr.shape}")

        if arr.dtype == np.int16:
            float_arr = arr.astype(np.float32) / 32768.0
        else:
            float_arr = arr.astype(np.float32)
            peak = float(np.max(np.abs(float_arr))) if float_arr.size else 0.0
            if peak > 1.0:
                float_arr = float_arr / peak

        if importlib.util.find_spec("soundfile") is not None:
            import soundfile as sf  # type: ignore

            sf.write(str(out_path), float_arr, samplerate=sample_rate, subtype="PCM_16")
            return

        # Standard-library PCM fallback if soundfile is unavailable in a test environment.
        pcm = (np.clip(float_arr, -1.0, 1.0) * 32767.0).astype("<i2")
        with wave.open(str(out_path), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            wf.writeframes(pcm.tobytes())

    def synthesize_segment(self, request: EngineSynthesisInput) -> Path:
        if request.language != "bn":
            raise EngineNotReadyError(
                f"IndicF5BengaliEngine supports Bengali ('bn') only; received '{request.language}'. "
                "English and mixed routing will be enabled in Stage 2."
            )
        if request.profile_type != ProfileType.ZERO_SHOT:
            raise EngineNotReadyError(
                "Trained personal checkpoint loading for IndicF5 is part of Tier 2 fine-tuning, "
                "not zero-shot inference. Use profile_type='zero_shot' for instant cloning."
            )
        if request.reference_wav_path is None:
            raise EngineInputError("reference_wav_path is required for IndicF5 zero-shot cloning.")

        try:
            validate_reference_wav(
                request.reference_wav_path,
                min_duration_sec=self._settings.min_reference_duration_sec,
                max_duration_sec=self._settings.max_reference_duration_sec,
            )
        except AudioProcessingError as exc:
            raise EngineInputError(str(exc)) from exc

        ref_text = self._resolve_reference_text(request)
        model, _ = self._ensure_model_loaded()

        self._infer_semaphore.acquire()
        try:
            with self._active_jobs_lock:
                self._active_jobs += 1

            try:
                import torch  # type: ignore

                ctx = torch.inference_mode()
            except ImportError:
                from contextlib import nullcontext

                ctx = nullcontext()

            try:
                with ctx:
                    audio = model(
                        request.text,
                        ref_audio_path=str(request.reference_wav_path),
                        ref_text=ref_text,
                    )
            except Exception as exc:
                raise EngineInferenceError(f"IndicF5 synthesis failed: {exc}") from exc

            raw_out = request.output_wav_path.with_name(f"{request.output_wav_path.stem}_raw.wav")
            self._write_array_to_wav(audio, raw_out, sample_rate=self.SAMPLE_RATE)

            try:
                if abs(request.speed - 1.0) >= 0.01:
                    adjust_wav_speed(raw_out, request.output_wav_path, speed=request.speed)
                    raw_out.unlink(missing_ok=True)
                else:
                    raw_out.replace(request.output_wav_path)
                validate_output_wav(request.output_wav_path)
            except AudioProcessingError as exc:
                raise EngineInferenceError(f"IndicF5 produced unusable audio: {exc}") from exc
        finally:
            with self._active_jobs_lock:
                self._active_jobs = max(0, self._active_jobs - 1)
            self._infer_semaphore.release()

        return request.output_wav_path
