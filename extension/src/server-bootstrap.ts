import * as cp from "child_process";
import { existsSync, promises as fs } from "fs";
import * as os from "os";
import * as path from "path";
import * as vscode from "vscode";

export interface ServerLaunch {
  command: string;
  args: string[];
}

const HOME_DIR_NAME = ".philologist-lsp";
const UV_INSTALL_URL =
  "https://docs.astral.sh/uv/getting-started/installation/";

let logChannel: vscode.OutputChannel | null = null;

export function getBootstrapLogChannel(): vscode.OutputChannel {
  if (!logChannel) {
    logChannel = vscode.window.createOutputChannel("Philologist · Bootstrap");
  }
  return logChannel;
}

function log(msg: string): void {
  getBootstrapLogChannel().appendLine(`${new Date().toISOString()} ${msg}`);
}

/**
 * Resolve how to launch the Philologist Python server.
 *
 * Priority:
 *   1. Explicit `philologist.serverPath` setting (an executable to run)
 *   2. Explicit `philologist.pythonPath` setting (a Python to spawn -m on)
 *   3. ExtensionMode.Development → use the local server/.venv if present
 *   4. Production → bootstrap a managed venv at ~/.philologist-lsp/venv
 *
 * The production path requires `uv` somewhere we can find. On macOS,
 * GUI-launched VSCode does NOT inherit the user's shell PATH, so checking
 * `PATH` alone is not enough — we also probe the standard install
 * locations (`~/.local/bin/uv`, `~/.cargo/bin/uv`, `/opt/homebrew/bin/uv`,
 * etc.) before declaring `uv` missing.
 */
export async function resolveServer(
  context: vscode.ExtensionContext,
): Promise<ServerLaunch> {
  const cfg = vscode.workspace.getConfiguration("philologist");
  const serverOverride = (cfg.get<string>("serverPath", "") || "").trim();
  if (serverOverride) {
    log(`using serverPath override: ${serverOverride}`);
    return { command: serverOverride, args: [] };
  }
  const pythonOverride = (cfg.get<string>("pythonPath", "") || "").trim();
  if (pythonOverride) {
    log(`using pythonPath override: ${pythonOverride}`);
    return { command: pythonOverride, args: ["-m", "philologist_lsp"] };
  }

  if (context.extensionMode === vscode.ExtensionMode.Development) {
    const repoRoot = path.resolve(context.extensionPath, "..");
    const devPython = path.join(
      repoRoot,
      "server",
      ".venv",
      "bin",
      "python",
    );
    if (existsSync(devPython)) {
      log(`development mode: using ${devPython}`);
      return { command: devPython, args: ["-m", "philologist_lsp"] };
    }
    log("development mode: no local venv, falling through to bootstrap");
  }

  return await bootstrapManagedServer(context);
}

async function bootstrapManagedServer(
  context: vscode.ExtensionContext,
): Promise<ServerLaunch> {
  const status = vscode.window.createStatusBarItem(
    vscode.StatusBarAlignment.Left,
    100,
  );
  status.text = "$(loading~spin) Philologist: starting…";
  status.show();

  try {
    const uvPath = await findUv();
    if (!uvPath) {
      status.text = "$(error) Philologist: uv not found";
      void promptUvMissing();
      throw new Error("uv not found on PATH or common install locations");
    }
    log(`using uv at ${uvPath}`);

    const wheelPath = await locateWheel(context);
    log(`using bundled wheel ${wheelPath}`);

    const venvDir = path.join(os.homedir(), HOME_DIR_NAME, "venv");
    const venvPython =
      process.platform === "win32"
        ? path.join(venvDir, "Scripts", "python.exe")
        : path.join(venvDir, "bin", "python");
    const stampPath = path.join(venvDir, ".philologist-version");

    const targetVersion: string =
      context.extension.packageJSON.version ?? "0.0.0";
    let installedVersion = "";
    try {
      installedVersion = (await fs.readFile(stampPath, "utf8")).trim();
    } catch {
      // first install
    }

    const venvUsable = existsSync(venvPython);
    const upToDate = venvUsable && installedVersion === targetVersion;
    if (upToDate) {
      log(`venv at ${venvDir} is up to date (${installedVersion})`);
      status.dispose();
      return { command: venvPython, args: ["-m", "philologist_lsp"] };
    }

    log(
      `bootstrap needed (venvUsable=${venvUsable}, installed=${installedVersion}, target=${targetVersion})`,
    );

    await vscode.window.withProgress(
      {
        location: vscode.ProgressLocation.Notification,
        title: venvUsable
          ? "Philologist: updating Python environment"
          : "Philologist: setting up Python environment (one-time)",
        cancellable: false,
      },
      async (progress) => {
        if (!venvUsable) {
          progress.report({ message: "Creating virtualenv via uv…" });
          status.text = "$(loading~spin) Philologist: creating venv";
          await ensureDir(path.dirname(venvDir));
          await runCommand(uvPath, ["venv", venvDir]);
        }
        progress.report({
          message:
            "Installing philologist-lsp + ML dependencies (downloads ~2 GB the first time)",
        });
        status.text = "$(loading~spin) Philologist: installing dependencies";
        await runCommand(uvPath, [
          "pip",
          "install",
          "--python",
          venvPython,
          "--upgrade",
          `${wheelPath}[nlp,llm]`,
        ]);
        await ensureDir(path.dirname(stampPath));
        await fs.writeFile(stampPath, targetVersion, "utf8");
      },
    );

    log("bootstrap complete");
    status.dispose();
    return { command: venvPython, args: ["-m", "philologist_lsp"] };
  } catch (err) {
    status.text = "$(error) Philologist: bootstrap failed";
    setTimeout(() => status.dispose(), 10_000);
    throw err;
  }
}

async function findUv(): Promise<string | null> {
  // Step 1: try PATH (works when VSCode is launched from a terminal that
  // has uv on PATH, or when uv was installed to a system path like
  // /usr/local/bin).
  if ((await execCheck("uv", ["--version"])).ok) {
    return "uv";
  }
  log("uv not on PATH; probing standard install locations");

  // Step 2: common install locations. macOS Dock/Spotlight launches
  // inherit a minimal PATH (usually just /usr/bin:/bin:/usr/sbin:/sbin),
  // so anything under ~/.local or homebrew is invisible.
  const home = os.homedir();
  const candidates: string[] = [
    path.join(home, ".local", "bin", "uv"),
    path.join(home, ".cargo", "bin", "uv"),
    "/opt/homebrew/bin/uv",
    "/usr/local/bin/uv",
    "/usr/bin/uv",
  ];
  if (process.platform === "win32") {
    candidates.push(
      path.join(home, ".local", "bin", "uv.exe"),
      path.join(home, ".cargo", "bin", "uv.exe"),
    );
  }

  for (const candidate of candidates) {
    if (!existsSync(candidate)) {
      continue;
    }
    if ((await execCheck(candidate, ["--version"])).ok) {
      return candidate;
    }
  }

  log(
    `uv missing. Tried PATH and: ${candidates.filter((c) => existsSync(c)).join(", ") || "(none of the standard paths exist)"}`,
  );
  return null;
}

async function locateWheel(
  context: vscode.ExtensionContext,
): Promise<string> {
  const dir = path.join(context.extensionPath, "server-wheel");
  let entries: string[] = [];
  try {
    entries = await fs.readdir(dir);
  } catch {
    throw new Error(
      `Bundled server wheel directory not found at ${dir}. ` +
        "Did the extension build skip `npm run build:wheel`?",
    );
  }
  const wheel = entries.find((e) => e.endsWith(".whl"));
  if (!wheel) {
    throw new Error(`No .whl in ${dir} — extension bundle is incomplete.`);
  }
  return path.join(dir, wheel);
}

async function execCheck(
  cmd: string,
  args: string[],
): Promise<{ ok: boolean; stderr: string }> {
  return new Promise((resolve) => {
    cp.execFile(cmd, args, (err, _stdout, stderr) => {
      resolve({ ok: !err, stderr: stderr?.toString() ?? "" });
    });
  });
}

async function promptUvMissing(): Promise<void> {
  const action = await vscode.window.showErrorMessage(
    "Philologist requires `uv` (Astral's Python package manager). " +
      "VSCode couldn't find it on PATH or in standard install locations " +
      "(~/.local/bin, ~/.cargo/bin, /opt/homebrew/bin, /usr/local/bin). " +
      "If uv is installed elsewhere, launch VSCode from a terminal that " +
      "has it on PATH, or symlink it into /usr/local/bin.",
    "Open install instructions",
    "Show diagnostics",
  );
  if (action === "Open install instructions") {
    void vscode.env.openExternal(vscode.Uri.parse(UV_INSTALL_URL));
  } else if (action === "Show diagnostics") {
    logChannel?.show();
  }
}

async function ensureDir(dir: string): Promise<void> {
  await fs.mkdir(dir, { recursive: true });
}

function runCommand(cmd: string, args: string[]): Promise<void> {
  log(`exec: ${cmd} ${args.join(" ")}`);
  return new Promise((resolve, reject) => {
    const child = cp.spawn(cmd, args, { stdio: ["ignore", "pipe", "pipe"] });
    let stderr = "";
    child.stdout?.on("data", (chunk) => {
      log(`  stdout: ${chunk.toString().trimEnd()}`);
    });
    child.stderr?.on("data", (chunk) => {
      const text = chunk.toString();
      stderr += text;
      log(`  stderr: ${text.trimEnd()}`);
    });
    child.on("error", reject);
    child.on("close", (code) => {
      if (code === 0) {
        resolve();
      } else {
        reject(
          new Error(
            `${cmd} ${args.join(" ")} exited with code ${code}\n${stderr}`,
          ),
        );
      }
    });
  });
}
