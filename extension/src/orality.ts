import * as vscode from "vscode";

interface OralityAlternative {
  marker: string;
  confidence: number;
  displayName: string;
}

interface OralitySpan {
  start: number;        // absolute char offset in the document
  end: number;
  marker: string;       // snake_case identifier
  category: "oral" | "literate";
  confidence: number;
  displayName: string;  // SCREAMING SNAKE for the tag label
  description: string;
  examples: string[];
  alternatives: OralityAlternative[];
}

export interface OralityParams {
  uri: string;
  version: number;
  spans: OralitySpan[];
  documentScore?: number | null;
  documentCategory?: string | null;
}

// Document-level status bar item, shared across all editors.
let statusBar: vscode.StatusBarItem | null = null;

function ensureStatusBar(): vscode.StatusBarItem {
  if (statusBar === null) {
    statusBar = vscode.window.createStatusBarItem(
      vscode.StatusBarAlignment.Right,
      100,
    );
    statusBar.tooltip = "Document-level orality (havelock-orality regressor)";
  }
  return statusBar;
}

/**
 * Refresh the status bar to reflect the *active* editor's orality score —
 * not whichever file was most recently analyzed. Without this, the bar
 * gets stale when the user switches between an English-y file and a
 * non-English one.
 */
function refreshStatusBar(): void {
  const bar = ensureStatusBar();
  const editor = vscode.window.activeTextEditor;
  if (!editor) {
    bar.hide();
    return;
  }
  const params = lastByUri.get(editor.document.uri.toString());
  if (
    !params ||
    params.documentScore === null ||
    params.documentScore === undefined ||
    !params.documentCategory
  ) {
    bar.hide();
    return;
  }
  const dot = params.documentScore >= 0.5 ? "🟢" : "🟣";
  const pct = Math.round(params.documentScore * 100);
  bar.text = `${dot} Orality ${pct}% — ${params.documentCategory}`;
  bar.show();
}

// One DecorationType per category. The marker name now lives in a CodeLens
// above the sentence (see server.py on_code_lens), not as inline after-content.
const typeCache = new Map<string, vscode.TextEditorDecorationType>();

// One DecorationType per sentence number, lazy-built. Each one carries an
// inline SVG number icon in the gutter — mirrors havelock.ai's left-margin
// numbering. The icon's path is a `data:` URI generated on demand.
const gutterTypeCache = new Map<number, vscode.TextEditorDecorationType>();

function gutterIconUri(n: number): vscode.Uri {
  // 16x16 SVG; subtle annotation gray so it doesn't fight the editor's own
  // line-number column (which sits to the right of the gutter icon).
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 16 16">` +
    `<text x="8" y="11" font-family="ui-monospace,Menlo,monospace" font-size="9" fill="#7A8794" text-anchor="middle">${n}</text>` +
    `</svg>`;
  return vscode.Uri.parse(
    "data:image/svg+xml;utf8," + encodeURIComponent(svg),
  );
}

function gutterTypeFor(n: number): vscode.TextEditorDecorationType {
  const cached = gutterTypeCache.get(n);
  if (cached) {
    return cached;
  }
  const type = vscode.window.createTextEditorDecorationType({
    gutterIconPath: gutterIconUri(n),
    gutterIconSize: "contain",
  });
  gutterTypeCache.set(n, type);
  return type;
}

function decorationTypeFor(span: OralitySpan): vscode.TextEditorDecorationType {
  const cacheKey = span.category;
  const cached = typeCache.get(cacheKey);
  if (cached) {
    return cached;
  }
  const bgKey = `philologist.orality.${span.category}.background`;
  const fgKey = `philologist.orality.${span.category}.foreground`;
  const type = vscode.window.createTextEditorDecorationType({
    backgroundColor: new vscode.ThemeColor(bgKey),
    color: new vscode.ThemeColor(fgKey),
    rangeBehavior: vscode.DecorationRangeBehavior.ClosedClosed,
  });
  typeCache.set(cacheKey, type);
  return type;
}

const lastByUri = new Map<string, OralityParams>();

export function applyOrality(params: OralityParams): void {
  lastByUri.set(params.uri, params);
  refreshStatusBar();
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
  refreshStatusBar();
}

export function clearForUri(uri: string): void {
  lastByUri.delete(uri);
  refreshStatusBar();
}

function paintEditor(
  editor: vscode.TextEditor,
  params: OralityParams,
): void {
  const byTypeKey = new Map<
    string,
    {
      type: vscode.TextEditorDecorationType;
      options: vscode.DecorationOptions[];
    }
  >();

  for (const span of params.spans) {
    const type = decorationTypeFor(span);
    const startPos = editor.document.positionAt(span.start);
    const endPos = editor.document.positionAt(span.end);

    const altLines = span.alternatives
      .map(
        (a) =>
          ` - **${a.displayName}** (${(a.confidence * 100).toFixed(0)}%)`,
      )
      .join("\n");
    const examples = span.examples.length
      ? `\n\n*Examples:*\n` +
        span.examples.map((e) => `> ${e}`).join("\n")
      : "";
    const altsBlock = altLines ? `\n\n*Also possible:*\n${altLines}` : "";
    const dot = span.category === "oral" ? "🟢" : "🟣";

    const md = new vscode.MarkdownString(
      `${dot} **${span.displayName}** — ${span.category.toUpperCase()} marker\n\n` +
        `${span.description}` +
        examples +
        altsBlock +
        `\n\n_Confidence: ${(span.confidence * 100).toFixed(0)}%_`,
    );
    md.isTrusted = true;

    let bucket = byTypeKey.get(span.category);
    if (!bucket) {
      bucket = { type, options: [] };
      byTypeKey.set(span.category, bucket);
    }
    bucket.options.push({
      range: new vscode.Range(startPos, endPos),
      hoverMessage: md,
    });
  }

  // Apply each bucket; clear unused types to handle removal between updates.
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

  // Gutter sentence numbers, anchored to the line where each sentence starts.
  const seenNumbers = new Set<number>();
  params.spans.forEach((span, idx) => {
    const n = idx + 1;
    seenNumbers.add(n);
    const lineStart = editor.document.positionAt(span.start);
    const lineRange = new vscode.Range(
      lineStart.line, 0, lineStart.line, 0,
    );
    editor.setDecorations(gutterTypeFor(n), [{ range: lineRange }]);
  });
  // Clear gutter icons for numbers no longer in this batch (sentences
  // removed via edit). We only clear types we created, leaving lower-
  // numbered ones in place if they're still active.
  for (const [n, type] of gutterTypeCache) {
    if (!seenNumbers.has(n)) {
      editor.setDecorations(type, []);
    }
  }
}

export function disposeAll(): void {
  for (const type of typeCache.values()) {
    type.dispose();
  }
  typeCache.clear();
  for (const type of gutterTypeCache.values()) {
    type.dispose();
  }
  gutterTypeCache.clear();
  lastByUri.clear();
  if (statusBar) {
    statusBar.dispose();
    statusBar = null;
  }
}
