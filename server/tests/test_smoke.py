"""Minimal smoke tests. Run with `uv run pytest tests/` from server/.

Heavier tests that exercise spaCy / lingua / havelock / Qwen go in
separate modules and are gated on the [nlp]/[llm] extras being installed.
"""

from __future__ import annotations


def test_server_module_imports() -> None:
    """The server module loads without ML extras installed."""
    from philologist_lsp import server

    assert hasattr(server, "PhilologistServer")
    assert hasattr(server, "main")


def test_disable_marker_regex() -> None:
    """The `philologist: off` marker is detected with reasonable variations."""
    from philologist_lsp.server import _is_disabled_in_file

    assert _is_disabled_in_file("philologist: off\n\nrest of file")
    assert _is_disabled_in_file("# philologist: disable\nrest")
    assert _is_disabled_in_file("<!-- philologist:disabled -->")
    assert _is_disabled_in_file("// philologist : OFF")
    assert not _is_disabled_in_file("regular text\nphilologist mentioned\nbut not the marker")
    assert not _is_disabled_in_file("")
    # Must be in the first 10 lines.
    head = "\n".join(["filler"] * 12) + "\nphilologist: off"
    assert not _is_disabled_in_file(head)


def test_glyph_table_has_all_cases() -> None:
    """Every standard case has a sigil + non-empty CSS color."""
    from philologist_lsp.glyphs import CASE_GLYPH

    for case in ("Nom", "Acc", "Dat", "Gen"):
        assert CASE_GLYPH[case], f"{case} missing glyph"


def test_orality_taxonomy_categorizes_known_markers() -> None:
    """The hand-curated mapping covers each marker visible in havelock.ai screenshots."""
    from philologist_lsp.analyzers.orality_taxonomy import (
        category_for,
        description_for,
    )

    oral_examples = ("vocative", "second_person", "temporal_anchor", "named_individual")
    literate_examples = (
        "nominalization",
        "third_person_reference",
        "qualified_assertion",
        "conditional",
        "metadiscourse",
    )
    for marker in oral_examples:
        assert category_for(marker) == "oral"
        assert description_for(marker)
    for marker in literate_examples:
        assert category_for(marker) == "literate"
        assert description_for(marker)
