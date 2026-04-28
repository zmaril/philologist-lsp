# Changelog

## 0.0.1 — initial release

- Per-word morphological analysis via spaCy for ~24 languages
- Auto language detection per paragraph (lingua)
- Custom semantic-token coloring by gender / number
- Case markers as colored bottom-border underlines (nominative / accusative / dative / genitive / vocative / instrumental / locative / ablative)
- Inline glyph markers for verb features (regular / irregular / modal / auxiliary / separable / comparative / superlative)
- Hover popup with morph table, contextual LLM definition (Qwen3.5-0.8B), and sentence orality marker
- Sentence-level orality classification via havelock-orality (71 markers, oral vs literate)
- Document-level orality score in status bar
- Per-sentence CodeLens with marker name + confidence
- Sentence numbering in the gutter
- Bootstrap Python environment via uv on first activation
