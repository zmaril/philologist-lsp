import * as vscode from "vscode";

interface DecorationItem {
  line: number;
  startCharacter: number;
  endCharacter: number;
  glyph: string;
  kind: string;
  tooltip: string;
}

export interface DecorationsParams {
  uri: string;
  version: number;
  decorations: DecorationItem[];
}

// Decoration kinds we know about. Each gets its own TextEditorDecorationType
// keyed by `kind` plus the glyph (since the glyph is fixed when the type is
// created — we have to make a new type per (kind, glyph) combination).
const KNOWN_KINDS: readonly string[] = [
  "case.nominative",
  "case.accusative",
  "case.dative",
  "case.genitive",
  "case.vocative",
  "case.instrumental",
  "case.locative",
  "case.ablative",
  "verb.regular",
  "verb.irregular",
  "verb.modal",
  "verb.auxiliary",
  "verb.separable",
  "degree.comparative",
  "degree.superlative",
];

// Cache: (kind|glyph) → TextEditorDecorationType.
const typeCache = new Map<string, vscode.TextEditorDecorationType>();

// Case decorations are rendered as colored bottom-borders (i.e. underlines)
// attached to the word's range itself. Style varies per case so the reader
// can tell them apart at a glance, like the geometric marks in the book.
//
// All four values: (border-top, border-right, border-bottom, border-left).
const CASE_BORDER: Record<string, { style: string; width: string }> = {
  "case.nominative":   { style: "none none solid none",  width: "0 0 1.5px 0" },
  "case.accusative":   { style: "none none solid none",  width: "0 0 2.5px 0" },
  "case.dative":       { style: "none none dashed none", width: "0 0 2px 0" },
  "case.genitive":     { style: "none none dotted none", width: "0 0 2px 0" },
  "case.vocative":     { style: "none none double none", width: "0 0 3px 0" },
  "case.instrumental": { style: "none none solid none",  width: "0 0 1px 0" },
  "case.locative":     { style: "none none groove none", width: "0 0 2px 0" },
  "case.ablative":     { style: "none none ridge none",  width: "0 0 2px 0" },
};

function typeFor(kind: string, glyph: string): vscode.TextEditorDecorationType {
  const cacheKey = `${kind}|${glyph}`;
  const cached = typeCache.get(cacheKey);
  if (cached) {
    return cached;
  }

  const caseStyle = CASE_BORDER[kind];
  if (caseStyle) {
    // Case marker: render as a bottom border on the word itself, no inline
    // glyph. Closer to the book's "mark-below-the-word" placement.
    const type = vscode.window.createTextEditorDecorationType({
      rangeBehavior: vscode.DecorationRangeBehavior.ClosedClosed,
      borderColor: new vscode.ThemeColor(`philologist.${kind}`),
      borderStyle: caseStyle.style,
      borderWidth: caseStyle.width,
    });
    typeCache.set(cacheKey, type);
    return type;
  }

  // Everything else (verb features, degree marks, …) keeps inline rendering
  // — these are sparse enough not to clutter the line, and the geometric
  // glyphs carry meaning the underline can't (modal vs auxiliary etc).
  const type = vscode.window.createTextEditorDecorationType({
    rangeBehavior: vscode.DecorationRangeBehavior.ClosedClosed,
    after: {
      contentText: ` ${glyph}`,
      color: new vscode.ThemeColor(`philologist.${kind}`),
      fontWeight: "normal",
      margin: "0 0 0 0",
    },
  });
  typeCache.set(cacheKey, type);
  return type;
}

// Last-known decorations per URI, so that switching tabs reapplies them
// without waiting for the server to re-emit.
const lastByUri = new Map<string, DecorationsParams>();

export function applyDecorations(params: DecorationsParams): void {
  lastByUri.set(params.uri, params);
  for (const editor of vscode.window.visibleTextEditors) {
    if (editor.document.uri.toString() === params.uri) {
      paintEditor(editor, params);
    }
  }
}

export function reapplyForEditor(editor: vscode.TextEditor): void {
  const params = lastByUri.get(editor.document.uri.toString());
  if (params) {
    paintEditor(editor, params);
  }
}

export function clearForUri(uri: string): void {
  lastByUri.delete(uri);
}

function paintEditor(
  editor: vscode.TextEditor,
  params: DecorationsParams,
): void {
  // Group ranges by (kind, glyph) since the decoration type is keyed by both.
  const byTypeKey = new Map<
    string,
    {
      type: vscode.TextEditorDecorationType;
      options: vscode.DecorationOptions[];
    }
  >();

  for (const d of params.decorations) {
    const key = `${d.kind}|${d.glyph}`;
    let bucket = byTypeKey.get(key);
    if (!bucket) {
      bucket = { type: typeFor(d.kind, d.glyph), options: [] };
      byTypeKey.set(key, bucket);
    }
    // Case decorations need the full word range (so the bottom border
    // covers the word). Other decorations only need an anchor point at
    // the end for the inline `after` glyph.
    const isCase = d.kind.startsWith("case.");
    const startPos = isCase
      ? new vscode.Position(d.line, d.startCharacter)
      : new vscode.Position(d.line, d.endCharacter);
    const endPos = new vscode.Position(d.line, d.endCharacter);
    bucket.options.push({
      range: new vscode.Range(startPos, endPos),
      hoverMessage: d.tooltip,
    });
  }

  // Apply each bucket; clear any previously-used (kind,glyph) combos that
  // aren't in this batch by setting an empty range list on them.
  const seen = new Set<string>();
  for (const [key, { type, options }] of byTypeKey) {
    seen.add(key);
    editor.setDecorations(type, options);
  }
  for (const [key, type] of typeCache) {
    if (!seen.has(key)) {
      editor.setDecorations(type, []);
    }
  }
}

export function disposeAll(): void {
  for (const type of typeCache.values()) {
    type.dispose();
  }
  typeCache.clear();
  lastByUri.clear();
}

// Expose the kind list so package.json can stay in sync if we want to
// regenerate `contributes.colors`. Not currently used at runtime.
export const allKinds = KNOWN_KINDS;
