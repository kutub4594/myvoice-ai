"""FFmpeg-based audio preprocessing, quality validation, stitching, and format conversion."""

from __future__ import annotations

import math
import shutil
import struct
import subprocess
import wave
from dataclasses import dataclass
from pathlib import Path


class AudioProcessingError(RuntimeError):
    """Raised when FFmpeg preprocessing, quality checks, stitching, or encoding fails."""


@dataclass(frozen=True)
class WavQualityMetrics:
    """Objective quality summary computed from a PCM WAV file."""

    duration_sec: float
    sample_rate: int
    channels: int
    rms_dbfs: float
    peak_dbfs: float
    clipping_ratio: float


def is_ffmpeg_available() -> bool:
    """Return True if the ffmpeg binary is available on PATH."""
    return shutil.which("ffmpeg") is not None


def _run_ffmpeg(args: list[str]) -> None:
    if not is_ffmpeg_available():
        raise AudioProcessingError("ffmpeg is not installed or not found on PATH.")
    proc = subprocess.run(
        ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise AudioProcessingError(proc.stderr.strip() or "ffmpeg command failed.")


def inspect_wav_quality(wav_path: Path) -> WavQualityMetrics:
    """Inspect a 16-bit PCM WAV file and compute duration, RMS/peak dBFS, and clipping ratio."""
    if not wav_path.exists():
        raise AudioProcessingError(f"WAV file does not exist: {wav_path}")

    try:
        with wave.open(str(wav_path), "rb") as wf:
            channels = wf.getnchannels()
            sample_width = wf.getsampwidth()
            sample_rate = wf.getframerate()
            frame_count = wf.getnframes()
            raw = wf.readframes(frame_count)
    except wave.Error as exc:
        raise AudioProcessingError(f"Invalid WAV file '{wav_path.name}': {exc}") from exc

    if sample_rate <= 0 or frame_count <= 0:
        raise AudioProcessingError("Audio clip contains zero frames.")
    if sample_width != 2:
        raise AudioProcessingError(f"Expected 16-bit PCM WAV, got {sample_width * 8}-bit.")

    sample_count = len(raw) // 2
    if sample_count == 0:
        raise AudioProcessingError("Audio clip contains zero samples.")

    samples = struct.unpack(f"<{sample_count}h", raw)
    # Remove DC offset so flat/DC-biased clips are accurately detected as silent.
    mean_val = sum(samples) / sample_count
    sum_sq = 0.0
    peak = 0
    clipped = 0
    for s in samples:
        abs_s = abs(s)
        if abs_s > peak:
            peak = abs_s
        if abs_s >= 32700:
            clipped += 1
        centered = s - mean_val
        sum_sq += centered * centered

    rms = math.sqrt(sum_sq / sample_count) / 32768.0
    peak_norm = peak / 32768.0
    rms_dbfs = 20.0 * math.log10(max(rms, 1e-9))
    peak_dbfs = 20.0 * math.log10(max(peak_norm, 1e-9))

    return WavQualityMetrics(
        duration_sec=frame_count / float(sample_rate),
        sample_rate=sample_rate,
        channels=channels,
        rms_dbfs=round(rms_dbfs, 2),
        peak_dbfs=round(peak_dbfs, 2),
        clipping_ratio=round(clipped / float(sample_count), 5),
    )


def validate_reference_wav(
    wav_path: Path,
    min_duration_sec: float = 1.5,
    max_duration_sec: float = 30.0,
) -> WavQualityMetrics:
    """Validate that a normalized reference voice sample is usable for cloning."""
    metrics = inspect_wav_quality(wav_path)
    if metrics.duration_sec < min_duration_sec:
        raise AudioProcessingError(
            f"Reference voice sample is too short ({metrics.duration_sec:.2f}s). "
            f"Please provide at least {min_duration_sec:.1f}s of clear speech."
        )
    if metrics.duration_sec > max_duration_sec:
        raise AudioProcessingError(
            f"Reference voice sample is too long ({metrics.duration_sec:.2f}s). "
            f"Please trim to at most {max_duration_sec:.0f}s for stable zero-shot cloning."
        )
    if metrics.rms_dbfs < -50.0:
        raise AudioProcessingError(
            "Reference voice sample appears silent or too quiet. Re-record closer to the mic."
        )
    if metrics.clipping_ratio > 0.08:
        raise AudioProcessingError(
            "Reference voice sample has heavy audio clipping. Record slightly farther from the mic."
        )
    return metrics


def validate_output_wav(wav_path: Path, min_duration_sec: float = 0.08) -> WavQualityMetrics:
    """Verify synthesized output WAV is non-empty, audible, and uncorrupted."""
    metrics = inspect_wav_quality(wav_path)
    if metrics.duration_sec < min_duration_sec:
        raise AudioProcessingError(
            f"Synthesized audio is unexpectedly short ({metrics.duration_sec:.3f}s)."
        )
    if metrics.rms_dbfs < -55.0:
        raise AudioProcessingError(
            "Synthesized audio is silent/corrupted (RMS below -55 dBFS)."
        )
    return metrics


def normalize_reference_audio(input_path: Path, output_wav_path: Path, sample_rate: int = 24000) -> Path:
    """Convert uploaded voice sample to mono PCM WAV, trim leading/trailing silence, and normalize loudness."""
    audio_filter = (
        "silenceremove=start_periods=1:start_silence=0.15:start_threshold=-45dB,"
        "areverse,"
        "silenceremove=start_periods=1:start_silence=0.15:start_threshold=-45dB,"
        "areverse,"
        "loudnorm=I=-16:TP=-1.5:LRA=11"
    )
    _run_ffmpeg(
        [
            "-i",
            str(input_path),
            "-ac",
            "1",
            "-ar",
            str(sample_rate),
            "-af",
            audio_filter,
            "-c:a",
            "pcm_s16le",
            str(output_wav_path),
        ]
    )
    return output_wav_path


def adjust_wav_speed(input_wav_path: Path, output_wav_path: Path, speed: float = 1.0) -> Path:
    """Apply pitch-preserving tempo adjustment via FFmpeg atempo."""
    if abs(speed - 1.0) < 0.01:
        shutil.copyfile(input_wav_path, output_wav_path)
        return output_wav_path
    if not (0.5 <= speed <= 1.75):
        raise AudioProcessingError(f"Unsupported playback speed {speed}; expected 0.5 to 1.75.")

    _run_ffmpeg(
        [
            "-i",
            str(input_wav_path),
            "-af",
            f"atempo={speed:.3f}",
            "-c:a",
            "pcm_s16le",
            str(output_wav_path),
        ]
    )
    return output_wav_path


def write_silence_wav(output_wav_path: Path, duration_ms: int, sample_rate: int = 24000) -> Path:
    """Create a silent mono 16-bit PCM WAV clip of the given duration."""
    frame_count = max(1, int(sample_rate * (duration_ms / 1000.0)))
    with wave.open(str(output_wav_path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(b"\x00\x00" * frame_count)
    return output_wav_path


def stitch_wav_segments(
    segment_wavs: list[tuple[Path, int]],
    output_wav_path: Path,
    work_dir: Path,
    sample_rate: int = 24000,
    crossfade_ms: int = 60,
    normalize_loudness: bool = False,
) -> Path:
    """Stitch ordered WAV segments with optional inter-segment pauses, loudness matching, and crossfades."""
    if not segment_wavs:
        raise AudioProcessingError("No audio segments provided to stitch.")

    seg_filter = "loudnorm=I=-16:TP=-1.5:LRA=11" if normalize_loudness else None

    if len(segment_wavs) == 1:
        single_path, _ = segment_wavs[0]
        args = ["-i", str(single_path), "-ac", "1", "-ar", str(sample_rate)]
        if seg_filter:
            args.extend(["-af", seg_filter])
        args.extend(["-c:a", "pcm_s16le", str(output_wav_path)])
        _run_ffmpeg(args)
        return output_wav_path

    # Normalize each segment to identical sample rate/channel layout and append pause clips.
    normalized_clips: list[Path] = []
    for idx, (wav_path, pause_after_ms) in enumerate(segment_wavs):
        norm_clip = work_dir / f"norm_seg_{idx}.wav"
        args = ["-i", str(wav_path), "-ac", "1", "-ar", str(sample_rate)]
        if seg_filter:
            args.extend(["-af", seg_filter])
        args.extend(["-c:a", "pcm_s16le", str(norm_clip)])
        _run_ffmpeg(args)
        normalized_clips.append(norm_clip)

        if pause_after_ms > 0 and idx < len(segment_wavs) - 1:
            pause_clip = work_dir / f"pause_{idx}.wav"
            write_silence_wav(pause_clip, duration_ms=pause_after_ms, sample_rate=sample_rate)
            normalized_clips.append(pause_clip)

    if len(normalized_clips) == 1:
        shutil.copyfile(normalized_clips[0], output_wav_path)
        return output_wav_path

    # Build an FFmpeg filter_complex chain applying short acrossfade joins between consecutive clips.
    inputs: list[str] = []
    for clip in normalized_clips:
        inputs.extend(["-i", str(clip)])

    fade_sec = max(0.01, min(crossfade_ms, 120) / 1000.0)
    filter_parts: list[str] = []
    last_label = "[0:a]"
    for idx in range(1, len(normalized_clips)):
        out_label = f"[a{idx}]"
        filter_parts.append(
            f"{last_label}[{idx}:a]acrossfade=d={fade_sec:.3f}:c1=tri:c2=tri{out_label}"
        )
        last_label = out_label

    _run_ffmpeg(
        [
            *inputs,
            "-filter_complex",
            ";".join(filter_parts),
            "-map",
            last_label,
            "-ac",
            "1",
            "-ar",
            str(sample_rate),
            "-c:a",
            "pcm_s16le",
            str(output_wav_path),
        ]
    )
    return output_wav_path


def convert_wav_to_mp3(input_wav_path: Path, output_mp3_path: Path, bitrate: str = "192k") -> Path:
    """Encode a WAV file to MP3 using FFmpeg."""
    _run_ffmpeg(
        [
            "-i",
            str(input_wav_path),
            "-codec:a",
            "libmp3lame",
            "-b:a",
            bitrate,
            str(output_mp3_path),
        ]
    )
    return output_mp3_path
