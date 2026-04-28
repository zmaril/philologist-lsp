"""Universal morphological feature extraction from a spaCy Doc.

The same TokenAnalysis shape applies to every language; features that don't
apply (e.g. case for English) are simply None. Render layers (semantic
tokens, inlay hints, hover) read these records and decide how to display
each one.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from philologist_lsp.verb_regularity import is_irregular

if TYPE_CHECKING:
    # spaCy is an optional `[nlp]` extra. Type hints stay as strings under
    # `from __future__ import annotations`, so deferring these imports lets
    # the module load without the full ML stack installed (useful for CI
    # import smoke tests).
    from spacy.tokens import Doc, Token


# spaCy lemmas. Wider than just German aux/modal because we want the same
# extractor to handle other languages cleanly later.
GERMAN_AUX_LEMMAS: frozenset[str] = frozenset({"sein", "haben", "werden"})
GERMAN_MODAL_LEMMAS: frozenset[str] = frozenset(
    {"können", "dürfen", "müssen", "sollen", "wollen", "mögen", "möchten"}
)


@dataclass(frozen=True, slots=True)
class TokenAnalysis:
    """One token's morphological profile.

    Offsets are absolute character positions within the source document.
    """

    text: str
    lemma: str
    pos: str           # spaCy UPOS, e.g. "NOUN", "VERB", "DET", "ADJ"
    tag: str           # spaCy fine-grained tag (language-specific)
    start: int
    end: int
    language: str      # ISO 639-1 code

    case: str | None
    gender: str | None
    number: str | None
    person: str | None
    tense: str | None
    mood: str | None
    verb_form: str | None
    voice: str | None
    definite: str | None
    pron_type: str | None
    degree: str | None

    # Derived (per-language).
    verb_class: str | None       # "full" | "aux" | "modal" | None
    regular: bool | None         # True | False | None
    separable: bool | None       # True | False | None

    @property
    def is_word(self) -> bool:
        """Whitespace + punctuation are not words for our purposes."""
        return self.pos not in {"SPACE", "PUNCT", "SYM", "X"}


def _morph_feature(token: Token, key: str) -> str | None:
    val = token.morph.get(key)
    if not val:
        return None
    return val[0]


def _verb_class(language: str, lemma: str, pos: str) -> str | None:
    if pos not in {"VERB", "AUX"}:
        return None
    if language == "de":
        if lemma in GERMAN_AUX_LEMMAS:
            return "aux"
        if lemma in GERMAN_MODAL_LEMMAS:
            return "modal"
        return "full"
    # No table for other languages yet.
    return None


def _separable(language: str, token: Token) -> bool | None:
    if language != "de":
        return None
    # In spaCy's German model, separable particles attach via the SVP
    # dependency. Detection here is "lemma is a verb that has an SVP child".
    if token.pos_ not in {"VERB", "AUX"}:
        return None
    return any(child.dep_ == "svp" for child in token.children)


def extract_tokens(
    doc: Doc,
    *,
    language: str,
    document_offset: int,
) -> list[TokenAnalysis]:
    """Walk a spaCy Doc and produce TokenAnalysis records.

    `document_offset` is added to each token's idx so the resulting char
    offsets are relative to the whole text document, not just the paragraph.
    """
    out: list[TokenAnalysis] = []
    for tok in doc:
        if tok.is_space:
            continue
        verb_class = _verb_class(language, tok.lemma_, tok.pos_)
        regular: bool | None = None
        if verb_class is not None and language == "de":
            irregular = is_irregular("de", tok.lemma_)
            if irregular is None:
                regular = True
            else:
                regular = not irregular
        out.append(
            TokenAnalysis(
                text=tok.text,
                lemma=tok.lemma_,
                pos=tok.pos_,
                tag=tok.tag_,
                start=document_offset + tok.idx,
                end=document_offset + tok.idx + len(tok.text),
                language=language,
                case=_morph_feature(tok, "Case"),
                gender=_morph_feature(tok, "Gender"),
                number=_morph_feature(tok, "Number"),
                person=_morph_feature(tok, "Person"),
                tense=_morph_feature(tok, "Tense"),
                mood=_morph_feature(tok, "Mood"),
                verb_form=_morph_feature(tok, "VerbForm"),
                voice=_morph_feature(tok, "Voice"),
                definite=_morph_feature(tok, "Definite"),
                pron_type=_morph_feature(tok, "PronType"),
                degree=_morph_feature(tok, "Degree"),
                verb_class=verb_class,
                regular=regular,
                separable=_separable(language, tok),
            )
        )
    return out


@dataclass(frozen=True, slots=True)
class Sentence:
    """A sentence span anchored to absolute offsets in the source document.

    `language` is the ISO code of the paragraph the sentence belongs to,
    so downstream consumers (e.g. orality) know whether to run on it.
    """

    text: str
    start: int
    end: int
    language: str


@dataclass(frozen=True, slots=True)
class DocumentAnalysis:
    """All tokens + sentences for one text document, plus the source text
    used to build them (so we can derive line/character positions on the
    fly)."""

    uri: str
    text: str
    tokens: tuple[TokenAnalysis, ...]
    sentences: tuple[Sentence, ...]
    version: int   # text-document version this analysis belongs to
