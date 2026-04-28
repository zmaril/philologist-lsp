# Philologist

Reads natural-language text the way a philologist does, in your editor.

- **Per-word morphology** for ~24 languages via spaCy: gender colors, case underlines (matching the visual encoding of Barbara Avila Vissirini's *Dieses kleine Buch ist für dich*), tense / mood / person / regularity for verbs.
- **Sentence-level orality scoring** for English via [havelock-orality](https://huggingface.co/thestalwart/havelock-orality): a 71-class oral / literate marker classifier from Walter Ong's framework, surfaced as CodeLenses above each sentence and a document-level score in the status bar.
- **One-sentence contextual definitions** for any word, generated locally by Qwen3.5-0.8B and shown in hover popups.
- **Auto language detection** per paragraph; mixed-language documents work — German, English, Spanish, French, Italian, Russian, Japanese, Chinese, etc. all coexist.
- Everything runs on your machine. No cloud APIs. No network round-trips after first-run model downloads.

## Requirements

- **VSCode 1.85+**
- **[uv](https://docs.astral.sh/uv/)** on `PATH` (Astral's Python package manager — used to create and populate the extension's managed Python environment)
- **~3 GB disk** for spaCy models, BERT base, the orality classifier + regressor, and the definition LLM. Downloads happen once on first use, with progress notifications.
- macOS Apple Silicon, Linux, or Windows. Apple MPS / CUDA accelerate inference; CPU is slower but works.

If `uv` isn't installed, the extension shows a one-click install link and refuses to activate. Install it once and reload.

## How to use

1. Install the extension.
2. Open any `.txt` or `.md` file. The extension activates and bootstraps a Python environment at `~/.philologist-lsp/venv` on first run.
3. Wait for first-run downloads (notifications appear in the status area). German, English, then any other languages your document contains will pull their spaCy models in the background; analysis fills in progressively.
4. Read.

## What you'll see

**On every word.** Words are colored by grammatical gender (blue masculine, pink feminine, purple neuter, …) via VSCode semantic tokens. Declined words get a colored bottom-border whose style encodes case: solid for nominative, dashed for dative, dotted for genitive, etc. Verbs get a small inline glyph for their class (■ irregular, □ regular, ⌘ modal, + auxiliary, ↔ separable).

**On every sentence (English).** A CodeLens above each sentence labels its dominant rhetorical marker — `🟢 VOCATIVE · 88%`, `🟣 NOMINALIZATION +2 · 43%` — drawn from havelock-orality's 71-class taxonomy. The status bar shows the document-level oral / literate score.

**On hover.** Lemma, full morph table with colored markers, an LLM-generated definition of the inflected form as it appears in context, and the orality marker for the sentence the word lives in. Hover any word in any English sentence to see the marker classification.

## Settings

| Setting | Default | What it does |
|---|---|---|
| `philologist.spacyModelSize` | `md` | spaCy core-model size: `sm` / `md` / `lg` / `trf`. Bigger is more accurate, slower. |
| `philologist.serverPath` | `""` | Override path to the language server executable (advanced). |
| `philologist.pythonPath` | `""` | Override Python interpreter (advanced). |

The default color palette for the gender / case / orality decorations is pre-configured; users can override via `editor.semanticTokenColorCustomizations` and `workbench.colorCustomizations` (color IDs are listed in the package contributions).

## Known limitations

- **Orality is English-only.** havelock-orality is a `bert-base-uncased` fine-tune; non-English paragraphs are silently skipped.
- **Languages without spaCy core models** (Latin, Hebrew, Sanskrit, Arabic, …) render as plain text.
- **Hover line styles** can't perfectly mirror editor underline styles. VSCode's markdown sanitizer strips most CSS, so hover uses colored emoji squares to indicate case/gender/verb features instead.
- **First-run download is heavy.** Each spaCy language model is ~50 MB; havelock weights are ~880 MB; Qwen3.5-0.8B is ~1.6 GB. Plan for ~3 GB disk and a few minutes the first time.
- **Latency.** On Apple Silicon (MPS) the LLM produces ~14 tok/s and havelock ~50 ms/sentence. On CPU it's roughly 4–10× slower.
- **Definition quality** at 0.8B parameters is uneven. High-frequency words in well-represented languages are good; rare technical vocabulary or non-Latin scripts can produce confident-but-wrong outputs.

## Credits

- Visual grammar inspired by Barbara Avila Vissirini, *Dieses kleine Buch ist für dich* (graphical grammar for German as a foreign language).
- Orality framework from Walter Ong's *Orality and Literacy* (1982); model from [thestalwart/havelock-orality](https://huggingface.co/thestalwart/havelock-orality) and [havelock.ai](https://havelock.ai).
- Built on [pygls](https://github.com/openlawlibrary/pygls), [lsprotocol](https://github.com/microsoft/lsprotocol), [spaCy](https://spacy.io), [lingua-py](https://github.com/pemistahl/lingua-py), [transformers](https://huggingface.co/transformers), and [vscode-languageclient](https://github.com/microsoft/vscode-languageserver-node).
