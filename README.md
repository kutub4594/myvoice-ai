# MyVoice AI

A free, open-source **AI Voice Cloning Android application** (Flutter) paired with a modular **Python FastAPI + optional Gradio** backend supporting **Bengali** (Stage 1: `IndicF5`), **English** (Stage 2 evaluation: `Chatterbox`), and **mixed Bengali–English** script routing.

> [!IMPORTANT]
> **Implementation Status (Stage 1 Bengali Engine Integrated; Live GPU Listening Benchmark Pending)**
> - **Implemented & Contract-Preserved**:
>   - Flutter Android app (`mobile/`): local private voice vault, SQLite metadata, explicit upload consent gate, script-aware preview, user-controlled deletion, configurable external GPU backend URL.
>   - FastAPI backend (`backend/`): `/health` with hardware capability diagnostics, `/api/v1/diagnostics` (non-secret), `/api/v1/engines`, `/api/v1/segment-preview`, `/api/v1/transcribe`, `/api/v1/synthesize`, and optional `/gradio`.
>   - **Stage 1 Bengali Zero-Shot Adapter (`indicf5`)**: real `ai4bharat/IndicF5` integration requiring clean reference audio (1.5–30s) + accurate Bengali transcript (or optional `faster-whisper` auto-transcribe), CUDA/MPS/CPU device detection, single-GPU concurrency semaphore, strict error reporting (never silently falls back to mock audio), reference/output WAV quality validation, and long-text clause chunking + FFmpeg loudness normalization/crossfade stitching.
> - **Experimental / Not Yet Benchmarked**:
>   - Live `IndicF5` audio quality and speaker similarity require execution on an external GPU host with Hugging Face `ai4bharat/IndicF5` gated access (`backend/scripts/benchmark_bengali.py`). Do **not** assume ElevenLabs-level quality without listening tests.
>   - **Stage 2 English (`chatterbox`)** and **`cpu_fallback`**: modular adapters remain disabled until Stage 2 dependency isolation and audio verification.
>   - **Tier 2 Personal Fine-Tuning (`training/colab_finetune.ipynb`)**: dataset validation and resumable training-job separation scaffold; full fine-tuning training loop pending Stage 2.

---

## Architecture Overview

```text
MyVoice AI (Flutter Android, Material 3, minSdk 24 / Android 7.0+, targetSdk 34)
  ├── Private on-device voice sample storage + SQLite metadata
  ├── Explicit user consent prompt before uploading any voice clip
  ├── User-controlled deletion (individual clips, history, full wipe)
  ├── Script-aware Bengali / English / Mixed text preview
  └── Configurable external GPU backend URL (Self-hosted GPU / Colab Tunnel / LAN)
            │
            ▼ HTTPS (Stateless multipart request; server purges temp files immediately)
Python FastAPI Backend (+ optional Gradio mount)
  ├── GET  /health               (active engine + GPU/CPU hardware diagnostics)
  ├── GET  /api/v1/diagnostics   (detailed runtime diagnostics; never exposes secrets)
  ├── GET  /api/v1/engines
  ├── GET  /api/v1/segment-preview
  ├── POST /api/v1/transcribe
  ├── POST /api/v1/synthesize    (long-text chunking -> engine -> loudness norm & crossfade -> WAV/MP3)
  └── Engine Registry:
        ├── indicf5      -> AI4Bharat IndicF5 Bengali zero-shot adapter [Stage 1 Implemented]
        ├── f5           -> Dual router: IndicF5 (bn) + F5-TTS gate (en; CC-BY-NC-4.0 notice)
        ├── chatterbox   -> ResembleAI Chatterbox English-only evaluation [Stage 2 Placeholder]
        ├── cpu_fallback -> MMS-TTS (bn) + Piper (en) + OpenVoice v2 [Placeholder]
        └── mock         -> Deterministic WAV generator for offline API/UI tests
```

### Two Distinct Voice Cloning Workflows
1. **Tier 1 — Instant Zero-Shot Cloning**: Uses 1 clean 3–15s voice reference clip **and its accurate transcript** at synthesis time without updating any model weights. Uploading a short clip never claims to "train" a personal model.
2. **Tier 2 — Personal Dataset Studio + Fine-Tuning**: Keeps **Speaker Profiles** separate from **Training Jobs** (`training/colab_finetune.ipynb`), validates `dataset.zip` (`wavs/` + `metadata.csv`), and tracks resumable Google Drive checkpoints (`job_state.json`).

---

## Verified Model Licenses, Evaluation Notes & Language Support

| Component | Role & Status | Verified Language Support | License & Access Notes |
| :--- | :--- | :--- | :--- |
| **IndicF5** (`ai4bharat/IndicF5`) | **Stage 1 Bengali** (implemented adapter) | 11 Indic languages including **Bengali** (no native English) | **MIT License**; **gated HF repo** (requires accepting terms + `HF_TOKEN` env var) |
| **Chatterbox** (`ResembleAI/chatterbox`) | **Stage 2 English** (evaluated placeholder) | **English** (upstream multilingual omits Bengali — never claim Bengali for Chatterbox) | **MIT License**; upstream GitHub repo is **archived/retired** (weights embed `PerTh` watermark; requires isolated `torch==2.6.0` env) |
| **F5-TTS** (`SWivid/F5-TTS`) | Optional future dual engine | **English**, Chinese | Code: **MIT**; pre-trained weights: **`CC-BY-NC-4.0` (Non-Commercial)** — do not deploy commercially without permission |
| **MMS-TTS Bengali** (`facebook/mms-tts-ben`) | Future CPU fallback | **Bengali** (`ben`) | **CC-BY-NC-4.0** (**Non-Commercial**) |
| **Piper** (`rhasspy/piper`) | Future CPU fallback | **English** | **MIT** (`OHF-Voice/piper1-gpl` fork is GPL) |
| **OpenVoice v2** (`myshell-ai/OpenVoice`) | Future CPU tone converter | Base English; cross-lingual needs testing | **MIT License** |

---

## Project Structure

```text
.
├── .github/workflows/android-build.yml   # CI: Python tests, Flutter tests, Android APK build
├── backend/
│   ├── .env.example
│   ├── requirements.txt
│   ├── requirements-ml.txt               # Stage 1 IndicF5 GPU/CPU dependencies
│   ├── app/
│   │   ├── main.py                       # FastAPI entrypoint + diagnostics + optional Gradio mount
│   │   ├── config.py                     # Env-based settings (HF_TOKEN read from env only)
│   │   ├── schemas.py                    # Pydantic API models & hardware/audio diagnostics
│   │   ├── engines/
│   │   │   ├── base.py                   # Abstract VoiceCloningEngine & typed errors
│   │   │   ├── indicf5_engine.py         # Real AI4Bharat IndicF5 Bengali zero-shot adapter
│   │   │   ├── f5_engine.py              # Dual router: IndicF5 (bn) + F5-TTS gate (en)
│   │   │   ├── chatterbox_engine.py      # Chatterbox English-only evaluation placeholder
│   │   │   ├── cpu_fallback_engine.py    # MMS-TTS + Piper + OpenVoice v2 placeholder
│   │   │   ├── mock_engine.py            # Offline deterministic test engine
│   │   │   └── registry.py               # Engine selector
│   │   ├── services/
│   │   │   ├── text_segmenter.py         # Bengali / English segmenter + long-text chunking
│   │   │   └── audio_processor.py        # FFmpeg norm, quality checks, loudness & crossfade stitch
│   │   └── gradio_app.py                 # Optional Gradio UI for Hugging Face Spaces
│   ├── scripts/
│   │   └── benchmark_bengali.py          # GPU benchmark & WAV output verification script
│   └── tests/
│       ├── test_text_segmenter.py
│       ├── test_long_text_chunking.py
│       ├── test_engines_contract.py
│       ├── test_indicf5_engine.py
│       └── test_api_scaffold.py
├── training/
│   └── colab_finetune.ipynb              # Tier 1 GPU backend + Tier 2 resumable training scaffold
└── mobile/
    ├── pubspec.yaml
    ├── analysis_options.yaml
    ├── android/                          # Android Gradle & Manifest (minSdk 24 / Android 7.0+)
    ├── lib/
    │   ├── main.dart
    │   ├── app.dart
    │   ├── core/                         # Theme, constants, exceptions, script detector
    │   ├── data/                         # Models, local storage vault, recorder, player, API client
    │   └── features/                     # Generate, Profiles, History, Backend Settings screens
    └── test/
```

---

## Quick Setup (Development)

### 1. Python Backend (Python 3.10–3.12 recommended for ML; 3.10+ for API scaffold)

```bash
cd backend
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env

# Run API server with the mock test engine (no GPU / weights required)
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# OR on a GPU/ML host for real Stage 1 Bengali IndicF5 cloning (do NOT install on Android):
# pip install -r requirements.txt -r requirements-ml.txt
# export HF_TOKEN=hf_your_read_token VOICE_ENGINE=indicf5 DEVICE=auto
# uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Verify health & diagnostics endpoints:
```bash
curl http://localhost:8000/health
curl http://localhost:8000/api/v1/diagnostics
```

Run Stage 1 Bengali benchmark on a GPU host:
```bash
python scripts/benchmark_bengali.py \
  --ref-audio /path/to/clean_ref.wav \
  --ref-text "আমি প্রতিদিন সকালে নিয়মিত বাংলা খবর পড়ি।" \
  --out-dir ./benchmark_outputs
```

Run backend unit tests:
```bash
python -m unittest discover -s tests -v
```

### 2. Flutter Android Frontend (Requires Flutter SDK + Android SDK on x86_64/macOS/Windows or CI)

```bash
cd mobile
flutter pub get
flutter analyze
flutter test
flutter build apk --release
```

### 3. Automated CI Builds (GitHub Actions)

Push to `main` or open a Pull Request—`.github/workflows/android-build.yml` automatically:
1. Runs `privacy-audit` (`scripts/check_staged_privacy.py --tracked`) as a mandatory dependency.
2. Runs Python backend unit tests (`needs: privacy-audit`).
3. Runs `flutter analyze`, `flutter test`, builds the Android APK (`needs: [privacy-audit, backend-tests]`), verifies zero voice/dataset/model entries inside `app-release.apk`, and uploads only the APK artifact.

---

## Privacy & Data Ownership Guarantees

* **Zero Voice Data in Git**: `.gitignore`, [`.githooks/pre-commit`](.githooks/pre-commit), [`scripts/check_staged_privacy.py`](scripts/check_staged_privacy.py) (path rules plus full-file streaming magic-byte & secret inspection), and CI checks block commits/builds containing audio files, disguised binaries, datasets, embeddings, SQLite voice DBs, checkpoints, or secrets. Enable hooks locally with:
  ```bash
  git config core.hooksPath .githooks
  ```
* **Authenticated & Owner-Isolated Backend**: Sensitive backend endpoints require Bearer/API-key authentication failing closed (`503`/`401`) if unconfigured. Multi-user deployments **must** set distinct per-user credentials via `MYVOICE_OWNER_TOKENS` (`alice:tokA,bob:tokB`) to isolate each user's remote datasets, embeddings, checkpoints, and outputs under separate `owners/<owner_id>` directories; a single shared `MYVOICE_API_TOKEN` intentionally shares one single-owner namespace across all holders of that token. Optional Gradio UI (`/gradio`) remains disabled unless authentication is configured and enforces credentials on login.
* **HTTPS Enforced & Trusted-Proxy Hardening**: Both Android (`network_security_config.xml` + `BackendConfig`) and backend (`enforce_https_transport`) enforce `https://` for remote connections, trusting `X-Forwarded-Proto` only from `TRUSTED_PROXY_IPS` (`127.0.0.1,::1` default) and permitting `http://` only for explicit local/emulator dev (`localhost`, `127.0.0.1`, `::1`, `10.0.2.2`) when opted in.
* **Android App-Private Storage by Default**: Voice profiles, dataset recordings, and generated outputs stay inside Android `getApplicationDocumentsDirectory()/myvoice_vault` with `android:allowBackup="false"`.
* **Fresh Explicit Consent on Every Cloud Upload**: Both zero-shot voice synthesis and training dataset exports/uploads require fresh per-upload consent every time (persistent consent caching is disabled/removed).
* **Separate Private Remote Storage & ZIP Bomb Protection**: Datasets, embeddings, and checkpoints stay outside Git (`PRIVATE_TRAINING_STORAGE_DIR`) with symlink, traversal, extension, compression-ratio, entry-count, and streamed decompression byte limits.
* **User-Controlled Local & Remote Deletion + Clean Temp Cleanup**: Users can delete local voice data or purge their remote training data (`DELETE /api/v1/training/data`), and temporary processing files are cleaned automatically.
