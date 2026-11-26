"""Integration & contract tests for the AI4Bharat IndicF5 Bengali voice cloning adapter.

Tests run cleanly without downloading multi-GB model weights by stubbing torch/transformers
modules unless RUN_LIVE_INDICF5_TESTS=1 is explicitly set on a GPU host with HF access.
"""

from __future__ import annotations

import contextlib
import importlib.util
import math
import os
import struct
import sys
import tempfile
import types
import unittest
import wave
from pathlib import Path
from unittest.mock import patch

PYDANTIC_AVAILABLE = importlib.util.find_spec("pydantic") is not None


def _write_test_wav(path: Path, duration_sec: float = 2.0, sample_rate: int = 24000, amp: float = 0.25) -> None:
    frames = int(duration_sec * sample_rate)
    samples = [
        int(max(-1.0, min(1.0, amp * math.sin(2.0 * math.pi * 180.0 * (i / sample_rate)))) * 32767.0)
        for i in range(frames)
    ]
    raw = struct.pack(f"<{frames}h", *samples)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(raw)


def _install_fake_ml_modules(model_obj: object):
    """Build lightweight fake torch/transformers/numpy modules for isolated inference testing."""
    fake_torch = types.ModuleType("torch")
    fake_cuda = types.SimpleNamespace(
        is_available=lambda: False,
        get_device_name=lambda idx: "MockCUDA",
        get_device_properties=lambda idx: types.SimpleNamespace(total_memory=16 * 1024**3),
    )
    fake_backends = types.SimpleNamespace(mps=types.SimpleNamespace(is_available=lambda: False))
    fake_torch.cuda = fake_cuda  # type: ignore[attr-defined]
    fake_torch.backends = fake_backends  # type: ignore[attr-defined]

    ctx_calls = {"inference_mode": 0, "no_grad": 0}

    @contextlib.contextmanager
    def _fake_inference_mode():
        ctx_calls["inference_mode"] += 1
        yield

    @contextlib.contextmanager
    def _fake_no_grad():
        ctx_calls["no_grad"] += 1
        yield

    fake_torch._ctx_calls = ctx_calls  # type: ignore[attr-defined]
    fake_torch.inference_mode = _fake_inference_mode  # type: ignore[attr-defined]
    fake_torch.no_grad = _fake_no_grad  # type: ignore[attr-defined]

    class _FakeAutoModel:
        last_args: tuple | None = None
        last_kwargs: dict | None = None

        @classmethod
        def from_pretrained(cls, model_id: str, **kwargs):
            cls.last_args = (model_id,)
            cls.last_kwargs = kwargs
            return model_obj

    fake_transformers = types.ModuleType("transformers")
    fake_transformers.AutoModel = _FakeAutoModel  # type: ignore[attr-defined]

    class _FakeArray:
        def __init__(self, data: list[float]):
            self._data = data
            self.ndim = 1
            self.size = len(data)
            self.shape = (len(data),)
            self.dtype = "float32"

        def astype(self, _dtype):
            return self

        def tobytes(self) -> bytes:
            pcm = [int(max(-1.0, min(1.0, x)) * 32767.0) for x in self._data]
            return struct.pack(f"<{len(pcm)}h", *pcm)

    fake_np = types.ModuleType("numpy")
    fake_np.float32 = "float32"  # type: ignore[attr-defined]
    fake_np.int16 = "int16"  # type: ignore[attr-defined]
    fake_np.asarray = lambda obj: obj if isinstance(obj, _FakeArray) else _FakeArray(list(obj))  # type: ignore[attr-defined]
    fake_np.squeeze = lambda arr: arr  # type: ignore[attr-defined]
    fake_np.max = lambda arr: max(abs(x) for x in arr._data) if arr._data else 0.0  # type: ignore[attr-defined]
    fake_np.abs = lambda arr: arr  # type: ignore[attr-defined]
    fake_np.clip = lambda arr, lo, hi: _FakeArray([max(lo, min(hi, x)) for x in arr._data])  # type: ignore[attr-defined]

    class _ScaledArray(_FakeArray):
        def __mul__(self, factor: float):
            return _FakeArray([x * factor for x in self._data])

    fake_np.clip = lambda arr, lo, hi: _ScaledArray([max(lo, min(hi, x)) for x in arr._data])  # type: ignore[attr-defined]

    fake_sf = types.ModuleType("soundfile")
    fake_sf.write = lambda path, data, samplerate=24000, subtype="PCM_16": _write_test_wav(  # type: ignore[attr-defined]
        Path(path),
        duration_sec=max(0.2, len(data._data) / float(samplerate)),
        sample_rate=samplerate,
        amp=0.25,
    )

    return {
        "torch": fake_torch,
        "transformers": fake_transformers,
        "numpy": fake_np,
        "soundfile": fake_sf,
    }


@unittest.skipUnless(PYDANTIC_AVAILABLE, "pydantic not installed in local environment")
class IndicF5EngineTests(unittest.TestCase):
    def test_probe_device_capability_defaults_cpu_without_torch(self) -> None:
        from app.engines.indicf5_engine import probe_device_capability

        with patch("importlib.util.find_spec", return_value=None):
            cap = probe_device_capability(requested_device="auto", max_concurrent_jobs=2)
        self.assertEqual(cap.selected_device, "cpu")
        self.assertFalse(cap.torch_installed)
        self.assertFalse(cap.cuda_available)
        self.assertEqual(cap.max_concurrent_jobs, 2)

    def test_engine_raises_not_ready_when_ml_deps_missing(self) -> None:
        from app.config import Settings
        from app.engines.base import EngineNotReadyError, EngineSynthesisInput
        from app.engines.indicf5_engine import IndicF5BengaliEngine
        from app.schemas import EngineStatus

        settings = Settings(voice_engine="indicf5", hf_token=None)
        engine = IndicF5BengaliEngine(settings=settings)
        with patch("importlib.util.find_spec", return_value=None):
            info = engine.info
            self.assertEqual(info.id, "indicf5")
            self.assertEqual(info.status, EngineStatus.UNAVAILABLE)
            self.assertTrue(info.supports_bengali)
            self.assertFalse(info.supports_english)

            with tempfile.TemporaryDirectory() as tmp:
                ref_wav = Path(tmp) / "ref.wav"
                _write_test_wav(ref_wav, duration_sec=2.0)
                with self.assertRaises(EngineNotReadyError):
                    engine.synthesize_segment(
                        EngineSynthesisInput(
                            text="আমার সোনার বাংলা",
                            language="bn",
                            reference_wav_path=ref_wav,
                            reference_text="এটি একটি বাংলা রেফারেন্স বাক্য।",
                            output_wav_path=Path(tmp) / "out.wav",
                        )
                    )

    def test_requires_transcript_and_rejects_english_or_short_audio(self) -> None:
        from app.config import Settings
        from app.engines.base import EngineInputError, EngineNotReadyError, EngineSynthesisInput
        from app.engines.indicf5_engine import IndicF5BengaliEngine

        engine = IndicF5BengaliEngine(settings=Settings(voice_engine="indicf5"))
        with tempfile.TemporaryDirectory() as tmp:
            ref_wav = Path(tmp) / "ref.wav"
            _write_test_wav(ref_wav, duration_sec=2.5)
            out_wav = Path(tmp) / "out.wav"

            # English segment is explicitly rejected (Stage 2 scope).
            with self.assertRaises(EngineNotReadyError):
                engine.synthesize_segment(
                    EngineSynthesisInput(
                        text="Hello world",
                        language="en",
                        reference_wav_path=ref_wav,
                        reference_text="Hello world",
                        output_wav_path=out_wav,
                    )
                )

            # Missing reference_text raises EngineInputError (not silent mock audio).
            with self.assertRaises(EngineInputError):
                engine.synthesize_segment(
                    EngineSynthesisInput(
                        text="বাংলা পরীক্ষা",
                        language="bn",
                        reference_wav_path=ref_wav,
                        reference_text=None,
                        output_wav_path=out_wav,
                    )
                )

            # Too-short reference audio raises EngineInputError.
            short_wav = Path(tmp) / "short.wav"
            _write_test_wav(short_wav, duration_sec=0.4)
            with self.assertRaises(EngineInputError):
                engine.synthesize_segment(
                    EngineSynthesisInput(
                        text="বাংলা পরীক্ষা",
                        language="bn",
                        reference_wav_path=short_wav,
                        reference_text="বাংলা",
                        output_wav_path=out_wav,
                    )
                )

    def test_mocked_indicf5_inference_writes_valid_wav_and_resets_active_jobs(self) -> None:
        from app.config import Settings
        from app.engines.base import EngineSynthesisInput
        from app.engines.indicf5_engine import IndicF5BengaliEngine

        calls: list[dict] = []

        class _FakeIndicF5Model:
            def to(self, device: str):
                calls.append({"to_device": device})
                return self

            def __call__(self, text: str, ref_audio_path: str, ref_text: str):
                calls.append({"text": text, "ref_audio_path": ref_audio_path, "ref_text": ref_text})
                # Return 1.2s of non-silent audio at 24 kHz
                return [0.2 * math.sin(2.0 * math.pi * 220.0 * (i / 24000.0)) for i in range(28800)]

        fake_mods = _install_fake_ml_modules(_FakeIndicF5Model())
        settings = Settings(voice_engine="indicf5", device="cpu", hf_token="hf_test_secret_token")
        engine = IndicF5BengaliEngine(settings=settings)

        with patch.dict(sys.modules, fake_mods), patch("importlib.util.find_spec", return_value=object()):
            with tempfile.TemporaryDirectory() as tmp:
                ref_wav = Path(tmp) / "ref.wav"
                out_wav = Path(tmp) / "out.wav"
                _write_test_wav(ref_wav, duration_sec=3.0)

                result_path = engine.synthesize_segment(
                    EngineSynthesisInput(
                        text="কেমন আছেন সবাই? আজ আবহাওয়া খুব সুন্দর।",
                        language="bn",
                        reference_wav_path=ref_wav,
                        reference_text="আমি বাংলায় কথা বলছি।",
                        output_wav_path=out_wav,
                    )
                )

                self.assertTrue(result_path.exists())
                self.assertTrue(result_path.read_bytes().startswith(b"RIFF"))
                self.assertEqual(calls[0]["to_device"], "cpu")
                self.assertEqual(calls[1]["ref_text"], "আমি বাংলায় কথা বলছি।")
                self.assertEqual(fake_mods["torch"]._ctx_calls["inference_mode"], 1)  # type: ignore[attr-defined]
                self.assertEqual(fake_mods["torch"]._ctx_calls["no_grad"], 0)  # type: ignore[attr-defined]
                # Never expose actual secret token in runtime_details
                details = engine.runtime_details()
                self.assertTrue(details["hf_token_configured"])
                self.assertNotIn("hf_test_secret_token", str(details))
                self.assertEqual(details["device"]["active_inference_jobs"], 0)

    def test_falls_back_to_no_grad_when_torch_lacks_inference_mode(self) -> None:
        from app.config import Settings
        from app.engines.base import EngineSynthesisInput
        from app.engines.indicf5_engine import IndicF5BengaliEngine

        class _FakeIndicF5Model:
            def to(self, _device: str):
                return self

            def __call__(self, text: str, ref_audio_path: str, ref_text: str):
                return [0.2 * math.sin(2.0 * math.pi * 220.0 * (i / 24000.0)) for i in range(28800)]

        fake_mods = _install_fake_ml_modules(_FakeIndicF5Model())
        delattr(fake_mods["torch"], "inference_mode")
        engine = IndicF5BengaliEngine(settings=Settings(voice_engine="indicf5", device="cpu"))

        with patch.dict(sys.modules, fake_mods), patch("importlib.util.find_spec", return_value=object()):
            with tempfile.TemporaryDirectory() as tmp:
                ref_wav = Path(tmp) / "ref.wav"
                out_wav = Path(tmp) / "out.wav"
                _write_test_wav(ref_wav, duration_sec=2.5)

                result_path = engine.synthesize_segment(
                    EngineSynthesisInput(
                        text="বাংলা বাক্য",
                        language="bn",
                        reference_wav_path=ref_wav,
                        reference_text="বাংলা রেফারেন্স",
                        output_wav_path=out_wav,
                    )
                )
                self.assertTrue(result_path.exists())
                self.assertEqual(fake_mods["torch"]._ctx_calls["no_grad"], 1)  # type: ignore[attr-defined]
                self.assertEqual(engine.runtime_details()["device"]["active_inference_jobs"], 0)

    def test_rejects_torch_without_inference_protection(self) -> None:
        from app.config import Settings
        from app.engines.base import EngineInferenceError, EngineSynthesisInput
        from app.engines.indicf5_engine import IndicF5BengaliEngine

        class _FakeIndicF5Model:
            def to(self, _device: str):
                return self

            def __call__(self, text: str, ref_audio_path: str, ref_text: str):
                raise AssertionError("Model must not be called without inference protection")

        fake_mods = _install_fake_ml_modules(_FakeIndicF5Model())
        delattr(fake_mods["torch"], "inference_mode")
        delattr(fake_mods["torch"], "no_grad")
        engine = IndicF5BengaliEngine(settings=Settings(voice_engine="indicf5", device="cpu"))

        with patch.dict(sys.modules, fake_mods), patch("importlib.util.find_spec", return_value=object()):
            with tempfile.TemporaryDirectory() as tmp:
                ref_wav = Path(tmp) / "ref.wav"
                out_wav = Path(tmp) / "out.wav"
                _write_test_wav(ref_wav, duration_sec=2.5)

                with self.assertRaises(EngineInferenceError):
                    engine.synthesize_segment(
                        EngineSynthesisInput(
                            text="বাংলা বাক্য",
                            language="bn",
                            reference_wav_path=ref_wav,
                            reference_text="বাংলা রেফারেন্স",
                            output_wav_path=out_wav,
                        )
                    )
                self.assertFalse(out_wav.exists())
                self.assertEqual(engine.runtime_details()["device"]["active_inference_jobs"], 0)

    def test_inference_failure_raises_error_without_mock_fallback(self) -> None:
        from app.config import Settings
        from app.engines.base import EngineInferenceError, EngineSynthesisInput
        from app.engines.indicf5_engine import IndicF5BengaliEngine

        class _FailingIndicF5Model:
            def to(self, _device: str):
                return self

            def __call__(self, text: str, ref_audio_path: str, ref_text: str):
                raise RuntimeError("CUDA out of memory")

        fake_mods = _install_fake_ml_modules(_FailingIndicF5Model())
        engine = IndicF5BengaliEngine(settings=Settings(voice_engine="indicf5", device="cpu"))

        with patch.dict(sys.modules, fake_mods), patch("importlib.util.find_spec", return_value=object()):
            with tempfile.TemporaryDirectory() as tmp:
                ref_wav = Path(tmp) / "ref.wav"
                out_wav = Path(tmp) / "out.wav"
                _write_test_wav(ref_wav, duration_sec=2.5)

                with self.assertRaises(EngineInferenceError):
                    engine.synthesize_segment(
                        EngineSynthesisInput(
                            text="পরীক্ষামূলক বাক্য।",
                            language="bn",
                            reference_wav_path=ref_wav,
                            reference_text="পরীক্ষামূলক রেফারেন্স।",
                            output_wav_path=out_wav,
                        )
                    )
                self.assertFalse(out_wav.exists())
                self.assertEqual(engine.runtime_details()["device"]["active_inference_jobs"], 0)

    @unittest.skipUnless(
        os.environ.get("RUN_LIVE_INDICF5_TESTS") == "1",
        "Set RUN_LIVE_INDICF5_TESTS=1 on a GPU host with IndicF5 weights & HF_TOKEN to run live inference",
    )
    def test_live_indicf5_bengali_cloning(self) -> None:
        from app.config import Settings
        from app.engines.base import EngineSynthesisInput
        from app.engines.indicf5_engine import IndicF5BengaliEngine

        ref_path = Path(os.environ.get("INDICF5_TEST_REF_WAV", ""))
        ref_text = os.environ.get("INDICF5_TEST_REF_TEXT", "").strip()
        if not ref_path.exists() or not ref_text:
            self.skipTest("Provide INDICF5_TEST_REF_WAV and INDICF5_TEST_REF_TEXT for live IndicF5 test.")

        engine = IndicF5BengaliEngine(settings=Settings(voice_engine="indicf5"))
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "live_bn.wav"
            engine.synthesize_segment(
                EngineSynthesisInput(
                    text="নমস্কার, এটি আমার বাংলা কণ্ঠস্বর ক্লোনিংয়ের একটি পরীক্ষামূলক অডিও।",
                    language="bn",
                    reference_wav_path=ref_path,
                    reference_text=ref_text,
                    output_wav_path=out,
                )
            )
            self.assertTrue(out.exists())
            self.assertGreater(out.stat().st_size, 10000)


if __name__ == "__main__":
    unittest.main()
