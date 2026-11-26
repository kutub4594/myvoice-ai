"""Private external storage management for user training datasets, embeddings, and checkpoints.

Enforces mandatory privacy & isolation invariants:
1. All personal voice datasets, embeddings, generated audio, and checkpoints MUST live outside
   the Git repository directory.
2. Storage is strictly partitioned per authenticated server-side owner (`owners/<owner_id>/...`)
   so one user cannot list, read, overwrite, or delete another user's data.
3. Remote dataset storage requires explicit per-upload consent (never automatic).
4. ZIP archive extraction enforces entry caps, extension allowlists, symlink/traversal rejection,
   compression-ratio checks, and streamed uncompressed byte limits against ZIP bombs.
"""

from __future__ import annotations

import io
import json
import os
import re
import shutil
import stat
import tempfile
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
_SAFE_ID_RE = re.compile(r"[^a-zA-Z0-9_-]+")
PRIVATE_SUBDIRS = ("datasets", "embeddings", "checkpoints", "generated_audio")
ALLOWED_DATASET_EXTENSIONS = frozenset(
    {".wav", ".mp3", ".m4a", ".flac", ".ogg", ".csv", ".txt", ".json"}
)
DEFAULT_MAX_ZIP_ENTRIES = 5000
DEFAULT_MAX_SINGLE_FILE_BYTES = 100 * 1024 * 1024
DEFAULT_MAX_UNCOMPRESSED_BYTES = 500 * 1024 * 1024
DEFAULT_MAX_COMPRESSION_RATIO = 50.0
_STREAM_CHUNK_BYTES = 64 * 1024


class PrivateStorageError(RuntimeError):
    """Raised when private external storage configuration or archive validation fails."""


class PrivateStorageConsentError(PermissionError):
    """Raised when attempting to store training voice data without explicit consent."""


def _is_within(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def resolve_private_training_dir(
    configured_dir: str | None = None,
    repo_root: Path | None = None,
) -> Path:
    """Resolve the private external storage root, rejecting any location inside the Git repo."""
    repo = (repo_root or REPO_ROOT).resolve()

    if configured_dir and configured_dir.strip():
        candidate = Path(configured_dir.strip()).expanduser().resolve()
        if _is_within(candidate, repo):
            raise PrivateStorageError(
                f"PRIVATE_TRAINING_STORAGE_DIR ('{candidate}') cannot be inside the Git repository ('{repo}')."
            )
        return candidate

    colab_drive = Path("/content/drive/MyDrive")
    if colab_drive.exists() and not _is_within(colab_drive, repo):
        return (colab_drive / "MyVoiceAI_Private").resolve()

    kaggle_work = Path("/kaggle/working")
    if kaggle_work.exists() and not _is_within(kaggle_work, repo):
        return (kaggle_work / "myvoice_private").resolve()

    home_candidate = (Path.home() / ".myvoice_ai_private").resolve()
    if not _is_within(home_candidate, repo):
        return home_candidate

    tmp_candidate = (Path(tempfile.gettempdir()) / "myvoice_ai_private").resolve()
    if _is_within(tmp_candidate, repo):
        raise PrivateStorageError("Unable to locate a private storage path outside the Git repository.")
    return tmp_candidate


def sanitize_identifier(raw_id: str | None, prefix: str = "ds") -> str:
    if raw_id and raw_id.strip():
        cleaned = _SAFE_ID_RE.sub("_", raw_id.strip()).strip("_")[:48]
        if cleaned:
            return cleaned
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    return f"{prefix}_{ts}_{uuid.uuid4().hex[:8]}"


def resolve_owner_storage_root(
    private_root: Path,
    owner_id: str,
    *,
    repo_root: Path | None = None,
) -> tuple[str, Path]:
    """Resolve and validate the isolated per-owner directory under private_root/owners/<owner_id>."""
    repo = (repo_root or REPO_ROOT).resolve()
    resolved_root = private_root.resolve()
    if _is_within(resolved_root, repo):
        raise PrivateStorageError("Private storage root resolved inside Git repo; aborting.")

    if not owner_id or not owner_id.strip():
        raise PrivateStorageError("Authenticated owner_id is required for private storage access.")

    safe_owner = _SAFE_ID_RE.sub("_", owner_id.strip()).strip("_")[:48]
    if not safe_owner:
        raise PrivateStorageError("Authenticated owner_id is invalid.")

    owners_base = (resolved_root / "owners").resolve()
    owner_root = (owners_base / safe_owner).resolve()
    if not _is_within(owner_root, owners_base) or owner_root == owners_base:
        raise PrivateStorageError("Invalid owner storage namespace.")

    return safe_owner, owner_root


def _ensure_private_subdirs(owner_root: Path) -> None:
    owner_root.mkdir(parents=True, exist_ok=True)
    for sub in PRIVATE_SUBDIRS:
        (owner_root / sub).mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(owner_root, 0o700)
    except OSError:
        pass


def _validate_zip_member(
    info: zipfile.ZipInfo,
    ds_dir: Path,
    *,
    max_single_file_bytes: int,
    max_compression_ratio: float,
) -> Path:
    if "\\" in info.filename or ":" in info.filename:
        raise PrivateStorageError(f"Unsafe ZIP entry path rejected: {info.filename}")

    rel = Path(info.filename)
    if rel.is_absolute() or ".." in rel.parts:
        raise PrivateStorageError(f"Unsafe ZIP entry path rejected: {info.filename}")

    # Reject UNIX symlinks and special non-regular files.
    unix_mode = (info.external_attr >> 16) & 0o170000
    if info.create_system == 3 and unix_mode != 0 and not stat.S_ISREG(unix_mode):
        raise PrivateStorageError(
            f"Unsupported non-regular file (symlink/device) rejected in ZIP: {info.filename}"
        )

    ext = rel.suffix.lower()
    if ext not in ALLOWED_DATASET_EXTENSIONS:
        raise PrivateStorageError(
            f"Unsupported file type '{ext or '<none>'}' in training ZIP: {info.filename}"
        )

    if info.file_size > max_single_file_bytes:
        raise PrivateStorageError(
            f"ZIP entry '{info.filename}' exceeds single-file uncompressed limit "
            f"({max_single_file_bytes} bytes)."
        )

    if info.compress_size > 0 and info.file_size > 1024 * 1024:
        ratio = info.file_size / float(info.compress_size)
        if ratio > max_compression_ratio:
            raise PrivateStorageError(
                f"Suspicious compression ratio ({ratio:.1f}x) rejected as potential ZIP bomb: {info.filename}"
            )
    elif info.compress_size == 0 and info.file_size > 0:
        raise PrivateStorageError(f"Malformed ZIP entry metadata rejected: {info.filename}")

    target = (ds_dir / rel).resolve()
    if not _is_within(target, ds_dir):
        raise PrivateStorageError(f"ZIP entry escapes target directory: {info.filename}")
    return target


def store_training_dataset_zip(
    private_root: Path,
    zip_bytes: bytes,
    *,
    owner_id: str,
    consent_confirmed: bool,
    dataset_id: str | None = None,
    repo_root: Path | None = None,
    max_entries: int = DEFAULT_MAX_ZIP_ENTRIES,
    max_uncompressed_bytes: int = DEFAULT_MAX_UNCOMPRESSED_BYTES,
    max_single_file_bytes: int = DEFAULT_MAX_SINGLE_FILE_BYTES,
    max_compression_ratio: float = DEFAULT_MAX_COMPRESSION_RATIO,
) -> dict:
    """Validate consent, isolate by owner, and safely extract a training ZIP outside Git."""
    if not consent_confirmed:
        raise PrivateStorageConsentError(
            "Explicit user consent is required for every training dataset upload."
        )
    if not zip_bytes:
        raise PrivateStorageError("Uploaded training dataset ZIP is empty.")

    safe_owner, owner_root = resolve_owner_storage_root(
        private_root, owner_id, repo_root=repo_root
    )
    _ensure_private_subdirs(owner_root)

    ds_id = sanitize_identifier(dataset_id, prefix="ds").lstrip(".") or sanitize_identifier(None, prefix="ds")
    datasets_root = (owner_root / "datasets").resolve()
    ds_dir = (datasets_root / ds_id).resolve()
    if not _is_within(ds_dir, datasets_root) or ds_dir == datasets_root:
        raise PrivateStorageError("Invalid dataset directory path.")

    staging_dir = (datasets_root / f".staging_{ds_id}_{uuid.uuid4().hex[:8]}").resolve()
    if not _is_within(staging_dir, datasets_root):
        raise PrivateStorageError("Invalid staging directory path.")
    staging_dir.mkdir(parents=True, exist_ok=True)

    extracted_count = 0
    actual_total_bytes = 0
    try:
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            members = [m for m in zf.infolist() if not m.is_dir()]
            if not members:
                raise PrivateStorageError("Uploaded dataset ZIP contains no files.")
            if len(members) > max_entries:
                raise PrivateStorageError(
                    f"ZIP contains {len(members)} entries, exceeding max allowed ({max_entries})."
                )

            declared_total = sum(max(0, m.file_size) for m in members)
            if declared_total > max_uncompressed_bytes:
                raise PrivateStorageError(
                    f"Declared uncompressed dataset size ({declared_total} bytes) exceeds "
                    f"limit ({max_uncompressed_bytes} bytes)."
                )

            for info in members:
                target = _validate_zip_member(
                    info,
                    staging_dir,
                    max_single_file_bytes=max_single_file_bytes,
                    max_compression_ratio=max_compression_ratio,
                )
                target.parent.mkdir(parents=True, exist_ok=True)

                file_bytes_written = 0
                with zf.open(info, "r") as src, target.open("wb") as dst:
                    while True:
                        chunk = src.read(_STREAM_CHUNK_BYTES)
                        if not chunk:
                            break
                        file_bytes_written += len(chunk)
                        actual_total_bytes += len(chunk)
                        if file_bytes_written > max_single_file_bytes:
                            raise PrivateStorageError(
                                f"Entry '{info.filename}' exceeded single-file extraction limit "
                                "while decompressing (possible spoofed ZIP header)."
                            )
                        if actual_total_bytes > max_uncompressed_bytes:
                            raise PrivateStorageError(
                                "Extracted dataset exceeded uncompressed total size limit "
                                "(ZIP bomb protection triggered)."
                            )
                        dst.write(chunk)

                extracted_count += 1

        manifest = {
            "owner_id": safe_owner,
            "dataset_id": ds_id,
            "uploaded_at_utc": datetime.now(timezone.utc).isoformat(),
            "file_count": extracted_count,
            "total_bytes": actual_total_bytes,
            "outside_git_repo": True,
        }
        (staging_dir / ".manifest.json").write_text(
            json.dumps(manifest, indent=2), encoding="utf-8"
        )

        # Atomically promote staging_dir only after full extraction and validation succeed.
        backup_dir: Path | None = None
        if ds_dir.exists():
            backup_dir = (datasets_root / f".backup_{ds_id}_{uuid.uuid4().hex[:8]}").resolve()
            ds_dir.replace(backup_dir)
        try:
            staging_dir.replace(ds_dir)
        except Exception:
            if backup_dir is not None and backup_dir.exists() and not ds_dir.exists():
                backup_dir.replace(ds_dir)
            raise
        if backup_dir is not None and backup_dir.exists():
            shutil.rmtree(backup_dir, ignore_errors=True)
    except zipfile.BadZipFile as exc:
        shutil.rmtree(staging_dir, ignore_errors=True)
        raise PrivateStorageError("Invalid or corrupted ZIP archive.") from exc
    except Exception:
        shutil.rmtree(staging_dir, ignore_errors=True)
        raise

    return manifest


def _dir_stats(directory: Path) -> tuple[int, int]:
    if not directory.exists():
        return (0, 0)
    files = 0
    size = 0
    for item in directory.rglob("*"):
        if item.is_file():
            files += 1
            size += item.stat().st_size
    return (files, size)


def list_remote_training_data(
    private_root: Path,
    *,
    owner_id: str,
    repo_root: Path | None = None,
) -> dict:
    """Summarize stored remote datasets, embeddings, checkpoints, and audio for owner_id only."""
    safe_owner, owner_root = resolve_owner_storage_root(
        private_root, owner_id, repo_root=repo_root
    )

    datasets = []
    ds_root = owner_root / "datasets"
    if ds_root.exists():
        for entry in sorted(ds_root.iterdir()):
            if entry.is_dir() and not entry.name.startswith("."):
                files, size = _dir_stats(entry)
                datasets.append({"dataset_id": entry.name, "file_count": files, "total_bytes": size})

    categories = {}
    for sub in PRIVATE_SUBDIRS:
        files, size = _dir_stats(owner_root / sub)
        categories[sub] = {"file_count": files, "total_bytes": size}

    return {
        "owner_id": safe_owner,
        "storage_scope": "private_external_owner_isolated",
        "outside_git_repo": True,
        "datasets": datasets,
        "categories": categories,
    }


def delete_remote_dataset(
    private_root: Path,
    dataset_id: str,
    *,
    owner_id: str,
    repo_root: Path | None = None,
) -> dict:
    """Delete a specific remote training dataset belonging exclusively to owner_id."""
    safe_owner, owner_root = resolve_owner_storage_root(
        private_root, owner_id, repo_root=repo_root
    )

    clean_id = sanitize_identifier(dataset_id)
    ds_root = (owner_root / "datasets").resolve()
    target = (ds_root / clean_id).resolve()
    if not target.exists() or not _is_within(target, ds_root) or target == ds_root:
        return {"owner_id": safe_owner, "deleted": False, "dataset_id": clean_id, "freed_bytes": 0}

    _, freed_bytes = _dir_stats(target)
    shutil.rmtree(target)
    return {"owner_id": safe_owner, "deleted": True, "dataset_id": clean_id, "freed_bytes": freed_bytes}


def delete_all_remote_training_data(
    private_root: Path,
    *,
    owner_id: str,
    repo_root: Path | None = None,
) -> dict:
    """Permanently purge all remote datasets, embeddings, checkpoints, and audio for owner_id."""
    safe_owner, owner_root = resolve_owner_storage_root(
        private_root, owner_id, repo_root=repo_root
    )

    deleted_items = 0
    freed_bytes = 0
    for sub in PRIVATE_SUBDIRS:
        sub_dir = owner_root / sub
        if sub_dir.exists():
            for entry in list(sub_dir.iterdir()):
                if entry.is_dir():
                    files, size = _dir_stats(entry)
                    deleted_items += max(1, files)
                    freed_bytes += size
                    shutil.rmtree(entry)
                elif entry.is_file():
                    deleted_items += 1
                    freed_bytes += entry.stat().st_size
                    entry.unlink()

    return {
        "owner_id": safe_owner,
        "storage_scope": "private_external_owner_isolated",
        "deleted_items": deleted_items,
        "freed_bytes": freed_bytes,
    }
