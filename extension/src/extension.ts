import * as vscode from "vscode";
import { ExtensionContext, workspace, window } from "vscode";
import {
  LanguageClient,
  LanguageClientOptions,
  ServerOptions,
  TransportKind,
} from "vscode-languageclient/node";

import {
  applyDecorations,
  clearForUri as clearDecorationsForUri,
  DecorationsParams,
  disposeAll as disposeDecorations,
  reapplyForEditor as reapplyDecorationsForEditor,
} from "./decorations";
import {
  applyOrality,
  clearForUri as clearOralityForUri,
  disposeAll as disposeOrality,
  OralityParams,
  reapplyForEditor as reapplyOralityForEditor,
} from "./orality";
import { resolveServer, getBootstrapLogChannel } from "./server-bootstrap";
import { registerCommands } from "./commands";

let client: LanguageClient | undefined;

export async function activate(context: ExtensionContext): Promise<void> {
  // Eager logging so users can confirm activation happened at all, even
  // if bootstrap fails before reaching its own log calls.
  const channel = getBootstrapLogChannel();
  channel.appendLine(
    `=== Philologist ${context.extension.packageJSON.version} activate() ===`,
  );
  channel.appendLine(`extensionPath: ${context.extensionPath}`);
  channel.appendLine(
    `extensionMode: ${context.extensionMode} (1=Production, 2=Development, 3=Test)`,
  );
  channel.appendLine(`platform: ${process.platform} ${process.arch}`);
  channel.appendLine(
    `process.env.PATH: ${process.env.PATH ?? "(unset)"}`,
  );

  // Manual diagnose command for cases where activation events misfire.
  context.subscriptions.push(
    vscode.commands.registerCommand("philologist.diagnose", () => {
      channel.show();
    }),
  );

  registerCommands(
    context,
    () => client,
    async () => {
      if (client) {
        await client.stop();
        await client.start();
      }
    },
    () => {
      client?.outputChannel.show();
    },
  );

  let launch;
  try {
    launch = await resolveServer(context);
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    channel.appendLine(`resolveServer threw: ${msg}`);
    if (!msg.includes("uv not found")) {
      window.showErrorMessage(
        `Philologist failed to start: ${msg}. See "Philologist · Bootstrap" output channel.`,
      );
    }
    return;
  }
  channel.appendLine(
    `resolveServer ok: command=${launch.command} args=${launch.args.join(" ")}`,
  );

  const serverOptions: ServerOptions = {
    run: {
      command: launch.command,
      args: launch.args,
      transport: TransportKind.stdio,
    },
    debug: {
      command: launch.command,
      args: launch.args,
      transport: TransportKind.stdio,
    },
  };

  const config = workspace.getConfiguration("philologist");
  const clientOptions: LanguageClientOptions = {
    documentSelector: [
      { scheme: "file", language: "plaintext" },
      { scheme: "file", language: "markdown" },
    ],
    synchronize: {
      configurationSection: "philologist",
    },
    outputChannelName: "Philologist",
    // Send the current settings up-front so the server has feature
    // toggles applied before the first analysis runs.
    initializationOptions: {
      philologist: {
        enable: config.get("enable", true),
        morphology: { enabled: config.get("morphology.enabled", true) },
        orality: {
          enabled: config.get("orality.enabled", true),
          minConfidence: config.get("orality.minConfidence", 0.25),
        },
        definitions: { enabled: config.get("definitions.enabled", true) },
        respectDisableMarker: config.get("respectDisableMarker", true),
        spacyModelSize: config.get("spacyModelSize", "md"),
      },
    },
  };

  client = new LanguageClient(
    "philologist-lsp",
    "Philologist",
    serverOptions,
    clientOptions,
  );

  try {
    await client.start();
  } catch (err) {
    window.showErrorMessage(
      `Philologist failed to start: ${err instanceof Error ? err.message : String(err)}`,
    );
    throw err;
  }

  // Listen for server-pushed sigil decorations and orality spans.
  context.subscriptions.push(
    client.onNotification(
      "philologist/decorations",
      (params: DecorationsParams) => applyDecorations(params),
    ),
    client.onNotification(
      "philologist/orality",
      (params: OralityParams) => applyOrality(params),
    ),
  );

  // Re-paint when an editor becomes visible (switching tabs etc).
  context.subscriptions.push(
    vscode.window.onDidChangeActiveTextEditor((editor) => {
      if (editor) {
        reapplyDecorationsForEditor(editor);
        reapplyOralityForEditor(editor);
      }
    }),
    vscode.window.onDidChangeVisibleTextEditors((editors) => {
      for (const editor of editors) {
        reapplyDecorationsForEditor(editor);
        reapplyOralityForEditor(editor);
      }
    }),
    vscode.workspace.onDidCloseTextDocument((doc) => {
      clearDecorationsForUri(doc.uri.toString());
      clearOralityForUri(doc.uri.toString());
    }),
  );
}

export async function deactivate(): Promise<void> {
  disposeDecorations();
  disposeOrality();
  if (client) {
    await client.stop();
    client = undefined;
  }
}
