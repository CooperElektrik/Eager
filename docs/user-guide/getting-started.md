# Getting Started

This guide walks you through creating, running, and validating your first visual novel with Eager.

## 1. Verify Your Environment

Before creating a project, check which rendering and audio backends are available:

```bash
uv run eager doctor
```

By default, Eager uses the software **PIL** renderer (`--backend pil`). For hardware-accelerated OpenGL rendering, ensure `pyglet` is installed and pass `--backend pyglet`.

---

## 2. Create a New Project

Scaffold a starter project:

```bash
uv run eager new my_story
```

Or scaffold a copy of the full showcase demo (complete with backgrounds, sprites, and translations):

```bash
uv run eager new my_demo --demo
```

A new project has the following layout:

```text
my_story/
├── game.toml            # Project title, window size, theme, and entry script
├── main.es              # Main screenplay file
└── assets/
    ├── bg/              # Background images
    ├── characters/      # Character sprite expressions
    └── audio/           # Music, sound effects, ambient, and voice
```

---

## 3. Run Your Visual Novel

Launch the project directory directly:

```bash
uv run eager run my_story
```

For live authoring, enable **hot-reload** (`--watch`) so the game reloads automatically whenever you save `main.es`:

```bash
uv run eager run my_story --watch
```

You can also play a standalone `.es` file directly:

```bash
# Default graphical window (PIL)
uv run eager play my_story/main.es

# Hardware-accelerated OpenGL window
uv run eager play my_story/main.es --backend pyglet

# Terminal text mode (no graphics required)
uv run eager play my_story/main.es --backend terminal
```

---

## 4. Validate Before Sharing

Check your screenplay syntax, scene links, and referenced assets:

```bash
uv run eager check my_story --assets
```

Run an automated playthrough across all choice branches without opening a window:

```bash
uv run eager test-run my_story/main.es --all-paths
```
