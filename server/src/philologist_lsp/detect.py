"""Paragraph-level language detection using lingua.

We let lingua detect across all its supported languages and rely on the
spaCy pool to no-op for any language we don't have a model for. If lingua
can't decide, the paragraph renders unannotated.
"""

from __future__ import annotations

from dataclasses import dataclass

from lingua import LanguageDetector, LanguageDetectorBuilder

# Paragraphs shorter than this skip detection entirely — single short
# words give too little signal for any reliable identification. CJK and
# other ideographic scripts pack lots of meaning per char, so the bar
# is intentionally low.
MIN_DETECTABLE_CHARS = 6


@dataclass(frozen=True, slots=True)
class Detection:
    """A language detection result for one paragraph."""

    iso_code: str | None  # ISO 639-1 lowercase, or None when undetermined.
    confidence: float


@dataclass(frozen=True, slots=True)
class Paragraph:
    """One paragraph in a document, with its character offsets."""

    text: str
    start: int
    end: int
    detection: Detection


class LanguageDetectorService:
    """Wraps lingua with paragraph splitting."""

    def __init__(self) -> None:
        self._detector: LanguageDetector = (
            LanguageDetectorBuilder.from_all_languages()
            .with_preloaded_language_models()
            .build()
        )

    def split_paragraphs(self, text: str) -> list[tuple[str, int, int]]:
        """Split on blank lines. Returns (text, start_offset, end_offset)."""
        paragraphs: list[tuple[str, int, int]] = []
        cursor = 0
        for chunk in text.split("\n\n"):
            start = cursor
            end = start + len(chunk)
            if chunk.strip():
                paragraphs.append((chunk, start, end))
            cursor = end + 2
        return paragraphs

    def _detect_one(self, text: str) -> Detection:
        if len(text.strip()) < MIN_DETECTABLE_CHARS:
            return Detection(None, 0.0)
        language = self._detector.detect_language_of(text)
        if language is None:
            return Detection(None, 0.0)
        # Pull the matching confidence value for this language for logging /
        # observability. compute_language_confidence_values returns descending,
        # so the chosen language's score is at index 0 unless the API disagrees
        # with detect_language_of (rare).
        confidence = 0.0
        for cv in self._detector.compute_language_confidence_values(text):
            if cv.language == language:
                confidence = cv.value
                break
        return Detection(language.iso_code_639_1.name.lower(), confidence)

    def detect_paragraphs(self, text: str) -> list[Paragraph]:
        return [
            Paragraph(chunk, start, end, self._detect_one(chunk))
            for chunk, start, end in self.split_paragraphs(text)
        ]
