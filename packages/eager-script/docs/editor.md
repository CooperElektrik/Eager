# Terminal Text Editor

`eager_s` includes an optional full-screen terminal text editor built specifically for screenplay authoring, featuring real-time syntax highlighting, live static diagnostics, and scene outline navigation.

---

## Installation

The editor is powered by [`blessed`](https://github.com/jquast/blessed) and is completely optional:

```bash
pip install "eager-s[editor]"
```

---

## Launching the Editor

```bash
# Open an existing or new script
eager-s edit screenplay.es

# Open in Eager-SP mode
eager-s edit --plain manuscript.es

# Open in read-only mode
eager-s edit --read-only screenplay.es
```

---

## Features

### 1. Eager-S DSL Syntax Highlighting
- Visual distinction for scene labels, character speakers, emotion tags, voice audio tags, append beats, fresh box beats, choice options, jumps, subroutine calls, returns, hooks, and comments.

### 2. Real-Time Diagnostics
- Syntax errors and static link validation run in the background as you type.
- Gutter markers flag issues:
  - `!` : Syntax or validation error.
  - `W` : Warning (unreachable scene, dead code, orphan label, loop).
- The status bar displays the diagnostic message corresponding to the current cursor line.

### 3. Scene Outline (`Ctrl+O`)
- An interactive fuzzy-searchable popup showing all screenplay scenes (`## Labels`).
- Filter by typing and press `Enter` to jump instantly to that scene.

### 4. Search & Navigation
- **Find (`Ctrl+F`)**: Forward text search with wrap-around across the script.
- **Go to Line (`Ctrl+G`)**: Instant jump to any line number.

---

## Keyboard Shortcuts

| Shortcut | Action |
| :--- | :--- |
| `Ctrl+S` | Save current file |
| `Ctrl+Q` | Quit editor (prompts if unsaved changes exist) |
| `Ctrl+O` | Open Scene Outline popup |
| `Ctrl+F` | Find text in script |
| `Ctrl+G` | Go to line |
| `Ctrl+Z` | Undo last edit |
| `Ctrl+Y` | Redo undone edit |
| `F1` | In-editor cheatsheet & help dialog |
| `Escape` | Dismiss active dialog/popup |
| `PageUp` / `PageDown` | Scroll viewport by half-screen |
| `Home` / `End` | Jump to line start / line end |
| `Ctrl+Home` / `Ctrl+End` | Jump to file beginning / file end |
