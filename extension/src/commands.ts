import * as vscode from "vscode";
import { LanguageClient } from "vscode-languageclient/node";

const DISABLE_MARKER_RE = /^.*\bphilologist\s*:\s*(off|disable|disabled)\b.*$/im;

const FILE_COMMENT_BY_LANG: Record<string, { open: string; close: string }> = {
  markdown: { open: "<!-- ", close: " -->" },
  plaintext: { open: "# ", close: "" },
};

export function registerCommands(
  context: vscode.ExtensionContext,
  getClient: () => LanguageClient | undefined,
  restartClient: () => Promise<void>,
  showServerLog: () => void,
): void {
  context.subscriptions.push(
    vscode.commands.registerCommand("philologist.restart", async () => {
      await restartClient();
      vscode.window.setStatusBarMessage(
        "$(sync) Philologist restarted",
        3000,
      );
    }),
    vscode.commands.registerCommand("philologist.showServerLog", () => {
      const client = getClient();
      if (client) {
        client.outputChannel.show();
      } else {
        vscode.window.showInformationMessage(
          "Philologist server isn't running.",
        );
      }
    }),
    vscode.commands.registerCommand("philologist.toggleMorphology", () =>
      toggleSetting("morphology.enabled", "Morphology"),
    ),
    vscode.commands.registerCommand("philologist.toggleOrality", () =>
      toggleSetting("orality.enabled", "Orality"),
    ),
    vscode.commands.registerCommand("philologist.toggleDefinitions", () =>
      toggleSetting("definitions.enabled", "LLM definitions"),
    ),
    vscode.commands.registerCommand("philologist.disableForFile", () =>
      insertDisableMarker(),
    ),
    vscode.commands.registerCommand("philologist.enableForFile", () =>
      removeDisableMarker(),
    ),
  );
}

async function toggleSetting(key: string, label: string): Promise<void> {
  const config = vscode.workspace.getConfiguration("philologist");
  const current = config.get<boolean>(key, true);
  const next = !current;
  // Persist at the most-specific scope where the setting is currently
  // defined; otherwise fall back to global. This way users who set the
  // value in their workspace get a workspace toggle, and others get a
  // global toggle.
  const inspect = config.inspect<boolean>(key);
  let scope: vscode.ConfigurationTarget = vscode.ConfigurationTarget.Global;
  if (inspect?.workspaceFolderValue !== undefined) {
    scope = vscode.ConfigurationTarget.WorkspaceFolder;
  } else if (inspect?.workspaceValue !== undefined) {
    scope = vscode.ConfigurationTarget.Workspace;
  }
  await config.update(key, next, scope);
  vscode.window.setStatusBarMessage(
    `${label}: ${next ? "on" : "off"}`,
    2000,
  );
}

async function insertDisableMarker(): Promise<void> {
  const editor = vscode.window.activeTextEditor;
  if (!editor) {
    return;
  }
  const doc = editor.document;
  // Already disabled? No-op.
  const head = headLines(doc, 10).join("\n");
  if (DISABLE_MARKER_RE.test(head)) {
    vscode.window.showInformationMessage(
      "Philologist is already disabled in this file.",
    );
    return;
  }
  const decoration = FILE_COMMENT_BY_LANG[doc.languageId] ?? {
    open: "",
    close: "",
  };
  const marker = `${decoration.open}philologist: off${decoration.close}\n\n`;
  await editor.edit((edit) => {
    edit.insert(new vscode.Position(0, 0), marker);
  });
}

async function removeDisableMarker(): Promise<void> {
  const editor = vscode.window.activeTextEditor;
  if (!editor) {
    return;
  }
  const doc = editor.document;
  const lines = headLines(doc, 10);
  let removed = false;
  await editor.edit((edit) => {
    for (let i = 0; i < lines.length; i++) {
      if (DISABLE_MARKER_RE.test(lines[i])) {
        const lineRange = doc.lineAt(i).rangeIncludingLineBreak;
        edit.delete(lineRange);
        removed = true;
        break; // remove only the first match — preserves any user content
      }
    }
  });
  if (!removed) {
    vscode.window.showInformationMessage(
      "No `philologist: off` marker found in this file.",
    );
  }
}

function headLines(doc: vscode.TextDocument, count: number): string[] {
  const max = Math.min(count, doc.lineCount);
  const lines: string[] = [];
  for (let i = 0; i < max; i++) {
    lines.push(doc.lineAt(i).text);
  }
  return lines;
}
