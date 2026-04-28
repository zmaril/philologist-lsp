"""Helpers for translating character offsets in our analysis to LSP
Positions (line + utf-16 character offset)."""

from __future__ import annotations

from bisect import bisect_right

from lsprotocol import types as lsp


class LineIndex:
    """Cached line offsets for a text document.

    Pre-computes the start offset of every line, then converts a char
    offset to a `Position` via binary search. UTF-16 conversion follows
    LSP semantics: BMP chars count as one unit, supplementary plane
    chars (surrogate pairs) count as two. Standard linguistic text
    stays inside the BMP, so this is rarely a hot issue, but we handle
    it correctly for completeness.
    """

    __slots__ = ("_text", "_line_starts")

    def __init__(self, text: str) -> None:
        self._text = text
        self._line_starts = [0]
        for i, ch in enumerate(text):
            if ch == "\n":
                self._line_starts.append(i + 1)

    def position(self, char_offset: int) -> lsp.Position:
        """Convert a Python-string char offset into an LSP Position."""
        line_idx = bisect_right(self._line_starts, char_offset) - 1
        if line_idx < 0:
            line_idx = 0
        line_start = self._line_starts[line_idx]
        substring = self._text[line_start:char_offset]
        char = sum(2 if ord(ch) > 0xFFFF else 1 for ch in substring)
        return lsp.Position(line=line_idx, character=char)

    def range(self, start: int, end: int) -> lsp.Range:
        return lsp.Range(start=self.position(start), end=self.position(end))
