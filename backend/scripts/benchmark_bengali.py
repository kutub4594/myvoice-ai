#!/usr/bin/env python3
"""Stage 1 Bengali Voice Cloning Benchmark & Output Verification Script.

Run on a GPU/Colab/Kaggle host after installing `backend/requirements-ml.txt` and setting HF_TOKEN:
    python scripts/benchmark_bengali.py \
        --ref-audio /path/to/clean_ref.wav \
        --ref-text "আমি প্রতিদিন সকালে নিয়মিত বাংলা খবর পড়ি।" \
        --out-dir ./benchmark_outputs
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.config import Settings
from app.engines.base import EngineSynthesisInput
from app.engines.indicf5_engine import IndicF5BengaliEngine, probe_device_capability
from app.services.audio_processor import (
    normalize_reference_audio,
    stitch_wav_segments,
    validate_output_wav,
    validate_reference_wav,
)
from app.services.text_segmenter import segment_for_synthesis

DEFAULT_CASES = [
    {
        "id": "bn_short_greeting",
        "text": "শুভ সকাল! কেমন আছেন সবাই? আশা করি আজকের দিনটি খুব সুন্দর কাটবে।",
    },
    {
        "id": "bn_pronunciation_conjuncts",
        "text": "কৃষ্ণচূড়া ফুলের রক্তিম আভায় বিশ্ববিদ্যালয় প্রাঙ্গণ আজ অপরূপ হয়ে উঠেছে।",
    },
    {
        "id": "bn_long_narrative",
        "text": (
            "আমাদের ছোট গ্রামটির পাশ দিয়েই বয়ে গেছে একটি শান্ত নদী। "
            "সকালবেলা সূর্যের আলো যখন জলের ওপর পড়ে, তখন পুরো পরিবেশটা সোনার মতো ঝলমল করে ওঠে। "
            "দূরের মাঠ থেকে কৃষকদের গান আর পাখির ডাক একসাথে ভেসে আসে, যা মনকে ভীষণ শান্তি দেয়।"
        ),
    },
]


def run_benchmark(ref_audio: Path, ref_text: str, out_dir: Path, device: str) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    work_dir = out_dir / "_work"
    work_dir.mkdir(parents=True, exist_ok=True)

    settings = Settings(voice_engine="indicf5", device=device)
    cap = probe_device_capability(requested_device=settings.device)
    norm_ref = normalize_reference_audio(ref_audio, work_dir / "ref_norm.wav")
    ref_metrics = validate_reference_wav(
        norm_ref,
        min_duration_sec=settings.min_reference_duration_sec,
        max_duration_sec=settings.max_reference_duration_sec,
    )

    engine = IndicF5BengaliEngine(settings=settings)
    results = []

    for case in DEFAULT_CASES:
        case_id = case["id"]
        text = case["text"]
        segments = segment_for_synthesis(
            text,
            mode="bn",
            base_pause_ms=settings.inter_segment_pause_ms,
            max_chunk_chars=settings.max_chunk_chars,
        )

        start = time.perf_counter()
        seg_outputs: list[tuple[Path, int]] = []
        for seg in segments:
            seg_wav = work_dir / f"{case_id}_seg_{seg.index}.wav"
            engine.synthesize_segment(
                EngineSynthesisInput(
                    text=seg.text,
                    language="bn",
                    reference_wav_path=norm_ref,
                    reference_text=ref_text,
                    output_wav_path=seg_wav,
                )
            )
            seg_outputs.append((seg_wav, seg.pause_after_ms))

        final_wav = out_dir / f"{case_id}.wav"
        stitch_wav_segments(
            seg_outputs,
            output_wav_path=final_wav,
            work_dir=work_dir,
            crossfade_ms=settings.crossfade_ms,
            normalize_loudness=True,
        )
        elapsed = time.perf_counter() - start
        metrics = validate_output_wav(final_wav)
        rtf = elapsed / metrics.duration_sec if metrics.duration_sec > 0 else 0.0

        results.append(
            {
                "id": case_id,
                "chunks": len(segments),
                "inference_time_sec": round(elapsed, 3),
                "audio_duration_sec": round(metrics.duration_sec, 3),
                "real_time_factor": round(rtf, 3),
                "rms_dbfs": round(metrics.rms_dbfs, 2),
                "peak_dbfs": round(metrics.peak_dbfs, 2),
                "clipping_ratio": round(metrics.clipping_ratio, 6),
                "wav_path": str(final_wav),
            }
        )

    report = {
        "engine": "indicf5",
        "device": cap.model_dump(),
        "reference_metrics": {
            "duration_sec": round(ref_metrics.duration_sec, 3),
            "rms_dbfs": round(ref_metrics.rms_dbfs, 2),
            "sample_rate": ref_metrics.sample_rate,
        },
        "cases": results,
        "manual_listening_note": (
            "Objective metrics verify duration, loudness, and absence of silence/clipping. "
            "Human listening evaluation on generated WAV files is required before judging naturalness or similarity."
        ),
    }
    report_path = out_dir / "benchmark_report.json"
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark Stage 1 Bengali IndicF5 cloning.")
    parser.add_argument("--ref-audio", required=True, type=Path, help="Clean Bengali reference clip (3-15s)")
    parser.add_argument("--ref-text", required=True, type=str, help="Exact Bengali transcript of ref audio")
    parser.add_argument("--out-dir", default=Path("./benchmark_outputs"), type=Path)
    parser.add_argument("--device", default="auto", choices=["auto", "cuda", "cpu", "mps"])
    args = parser.parse_args()

    report = run_benchmark(args.ref_audio, args.ref_text.strip(), args.out_dir, args.device)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
