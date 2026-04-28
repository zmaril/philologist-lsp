"""Hover content — the markdown morph card per token."""

from __future__ import annotations

from lsprotocol import types as lsp

from philologist_lsp.analyzers.morph import DocumentAnalysis, TokenAnalysis
from philologist_lsp.render.positions import LineIndex


GENDER_LABEL: dict[str, str] = {
    "Masc": "masculine",
    "Fem": "feminine",
    "Neut": "neuter",
    "Com": "common",
}
NUMBER_LABEL: dict[str, str] = {
    "Sing": "singular",
    "Plur": "plural",
    "Dual": "dual",
}
CASE_LABEL: dict[str, str] = {
    "Nom": "nominative",
    "Acc": "accusative",
    "Dat": "dative",
    "Gen": "genitive",
    "Voc": "vocative",
    "Ins": "instrumental",
    "Loc": "locative",
    "Abl": "ablative",
}

# Inline CSS that mirrors the editor's bottom-border underline styles, so
# the hover tooltip echoes the visual encoding the reader sees in-text.
# VSCode's markdown HTML sanitizer is strict — it only allows a handful of
# CSS properties through, notably `color`, `background-color`,
# `font-weight`, `font-style`, and `text-decoration`. Border / padding /
# margin are stripped. So we encode the case via a colored
# `text-decoration: underline` with a matching style keyword instead of
# `border-bottom`. Hex defaults must stay in sync with package.json's
# `philologist.case.*` color contributions.
# Colored unicode shapes — render reliably in VSCode hover popups
# regardless of any HTML sanitization. Each dimension gets its own shape so
# the eye can tell case-vs-gender-vs-verb apart at a glance, while the
# colors match the corresponding editor decoration.
#
# Case → squares (matches editor underline)
CASE_EMOJI: dict[str, str] = {
    "Nom": "🟦",
    "Acc": "🟥",
    "Dat": "🟧",
    "Gen": "🟩",
    "Voc": "🟪",
    "Ins": "🟦",
    "Loc": "🟦",
    "Abl": "🟪",
}

# Gender → hearts (pink heart fills the gap left by the missing pink
# square emoji; uniformly hearts so all gender markers share a shape).
GENDER_EMOJI: dict[str, str] = {
    "Masc": "💙",
    "Fem": "💗",
    "Neut": "💜",
    "Com": "🧡",
}

# Number → green heart for plural; singular gets no marker.
NUMBER_EMOJI: dict[str, str] = {
    "Plur": "💚",
}

# Verb class / regularity / separability → circles.
VERB_CLASS_EMOJI: dict[str, str] = {
    "modal": "🟣",
    "aux": "⚪",
}
REGULAR_EMOJI = "🟢"
IRREGULAR_EMOJI = "🔴"
SEPARABLE_EMOJI = "🟡"


def _styled_case(case_value: str) -> str:
    label = CASE_LABEL.get(case_value, case_value)
    emoji = CASE_EMOJI.get(case_value, "")
    return f"{emoji} **{label}**" if emoji else label


def _styled_gender(gender_value: str) -> str:
    label = GENDER_LABEL.get(gender_value, gender_value)
    emoji = GENDER_EMOJI.get(gender_value, "")
    return f"{emoji} **{label}**" if emoji else label


def _styled_number(number_value: str) -> str:
    label = NUMBER_LABEL.get(number_value, number_value)
    emoji = NUMBER_EMOJI.get(number_value, "")
    return f"{emoji} **{label}**" if emoji else label


def _styled_verb_class(verb_class: str) -> str:
    emoji = VERB_CLASS_EMOJI.get(verb_class, "")
    return f"{emoji} **{verb_class}**" if emoji else verb_class


def _styled_regularity(regular: bool) -> str:
    if regular:
        return f"{REGULAR_EMOJI} **regelmäßig**"
    return f"{IRREGULAR_EMOJI} **unregelmäßig**"


TENSE_LABEL: dict[str, str] = {
    "Pres": "present",
    "Past": "past",
    "Fut": "future",
    "Imp": "imperfect",
    "Pqp": "pluperfect",
}
MOOD_LABEL: dict[str, str] = {
    "Ind": "indicative",
    "Sub": "subjunctive",
    "Imp": "imperative",
    "Cnd": "conditional",
}


def _row(label: str, value: str | None) -> str | None:
    if value is None:
        return None
    return f"| {label} | {value} |"


def find_token(
    analysis: DocumentAnalysis, position: lsp.Position
) -> tuple[TokenAnalysis, lsp.Range] | None:
    """Locate the analysis token at `position`, with its LSP range."""
    line_index = LineIndex(analysis.text)
    for token in analysis.tokens:
        if not token.is_word:
            continue
        token_range = line_index.range(token.start, token.end)
        if _position_in_range(position, token_range):
            return token, token_range
    return None


def sentence_for(analysis: DocumentAnalysis, token: TokenAnalysis) -> str:
    """Find the smallest line-bounded chunk of the document containing the
    token. Used as context when prompting the definition LLM. We avoid
    feeding multi-paragraph blobs since the LLM should focus on local
    usage."""
    text = analysis.text
    start = text.rfind("\n", 0, token.start) + 1
    end = text.find("\n", token.end)
    if end == -1:
        end = len(text)
    return text[start:end].strip()


def _morph_table(token: TokenAnalysis) -> str:
    """Just the morphology table (without header or definition)."""
    rows: list[str] = []
    rows.append("|       |       |")
    rows.append("|-------|-------|")
    body: list[str | None] = [
        _row("Lemma", token.lemma),
        _row("Language", token.language),
        _row("Gender", _styled_gender(token.gender) if token.gender else None),
        _row("Number", _styled_number(token.number) if token.number else None),
        _row("Case", _styled_case(token.case) if token.case else None),
        _row("Person", token.person),
        _row(
            "Tense",
            TENSE_LABEL.get(token.tense or "", token.tense) if token.tense else None,
        ),
        _row(
            "Mood", MOOD_LABEL.get(token.mood or "", token.mood) if token.mood else None
        ),
        _row("Verb form", token.verb_form),
        _row("Voice", token.voice),
        _row("Definite", token.definite),
        _row("Pronoun type", token.pron_type),
        _row(
            "Degree", token.degree if token.degree and token.degree != "Pos" else None
        ),
        _row(
            "Verb class",
            _styled_verb_class(token.verb_class) if token.verb_class else None,
        ),
    ]
    if token.regular is not None and token.language == "de":
        body.append(_row("Regularity", _styled_regularity(token.regular)))
    if token.separable:
        body.append(_row("Separable", f"{SEPARABLE_EMOJI} **yes**"))
    rows.extend(r for r in body if r)
    return "\n".join(rows)


def build(
    analysis: DocumentAnalysis,
    position: lsp.Position,
    definition: str | None = None,
    orality_block: str | None = None,
) -> lsp.Hover | None:
    """Return a Hover for the token at `position`, or None.

    Sections, top to bottom:
        1. Orality marker (if the token's sentence is classified)
        2. ── divider ──
        3. Word header (lemma + POS)
        4. Definition (if available)
        5. ── divider ──
        6. Morphology table

    Each section is separated by a horizontal rule so the reader can scan
    from "what kind of utterance is this?" down to "what does this exact
    word do here?".
    """
    located = find_token(analysis, position)
    if located is None:
        return None
    token, token_range = located

    sections: list[str] = []

    if orality_block:
        sections.append(orality_block.strip())

    word_section = [f"**{token.text}** — `{token.pos}` ({token.tag})"]
    if definition:
        word_section.append("")
        word_section.append(definition.strip())
    sections.append("\n".join(word_section))

    sections.append(_morph_table(token))

    md = "\n\n---\n\n".join(sections)
    return lsp.Hover(
        contents=lsp.MarkupContent(kind=lsp.MarkupKind.Markdown, value=md),
        range=token_range,
    )


def _position_in_range(pos: lsp.Position, rng: lsp.Range) -> bool:
    if pos.line < rng.start.line or pos.line > rng.end.line:
        return False
    if pos.line == rng.start.line and pos.character < rng.start.character:
        return False
    if pos.line == rng.end.line and pos.character > rng.end.character:
        return False
    return True
