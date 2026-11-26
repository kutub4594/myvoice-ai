"""Script-based text segmentation and long-text chunking for Bengali, English, and mixed inputs.

Splits mixed Bengali-English text into language-homogeneous runs, and splits long paragraphs
into prosody-safe sentence/clause chunks while preserving natural pause timings.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

SegmentLang = Literal["bn", "en"]

_BENGALI_CHAR_RE = re.compile(r"[\u0980-\u09FF]")
_LATIN_CHAR_RE = re.compile(r"[A-Za-z]")
_SENTENCE_END_CHARS = {".", "!", "?", "।", "॥"}
_CLAUSE_PAUSE_CHARS = {",", ";", ":", "-", "—"}
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[।॥.!?])\s+")
_CLAUSE_SPLIT_RE = re.compile(r"(?<=[,;:\—])\s+")


@dataclass(frozen=True)
class TextSegment:
    """A single language-tagged text span ready for TTS synthesis."""

    index: int
    language: SegmentLang
    text: str
    pause_after_ms: int


def _token_script(token: str) -> SegmentLang | None:
    has_bn = bool(_BENGALI_CHAR_RE.search(token))
    has_en = bool(_LATIN_CHAR_RE.search(token))
    if has_bn and not has_en:
        return "bn"
    if has_en and not has_bn:
        return "en"
    if has_bn and has_en:
        bn_count = len(_BENGALI_CHAR_RE.findall(token))
        en_count = len(_LATIN_CHAR_RE.findall(token))
        return "bn" if bn_count >= en_count else "en"
    return None


def _first_script_from(tokens: list[str], start_idx: int) -> SegmentLang | None:
    for idx in range(start_idx, len(tokens)):
        detected = _token_script(tokens[idx])
        if detected is not None:
            return detected
    return None


def _pause_for_text(text: str, base_pause_ms: int, is_last: bool) -> int:
    if is_last:
        return 0
    stripped = text.rstrip()
    if not stripped:
        return base_pause_ms
    last_char = stripped[-1]
    if last_char in _SENTENCE_END_CHARS:
        return max(base_pause_ms * 2, 220)
    if last_char in _CLAUSE_PAUSE_CHARS:
        return max(int(base_pause_ms * 1.35), 150)
    return base_pause_ms


def detect_dominant_language(text: str) -> Literal["bn", "en", "mixed"]:
    """Inspect Unicode character counts to classify input as Bengali, English, or mixed."""
    bn_count = len(_BENGALI_CHAR_RE.findall(text))
    en_count = len(_LATIN_CHAR_RE.findall(text))
    if bn_count > 0 and en_count > 0:
        return "mixed"
    if bn_count > 0:
        return "bn"
    return "en"


def segment_text(
    text: str,
    mode: str = "auto",
    base_pause_ms: int = 110,
) -> list[TextSegment]:
    """Segment input text into Bengali and/or English spans with pause timings."""
    normalized = " ".join(text.strip().split())
    if not normalized:
        return []

    resolved_mode = mode.lower().strip()
    if resolved_mode == "auto":
        resolved_mode = detect_dominant_language(normalized)

    if resolved_mode in {"bn", "en"}:
        lang: SegmentLang = "bn" if resolved_mode == "bn" else "en"
        return [TextSegment(index=0, language=lang, text=normalized, pause_after_ms=0)]

    tokens = normalized.split(" ")
    grouped: list[tuple[SegmentLang, list[str]]] = []
    current_lang: SegmentLang | None = None
    current_tokens: list[str] = []

    for idx, token in enumerate(tokens):
        detected = _token_script(token)
        if detected is None:
            if current_tokens:
                current_tokens.append(token)
            else:
                current_lang = _first_script_from(tokens, idx + 1) or "en"
                current_tokens.append(token)
            continue

        if current_lang is None:
            current_lang = detected
            current_tokens = [token]
        elif detected == current_lang:
            current_tokens.append(token)
        else:
            grouped.append((current_lang, current_tokens))
            current_lang = detected
            current_tokens = [token]

    if current_tokens and current_lang is not None:
        grouped.append((current_lang, current_tokens))

    total = len(grouped)
    segments: list[TextSegment] = []
    for idx, (seg_lang, seg_tokens) in enumerate(grouped):
        seg_text = " ".join(seg_tokens).strip()
        segments.append(
            TextSegment(
                index=idx,
                language=seg_lang,
                text=seg_text,
                pause_after_ms=_pause_for_text(
                    seg_text,
                    base_pause_ms=base_pause_ms,
                    is_last=(idx == total - 1),
                ),
            )
        )
    return segments


def _split_oversized_clause(clause: str, max_chars: int) -> list[str]:
    """Split a single clause exceeding max_chars along sub-clauses or word boundaries."""
    if len(clause) <= max_chars:
        return [clause]

    parts = [p.strip() for p in _CLAUSE_SPLIT_RE.split(clause) if p.strip()]
    if len(parts) == 1:
        parts = clause.split(" ")

    chunks: list[str] = []
    buf: list[str] = []
    buf_len = 0
    for part in parts:
        extra = len(part) if not buf else len(part) + 1
        if buf and buf_len + extra > max_chars:
            chunks.append(" ".join(buf))
            buf = [part]
            buf_len = len(part)
        else:
            buf.append(part)
            buf_len += extra
    if buf:
        chunks.append(" ".join(buf))
    return chunks


def chunk_long_text(
    text: str,
    language: SegmentLang,
    max_chars: int = 160,
    base_pause_ms: int = 110,
) -> list[TextSegment]:
    """Split a long single-language paragraph into sentence/clause chunks <= max_chars."""
    normalized = " ".join(text.strip().split())
    if not normalized:
        return []
    if max_chars <= 0 or len(normalized) <= max_chars:
        return [TextSegment(index=0, language=language, text=normalized, pause_after_ms=0)]

    sentences = [s.strip() for s in _SENTENCE_SPLIT_RE.split(normalized) if s.strip()]
    raw_chunks: list[str] = []
    current_group = ""

    for sentence in sentences:
        if len(sentence) > max_chars:
            if current_group:
                raw_chunks.append(current_group)
                current_group = ""
            raw_chunks.extend(_split_oversized_clause(sentence, max_chars))
            continue

        candidate = f"{current_group} {sentence}".strip() if current_group else sentence
        if len(candidate) <= max_chars:
            current_group = candidate
        else:
            raw_chunks.append(current_group)
            current_group = sentence

    if current_group:
        raw_chunks.append(current_group)

    total = len(raw_chunks)
    return [
        TextSegment(
            index=idx,
            language=language,
            text=chunk,
            pause_after_ms=_pause_for_text(
                chunk,
                base_pause_ms=base_pause_ms,
                is_last=(idx == total - 1),
            ),
        )
        for idx, chunk in enumerate(raw_chunks)
    ]


def segment_for_synthesis(
    text: str,
    mode: str = "auto",
    base_pause_ms: int = 110,
    max_chunk_chars: int = 160,
) -> list[TextSegment]:
    """Segment text by script and split long spans for discontinuity-free synthesis."""
    base_segments = segment_text(text, mode=mode, base_pause_ms=base_pause_ms)
    if not base_segments:
        return []

    expanded: list[TextSegment] = []
    for seg in base_segments:
        sub_chunks = chunk_long_text(
            seg.text,
            language=seg.language,
            max_chars=max_chunk_chars,
            base_pause_ms=base_pause_ms,
        )
        for sub_idx, chunk in enumerate(sub_chunks):
            is_last_sub = sub_idx == len(sub_chunks) - 1
            pause = seg.pause_after_ms if is_last_sub else chunk.pause_after_ms
            expanded.append(
                TextSegment(
                    index=len(expanded),
                    language=chunk.language,
                    text=chunk.text,
                    pause_after_ms=pause,
                )
            )
    return expanded
