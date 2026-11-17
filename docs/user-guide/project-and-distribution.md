# Project Configuration, Localization & Distribution

## `game.toml` Configuration

Place a `game.toml` file in your project root to configure your game's metadata, window dimensions, and presentation defaults:

```toml
[game]
title = "My First Visual Novel"
version = "0.1.0"
author = "Your Name"
entry_script = "main.es"

[window]
width = 1920
height = 1080
```

Additional supported fields in `ProjectConfig` include `theme`, `scale_mode` (`letterbox`, `stretch`, `crop`, `fit_width`, `fit_height`), `render_preset` (`performance`, `balanced`, `quality`, `debug`), and `show_fps`.

---

## Localization (`eager i18n`)

Eager includes built-in translation catalog extraction and validation:

```bash
# Extract translatable strings from your screenplay
uv run eager i18n extract my_story/main.es -o my_story/locales/vi.json --locale vi

# Check translation coverage
uv run eager i18n check my_story/main.es my_story/locales/vi.json --strict

# Play with a specific locale
uv run eager run my_story --lang vi
```

---

## Bundling & Distribution

### 1. Project Archive (`eager build`)

`eager build` validates your project (unless `--no-check` is passed) and packages your scripts, `game.toml`, `assets/`, and `locales/` into a distributable `.zip` archive:

```bash
uv run eager build my_story -o dist/my_story_dist.zip
```

### 2. Standalone Executables & Installers

To build a standalone executable (no Python installation required for players), Windows Inno Setup installer, or Debian `.deb` package, use `packaging/build_export.py` from the repository root:

```bash
# Install PyInstaller in your active environment first
uv pip install pyinstaller

# Build standalone directory for the current platform
python packaging/build_export.py

# Target Windows or Debian/Ubuntu specifically
python packaging/build_export.py --platform windows --output dist/windows
python packaging/build_export.py --platform debian --output dist/debian
```

See `packaging/README.md` for platform prerequisites (`iscc` for Windows installers, `dpkg-dev` for `.deb` packages).
