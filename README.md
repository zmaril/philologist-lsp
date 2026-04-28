# philologist-lsp

A Language Server that surfaces the morphological and rhetorical structure of natural-language text the way a philologist reads it.

- **Per-token morphology** via spaCy: gender, number, case, tense, mood, voice. Rendered as semantic-token colors and inlay-hint sigils.
- **Per-paragraph orality** via [havelock-orality](https://huggingface.co/thestalwart/havelock-orality): regressor (0–1 score), category (oral / literate), and 68-class subtype span markers. English only for now.
- **Auto language detection** per paragraph via [lingua](https://github.com/pemistahl/lingua-py); spaCy models for ~24 languages auto-download on first use.
- **Pure LSP**, runs locally, no external API calls.

See [DESIGN.md](./DESIGN.md) for architecture and rationale.

Inspired by Barbara Avila Vissirini, *Dieses kleine Buch ist für dich* — a graphical grammar for German as a foreign language.

## Status

Early development. Currently:

- [x] P0 — server + extension scaffolding
- [x] P1 — language detect + spaCy pool
- [x] P2 — morph rendering (semantic tokens, inlay hints, hover)
- [ ] P3 — orality regressor + category
- [ ] P4 — orality subtype spans
- [ ] P5 — packaging

## Repo layout

```
philologist-lsp/
├── DESIGN.md           # design doc
├── server/             # Python LSP (pygls)
│   ├── pyproject.toml
│   └── src/philologist_lsp/
└── extension/          # VSCode extension (TypeScript)
    ├── package.json
    └── src/extension.ts
```

## Running locally (dev)

Prerequisites: `python ≥ 3.10`, `uv`, `node ≥ 20`, VSCode.

```bash
# server
cd server
uv sync                                  # installs pygls + lsprotocol
uv run python -m philologist_lsp         # smoke test (Ctrl-C to exit)

# extension
cd ../extension
npm install
npm run typecheck                        # tsc check
```

In VSCode: open `extension/`, press `F5` to launch the Extension Development Host. Open a `.txt` or `.md` file in the new window — the language server will activate.

## Releasing

Releases are built and published to GitHub Releases by `.github/workflows/release.yml` on tag push:

```bash
# bump version in extension/package.json (and server/pyproject.toml if you want them in sync)
git commit -am "v0.0.7"
git tag v0.0.7
git push origin v0.0.7
```

The workflow runs `vsce package` against a clean checkout, attaches the `.vsix` to a new GitHub Release, and includes auto-generated release notes. Anyone can install with `code --install-extension philologist-lsp-0.0.7.vsix` after downloading the asset.

Manual builds (no release) can be triggered from the Actions tab via *Run workflow*.

## Theming the gender colors

The extension ships a default color palette for its custom semantic-token types (`philologistMasculine`, `philologistFeminine`, `philologistNeuter`, `philologistCommon`, `philologistPlural`, `philologistVerb`, `philologistAdjective`, …) via `contributes.configurationDefaults`. Colors apply automatically the moment the extension activates — no manual `settings.json` edit required.

To override, add your own block to User `settings.json`:

```json
"editor.semanticTokenColorCustomizations": {
  "rules": {
    "philologistMasculine": "#88E0FF",
    "philologistFeminine":  "#FFB6C1"
  }
}
```

Modifiers available for fine-grained styling: `plural`, `definite`, `indefinite`, `regular`, `irregular`, `modal`, `auxiliary`, `separable`, `comparative`, `superlative`, `nominative`, `accusative`, `dative`, `genitive`.

## Configuration

See `philologist.*` settings in VSCode (contributed by the extension). Defaults are sensible.
