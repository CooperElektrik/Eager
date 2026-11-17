# IDE & Debugging Workflow

Eager ships with a Language Server Protocol (LSP 3.17+) server (`eager-script-lsp`) and a VS Code extension (`editors/vscode/`) for a fast authoring and debugging loop.

---

## VS Code Extension

The extension in `editors/vscode/` provides:

- **Syntax highlighting** for `.es` files.
- **Real-time diagnostics** powered by `eager-script-lsp` (broken jumps, duplicate labels, unreachable scenes).
- **Play from Here (Warp & Play)** CodeLens (`eager.warpAndPlay`) to launch the player directly at any scene.
- **Show Scene References** (`eager.showReferences`) to find all jumps/choices targeting a scene.

Configurable extension settings:

- `eager.server.path`: Custom path/command for `eager-script-lsp` (defaults to `uv run eager-script-lsp`).
- `eager.player.backend`: `pil` (default), `pyglet`, or `terminal`.
- `eager.player.watch`: Enable hot-reload watcher (`true` by default).

---

## CLI Debugging & Inspection Tools

### Warp to a Scene

Jump directly to any scene label without replaying from the beginning:

```bash
uv run eager run my_story --warp shrine_twilight --skip-title
```

Add `--no-warp-sim` to skip state simulation when warping.

### Live Hot-Reload

```bash
uv run eager run my_story --watch
```

### Scene Graph & Topology

Inspect scene entry points and export a Mermaid flowchart of your story:

```bash
uv run eager inspect my_story/main.es
uv run eager-script graph my_story/main.es --format mermaid
```

### Headless Verification

Run all choice paths or render frames headlessly in CI:

```bash
uv run eager test-run my_story/main.es --all-paths
uv run eager render my_story/main.es --auto-choose 0
```
