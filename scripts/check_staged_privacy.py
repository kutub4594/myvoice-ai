#!/usr/bin/env python3
"""Git privacy safeguard: reject staged/tracked voice data, datasets, embeddings, checkpoints & secrets.

Inspects BOTH file paths/extensions AND complete file contents via bounded streaming chunks
(64 KB chunks with 256-byte overlap) so secrets past 256 KB or straddling boundaries cannot evade detection.

Usage:
    python3 scripts/check_staged_privacy.py --staged   # pre-commit check on Git staged index blobs
    python3 scripts/check_staged_privacy.py --tracked  # CI / audit check on all tracked files
"""

from __future__ import annotations

import argparse
import json
import re
import struct
import subprocess
import sys
from collections.abc import Callable, Iterable
from pathlib import Path

FORBIDDEN_EXTENSIONS = frozenset(
    {
        # Audio formats
        ".wav",
        ".mp3",
        ".m4a",
        ".ogg",
        ".flac",
        ".aac",
        ".opus",
        ".wma",
        ".amr",
        ".3gp",
        ".webm",
        ".aiff",
        # Dataset archives
        ".zip",
        ".tar",
        ".tgz",
        ".gz",
        ".7z",
        ".rar",
        # Embeddings & numeric caches
        ".npy",
        ".npz",
        ".pkl",
        ".pickle",
        ".h5",
        ".hdf5",
        # Model checkpoints & weights
        ".pt",
        ".pth",
        ".ckpt",
        ".safetensors",
        ".bin",
        ".onnx",
        # Local SQLite vaults & private keys
        ".db",
        ".sqlite",
        ".sqlite3",
        ".pem",
        ".key",
        ".jks",
        ".keystore",
    }
)

FORBIDDEN_DIR_SEGMENTS = frozenset(
    {
        "datasets",
        "recordings",
        "voice_samples",
        "myvoice_vault",
        "speaker_embeddings",
        "embeddings",
        "generated",
        "generated_audio",
        "benchmark_outputs",
        "training_data",
        "training_jobs",
        "speaker_profiles",
        "checkpoints",
        "weights",
        "hf_cache",
        "huggingface_cache",
    }
)

FORBIDDEN_FILENAMES = frozenset(
    {
        "metadata.csv",
        "myvoice.db",
        "job_state.json",
    }
)

_STREAM_CHUNK_BYTES = 64 * 1024
_OVERLAP_BYTES = 256
_MEDIA_FTYP_BRANDS = (b"M4A ", b"M4B ", b"M4P ", b"mp42", b"isom", b"3gp4", b"3gp5", b"qt  ")
_HF_TOKEN_RE = re.compile(rb"\bhf_[A-Za-z0-9]{20,}\b")
_PRIVATE_KEY_RE = re.compile(rb"-----BEGIN (?:RSA |EC |DSA |OPENSSH |ENCRYPTED )?PRIVATE KEY-----")
_MANIFEST_AUDIO_LINE_RE = re.compile(rb"\.(?:wav|mp3|m4a|flac|ogg|aac)\s*\|", re.IGNORECASE)


def find_path_violation(raw_path: str) -> str | None:
    """Return violation reason if raw_path matches forbidden dirs, names, or extensions."""
    norm = raw_path.replace("\\", "/").strip()
    if not norm:
        return None

    p = Path(norm)
    parts_lower = [part.lower() for part in p.parts]
    name_lower = p.name.lower()

    if name_lower == ".env" or (name_lower.startswith(".env.") and name_lower != ".env.example"):
        return "Environment secret file (.env) must never be committed."

    if name_lower in FORBIDDEN_FILENAMES:
        return f"Private dataset/training manifest '{p.name}' must stay outside Git."

    matched_dir = next((seg for seg in parts_lower[:-1] if seg in FORBIDDEN_DIR_SEGMENTS), None)
    if matched_dir:
        return f"Files inside '{matched_dir}/' belong in private external storage, not Git."

    suffixes_lower = [s.lower() for s in p.suffixes]
    bad_ext = next((s for s in suffixes_lower if s in FORBIDDEN_EXTENSIONS), None)
    if bad_ext:
        return f"Forbidden audio, archive, embedding, database, or model file extension '{bad_ext}'."

    return None


def _looks_like_safetensors(data: bytes) -> bool:
    if len(data) < 16:
        return False
    header_len = struct.unpack("<Q", data[:8])[0]
    if not (2 <= header_len <= 10 * 1024 * 1024) or len(data) < 8 + min(header_len, 256):
        return False
    sample = data[8 : 8 + min(header_len, 4096)]
    if not sample.lstrip().startswith(b"{"):
        return False
    if header_len <= 4096:
        try:
            obj = json.loads(sample.decode("utf-8"))
            if isinstance(obj, dict) and (
                "__metadata__" in obj
                or any(
                    isinstance(v, dict) and "dtype" in v and "shape" in v and "data_offsets" in v
                    for v in obj.values()
                )
            ):
                return True
        except Exception:
            return False
    return b'"dtype"' in sample and b'"data_offsets"' in sample


def _inspect_header_magic(head: bytes) -> str | None:
    if not head:
        return None

    if len(head) >= 12 and head[:4] == b"RIFF" and head[8:12] == b"WAVE":
        return "Disguised RIFF/WAVE audio file detected via magic bytes."
    if head.startswith(b"ID3") or (
        len(head) >= 3 and head[:2] in {b"\xff\xfb", b"\xff\xf3", b"\xff\xf2"}
    ):
        return "Disguised MP3 audio stream detected via header bytes."
    if head.startswith(b"fLaC"):
        return "Disguised FLAC audio file detected via magic bytes."
    if head.startswith(b"OggS"):
        return "Disguised Ogg/Opus audio file detected via magic bytes."
    if len(head) >= 12 and head[:4] == b"FORM" and head[8:12] in {b"AIFF", b"AIFC"}:
        return "Disguised AIFF audio file detected via magic bytes."
    if head.startswith(b"#!AMR"):
        return "Disguised AMR audio file detected via magic bytes."
    if len(head) >= 12 and head[4:8] == b"ftyp" and any(b == head[8:12] for b in _MEDIA_FTYP_BRANDS):
        return "Disguised M4A/MP4/3GP media container detected via magic bytes."

    if head.startswith((b"PK\x03\x04", b"PK\x05\x06")):
        return "Disguised ZIP/PyTorch archive detected via PK magic bytes."
    if head.startswith(b"\x1f\x8b\x08"):
        return "Disguised GZIP compressed archive detected via magic bytes."
    if head.startswith(b"7z\xbc\xaf'\x1c"):
        return "Disguised 7-Zip archive detected via magic bytes."
    if head.startswith(b"Rar!\x1a\x07"):
        return "Disguised RAR archive detected via magic bytes."
    if len(head) > 265 and head[257:262] == b"ustar":
        return "Disguised TAR archive detected via ustar header."

    if head.startswith(b"\x93NUMPY"):
        return "Disguised NumPy array/embedding (.npy) detected via magic bytes."
    if head.startswith((b"\x80\x02", b"\x80\x03", b"\x80\x04", b"\x80\x05")):
        return "Disguised Python pickle checkpoint/embedding detected via magic bytes."
    if head.startswith(b"\x89HDF\r\n\x1a\n"):
        return "Disguised HDF5 checkpoint/dataset detected via magic bytes."
    if head.startswith(b"SQLite format 3\x00"):
        return "Disguised SQLite database detected via magic bytes."
    if head.startswith(b"GGUF"):
        return "Disguised GGUF model weight file detected via magic bytes."
    if _looks_like_safetensors(head):
        return "Disguised Safetensors model checkpoint detected via header inspection."

    return None


def _inspect_text_window(raw_path: str, window: bytes) -> str | None:
    if _HF_TOKEN_RE.search(window):
        return "Hardcoded Hugging Face token pattern (hf_...) detected in file content."
    if _PRIVATE_KEY_RE.search(window):
        return "Private cryptographic key header detected in file content."

    ext = Path(raw_path).suffix.lower()
    if ext in {".csv", ".tsv", ".jsonl"} and _MANIFEST_AUDIO_LINE_RE.search(window):
        return "Audio dataset transcript manifest content detected."

    return None


def inspect_stream_violation(raw_path: str, chunks: Iterable[bytes]) -> str | None:
    """Inspect magic header + full byte stream using bounded-memory overlapping windows."""
    overlap_tail = b""
    first_chunk = True

    for chunk in chunks:
        if not chunk:
            continue
        if first_chunk:
            first_chunk = False
            magic_reason = _inspect_header_magic(chunk)
            if magic_reason:
                return magic_reason

        window = overlap_tail + chunk
        text_reason = _inspect_text_window(raw_path, window)
        if text_reason:
            return text_reason
        overlap_tail = window[-_OVERLAP_BYTES:] if len(window) >= _OVERLAP_BYTES else window

    return None


def inspect_content_violation(raw_path: str, data: bytes) -> str | None:
    """Inspect in-memory bytes using the same chunk/overlap pipeline."""
    if not data:
        return None
    slices = (
        data[i : i + _STREAM_CHUNK_BYTES] for i in range(0, len(data), _STREAM_CHUNK_BYTES)
    )
    return inspect_stream_violation(raw_path, slices)


def find_privacy_violations(
    paths: list[str],
    *,
    content_loader: Callable[[str], bytes | None] | None = None,
    stream_loader: Callable[[str], Iterable[bytes] | None] | None = None,
) -> list[tuple[str, str]]:
    """Return list of (path, reason) tuples for path OR full-file content privacy violations."""
    violations: list[tuple[str, str]] = []
    for raw in paths:
        norm = raw.replace("\\", "/").strip()
        if not norm:
            continue

        path_reason = find_path_violation(norm)
        if path_reason:
            violations.append((norm, path_reason))
            continue

        if stream_loader is not None:
            stream = stream_loader(norm)
            if stream is not None:
                reason = inspect_stream_violation(norm, stream)
                if reason:
                    violations.append((norm, reason))
                continue

        if content_loader is not None:
            data = content_loader(norm)
            if data is not None:
                reason = inspect_content_violation(norm, data)
                if reason:
                    violations.append((norm, reason))

    return violations


def _git_paths(mode: str, repo_root: Path) -> list[str]:
    if mode == "staged":
        cmd = ["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR", "-z"]
    else:
        cmd = ["git", "ls-files", "-z"]

    proc = subprocess.run(cmd, cwd=repo_root, capture_output=True, check=True)
    raw = proc.stdout.decode("utf-8", errors="replace")
    return [item for item in raw.split("\x00") if item]


def _iter_blob_chunks(mode: str, repo_root: Path, rel_path: str) -> Iterable[bytes] | None:
    if mode == "staged":
        # Stream exact staged blob directly from Git index without loading huge files into RAM.
        proc = subprocess.Popen(
            ["git", "cat-file", "blob", f":{rel_path}"],
            cwd=repo_root,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
        assert proc.stdout is not None

        def _gen():
            try:
                while True:
                    chunk = proc.stdout.read(_STREAM_CHUNK_BYTES)
                    if not chunk:
                        break
                    yield chunk
            finally:
                proc.stdout.close()
                proc.wait()

        return _gen()

    target = repo_root / rel_path
    if not target.is_file():
        return None

    def _file_gen():
        with target.open("rb") as fh:
            while True:
                chunk = fh.read(_STREAM_CHUNK_BYTES)
                if not chunk:
                    break
                yield chunk

    return _file_gen()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify no personal voice data, disguised binaries, or secrets are in Git."
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--staged", action="store_true", help="Inspect staged Git index blobs.")
    group.add_argument("--tracked", action="store_true", help="Inspect all Git tracked files.")
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[1]
    mode = "staged" if args.staged else "tracked"
    paths = _git_paths(mode, repo_root)
    violations = find_privacy_violations(
        paths,
        stream_loader=lambda rel: _iter_blob_chunks(mode, repo_root, rel),
    )

    if violations:
        print("PRIVACY SAFEGUARD FAILED — commit/build blocked:", file=sys.stderr)
        for path, reason in violations:
            print(f"  - {path}: {reason}", file=sys.stderr)
        print(
            "\nAction required: unstage with 'git reset HEAD <file>' and move voice recordings, "
            "datasets, embeddings, or checkpoints outside the repository.",
            file=sys.stderr,
        )
        return 1

    print(
        f"Privacy check passed ({mode}: {len(paths)} files full-stream path+content inspected, "
        "0 personal voice/model/secret violations)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
