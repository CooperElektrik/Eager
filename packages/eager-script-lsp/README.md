# Eager-Script-LSP

Full-featured Language Server Protocol (LSP 3.17+) server for Eager-Script (`.es`) screenplays.

`eager-script-lsp` provides deep language intelligence, resilient real-time error recovery, and interactive editing capabilities for Eager visual novel authors. It can run as a background language server over standard I/O, TCP, or WebSocket, or execute as a headless batch diagnostic checker in CI/CD pipelines.

---

## Language Server Features

### 1. Real-Time Diagnostics
- **Resilient Syntax Recovery**: Recovers from incomplete lines while strictly preserving block indentation inside nested choice structures.
- **Cross-File Link Checking**: Validates scene jump (`>`) and subroutine call (`>>`) targets across the entire workspace project graph without single-file false positives.
- **Asset Validation**: Verifies referenced images, audio tracks, and voice clips exist on disk.
- **Clean Editor Buffers**: Stale diagnostic squiggles are immediately cleared when untracked or deleted files are closed.

### 2. Context-Aware Auto-Completion
- **Partial Filter Autocompletion**: Incremental typing like `> s` or `visited('s` filters matching scene symbols dynamically.
- **Character Identifiers & Emotions**: Autocompletes declared `@character` IDs and asset-discovered character emotion sprites.
- **Directives & Built-ins**: Autocompletes screenplay directives (`@if`, `@default`, etc.) and built-in DSL expression functions (`visited`, `seen`, `random`, `chance`, `min`, `max`, `abs`, `len`, `int`, `str`, `round`).

### 3. Hover Previews
- **Scene Topology**: Hover over jump/call targets to inspect incoming edges, outgoing choices, and scene line previews.
- **Character Sheets**: Hover over speaker tags or character references in engine hooks (`~ show <char>`) to view display names, colors, and asset references.
- **Expression Functions**: Hover over built-in expression functions for argument documentation and return types.

### 4. Navigation & Definition
- **Go-to-Definition**: Jump directly to scene label declarations, subroutine entry points, and character definitions.
- **Variable Mutation Navigation**: When an explicit `@default` is absent, definition lookup intelligently falls back to the first variable mutation site.
- **Find References**: Find all jump sites, call sites, and variable accesses throughout the multi-file screenplay workspace.

### 5. Semantic Tokens & Syntax Highlighting
- Rich semantic classification for speakers, character aliases, emotion tags, built-in functions, directives, hook commands, and dialogue formatting tags.

### 6. Code Lenses & Actions
- **Warp & Play**: Launch interactive playthroughs directly from any scene heading within supported editor environments.

---

## Installation

```bash
# Standalone installation
pip install eager-script-lsp

# As an extra from eager-runtime
pip install 'eager-runtime[lsp]'
```

---

## Command-Line Usage

The `eager-script-lsp` binary can be run standalone or through `eager lsp`:

```bash
# Display version information
eager-script-lsp --version

# Run language server over Standard I/O (default, used by VS Code)
eager-script-lsp --stdio

# Run over TCP socket
eager-script-lsp --tcp --host 127.0.0.1 --port 2087

# Run over WebSocket
eager-script-lsp --ws --host 127.0.0.1 --port 2087

# Headless batch diagnostic verification for a script or workspace
eager-script-lsp --check story.es
eager-script-lsp --check ./scripts/
```

When invoked with `--check`:
- Validates all `.es` screenplay files in the specified path.
- Emits structured diagnostic messages with 1-indexed lines and columns (`[ERROR]` or `[WARNING]`).
- Exits with returncode `0` on clean validation or warnings, and `1` if any syntax or semantic errors are found.

---

## Editor Configuration

### VS Code
Use the bundled VS Code extension in `editors/vscode`:
```bash
cd editors/vscode
npm install
npm run package
code --install-extension eager-script-*.vsix
```

### Neovim (`nvim-lspconfig`)
```lua
local lspconfig = require('lspconfig')
local configs = require('lspconfig.configs')

if not configs.eager_lsp then
  configs.eager_lsp = {
    default_config = {
      cmd = { 'eager-script-lsp', '--stdio' },
      filetypes = { 'eager', 'es' },
      root_dir = lspconfig.util.root_pattern('game.toml', '.git'),
      settings = {},
    },
  }
end
lspconfig.eager_lsp.setup({})
```

### Helix (`languages.toml`)
```toml
[[language]]
name = "eager"
scope = "source.es"
file-types = ["es"]
roots = ["game.toml"]
language-servers = [ "eager-lsp" ]

[language-server.eager-lsp]
command = "eager-script-lsp"
args = ["--stdio"]
```

---

## License

MIT
