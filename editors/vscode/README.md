# Eager-Script VS Code Extension

Official VS Code extension for authoring **Eager-Script (`.es`)** visual novel screenplays.

## Features

- **Real-Time Language Server (LSP)**: Backed by `eager-script-lsp` via standard I/O.
- **Diagnostics**: Resilient line parsing, link/target validation, asset linter, and i18n checks.
- **Auto-Completions**: Context-aware completions for scenes, characters, asset emotion sprites, engine hooks, and variables.
- **Go to Definition & References**: Cross-file jumps, calls, choice targets, speaker definitions, and media files.
- **Code Lenses ("Warp & Play")**: Click **"▶ Play from here"** directly above any scene header to launch and preview the scene immediately.
- **Syntax Highlighting**: Built-in TextMate grammar and delta-encoded LSP Semantic Tokens.

## Installation

### From VSIX
```bash
code --install-extension eager-script-vscode-0.5.0.vsix
```

### Development / Local Testing
1. Open this folder in VS Code (`code editors/vscode`).
2. Press `F5` to open an Extension Development Host window.
3. Open any workspace containing `.es` scripts.
