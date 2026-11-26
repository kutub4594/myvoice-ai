"""Contract tests for registered engines (mock vs placeholder enforcement)."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

try:
    from app.engines.base import EngineNotReadyError, EngineSynthesisInput
    from app.engines.registry import get_engine, list_engines
    from app.schemas import EngineStatus

    PYDANTIC_AVAILABLE = True
except ImportError:
    PYDANTIC_AVAILABLE = False


@unittest.skipUnless(PYDANTIC_AVAILABLE, "pydantic not installed in local environment")
class EngineContractTests(unittest.TestCase):
    def test_mock_engine_is_explicitly_labeled_and_generates_wav(self) -> None:
        engine = get_engine("mock")
        self.assertTrue(engine.info.is_mock)
        self.assertEqual(engine.info.status, EngineStatus.READY)

        with tempfile.TemporaryDirectory() as tmp:
            out_path = Path(tmp) / "mock.wav"
            result = engine.synthesize_segment(
                EngineSynthesisInput(
                    text="আমি বাংলায় বলছি",
                    language="bn",
                    output_wav_path=out_path,
                )
            )
            self.assertTrue(result.exists())
            self.assertTrue(result.read_bytes().startswith(b"RIFF"))

    def test_placeholder_engines_refuse_fake_synthesis(self) -> None:
        for engine_id in ("indicf5", "f5", "chatterbox", "cpu_fallback"):
            engine = get_engine(engine_id)
            self.assertFalse(engine.info.is_mock)
            if engine_id in {"chatterbox", "cpu_fallback"}:
                self.assertEqual(engine.info.status, EngineStatus.PLACEHOLDER)
            with tempfile.TemporaryDirectory() as tmp:
                with self.assertRaises(EngineNotReadyError):
                    engine.synthesize_segment(
                        EngineSynthesisInput(
                            text="Hello",
                            language="en",
                            output_wav_path=Path(tmp) / "out.wav",
                        )
                    )

    def test_registry_lists_all_engines(self) -> None:
        ids = {e.info.id for e in list_engines()}
        self.assertEqual(ids, {"indicf5", "f5", "chatterbox", "cpu_fallback", "mock"})


if __name__ == "__main__":
    unittest.main()
