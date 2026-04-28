# philologist-lsp

A Language Server that surfaces the morphological and rhetorical structure of natural-language text the way a philologist reads it.

- **Per-token morphology** via spaCy: gender, number, case, tense, mood, voice. Rendered as semantic-token colors and `TextEditorDecorationType` underlines.
- **Sentence-level orality** for English via [havelock-orality](https://huggingface.co/thestalwart/havelock-orality): a 71-class oral / literate marker classifier surfaced as CodeLenses, plus a document-level regressor in the status bar.
- **Per-word definitions** generated locally by [Qwen3.5-0.8B](https://huggingface.co/Qwen/Qwen3.5-0.8B) on hover.
- **Auto language detection** per paragraph via [lingua](https://github.com/pemistahl/lingua-py); spaCy models for ~24 languages auto-download on first use.
- Runs locally. No cloud APIs after the first model downloads.

## Install

Grab the `.vsix` from the [latest release](https://github.com/zmaril/philologist-lsp/releases/latest) and install it:

```bash
code --install-extension philologist-lsp-<version>.vsix
```

Or in VSCode: `Extensions: Install from VSIX…` and pick the downloaded file.

**Requirements:**
- VSCode 1.85+
- [`uv`](https://docs.astral.sh/uv/) on `PATH` (the extension uses it to manage its own Python venv)
- ~3 GB free disk for first-run language-model downloads (spaCy models, BERT, Qwen). Done lazily, with progress notifications.

On first activation, the extension creates `~/.philologist-lsp/venv` and installs the bundled wheel into it. Subsequent updates re-install in place.

## Inspirations

- **Visual grammar**: Barbara Avila Vissirini, *[Dieses kleine Buch ist für dich](https://barbaravissirini.com/dieses-kleine-buch)* — a graphical grammar for German as a foreign language. The case-underline + gender-color encoding mirrors hers as closely as VSCode allows.
- **Orality framework**: Walter Ong, *[Orality and Literacy: The Technologizing of the Word](https://en.wikipedia.org/wiki/Orality_and_Literacy)* (1982). The 71-class taxonomy and the oral / literate split come from this framework.
- **Theory background**: Eric Havelock, *[Preface to Plato](https://en.wikipedia.org/wiki/Eric_A._Havelock#Preface_to_Plato)* (1963), which the [havelock.ai](https://havelock.ai/) project is named after.

## Repo layout

```
philologist-lsp/
├── server/             # Python LSP (pygls)
│   ├── pyproject.toml
│   └── src/philologist_lsp/
├── extension/          # VSCode extension (TypeScript)
│   ├── package.json
│   └── src/extension.ts
└── .github/workflows/  # CI + release
```

## Running locally (dev)

Prerequisites: `python ≥ 3.10`, [`uv`](https://docs.astral.sh/uv/), `node ≥ 20`, VSCode.

```bash
# server
cd server
uv sync                            # installs spaCy, transformers, torch, etc.
uv run python -m philologist_lsp   # smoke test (Ctrl-C to exit)

# extension
cd ../extension
npm install
npm run typecheck
```

`uv sync` defaults to installing the `nlp` + `llm` extras via `[tool.uv] default-extras`. To skip the ML stack (e.g. to verify the server module still loads with only base deps), run `uv sync --no-default-extras`.

In VSCode: open `extension/`, press `F5` to launch the Extension Development Host. Open a `.txt` or `.md` file in the new window — the language server will activate.

## Releasing

Releases are built and published to GitHub Releases by `.github/workflows/release.yml` on tag push. The workflow syncs the version from the tag into both `extension/package.json` and `server/pyproject.toml`, builds the `.vsix`, and attaches it to a release with auto-generated notes:

```bash
git tag v0.0.10
git push origin v0.0.10
```

Manual builds without a release can be triggered from the Actions tab via *Run workflow*.

## Theming

The extension ships a default color palette for its custom semantic-token types (`philologistMasculine`, `philologistFeminine`, `philologistNeuter`, `philologistCommon`, `philologistPlural`, `philologistVerb`, `philologistAdjective`, …) and case-underline colors (`philologist.case.*`) via `contributes.configurationDefaults`. Colors apply automatically when the extension activates.

To override:

```json
"editor.semanticTokenColorCustomizations": {
  "rules": {
    "philologistMasculine": "#88E0FF",
    "philologistFeminine":  "#FFB6C1"
  }
},
"workbench.colorCustomizations": {
  "philologist.case.dative": "#FFD700"
}
```

Modifiers available: `plural`, `definite`, `indefinite`, `regular`, `irregular`, `modal`, `auxiliary`, `separable`, `comparative`, `superlative`, `nominative`, `accusative`, `dative`, `genitive`.

## Configuration + Commands

`philologist.*` settings let you toggle morphology, orality, and LLM definitions individually. Command palette: `Philologist: Restart Server`, `Toggle Morphology`, `Disable For Current File`, `Show Server Output`, etc. See the marketplace [extension README](./extension/README.md) for the full list.

## License

MIT — see [LICENSE](./LICENSE).
