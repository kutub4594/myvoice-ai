"""Integration tests for FastAPI scaffold endpoints (runs in CI when fastapi/httpx are installed)."""

from __future__ import annotations

import io
import os
import sys
import unittest
import wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

try:
    from fastapi.testclient import TestClient
    from app.main import create_app

    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False


def _make_test_wav_bytes(duration_sec: float = 0.5, sample_rate: int = 16000) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(b"\x10\x00" * int(sample_rate * duration_sec))
    return buf.getvalue()


@unittest.skipUnless(FASTAPI_AVAILABLE, "fastapi/httpx not installed in local environment")
class ApiScaffoldTests(unittest.TestCase):
    def setUp(self) -> None:
        os.environ["VOICE_ENGINE"] = "mock"
        self.client = TestClient(create_app())

    def test_health_and_engines_endpoints(self) -> None:
        resp = self.client.get("/health")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["active_engine"]["id"], "mock")
        self.assertTrue(body["active_engine"]["is_mock"])

        engines_resp = self.client.get("/api/v1/engines")
        self.assertEqual(engines_resp.status_code, 200)
        engine_ids = {item["id"] for item in engines_resp.json()}
        self.assertEqual(engine_ids, {"f5", "chatterbox", "cpu_fallback", "mock"})

    def test_synthesize_requires_consent(self) -> None:
        wav_bytes = _make_test_wav_bytes()
        resp = self.client.post(
            "/api/v1/synthesize",
            data={"text": "Hello world", "consent_confirmed": "false"},
            files={"reference_audio": ("ref.wav", wav_bytes, "audio/wav")},
        )
        self.assertEqual(resp.status_code, 403)

    def test_synthesize_mock_mixed_wav_and_mp3(self) -> None:
        wav_bytes = _make_test_wav_bytes()
        resp_wav = self.client.post(
            "/api/v1/synthesize",
            data={
                "text": "হ্যালো, welcome to MyVoice AI!",
                "language_mode": "auto",
                "output_format": "wav",
                "consent_confirmed": "true",
            },
            files={"reference_audio": ("ref.wav", wav_bytes, "audio/wav")},
        )
        self.assertEqual(resp_wav.status_code, 200)
        self.assertEqual(resp_wav.headers.get("x-voice-engine"), "mock")
        self.assertTrue(resp_wav.content.startswith(b"RIFF"))

        resp_mp3 = self.client.post(
            "/api/v1/synthesize",
            data={
                "text": "Testing MP3 export.",
                "language_mode": "en",
                "output_format": "mp3",
                "consent_confirmed": "true",
            },
            files={"reference_audio": ("ref.wav", wav_bytes, "audio/wav")},
        )
        self.assertEqual(resp_mp3.status_code, 200)
        self.assertGreater(len(resp_mp3.content), 100)


if __name__ == "__main__":
    unittest.main()
