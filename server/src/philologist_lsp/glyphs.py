"""Unicode sigils mirroring the book's geometric marks.

The book uses geometric shapes printed below each declinable word; our LSP
inlay hints can only render text, so we approximate with Unicode glyphs that
read the same way. See DESIGN.md for the full mapping.
"""

from __future__ import annotations

# Case → sigil. spaCy's morph values in the LHS.
CASE_GLYPH: dict[str, str] = {
    "Nom": "◇",
    "Acc": "◆",
    "Dat": "▽",
    "Gen": "▼",
    "Voc": "○",
    "Ins": "◎",
    "Loc": "◉",
    "Abl": "◐",
}

# Degree → sigil (for adjectives / adverbs).
DEGREE_GLYPH: dict[str, str] = {
    "Cmp": "›",
    "Sup": "»",
}

# Verb classification → sigil.
VERB_CLASS_GLYPH: dict[str, str] = {
    "modal": "⌘",
    "aux": "+",
    "full": "",
}

# Regular vs irregular for verbs (German only — None means we don't know).
VERB_REGULAR_GLYPH: dict[bool, str] = {
    True: "□",  # regelmäßig
    False: "■",  # unregelmäßig
}

VERB_SEPARABLE_GLYPH = "↔"

# Tense / mood compact labels for verb hints.
TENSE_LABEL: dict[str, str] = {
    "Past": "Prät",
    "Pres": "Präs",
    "Fut": "Fut",
    "Pqp": "Plusq",
    "Imp": "Imp",
}
MOOD_LABEL: dict[str, str] = {
    "Ind": "Ind",
    "Sub": "Konj",
    "Imp": "Imp",
    "Cnd": "Kond",
}
PERSON_GLYPH: dict[str, str] = {
    "1": "①",
    "2": "②",
    "3": "③",
}
NUMBER_LABEL: dict[str, str] = {
    "Sing": "Sg",
    "Plur": "Pl",
}


def case_sigil(case: str | None) -> str:
    return CASE_GLYPH.get(case or "", "") if case else ""


def degree_sigil(degree: str | None) -> str:
    return DEGREE_GLYPH.get(degree or "", "") if degree else ""


def verb_sigil(
    *,
    verb_class: str | None,
    regular: bool | None,
    separable: bool | None,
    person: str | None,  # accepted for API stability; not rendered as text
    number: str | None,
    tense: str | None,
    mood: str | None,
) -> str:
    """Compose the inlay-hint label for a verb token.

    The book uses pure sigils for verb type (modal / aux / regular /
    irregular / separable). Conjugation features (person, number, tense,
    mood) appear in the hover, not as inline clutter.
    """
    del person, number, tense, mood
    parts: list[str] = []
    if verb_class and verb_class in VERB_CLASS_GLYPH and VERB_CLASS_GLYPH[verb_class]:
        parts.append(VERB_CLASS_GLYPH[verb_class])
    if regular is not None:
        parts.append(VERB_REGULAR_GLYPH[regular])
    if separable:
        parts.append(VERB_SEPARABLE_GLYPH)
    return "".join(parts)
