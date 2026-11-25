"""Script-based text segmentation for Bengali, English, and mixed inputs.

Splits mixed Bengali-English text into language-homogeneous runs while preserving
clause punctuation and estimating natural inter-segment pause timings.
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
    """Segment input text into Bengali and/or English spans with pause timings.

    Args:
        text: Input string from user.
        mode: One of 'bn', 'en', 'mixed', or 'auto'.
        base_pause_ms: Default pause between adjacent language switches.

    Returns:
        Ordered list of TextSegment items.
    """
    normalized = " ".join(text.strip().split())
    if not normalized:
        return []

    resolved_mode = mode.lower().strip()
    if resolved_mode == "auto":
        resolved_mode = detect_dominant_language(normalized)

    if resolved_mode in {"bn", "en"}:
        lang: SegmentLang = "bn" if resolved_mode == "bn" else "en"
        return [TextSegment(index=0, language=lang, text=normalized, pause_after_ms=0)]

    # Mixed / script-based segmentation: group adjacent tokens sharing a script.
    tokens = normalized.split(" ")
    grouped: list[tuple[SegmentLang, list[str]]] = []
    current_lang: SegmentLang | None = None
    current_tokens: list[str] = []

    for token in tokens:
        detected = _token_script(token)
        if detected is None:
            # Neutral tokens (numbers, punctuation) attach to the current run if present.
            if current_tokens:
                current_tokens.append(token)
            else:
                current_lang = "bn" if _BENGALI_CHAR_RE.search(normalized) else "en"
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
