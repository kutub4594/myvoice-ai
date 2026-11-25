"""FFmpeg-based audio preprocessing, stitching, and format conversion utilities."""

from __future__ import annotations

import shutil
import subprocess
import wave
from pathlib import Path


class AudioProcessingError(RuntimeError):
    """Raised when FFmpeg preprocessing, stitching, or encoding fails."""


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
) -> Path:
    """Stitch ordered WAV segments with optional inter-segment pauses and crossfades."""
    if not segment_wavs:
        raise AudioProcessingError("No audio segments provided to stitch.")

    if len(segment_wavs) == 1:
        single_path, _ = segment_wavs[0]
        _run_ffmpeg(
            [
                "-i",
                str(single_path),
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

    # Normalize each segment to identical sample rate/channel layout and append pause clips.
    normalized_clips: list[Path] = []
    for idx, (wav_path, pause_after_ms) in enumerate(segment_wavs):
        norm_clip = work_dir / f"norm_seg_{idx}.wav"
        _run_ffmpeg(
            [
                "-i",
                str(wav_path),
                "-ac",
                "1",
                "-ar",
                str(sample_rate),
                "-c:a",
                "pcm_s16le",
                str(norm_clip),
            ]
        )
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
