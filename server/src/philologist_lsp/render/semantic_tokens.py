"""Encode TokenAnalysis records into the LSP semantic-tokens wire format."""

from __future__ import annotations

from philologist_lsp.analyzers.morph import DocumentAnalysis, TokenAnalysis
from philologist_lsp.colors import (
    GENDER_TYPE,
    POS_TYPE_FALLBACK,
    TYPE_INDEX,
    encode_modifiers,
)
from philologist_lsp.render.positions import LineIndex


def _classify(token: TokenAnalysis) -> tuple[str | None, list[str]]:
    """Pick a token type + modifiers for one token."""
    modifiers: list[str] = []

    if token.number == "Plur":
        modifiers.append("plural")
    case_modifier = {
        "Nom": "nominative",
        "Acc": "accusative",
        "Dat": "dative",
        "Gen": "genitive",
    }.get(token.case or "")
    if case_modifier:
        modifiers.append(case_modifier)

    if token.definite == "Def":
        modifiers.append("definite")
    elif token.definite == "Ind":
        modifiers.append("indefinite")

    if token.degree == "Cmp":
        modifiers.append("comparative")
    elif token.degree == "Sup":
        modifiers.append("superlative")

    if token.verb_class == "modal":
        modifiers.append("modal")
    elif token.verb_class == "aux":
        modifiers.append("auxiliary")
    if token.regular is True:
        modifiers.append("regular")
    elif token.regular is False:
        modifiers.append("irregular")
    if token.separable:
        modifiers.append("separable")

    # Decide token type. Gender takes priority for nouns/articles/adjectives/
    # pronouns. For verbs use the verb type; for other parts of speech, use
    # the POS fallback. Anything we don't have a custom type for is skipped
    # (returns None).
    if token.gender and token.gender in GENDER_TYPE:
        return GENDER_TYPE[token.gender], modifiers
    if token.number == "Plur" and token.pos in {"NOUN", "PRON", "DET", "ADJ", "PROPN"}:
        return "philologistPlural", modifiers
    if token.pos in POS_TYPE_FALLBACK:
        return POS_TYPE_FALLBACK[token.pos], modifiers
    return None, modifiers


def encode(analysis: DocumentAnalysis) -> list[int]:
    """Return the flat int array LSP expects for SemanticTokens.data."""
    line_index = LineIndex(analysis.text)
    out: list[int] = []
    prev_line = 0
    prev_char = 0
    for token in analysis.tokens:
        if not token.is_word:
            continue
        type_name, modifiers = _classify(token)
        if type_name is None:
            continue
        type_idx = TYPE_INDEX.get(type_name)
        if type_idx is None:
            continue
        position = line_index.position(token.start)
        end_position = line_index.position(token.end)
        # We don't render multi-line tokens — every word in our analyzer
        # is a single token within a single line.
        if position.line != end_position.line:
            continue
        length = end_position.character - position.character
        if length <= 0:
            continue
        delta_line = position.line - prev_line
        delta_start = (
            position.character - prev_char if delta_line == 0 else position.character
        )
        out.extend(
            [
                delta_line,
                delta_start,
                length,
                type_idx,
                encode_modifiers(modifiers),
            ]
        )
        prev_line = position.line
        prev_char = position.character
    return out
