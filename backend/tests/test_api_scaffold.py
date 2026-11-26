"""Integration tests for FastAPI scaffold endpoints (runs in CI when fastapi/httpx are installed)."""

from __future__ import annotations

import io
import os
import sys
import tempfile
import unittest
import wave
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

try:
    from fastapi.testclient import TestClient
    from app.config import get_settings
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
        frames = int(duration_sec * sample_rate)
        wf.writeframes(b"\x10\x00" * frames)
    return buf.getvalue()


@unittest.skipUnless(FASTAPI_AVAILABLE, "fastapi/httpx not installed in local environment")
class ApiScaffoldTests(unittest.TestCase):
    def setUp(self) -> None:
        self._old_env = {
            "VOICE_ENGINE": os.environ.get("VOICE_ENGINE"),
            "MYVOICE_API_TOKEN": os.environ.get("MYVOICE_API_TOKEN"),
            "MYVOICE_OWNER_TOKENS": os.environ.get("MYVOICE_OWNER_TOKENS"),
            "ALLOW_LOCAL_HTTP_DEV": os.environ.get("ALLOW_LOCAL_HTTP_DEV"),
            "PRIVATE_TRAINING_STORAGE_DIR": os.environ.get("PRIVATE_TRAINING_STORAGE_DIR"),
        }
        os.environ["VOICE_ENGINE"] = "mock"
        os.environ["MYVOICE_OWNER_TOKENS"] = "alice:token_alice_test,bob:token_bob_test"
        os.environ["ALLOW_LOCAL_HTTP_DEV"] = "false"
        get_settings.cache_clear()
        self.client = TestClient(create_app(), base_url="https://testserver")
        self.alice_headers = {"Authorization": "Bearer token_alice_test"}
        self.bob_headers = {"Authorization": "Bearer token_bob_test"}

    def tearDown(self) -> None:
        for key, val in self._old_env.items():
            if val is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = val
        get_settings.cache_clear()

    def test_health_diagnostics_and_engines_endpoints(self) -> None:
        resp = self.client.get("/health")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["active_engine"]["id"], "mock")
        self.assertTrue(body["active_engine"]["is_mock"])

        engines_resp = self.client.get("/api/v1/engines")
        self.assertEqual(engines_resp.status_code, 200)
        engine_ids = {item["id"] for item in engines_resp.json()}
        self.assertEqual(engine_ids, {"indicf5", "f5", "chatterbox", "cpu_fallback", "mock"})

        self.assertEqual(self.client.get("/api/v1/diagnostics").status_code, 401)
        diag_resp = self.client.get("/api/v1/diagnostics", headers=self.alice_headers)
        self.assertEqual(diag_resp.status_code, 200)
        diag = diag_resp.json()
        self.assertEqual(diag["runtime_details"]["authenticated_owner_id"], "alice")
        self.assertNotIn("hf_token", str(diag).lower())

    def test_rejects_unauthenticated_and_remote_plain_http_requests(self) -> None:
        wav_bytes = _make_test_wav_bytes()
        unauth = self.client.post(
            "/api/v1/synthesize",
            data={"text": "Hello", "consent_confirmed": "true"},
            files={"reference_audio": ("ref.wav", wav_bytes, "audio/wav")},
        )
        self.assertEqual(unauth.status_code, 401)

        self.assertEqual(self.client.get("/api/v1/training/data").status_code, 401)
        self.assertEqual(self.client.delete("/api/v1/training/data").status_code, 401)

        http_client = TestClient(create_app(), base_url="http://remote.example.com")
        denied_http = http_client.post(
            "/api/v1/synthesize",
            headers={**self.alice_headers, "X-Forwarded-Proto": "https"},
            data={"text": "Hello", "consent_confirmed": "true"},
            files={"reference_audio": ("ref.wav", wav_bytes, "audio/wav")},
        )
        self.assertEqual(denied_http.status_code, 403)

    def test_bounded_upload_rejects_oversized_payload_early(self) -> None:
        import asyncio
        from fastapi import HTTPException
        from app.main import read_upload_bounded

        class _HugeFakeUpload:
            def __init__(self) -> None:
                self.reads = 0
                self.closed = False

            async def read(self, size: int = -1) -> bytes:
                self.reads += 1
                if self.reads > 10:
                    raise AssertionError("Stream was read past early abort threshold")
                return b"X" * min(size if size > 0 else 65536, 65536)

            async def close(self) -> None:
                self.closed = True

        fake = _HugeFakeUpload()
        with self.assertRaises(HTTPException) as exc_ctx:
            asyncio.run(read_upload_bounded(fake, max_bytes=100 * 1024, label="Dataset"))  # type: ignore[arg-type]
        self.assertEqual(exc_ctx.exception.status_code, 413)
        self.assertTrue(fake.closed)
        self.assertEqual(fake.reads, 2)

    def test_gradio_guard_blocks_when_auth_missing(self) -> None:
        old_enable = os.environ.get("ENABLE_GRADIO")
        old_tok = os.environ.get("MYVOICE_API_TOKEN")
        old_owners = os.environ.get("MYVOICE_OWNER_TOKENS")
        try:
            os.environ["ENABLE_GRADIO"] = "true"
            os.environ.pop("MYVOICE_API_TOKEN", None)
            os.environ.pop("MYVOICE_OWNER_TOKENS", None)
            get_settings.cache_clear()
            guard_client = TestClient(create_app(), base_url="https://testserver")
            resp = guard_client.get("/gradio")
            self.assertEqual(resp.status_code, 503)
        finally:
            if old_enable is None:
                os.environ.pop("ENABLE_GRADIO", None)
            else:
                os.environ["ENABLE_GRADIO"] = old_enable
            if old_tok is not None:
                os.environ["MYVOICE_API_TOKEN"] = old_tok
            if old_owners is not None:
                os.environ["MYVOICE_OWNER_TOKENS"] = old_owners
            get_settings.cache_clear()

    def test_synthesize_requires_consent(self) -> None:
        wav_bytes = _make_test_wav_bytes()
        resp = self.client.post(
            "/api/v1/synthesize",
            headers=self.alice_headers,
            data={"text": "Hello world", "consent_confirmed": "false"},
            files={"reference_audio": ("ref.wav", wav_bytes, "audio/wav")},
        )
        self.assertEqual(resp.status_code, 403)

    def test_synthesize_mock_mixed_wav_and_mp3(self) -> None:
        wav_bytes = _make_test_wav_bytes()
        resp_wav = self.client.post(
            "/api/v1/synthesize",
            headers=self.alice_headers,
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
            headers=self.alice_headers,
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

    def test_training_upload_consent_owner_isolation_and_remote_delete(self) -> None:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("metadata.csv", "utt_0001.wav|হ্যালো|bn|neutral\n")
            zf.writestr("wavs/utt_0001.wav", _make_test_wav_bytes())
        zip_bytes = buf.getvalue()

        with tempfile.TemporaryDirectory() as external_dir:
            os.environ["PRIVATE_TRAINING_STORAGE_DIR"] = external_dir
            get_settings.cache_clear()

            denied = self.client.post(
                "/api/v1/training/upload",
                headers=self.alice_headers,
                data={"consent_confirmed": "false"},
                files={"dataset_zip": ("dataset.zip", zip_bytes, "application/zip")},
            )
            self.assertEqual(denied.status_code, 403)

            allowed = self.client.post(
                "/api/v1/training/upload",
                headers=self.alice_headers,
                data={"consent_confirmed": "true", "dataset_id": "alice_ds"},
                files={"dataset_zip": ("dataset.zip", zip_bytes, "application/zip")},
            )
            self.assertEqual(allowed.status_code, 200)
            body = allowed.json()
            self.assertEqual(body["owner_id"], "alice")
            self.assertEqual(body["dataset_id"], "alice_ds")
            self.assertTrue(body["outside_git_repo"])

            # Bob cannot list or delete Alice's dataset
            bob_summary = self.client.get("/api/v1/training/data", headers=self.bob_headers)
            self.assertEqual(bob_summary.status_code, 200)
            self.assertEqual(bob_summary.json()["datasets"], [])

            bob_del = self.client.delete(
                "/api/v1/training/data/alice_ds", headers=self.bob_headers
            )
            self.assertEqual(bob_del.status_code, 200)
            self.assertFalse(bob_del.json()["deleted"])

            alice_summary = self.client.get("/api/v1/training/data", headers=self.alice_headers)
            self.assertEqual(len(alice_summary.json()["datasets"]), 1)

            deleted = self.client.delete("/api/v1/training/data", headers=self.alice_headers)
            self.assertEqual(deleted.status_code, 200)
            self.assertGreaterEqual(deleted.json()["deleted_items"], 1)

            after = self.client.get("/api/v1/training/data", headers=self.alice_headers)
            self.assertEqual(after.json()["datasets"], [])


if __name__ == "__main__":
    unittest.main()
