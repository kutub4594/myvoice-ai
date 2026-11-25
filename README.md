# MyVoice AI

A free, open-source **AI Voice Cloning Android application** (Flutter) paired with a modular **Python FastAPI + optional Gradio** backend supporting **Bengali**, **English**, and **mixed Bengali–English** text-to-speech.

> [!IMPORTANT]
> **Current Status: Initial Scaffolding Only**
> This repository currently contains the project structure, UI screens, local privacy/profile vault, API contracts, script-based text segmenter, audio stitching utilities, and engine placeholders (`mock` engine works out-of-the-box for integration testing; `f5` and `cpu_fallback` engines are scaffolded interfaces awaiting model weight integration and hardware testing). No multi-gigabyte ML weights are downloaded yet, and real voice cloning inference has **not** been tested yet.

---

## Architecture Overview

```text
MyVoice AI (Flutter Android, Material 3, minSdk 24 / Android 7.0+)
  ├── Private on-device voice sample storage + SQLite metadata
  ├── Explicit user consent prompt before uploading any voice clip
  ├── Script-aware Bengali / English / Mixed text preview
  └── Configurable backend URL (Local PC LAN / Colab Tunnel / HF Space)
            │
            ▼ HTTPS (Stateless multipart request; server purges temp files)
Python FastAPI Backend (+ optional Gradio mount for HF Spaces)
  ├── /health & /api/v1/engines
  ├── /api/v1/synthesize  (script segmentation -> engine -> FFmpeg stitch -> WAV/MP3)
  └── Engine Registry:
        ├── f5           -> IndicF5 (Bengali) + F5-TTS (English) [Scaffolded]
        ├── chatterbox   -> Chatterbox + Bangla adaptation [Optional Comparison Scaffold]
        ├── cpu_fallback -> MMS-TTS (Bengali) + Piper (English) + OpenVoice v2 [Scaffolded]
        └── mock         -> Synthetic WAV generator for offline API/UI testing
```

### Two Personal Voice Cloning Workflows
1. **Tier 1 — Instant Voice Profile (Zero-Shot)**: Record or upload 1–5 clean style-tagged clips (*Neutral*, *Conversational*, *Expressive*, *Calm*) for immediate zero-shot conditioning without updating model weights.
2. **Tier 2 — Personal Dataset Studio + Colab Fine-Tuning**: Use the guided Bengali & English prompt studio in the app to collect 15–60 minutes of clean transcribed utterances, export `dataset.zip` (`wavs/` + `metadata.csv`), and run `training/colab_finetune.ipynb` on a free Google Colab T4 GPU to train a personal checkpoint.

---

## Verified Model Licenses & Language Support

Before integrating or distributing builds with model weights, note the verified licenses and constraints:

| Component | Target Role | Verified Language Support | License & Access Notes |
| :--- | :--- | :--- | :--- |
| **IndicF5** (`ai4bharat/IndicF5`) | Bengali voice cloning | 11 Indic languages including **Bengali** (no native English) | **MIT License**; **gated Hugging Face repo** (requires free HF account & accepting model terms) |
| **F5-TTS** (`SWivid/F5-TTS`) | English voice cloning | **English**, Chinese | Code: **MIT**; Pre-trained weights: **CC-BY-NC-4.0** (**Non-Commercial**) |
| **Chatterbox** (`ResembleAI/chatterbox` + `Banglabox/chatterbox-bangla-tts`) | Optional expressive comparison | Official: English (23 langs omit Bangla); Community `Banglabox`: Bengali | **MIT License** (official weights embed Resemble's `PerTh` watermark; Bangla adaptation requires listening tests) |
| **MMS-TTS Bengali** (`facebook/mms-tts-ben`) | CPU fallback Bengali TTS | **Bengali** (`ben`) | **CC-BY-NC-4.0** (**Non-Commercial**) |
| **Piper** (`rhasspy/piper`) | CPU fallback English TTS | **English** (`en_US`, `en_GB`, etc.) | Code: **MIT** (check individual voice card licenses; `OHF-Voice/piper1-gpl` fork is GPL) |
| **OpenVoice v2** (`myshell-ai/OpenVoice`) | CPU fallback tone-color conversion | ToneColorConverter is acoustic/language-agnostic (base MeloTTS is EN/ES/FR/ZH/JP/KR) | **MIT License** (code & weights). Cross-lingual conversion on Bengali MMS-TTS requires empirical testing |

---

## Project Structure

```text
.
├── .github/workflows/android-build.yml   # CI: Python tests, Flutter tests, Android APK build
├── backend/
│   ├── .env.example
│   ├── requirements.txt
│   ├── app/
│   │   ├── main.py                       # FastAPI entrypoint + optional Gradio mount
│   │   ├── config.py                     # Env-based settings (no secrets hardcoded)
│   │   ├── schemas.py                    # Pydantic API models
│   │   ├── engines/
│   │   │   ├── base.py                   # Abstract VoiceCloningEngine interface
│   │   │   ├── f5_engine.py              # IndicF5 + F5-TTS placeholder
│   │   │   ├── chatterbox_engine.py      # Chatterbox comparison placeholder
│   │   │   ├── cpu_fallback_engine.py    # MMS-TTS + Piper + OpenVoice v2 placeholder
│   │   │   ├── mock_engine.py            # Offline deterministic test engine
│   │   │   └── registry.py               # Engine selector
│   │   ├── services/
│   │   │   ├── text_segmenter.py         # Bengali / English / Mixed Unicode segmenter
│   │   │   └── audio_processor.py        # FFmpeg normalization, stitching & WAV/MP3 export
│   │   └── gradio_app.py                 # Optional Gradio UI for Hugging Face Spaces
│   └── tests/
│       ├── test_text_segmenter.py
│       └── test_api_scaffold.py
├── training/
│   └── colab_finetune.ipynb              # Tier 2 Google Colab T4 fine-tuning scaffold
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
```

Verify health endpoint:
```bash
curl http://localhost:8000/health
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
1. Runs Python backend unit tests.
2. Runs `flutter analyze` and `flutter test`.
3. Builds a release Android APK (unsigned debug/release artifact) and uploads it as a GitHub Actions artifact.

---

## Privacy & Security Principles

* Voice samples are stored **only inside the app's private directory** on the user's phone.
* The app requires **explicit user consent** before uploading a voice sample to any configured backend URL.
* Users can **delete individual voice profiles, audio history, or all local data** at any time.
* The backend processes uploaded reference clips inside ephemeral temporary directories and deletes them immediately after synthesis.
* No paid APIs, analytics trackers, or hardcoded secrets are included.
