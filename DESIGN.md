# philologist-lsp — design

A Language Server that surfaces the morphological and rhetorical structure of natural-language text the way a philologist reads it: each word annotated with its grammatical role (color + sigil), each passage scored on the oral↔literate spectrum.

Inspired by Barbara Avila Vissirini's *Dieses kleine Buch ist für dich* (graphical grammar for German as a foreign language) and the orality–literacy theory of Walter Ong / Eric Havelock.

## Goals

1. **Mirror the book in the editor.** When you open a text file in VSCode, every declinable word is colored by gender/number and sigil-marked by case; every verb is sigil-marked by tense/mood/person and tagged regular/irregular. Hovering shows the full morph card.
2. **All languages spaCy supports.** Auto-detect language per paragraph; lazy-load and cache the right spaCy model. Languages without a spaCy model degrade gracefully (sentence segmentation only).
3. **Layer orality on top.** For English text, run [havelock-orality](https://huggingface.co/thestalwart/havelock-orality) and surface its three heads as code lenses (regressor), workspace diagnostics (category), and inline span markers (subtype).
4. **Local only.** No external API calls. spaCy models, havelock weights, and lingua language-id models all download on first use into a local cache.
5. **Pure LSP for v1.** Use only LSP-standard channels (semantic tokens, inlay hints, hover, code lens, diagnostics, document symbols). No `TextEditorDecorationType` yet — that's a Phase 5+ enhancement if Unicode glyphs prove insufficient.

## Non-goals (for now)

- Extracting strings from source code (docstrings, comments, JSX text).
- Drawing custom shapes / SVG sigils. Unicode geometric glyphs only.
- Server-side LLM calls. Everything runs locally.
- Per-language verb-regularity tables for languages other than German. We ship a German strong/mixed-verb list; other languages report POS only on hover.
- Authoring features (autocomplete, refactor). This is a read-only annotator.

## Architecture

```
┌─────────────────────────────┐         ┌──────────────────────────────────┐
│  VSCode extension (TS)      │  stdio  │  Python LSP server (pygls)       │
│  vscode-languageclient      │◄───────►│                                  │
│  spawns python -m           │   LSP   │  detect → spaCy → render         │
│  philologist_lsp            │         │              ↘ orality (English) │
└─────────────────────────────┘         └──────────────────────────────────┘
                                                    │
                                                    ▼
                                        ~/Library/Application Support/
                                          philologist-lsp/
                                            spacy/    havelock/    lingua/
```

### Server (Python)

```
server/
├── pyproject.toml
└── src/philologist_lsp/
    ├── __main__.py           # python -m philologist_lsp → server.start()
    ├── server.py             # pygls LanguageServer, capability registration
    ├── detect.py             # lingua wrapper, paragraph-level language id
    ├── spacy_pool.py         # lazy load + auto-download per ISO code
    ├── analyzers/
    │   ├── morph.py          # Doc → universal feature extraction
    │   └── orality.py        # havelock 3-head inference
    ├── render/
    │   ├── semantic_tokens.py
    │   ├── inlay_hints.py
    │   ├── hover.py
    │   ├── code_lens.py
    │   ├── diagnostics.py
    │   └── document_symbols.py
    ├── glyphs.py             # case, tense, mood, voice → Unicode sigil
    ├── colors.py             # gender × number → semantic-token type name
    ├── verb_regularity/
    │   ├── __init__.py
    │   └── de.json           # German strong + mixed verbs (Duden list)
    └── cache.py              # platformdirs + sha256 download helper
```

### Client (TypeScript)

```
extension/
├── package.json              # activationEvents + contributes
├── tsconfig.json
└── src/extension.ts          # spawn server, register LanguageClient
```

The extension does the bare minimum: detect Python, ensure a venv exists with the server installed, spawn the server, register it as a LanguageClient. No UI of its own — every annotation comes back over LSP.

## Language detection

We use [`lingua-language-detector`](https://github.com/pemistahl/lingua-py) rather than `langdetect` because it's accurate on short text (a single sentence). Trade-off: ~100MB on disk for the high-accuracy mode. Acceptable.

- **Granularity:** per paragraph (blank-line-separated). Paragraphs shorter than ~30 chars fall back to the document's dominant language.
- **Confidence threshold:** 0.65. Below that, paragraph is rendered with sentence-segmentation only (no morph).
- **Caching:** detection results are memoized per-paragraph by content hash for the lifetime of the document.

## spaCy pool

`spacy_pool.py` maintains `dict[str, spacy.Language]` keyed by ISO code. Resolution order on miss:

1. Look up the canonical model name for the language (e.g. `de` → `de_core_news_md`, `en` → `en_core_web_md`, `zh` → `zh_core_web_md`). Mapping table lives in `spacy_pool.LANGUAGE_MODELS`.
2. If not installed, run `spacy.cli.download(model_name)` while emitting `$/progress` over LSP. Subsequent loads are instant.
3. If no model exists for that ISO code, fall back to `xx_sent_ud_sm` (multi-language sentence segmenter). Render only sentence boundaries; skip morph.

`md` size models are the default — fast on CPU, decent morphology. Users can opt into `lg` or `trf` per language via settings.

## Morphological analysis (analyzers/morph.py)

We extract a universal feature dict per token, derived from spaCy's `Token.morph`. The same dict shape works across all languages — features that don't apply to a language are absent.

```python
{
  "text": "den",
  "lemma": "der",
  "pos": "DET",
  "tag": "ART",
  "case": "Acc",         # Nom, Acc, Dat, Gen, Voc, Ins, Loc, ...
  "gender": "Masc",      # Masc, Fem, Neut, Com
  "number": "Sing",      # Sing, Plur, Dual
  "person": None,
  "tense": None,         # Pres, Past, Imp, Fut, ...
  "mood": None,          # Ind, Sub, Imp, Cond, ...
  "verb_form": None,     # Inf, Fin, Part, Ger, ...
  "voice": None,         # Act, Pass, Mid
  "definite": "Def",     # Def, Ind
  "pron_type": None,     # Prs, Dem, Int, Ind, Rel, Neg, Tot, ...
  "degree": None,        # Pos, Cmp, Sup
  "verb_class": None,    # full | aux | modal           (German only for MVP)
  "regular": None,       # True | False | None          (German only for MVP)
  "separable": None,     # True | False                 (German only for MVP)
}
```

`verb_class`, `regular`, and `separable` are derived in language-specific shims:

- `verb_class`: lemma in {sein, haben, werden} → aux; lemma in {können, dürfen, müssen, sollen, wollen, mögen, möchten} → modal; else full.
- `regular`: lookup against `verb_regularity/de.json`. Returns `False` for strong/mixed verbs, `True` if not in list, `None` if no table for the language.
- `separable`: presence of a `PTKVZ` token with `svp` dep edge.

## Visual encoding (the "mirror the book" core)

The book uses two channels: **color** (gender × number) and **sigil under the word** (case for nouns/articles/adj/pronouns; mood/tense/regularity for verbs). LSP gives us:

### Semantic tokens — for color

Custom token types registered at `initialize`:

```
philologist.masculine
philologist.feminine
philologist.neuter
philologist.common         # Swedish, Dutch
philologist.singular       # modifier
philologist.plural         # modifier
philologist.verb.regular
philologist.verb.irregular
philologist.verb.modal
philologist.verb.auxiliary
```

Users theme via `editor.semanticTokenColorCustomizations`. We ship a default theme block in the README:

```json
{
  "[Default Dark Modern]": {
    "rules": {
      "philologist.masculine": "#5BA3FF",
      "philologist.feminine":  "#FF6B9D",
      "philologist.neuter":    "#9D5BFF",
      "philologist.plural":    { "fontStyle": "italic" }
    }
  }
}
```

### Inlay hints — for sigils

After-token text labels using Unicode geometric shapes. Core sigils (subject to iteration; the legend is meant to mirror book p.222 as closely as text rendering allows):

| Feature | Sigil |
|---|---|
| Nominative | `◇` |
| Accusative | `◆` |
| Dative | `▽` |
| Genitive | `▼` |
| Vocative | `○` |
| Instrumental | `◎` |
| Locative | `◉` |
| Verb · regular | `□` |
| Verb · irregular | `■` |
| Verb · modal | `⌘` |
| Verb · auxiliary | `+` |
| Verb · separable | `↔` |
| Comparative | `›` |
| Superlative | `»` |

Hint position: `InlayHintKind.Type`, after the token, with a leading thin space. Padding-left on, padding-right off, so the cluster reads as a single unit.

### Hover — for the full morph card

Markdown table on hover. Example for `den` in `Ich sehe den Mann`:

```
**den** — definite article

|             |               |
|-------------|---------------|
| Lemma       | der           |
| POS         | DET           |
| Gender      | masculine     |
| Number      | singular      |
| Case        | accusative    |
| Definite    | yes           |

→ See: Artikel im Akkusativ
```

For verbs we add `regelmäßig` / `unregelmäßig` (German only; other languages omit). MVP does *not* include full conjugation tables — that's a Phase 4+ concern.

### Document symbols — for outline

Sentences as level-1 symbols, each labeled with its dominant tense + voice (e.g. `Sentence 3: Past, active`). Useful for navigating long texts and getting a sense of register at a glance.

## Orality (analyzers/orality.py)

Three heads on a shared `bert-base-uncased` backbone. **English-only** until havelock expands. Trigger: paragraph language detected as `en` with confidence ≥ 0.65.

### Head 1 — Regressor → Code Lens

A single linear layer + sigmoid producing one float ∈ [0,1] per chunk. Renders as a code lens at the top of each English paragraph:

```
Orality 0.42 · mixed
```

Document-level aggregate appears in the status bar.

Cost: cheapest. Runs on every change (debounced).

### Head 2 — Category classifier → Workspace diagnostic

Discrete label (oral / literate, plus possibly subcategories per the model card). Appears as a single workspace-level diagnostic at the top of each English paragraph with severity `Information`. Provides the "narrative" of the paragraph at a glance.

Cost: cheap. Runs alongside the regressor.

### Head 3 — Subtype classifier → Inline diagnostics

68-class span classifier — the *crown jewel* of the orality side. Each span gets a diagnostic with severity `Hint` (faint underline, only visible in Problems panel by default; users can toggle).

Pipeline:

1. Tokenize the English paragraph with BertTokenizer. Window into 512-token chunks with stride 128 to handle paragraphs longer than the model's context.
2. Run the subtype head on each window. Per-token logits over 68 + 1 classes (one extra for "no marker").
3. Decode contiguous same-label runs into spans (no BIO assumed unless the model card specifies; if so, swap in BIO decoding).
4. Map sub-word spans back to original character offsets.
5. Aggregate across windows by max-confidence at each character position.
6. Emit one `Diagnostic` per span:
   - `severity = DiagnosticSeverity.Hint`
   - `source = "havelock"`
   - `code = subtype_id` (integer)
   - `message = subtype_name` (e.g. "epithet", "formulaic phrase", "nominalization")
   - `tags = [Unnecessary]` *not* set — Hint severity alone is enough for faint rendering.

Settings:

- `philologist.orality.subtype.minConfidence` (default 0.6) — drop spans below this.
- `philologist.orality.subtype.enabled` (default true).
- `philologist.orality.subtype.filter` — optional list of subtype names to include / exclude.

Cost: most expensive head. Runs on save by default; can be set to debounced-on-change.

### Weight loading

On first English paragraph encounter:

1. `huggingface_hub.snapshot_download("thestalwart/havelock-orality", cache_dir=<cache>/havelock)` — gets all `.pt` files + tokenizer config.
2. Build a single `nn.Module` with shared BERT + three heads. Load each head's `.pt` into the right submodule.
3. Move to MPS (Apple Silicon) if available, else CPU. Inference runs in a worker thread to keep the LSP responsive.

Progress is reported via `$/progress`. Total weight ≈ 440MB.

### Why not run havelock on non-English text?

The base model is `bert-base-uncased`, a monolingual English model. Running it on German (or any other language) would emit numbers but those numbers carry no signal — the encoder has no representation for non-English tokens. Better to stay silent than to lie convincingly.

## Performance

- Debounce `didChange` at 250ms.
- Morph analysis is incremental: only re-analyze paragraphs that changed (paragraph hash → cached `Doc`).
- Orality runs in a thread pool to avoid blocking morph rendering.
- Heavy imports (`torch`, `transformers`) are deferred until the first English paragraph is detected.

## Settings (extension contributes)

```json
{
  "philologist.spacyModelSize": "md",          // sm | md | lg | trf
  "philologist.spacyDownloadOnFirstUse": true,
  "philologist.orality.enabled": true,
  "philologist.orality.subtype.enabled": true,
  "philologist.orality.subtype.minConfidence": 0.6,
  "philologist.languageDetect.minConfidence": 0.65,
  "philologist.cacheDir": ""                   // override default cache location
}
```

## Phasing

- **P0 — bootstrap.** Repo skeleton, server stdio, extension client, hello-world activation.
- **P1 — language detect + spaCy pool.** lingua, lazy-load + auto-download with progress, paragraph-level caching.
- **P2 — morph rendering.** Semantic tokens + inlay hints + hover. German verb regularity. Default token-color theme in README.
- **P3 — orality regressor + category.** First-run havelock weight download, paragraph code lens, status bar.
- **P4 — orality subtype.** 68-class span decoding, sliding window, diagnostics with min-confidence filter.
- **P5 — packaging.** README polish, marketplace metadata, `.vsix` build, troubleshooting docs.

Future (post-MVP): per-language verb regularity tables; full conjugation tables on hover; client-side `TextEditorDecorationType` for true sigils; document-symbol outline; comments/strings extraction from code.

## Open risks

- **Python distribution.** We require Python ≥ 3.10 and `uv` on the user's machine. The extension creates a venv at `~/.philologist-lsp/venv` on first activation. If `uv` is missing we prompt the user to install it. Not a fully self-contained extension. Acceptable for v1.
- **Model download size.** spaCy md models (~50MB each) × N languages + havelock (~440MB) + lingua (~100MB) adds up. We surface progress and let the user pre-warm via a command (`Philologist: Pre-download models`).
- **Glyph rendering.** Inlay hints render in the editor's font. Some Unicode shapes look weak in narrow programming fonts. We may need a curated list of "fonts that render the legend well" in the README.
