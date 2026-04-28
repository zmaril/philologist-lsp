"""Per-language verb-regularity lookup tables.

We currently ship German only. A verb listed here is treated as
unregelmäßig/irregular (strong, mixed, or modal). All other verbs in spaCy's
output default to regelmäßig/regular.
"""

from __future__ import annotations

import json
from importlib.resources import files

_TABLES: dict[str, frozenset[str]] = {}


def is_irregular(language: str, lemma: str) -> bool | None:
    """Return True/False if we have a table for this language, else None."""
    table = _TABLES.get(language)
    if table is None:
        try:
            data = json.loads(
                files("philologist_lsp.verb_regularity").joinpath(f"{language}.json").read_text()
            )
        except (FileNotFoundError, ModuleNotFoundError):
            return None
        table = frozenset(data)
        _TABLES[language] = table
    return lemma in table
