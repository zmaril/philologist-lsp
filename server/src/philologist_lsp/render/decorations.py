"""Build per-token decoration items for the client to render via
TextEditorDecorationType.

Each token gets at most one decoration. The `kind` tag drives the color
(themed via VSCode color customizations); the `glyph` is the actual
unicode sigil that appears after the token.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from philologist_lsp.analyzers.morph import DocumentAnalysis, TokenAnalysis
from philologist_lsp.glyphs import (
    CASE_GLYPH,
    DEGREE_GLYPH,
    VERB_CLASS_GLYPH,
    VERB_REGULAR_GLYPH,
    VERB_SEPARABLE_GLYPH,
)
from philologist_lsp.render.positions import LineIndex


CASE_KIND: dict[str, str] = {
    "Nom": "case.nominative",
    "Acc": "case.accusative",
    "Dat": "case.dative",
    "Gen": "case.genitive",
    "Voc": "case.vocative",
    "Ins": "case.instrumental",
    "Loc": "case.locative",
    "Abl": "case.ablative",
}


@dataclass(frozen=True, slots=True)
class Decoration:
    line: int
    start_character: int
    end_character: int
    glyph: str
    kind: str
    tooltip: str

    def to_payload(self) -> dict[str, Any]:
        return {
            "line": self.line,
            "startCharacter": self.start_character,
            "endCharacter": self.end_character,
            "glyph": self.glyph,
            "kind": self.kind,
            "tooltip": self.tooltip,
        }


def _verb_decoration(token: TokenAnalysis) -> tuple[str, str] | None:
    """Pick the single most informative sigil + kind for a verb token."""
    parts: list[str] = []
    kind: str | None = None

    if token.verb_class == "modal":
        parts.append(VERB_CLASS_GLYPH["modal"])
        kind = "verb.modal"
    elif token.verb_class == "aux":
        parts.append(VERB_CLASS_GLYPH["aux"])
        kind = "verb.auxiliary"

    if token.separable:
        parts.append(VERB_SEPARABLE_GLYPH)
        if kind is None:
            kind = "verb.separable"

    if token.regular is True:
        parts.append(VERB_REGULAR_GLYPH[True])
        if kind is None:
            kind = "verb.regular"
    elif token.regular is False:
        parts.append(VERB_REGULAR_GLYPH[False])
        if kind is None:
            kind = "verb.irregular"

    if not parts:
        return None
    return ("".join(parts), kind or "verb.regular")


def _verb_tooltip(token: TokenAnalysis) -> str:
    fragments: list[str] = ["Verb"]
    if token.verb_class:
        fragments.append(token.verb_class)
    if token.regular is True:
        fragments.append("regelmäßig")
    elif token.regular is False:
        fragments.append("unregelmäßig")
    if token.separable:
        fragments.append("trennbar")
    if token.tense:
        fragments.append(f"tense: {token.tense}")
    if token.mood and token.mood != "Ind":
        fragments.append(f"mood: {token.mood}")
    if token.person:
        fragments.append(f"person: {token.person}")
    if token.number:
        fragments.append(f"number: {token.number}")
    return " · ".join(fragments)


def _case_tooltip(token: TokenAnalysis) -> str:
    fragments: list[str] = []
    if token.pos:
        fragments.append(token.pos)
    if token.gender:
        fragments.append(token.gender)
    if token.number:
        fragments.append(token.number)
    if token.case:
        fragments.append(f"case: {token.case}")
    return " · ".join(fragments)


def build(analysis: DocumentAnalysis) -> list[Decoration]:
    line_index = LineIndex(analysis.text)
    decorations: list[Decoration] = []

    for token in analysis.tokens:
        if not token.is_word:
            continue

        token_range = line_index.range(token.start, token.end)
        # Only render decorations for single-line tokens (always true for
        # our extractor, but assert anyway).
        if token_range.start.line != token_range.end.line:
            continue
        start_pos = token_range.start
        end_pos = token_range.end

        if token.pos in {"VERB", "AUX"}:
            verb = _verb_decoration(token)
            if verb is not None:
                glyph, kind = verb
                decorations.append(
                    Decoration(
                        line=end_pos.line,
                        start_character=start_pos.character,
                        end_character=end_pos.character,
                        glyph=glyph,
                        kind=kind,
                        tooltip=_verb_tooltip(token),
                    )
                )
            continue

        if token.case and token.case in CASE_KIND:
            decorations.append(
                Decoration(
                    line=end_pos.line,
                    start_character=start_pos.character,
                    end_character=end_pos.character,
                    glyph=CASE_GLYPH[token.case],
                    kind=CASE_KIND[token.case],
                    tooltip=_case_tooltip(token),
                )
            )
            continue

        if token.degree == "Cmp":
            decorations.append(
                Decoration(
                    line=end_pos.line,
                    start_character=start_pos.character,
                    end_character=end_pos.character,
                    glyph=DEGREE_GLYPH["Cmp"],
                    kind="degree.comparative",
                    tooltip=f"{token.pos} · comparative",
                )
            )
        elif token.degree == "Sup":
            decorations.append(
                Decoration(
                    line=end_pos.line,
                    start_character=start_pos.character,
                    end_character=end_pos.character,
                    glyph=DEGREE_GLYPH["Sup"],
                    kind="degree.superlative",
                    tooltip=f"{token.pos} · superlative",
                )
            )

    return decorations


def build_payload(analysis: DocumentAnalysis) -> dict[str, Any]:
    return {
        "uri": analysis.uri,
        "version": analysis.version,
        "decorations": [d.to_payload() for d in build(analysis)],
    }
