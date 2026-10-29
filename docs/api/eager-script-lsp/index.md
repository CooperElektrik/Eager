# eager-script-lsp

Full-featured Language Server Protocol (LSP 3.17+) server for Eager-Script (`.es`) screenplays. Provides real-time diagnostics, autocompletion, hover previews, navigation, and a headless batch diagnostic checker.

## Architecture & Conventions

All primitives must be imported directly from their defining submodule. Root re-export shims are strictly forbidden:

```python
from eager_script_lsp.server import EagerLanguageServer
from eager_script_lsp.workspace import Workspace
from eager_script_lsp.document import Document
```

## Modules

| Module | Description |
|--------|-------------|
| [server](server.md) | Language server implementation (`EagerLanguageServer`) and pygls JSON-RPC protocol handling. |
| [workspace](workspace.md) | Workspace management (`Workspace`) and multi-file cross-referencing index. |
| [document](document.md) | Document buffer management (`Document`) and line offset tracking. |
| [cli](cli.md) | Command-line interface (`eager-lsp`) and batch diagnostic checker (`--check`). |

## Language Features

- [Language Features Overview](features/index.md): Real-time analysis and editor capabilities.
    - [Completion](features/completion.md): Context-aware auto-completion for scenes, characters, and variables.
    - [Diagnostics](features/diagnostics.md): Syntax and semantic error/warning reporting.
    - [Hover](features/hover.md): Hover documentation and variable/scene previews.
    - [Navigation](features/navigation.md): Definition jumping, reference finding, and symbol outline.
    - [Code Lenses](features/lenses.md): In-editor scene jump references and action triggers.
    - [Refactor](features/refactor.md): Safe symbol rename and code action assists.
    - [Semantic Tokens](features/tokens.md): Semantic tokenization for editor syntax highlighting.
