# Staging, Visuals & Audio Hooks

Lines starting with `~` send staging, visual effect, and audio commands to the presentation layer (`StageDirector`).

---

## Backgrounds & Scenes

```es
~ bg classroom_day with crossfade duration=1.0
~ bg_clear
```

- `~ bg <asset_id> [with <transition>] [duration=<sec>]` sets the active background.
- `~ bg_clear` clears the current background.

---

## Characters

```es
~ show hoshiko smile at center with fade duration=0.6
~ move hoshiko to center_left duration=0.5
~ expr hoshiko surprised
~ hide hoshiko with fade duration=0.4
```

| Hook | Purpose |
|------|---------|
| `~ show <id> [expr] [at <pos>] [with <trans>] [duration=<sec>]` | Display a character sprite on stage. |
| `~ expr <id> <expression>` | Change a visible character's expression. |
| `~ move <id> [to] <pos> [duration=<sec>]` | Animate character movement to a stage position (`left`, `center_left`, `center`, `center_right`, `right`). |
| `~ hide <id> [with <trans>] [duration=<sec>]` | Remove a character from the stage. |

---

## Screen Effects & Overlays

```es
~ fade_in duration=0.8
~ fade_out duration=0.8
~ flash color=#ffffff duration=0.2
~ shake intensity=2.0 duration=0.4
~ image cg_sunset at center
~ hide_image cg_sunset
```

---

## Audio

Use `~ play`, `~ queue`, `~ pause`, `~ resume`, `~ stop`, and `~ volume`, or channel shorthands:

- **Play shorthands:** `~ play_bgm`, `~ play_music`, `~ play_sfx`, `~ play_sound`, `~ play_voice`, `~ play_ambient`
- **Queue shorthands:** `~ queue_bgm`, `~ queue_music`, `~ queue_sfx`, `~ queue_sound`, `~ queue_voice`, `~ queue_ambient`
- **Pause / Resume shorthands:** `~ pause_bgm` / `~ resume_bgm` (and `_music`, `_sfx`, `_sound`, `_voice`, `_ambient`)

---

## Asset Directory Layout

By default, Eager looks for an `assets/` folder next to your script (or project root), or you can pass `--asset-dir <path>`:

```text
assets/
├── bg/            # Background images (e.g. classroom_day.png)
├── characters/    # Character folders or sprites (e.g. hoshiko/smile.png)
└── audio/         # Music, sound effects, ambient, and voice files
```

Validate that every asset referenced in your script exists on disk:

```bash
uv run eager check my_story --assets
```
