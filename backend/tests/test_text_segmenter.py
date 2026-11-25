"""Unit tests for Bengali, English, and mixed script segmentation."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.text_segmenter import detect_dominant_language, segment_text


class TextSegmenterTests(unittest.TestCase):
    def test_pure_bengali_detection_and_segmentation(self) -> None:
        text = "আমি বাংলায় গান গাই।"
        self.assertEqual(detect_dominant_language(text), "bn")
        segments = segment_text(text, mode="auto")
        self.assertEqual(len(segments), 1)
        self.assertEqual(segments[0].language, "bn")
        self.assertEqual(segments[0].pause_after_ms, 0)

    def test_pure_english_detection_and_segmentation(self) -> None:
        text = "Hello, welcome to MyVoice AI."
        self.assertEqual(detect_dominant_language(text), "en")
        segments = segment_text(text, mode="auto")
        self.assertEqual(len(segments), 1)
        self.assertEqual(segments[0].language, "en")

    def test_mixed_bengali_english_segmentation(self) -> None:
        text = "আজকে আমি office থেকে বাড়ি ফিরব। See you soon!"
        self.assertEqual(detect_dominant_language(text), "mixed")
        segments = segment_text(text, mode="auto", base_pause_ms=100)
        self.assertEqual([s.language for s in segments], ["bn", "en", "bn", "en"])
        self.assertEqual(segments[0].text, "আজকে আমি")
        self.assertEqual(segments[1].text, "office")
        self.assertEqual(segments[2].text, "থেকে বাড়ি ফিরব।")
        self.assertGreaterEqual(segments[2].pause_after_ms, 200)
        self.assertEqual(segments[3].pause_after_ms, 0)

    def test_forced_language_mode_keeps_single_segment(self) -> None:
        text = "আমি MyVoice ব্যবহার করছি"
        segments = segment_text(text, mode="bn")
        self.assertEqual(len(segments), 1)
        self.assertEqual(segments[0].language, "bn")

    def test_empty_input_returns_empty_list(self) -> None:
        self.assertEqual(segment_text("   \n  "), [])


if __name__ == "__main__":
    unittest.main()
