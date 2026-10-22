import * as vscode from "vscode";
import {
  LanguageClient,
  LanguageClientOptions,
  ServerOptions,
} from "vscode-languageclient/node";

let client: LanguageClient | undefined;

export function activate(context: vscode.ExtensionContext) {
  const config = vscode.workspace.getConfiguration("eager");
  const customServerPath = config.get<string>("server.path", "").trim();

  const workspaceFolder =
    vscode.workspace.workspaceFolders?.[0]?.uri.fsPath || process.cwd();

  let serverOptions: ServerOptions;

  if (customServerPath) {
    const parts = customServerPath.split(" ");
    serverOptions = {
      command: parts[0],
      args: [...parts.slice(1), "--stdio"],
      options: { cwd: workspaceFolder },
    };
  } else {
    // Default: use uv run eager-script-lsp --stdio
    serverOptions = {
      command: "uv",
      args: ["run", "--directory", workspaceFolder, "eager-script-lsp", "--stdio"],
      options: { cwd: workspaceFolder },
    };
  }

  const clientOptions: LanguageClientOptions = {
    documentSelector: [{ scheme: "file", language: "eager-script" }],
    synchronize: {
      fileEvents: [
        vscode.workspace.createFileSystemWatcher("**/*.es"),
        vscode.workspace.createFileSystemWatcher("**/game.toml"),
        vscode.workspace.createFileSystemWatcher("**/assets/**"),
        vscode.workspace.createFileSystemWatcher("**/locales/*.json"),
      ],
    },
  };

  client = new LanguageClient(
    "eager-script-lsp",
    "Eager Script Language Server",
    serverOptions,
    clientOptions
  );

  client.start();

  // Command: Play from here (Warp & Play)
  context.subscriptions.push(
    vscode.commands.registerCommand(
      "eager.warpAndPlay",
      (fileUri: string, sceneId: string) => {
        const playerBackend = config.get<string>("player.backend", "pil");
        const watchFlag = config.get<boolean>("player.watch", true) ? "--watch" : "";

        let fsPath = fileUri;
        try {
          fsPath = vscode.Uri.parse(fileUri).fsPath;
        } catch {
          fsPath = fileUri;
        }

        let terminal = vscode.window.terminals.find((t) => t.name === "Eager Player");
        if (!terminal) {
          terminal = vscode.window.createTerminal("Eager Player");
        }
        terminal.show();

        const playCmd = `uv run eager play "${fsPath}" --backend ${playerBackend} --warp "${sceneId}" ${watchFlag}`.trim();
        terminal.sendText(playCmd);
      }
    )
  );

  // Command: Show scene references
  context.subscriptions.push(
    vscode.commands.registerCommand(
      "eager.showReferences",
      (_fileUri: string, _sceneId: string) => {
        vscode.commands.executeCommand("editor.action.referenceSearch.trigger");
      }
    )
  );

  // Command: Restart Language Server
  context.subscriptions.push(
    vscode.commands.registerCommand("eager.restartServer", async () => {
      if (client) {
        await client.stop();
        client.start();
        vscode.window.showInformationMessage("Eager Script Language Server restarted.");
      }
    })
  );
}

export function deactivate(): Thenable<void> | undefined {
  if (!client) {
    return undefined;
  }
  return client.stop();
}
