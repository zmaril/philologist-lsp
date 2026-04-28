"""Semantic-token type and modifier definitions.

Token types encode gender (or verb category); modifiers encode number,
verb regularity, and morphological accents. The user themes the resulting
classes via editor.semanticTokenColorCustomizations.
"""

from __future__ import annotations

# Custom token types we emit. VSCode's defaults provide nothing useful for
# natural-language morphology, so we register our own.
TOKEN_TYPES: tuple[str, ...] = (
    "philologistMasculine",
    "philologistFeminine",
    "philologistNeuter",
    "philologistCommon",
    "philologistPlural",  # used when gender is unknown but plural is
    "philologistVerb",
    "philologistAdjective",
    "philologistAdverb",
    "philologistParticle",
    "philologistConjunction",
    "philologistInterjection",
)

TOKEN_MODIFIERS: tuple[str, ...] = (
    "plural",
    "definite",
    "indefinite",
    "regular",
    "irregular",
    "modal",
    "auxiliary",
    "separable",
    "comparative",
    "superlative",
    "nominative",
    "accusative",
    "dative",
    "genitive",
)

# Inverse maps for fast encoding.
TYPE_INDEX: dict[str, int] = {t: i for i, t in enumerate(TOKEN_TYPES)}
MOD_INDEX: dict[str, int] = {m: i for i, m in enumerate(TOKEN_MODIFIERS)}


GENDER_TYPE: dict[str, str] = {
    "Masc": "philologistMasculine",
    "Fem": "philologistFeminine",
    "Neut": "philologistNeuter",
    "Com": "philologistCommon",
}

POS_TYPE_FALLBACK: dict[str, str] = {
    "VERB": "philologistVerb",
    "AUX": "philologistVerb",
    "ADJ": "philologistAdjective",
    "ADV": "philologistAdverb",
    "PART": "philologistParticle",
    "CCONJ": "philologistConjunction",
    "SCONJ": "philologistConjunction",
    "INTJ": "philologistInterjection",
}


def encode_modifiers(mods: list[str]) -> int:
    """Pack modifier names into LSP's bitfield format."""
    bits = 0
    for mod in mods:
        idx = MOD_INDEX.get(mod)
        if idx is not None:
            bits |= 1 << idx
    return bits
