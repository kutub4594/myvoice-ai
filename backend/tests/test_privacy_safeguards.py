"""Security regression tests for Git privacy scanner, auth/HTTPS policy, isolation, and ZIP bombs."""

from __future__ import annotations

import importlib.util
import io
import json
import os
import stat
import struct
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from check_staged_privacy import find_privacy_violations, inspect_stream_violation  # noqa: E402
from app.services.private_storage import (  # noqa: E402
    PrivateStorageConsentError,
    PrivateStorageError,
    delete_all_remote_training_data,
    delete_remote_dataset,
    list_remote_training_data,
    resolve_private_training_dir,
    store_training_dataset_zip,
)

try:
    from app.config import Settings
    from app.security import (
        SecurityPolicyError,
        authenticate_request_token,
        enforce_https_transport,
        has_configured_auth,
        verify_gradio_credentials,
    )

    SECURITY_MODULES_AVAILABLE = True
except ImportError:
    SECURITY_MODULES_AVAILABLE = False

PYDANTIC_AVAILABLE = importlib.util.find_spec("pydantic") is not None


def _make_sample_dataset_zip(bad_entry: str | None = None, payload: bytes = b"RIFFDATA") -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("metadata.csv", "utt_0001.wav|আমি বাংলায় কথা বলছি|bn|neutral\n")
        zf.writestr("wavs/utt_0001.wav", payload)
        if bad_entry:
            zf.writestr(bad_entry, b"evil")
    return buf.getvalue()


class GitPrivacySafeguardTests(unittest.TestCase):
    def test_blocks_audio_datasets_embeddings_checkpoints_and_secrets(self) -> None:
        forbidden = [
            "voice_sample.wav",
            "nested/clip.mp3",
            "datasets/utt_0001.wav",
            "recordings/take1.m4a",
            "speaker_embeddings/user.npy",
            "checkpoints/step_1000.safetensors",
            "weights/model.pt",
            "exports/myvoice_dataset.zip",
            "generated/out.wav",
            "myvoice_vault/myvoice.db",
            "metadata.csv",
            "backend/.env",
        ]
        violations = find_privacy_violations(forbidden)
        self.assertEqual({path for path, _ in violations}, set(forbidden))

    def test_blocks_disguised_binary_content_and_tokens_via_magic_bytes(self) -> None:
        st_header = json.dumps({"weight": {"dtype": "F16", "shape": [2], "data_offsets": [0, 4]}}).encode()
        disguised_safetensors = struct.pack("<Q", len(st_header)) + st_header + b"\x00\x00\x00\x00"

        samples = {
            "notes.txt": b"RIFF\x24\x00\x00\x00WAVEfmt ",
            "readme_copy.md": b"ID3\x03\x00\x00\x00",
            "blob_a.dat": b"fLaC\x00\x00\x00\x22",
            "blob_b.dat": b"OggS\x00\x02",
            "blob_c.dat": b"\x93NUMPY\x01\x00",
            "blob_d.dat": b"PK\x03\x04\x14\x00",
            "blob_e.dat": b"\x80\x04\x95\x00\x00",
            "blob_f.dat": b"SQLite format 3\x00",
            "blob_g.dat": disguised_safetensors,
            "config_leak.txt": b"TOKEN=" + b"hf_" + b"AbCdEfGhIjKlMnOpQrStUvWxYz",
            "leak.pem.txt": b"-----BEGIN " + b"PRIVATE KEY-----\nAAAA",
            "custom_list.csv": b"clip_01.wav|secret voice line\n",
        }
        violations = find_privacy_violations(
            list(samples.keys()),
            content_loader=lambda rel: samples[rel],
        )
        self.assertEqual({p for p, _ in violations}, set(samples.keys()))

    def test_detects_secrets_past_256kb_and_across_stream_chunk_boundaries(self) -> None:
        # Place secret past 400 KB AND split across two 64 KB chunks
        token = b"hf_" + b"Z9Y8X7W6V5U4T3S2R1Q0P9O8"
        padding = b"x" * (65536 * 6 - 1) + b"\n"  # 393,216 bytes (> 256 KB)
        part1 = padding + token[:8]
        part2 = token[8:] + b"\nend"

        reason = inspect_stream_violation(
            "large_log.txt",
            [part1[i : i + 65536] for i in range(0, len(part1), 65536)] + [part2],
        )
        self.assertIsNotNone(reason)
        self.assertIn("Hugging Face token", reason or "")

    def test_allows_legitimate_source_and_template_files(self) -> None:
        allowed = {
            ".gitignore": b"*.wav\n",
            ".env.example": b"HF_TOKEN=\nMYVOICE_API_TOKEN=change-me\n",
            "backend/app/main.py": b"from fastapi import FastAPI\n",
            "mobile/lib/app.dart": b"class MyVoiceApp {}\n",
        }
        violations = find_privacy_violations(
            list(allowed.keys()),
            content_loader=lambda rel: allowed[rel],
        )
        self.assertEqual(violations, [])


class PrivateExternalStorageAndIsolationTests(unittest.TestCase):
    def test_rejects_storage_dir_inside_git_repository(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fake_repo = Path(tmp) / "repo"
            fake_repo.mkdir()
            inside_path = fake_repo / "private_data"
            with self.assertRaises(PrivateStorageError):
                resolve_private_training_dir(str(inside_path), repo_root=fake_repo)

            outside_path = Path(tmp) / "external_private"
            resolved = resolve_private_training_dir(str(outside_path), repo_root=fake_repo)
            self.assertEqual(resolved, outside_path.resolve())

    def test_requires_explicit_consent_and_blocks_traversal_symlink_and_bad_ext(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fake_repo = Path(tmp) / "repo"
            fake_repo.mkdir()
            private_root = Path(tmp) / "private_external"
            zip_bytes = _make_sample_dataset_zip()

            with self.assertRaises(PrivateStorageConsentError):
                store_training_dataset_zip(
                    private_root,
                    zip_bytes,
                    owner_id="alice",
                    consent_confirmed=False,
                    repo_root=fake_repo,
                )

            bad_zip = _make_sample_dataset_zip(bad_entry="../../escape.wav")
            with self.assertRaises(PrivateStorageError):
                store_training_dataset_zip(
                    private_root,
                    bad_zip,
                    owner_id="alice",
                    consent_confirmed=True,
                    repo_root=fake_repo,
                )

            # Disallowed executable file extension inside dataset ZIP
            exe_zip = _make_sample_dataset_zip(bad_entry="scripts/evil.sh")
            with self.assertRaises(PrivateStorageError):
                store_training_dataset_zip(
                    private_root,
                    exe_zip,
                    owner_id="alice",
                    consent_confirmed=True,
                    repo_root=fake_repo,
                )

            # Symlink entry inside UNIX ZIP must be rejected
            sym_buf = io.BytesIO()
            with zipfile.ZipFile(sym_buf, "w") as zf:
                info = zipfile.ZipInfo("wavs/link.wav")
                info.create_system = 3
                info.external_attr = (stat.S_IFLNK | 0o777) << 16
                zf.writestr(info, "/etc/passwd")
            with self.assertRaises(PrivateStorageError):
                store_training_dataset_zip(
                    private_root,
                    sym_buf.getvalue(),
                    owner_id="alice",
                    consent_confirmed=True,
                    repo_root=fake_repo,
                )

    def test_zip_bomb_entry_and_uncompressed_size_limits(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fake_repo = Path(tmp) / "repo"
            fake_repo.mkdir()
            private_root = Path(tmp) / "private_external"

            # Exceeding max_uncompressed_bytes aborts and cleans up extracted directory
            oversized_zip = _make_sample_dataset_zip(payload=b"A" * 4096)
            with self.assertRaises(PrivateStorageError):
                store_training_dataset_zip(
                    private_root,
                    oversized_zip,
                    owner_id="alice",
                    consent_confirmed=True,
                    dataset_id="bomb_test",
                    repo_root=fake_repo,
                    max_uncompressed_bytes=1024,
                )
            self.assertFalse((private_root / "owners" / "alice" / "datasets" / "bomb_test").exists())

            # Exceeding max_entries limit rejects archive
            many_buf = io.BytesIO()
            with zipfile.ZipFile(many_buf, "w") as zf:
                for i in range(6):
                    zf.writestr(f"wavs/u_{i}.wav", b"RIFF")
            with self.assertRaises(PrivateStorageError):
                store_training_dataset_zip(
                    private_root,
                    many_buf.getvalue(),
                    owner_id="alice",
                    consent_confirmed=True,
                    repo_root=fake_repo,
                    max_entries=3,
                )

    def test_owner_isolation_prevents_cross_user_access_or_deletion(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fake_repo = Path(tmp) / "repo"
            fake_repo.mkdir()
            private_root = Path(tmp) / "private_external"
            zip_bytes = _make_sample_dataset_zip()

            alice_manifest = store_training_dataset_zip(
                private_root,
                zip_bytes,
                owner_id="alice",
                consent_confirmed=True,
                dataset_id="shared_name",
                repo_root=fake_repo,
            )
            bob_manifest = store_training_dataset_zip(
                private_root,
                zip_bytes,
                owner_id="bob",
                consent_confirmed=True,
                dataset_id="shared_name",
                repo_root=fake_repo,
            )
            self.assertEqual(alice_manifest["owner_id"], "alice")
            self.assertEqual(bob_manifest["owner_id"], "bob")

            # Simulate Alice embeddings & checkpoints
            alice_root = private_root / "owners" / "alice"
            (alice_root / "embeddings" / "a.npy").write_bytes(b"EMB")
            (alice_root / "checkpoints" / "a.pt").write_bytes(b"CKPT")

            # Bob deleting everything must NEVER touch Alice's datasets, embeddings, or checkpoints
            bob_purge = delete_all_remote_training_data(
                private_root, owner_id="bob", repo_root=fake_repo
            )
            self.assertGreaterEqual(bob_purge["deleted_items"], 1)

            alice_summary = list_remote_training_data(
                private_root, owner_id="alice", repo_root=fake_repo
            )
            self.assertEqual(len(alice_summary["datasets"]), 1)
            self.assertEqual(alice_summary["categories"]["embeddings"]["file_count"], 1)
            self.assertEqual(alice_summary["categories"]["checkpoints"]["file_count"], 1)

            # Bob cannot delete Alice's specific dataset
            cross_del = delete_remote_dataset(
                private_root, "shared_name", owner_id="bob", repo_root=fake_repo
            )
            self.assertFalse(cross_del["deleted"])
            self.assertEqual(
                len(list_remote_training_data(private_root, owner_id="alice", repo_root=fake_repo)["datasets"]),
                1,
            )

    def test_failed_reupload_with_same_dataset_id_preserves_existing_dataset(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fake_repo = Path(tmp) / "repo"
            fake_repo.mkdir()
            private_root = Path(tmp) / "private_external"

            original = _make_sample_dataset_zip(payload=b"RIFFORIGINAL")
            store_training_dataset_zip(
                private_root,
                original,
                owner_id="alice",
                consent_confirmed=True,
                dataset_id="my_ds",
                repo_root=fake_repo,
            )

            # Attempt failing upload reusing the exact same dataset_id ("my_ds")
            bad_zip = _make_sample_dataset_zip(bad_entry="evil.sh")
            with self.assertRaises(PrivateStorageError):
                store_training_dataset_zip(
                    private_root,
                    bad_zip,
                    owner_id="alice",
                    consent_confirmed=True,
                    dataset_id="my_ds",
                    repo_root=fake_repo,
                )

            ds_root = private_root / "owners" / "alice" / "datasets"
            ds_dir = ds_root / "my_ds"
            self.assertTrue((ds_dir / "wavs" / "utt_0001.wav").exists())
            self.assertEqual((ds_dir / "wavs" / "utt_0001.wav").read_bytes(), b"RIFFORIGINAL")
            self.assertFalse(any(p.name.startswith(".staging_") for p in ds_root.iterdir()))


@unittest.skipUnless(SECURITY_MODULES_AVAILABLE, "app.security unavailable")
class AuthAndHttpsPolicyTests(unittest.TestCase):
    def test_auth_fails_closed_when_unconfigured_and_isolates_owner_tokens(self) -> None:
        unconfigured = Settings(api_auth_token=None, owner_tokens_raw=None)
        with self.assertRaises(SecurityPolicyError) as ctx:
            authenticate_request_token("Bearer anything", None, settings=unconfigured)
        self.assertEqual(ctx.exception.status_code, 503)

        multi = Settings(owner_tokens_raw="alice:secret_a,bob:secret_b")
        with self.assertRaises(SecurityPolicyError) as missing_ctx:
            authenticate_request_token(None, None, settings=multi)
        self.assertEqual(missing_ctx.exception.status_code, 401)

        with self.assertRaises(SecurityPolicyError) as bad_ctx:
            authenticate_request_token("Bearer wrong_token", None, settings=multi)
        self.assertEqual(bad_ctx.exception.status_code, 401)

        self.assertEqual(
            authenticate_request_token("Bearer secret_a", None, settings=multi),
            "alice",
        )
        self.assertEqual(
            authenticate_request_token(None, "secret_b", settings=multi),
            "bob",
        )

    def test_https_enforced_for_remote_and_local_http_requires_explicit_opt_in(self) -> None:
        strict_cfg = Settings(allow_local_http_dev=False)
        enforce_https_transport(
            scheme="https",
            forwarded_proto=None,
            host_header="voice.example.com",
            url_hostname="voice.example.com",
            settings=strict_cfg,
        )
        with self.assertRaises(SecurityPolicyError):
            enforce_https_transport(
                scheme="http",
                forwarded_proto="http",
                host_header="localhost:8000",
                url_hostname="localhost",
                settings=strict_cfg,
            )

        dev_cfg = Settings(allow_local_http_dev=True)
        enforce_https_transport(
            scheme="http",
            forwarded_proto=None,
            host_header="10.0.2.2:8000",
            url_hostname="10.0.2.2",
            settings=dev_cfg,
        )
        with self.assertRaises(SecurityPolicyError):
            enforce_https_transport(
                scheme="http",
                forwarded_proto=None,
                host_header="remote.example.com",
                url_hostname="remote.example.com",
                settings=dev_cfg,
            )

        # Spoofed X-Forwarded-Proto from untrusted public IP MUST be ignored
        proxy_cfg = Settings(allow_local_http_dev=False, trusted_proxy_ips_raw="127.0.0.1,10.0.0.0/8")
        with self.assertRaises(SecurityPolicyError):
            enforce_https_transport(
                scheme="http",
                forwarded_proto="https",
                host_header="voice.example.com",
                url_hostname="voice.example.com",
                client_host="203.0.113.99",
                settings=proxy_cfg,
            )

        # Trusted reverse proxy IP sending X-Forwarded-Proto: https succeeds
        enforce_https_transport(
            scheme="http",
            forwarded_proto="https",
            host_header="voice.example.com",
            url_hostname="voice.example.com",
            client_host="10.1.2.3",
            settings=proxy_cfg,
        )

    def test_gradio_credentials_and_auth_presence(self) -> None:
        self.assertFalse(has_configured_auth(Settings(api_auth_token=None, owner_tokens_raw=None)))
        cfg = Settings(owner_tokens_raw="alice:tok_a", api_auth_token="shared_tok")
        self.assertTrue(has_configured_auth(cfg))
        self.assertTrue(verify_gradio_credentials("alice", "tok_a", settings=cfg))
        self.assertFalse(verify_gradio_credentials("alice", "wrong", settings=cfg))
        self.assertTrue(verify_gradio_credentials("anyone", "shared_tok", settings=cfg))


@unittest.skipUnless(PYDANTIC_AVAILABLE, "pydantic not installed in local environment")
class GradioTempCleanupTests(unittest.TestCase):
    def test_cleanup_gradio_outputs_deletes_expired_temp_files(self) -> None:
        from app import gradio_app

        with tempfile.TemporaryDirectory() as tmp:
            stale = Path(tmp) / "myvoice_out_old.wav"
            stale.write_bytes(b"RIFF")
            old_ts = os.path.getmtime(stale) - 600
            os.utime(stale, (old_ts, old_ts))
            gradio_app._GRADIO_OUTPUT_FILES.append(stale)

            gradio_app._cleanup_gradio_outputs(max_age_seconds=300)
            self.assertFalse(stale.exists())


if __name__ == "__main__":
    unittest.main()
