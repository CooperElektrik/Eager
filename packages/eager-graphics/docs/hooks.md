# Screenplay Hook Reference

Writers control visual staging, character placement, transitions, and camera effects using Eager-Script engine hooks (`~`).

---

## 1. Hook Argument Syntax

Hook arguments support both positional tokens and key-value pairs:

```es
~ command [positional_args...] [key=value...]
```

Special keyword markers:
- `at <position>`: Specifies stage position (e.g. `at left`, `at center`).
- `with <transition>`: Specifies transition effect (e.g. `with fade`, `with crossfade`).
- `to <position>`: Specifies target position for moves (e.g. `to right`).
- `duration=<seconds>`: Animation duration in seconds (float).
- `easing=<name>`: Easing curve function name.
- `color=<hex>`: Color code (e.g. `#ffffff`, `#000000`).
- `intensity=<number>`: Intensity factor (e.g. for shake).

---

## 2. Background Hooks

### `~ bg <asset_name> [with <transition>] [duration=<seconds>]`
Swaps the active environment background. If a transition is specified, the incoming background crossfades over the outgoing one.

```es
# Instant background cut
~ bg castle_courtyard with cut

# Smooth 1.0s crossfade
~ bg great_hall with crossfade duration=1.0

# 1.5s dissolve
~ bg forest_night with dissolve duration=1.5
```

Asset convention: `bg/<asset_name>`.

### `~ bg_clear [with <transition>] [duration=<seconds>]`
Clears the active background.

```es
~ bg_clear with fade duration=0.5
```

### `~ scene <asset_name> [with <transition>] [duration=<seconds>]`
Starts a new scene: removes every character sprite from the stage, then sets the background exactly like `~ bg` (same arguments and asset convention).

```es
~ scene rooftop_dawn with crossfade duration=1.0
```

---

## 3. Character Sprite Hooks

### `~ show <character> [<expression>] [at <position>] [with <transition>] [duration=<seconds>] [flip=true|false]`
Places a character on the stage or updates an existing character.

```es
# Show at center with default expression
~ show alice

# Show at left with specific expression and slide transition
~ show alice happy at left with slide_right duration=0.5

# Instant appearance
~ show guard stern at right with cut

# Flipped horizontally
~ show bob smiling at center_left flip=true
```

Built-in positions:
- `left` (25% width)
- `center_left` (37.5% width)
- `center` (50% width)
- `center_right` (62.5% width)
- `right` (75% width)

Asset convention: `<character>/<expression>`.

### `~ hide <character> [with <transition>] [duration=<seconds>]`
Fades out or removes a character from the stage.

```es
~ hide guard with dissolve duration=0.4
~ hide alice with cut
```

### `~ move <character> to <position> [duration=<seconds>] [easing=<curve>]`
Tweens a character from their current position to a new stage position.

```es
~ move alice to center duration=0.8 easing=ease_in_out_quad
~ move bob to right duration=0.5
```

### `~ expr <character> <expression>`
Changes a character's expression without affecting their position or playing enter/exit transitions.

```es
~ expr alice surprised
```

### `~ image <name> <asset> [at <position>] [z=<int>]`
Places an arbitrary named image on the foreground layer (props, overlays, letterbox bars). Unlike `~ show`, the element is not tied to a character. Defaults: `at center`, `z=50`. The asset ID is used verbatim (no prefix added); positions are the same named set as `~ show`.

```es
~ image letterbox_top black_bar at center
~ image clue_photo photo_clue at right z=60
```

---

## 4. Dialogue Emotion Auto-Sync

When a speaker has an emotion tag in dialogue:

```es
Alice (worried): Are you sure about this?
```

`StageDirector` automatically detects the emotion tag and updates Alice's active sprite expression to `worried` (`alice/worried`). Writers do not need to manually write `~ expr alice worried`.

---

## 5. Camera & Screen Effects

### `~ shake [intensity=<float>] [duration=<seconds>]`
Triggers camera screen shake. Affects background and character layers while leaving UI and textboxes stable.

```es
~ shake intensity=2.0 duration=0.4
```

### `~ flash [duration=<seconds>] [color=<hex>]`
Flashes the screen with a color that quickly fades out.

```es
~ flash duration=0.2 color=#ffffff
~ flash duration=0.3 color=#ff0000
```

### `~ fade_out [duration=<seconds>] [color=<hex>]`
Fades the screen overlay to a solid color.

```es
~ fade_out duration=1.0 color=#000000
```

### `~ fade_in [duration=<seconds>]`
Fades the screen overlay from solid color to fully transparent.

```es
~ fade_in duration=1.0
```

---

## 6. Transitions & Easing Curves

### Supported Transitions
- `cut`: Immediate switch (duration 0).
- `fade`: Opacity tween.
- `crossfade`: Overlapping opacity fade.
- `dissolve`: Smooth dissolve fade (currently implemented identically to `crossfade`; a future release may add a noise-mask dissolve pattern).
- `slide_left`: Enters sliding towards the left.
- `slide_right`: Enters sliding towards the right.
- `slide_up`: Enters sliding upwards.
- `slide_down`: Enters sliding downwards.

### Supported Easing Curves
- `linear`
- `ease_in_quad`, `ease_out_quad`, `ease_in_out_quad`
- `ease_in_cubic`, `ease_out_cubic`, `ease_in_out_cubic`
- `ease_in_quart`, `ease_out_quart`, `ease_in_out_quart`
- `ease_in_sine`, `ease_out_sine`, `ease_in_out_sine`
- `ease_in_expo`, `ease_out_expo`, `ease_in_out_expo`
- `ease_in_back`, `ease_out_back`, `ease_in_out_back`
- `ease_in_bounce`, `ease_out_bounce`, `ease_in_out_bounce`

---

## 7. Audio Hooks

Audio hooks drive the injected `AudioMixer` over its channels (`music`, `ambient`, `sound`, `voice`, plus custom channels). They are no-ops when no mixer is attached (e.g. pure headless runs).

### `~ play <channel> <track> [fade=<seconds>] [volume=<level>] [loop=true|false] [loop_start=<seconds>] [loop_end=<seconds>]`
Plays a track on a channel. `fade` (also accepted as `fade_in`) fades the volume in over that many seconds; `volume` defaults to `1.0`. `loop` overrides the channel default (`music`/`ambient` loop; `sound`/`voice` do not). `loop_start` and `loop_end` specify intro-to-loop seamless boundaries in seconds.

```es
~ play music theme.ogg fade=2.0 volume=0.8 loop=true loop_start=12.5 loop_end=95.0
~ play sound thunder.ogg
~ play voice greeting.ogg volume=1.0
```

### Voice Playback & Management
When dialogue events specify a voice tag (e.g. `{voice=alice_01.ogg}`), `StageDirector` automatically plays the audio clip on the `voice` channel. When subsequent dialogue lines or narration events lack voice tags, the voice channel is automatically stopped to prevent audio bleed. Exiting scenes or ending the story also stops any active voice clip.

During fast skip mode (`skip_mode`), one-shot sound effects (`sound`) and voice playback (`voice`) are automatically suppressed, while background music (`music`) and ambient tracks continue playing.

### `~ stop [<channel>|all] [fade=<seconds>]`
Stops a channel, or every channel with `all` (the default when no channel is given). `fade` (also accepted as `fade_out`) fades out over that many seconds.

```es
~ stop music fade=1.5
~ stop all
```

### `~ volume <channel> <level>`
Sets a channel's volume immediately (`0.0`–`1.0`).

```es
~ volume music 0.5
```

---

## 8. NVL Mode

NVL mode replaces the single dialogue box with a full-screen scrolling backlog: while it is on, dialogue and narration lines accumulate in `UIState.nvl_entries` instead of only filling the textbox.

### `~ nvl [on|off|clear]`
Enables NVL mode (the default when no argument is given). `off` (also `false`, `0`) returns to dialogue-box (ADV) mode. `clear` wipes the NVL backlog without changing the mode.

```es
~ nvl
~ nvl off
~ nvl clear
```

### `~ nvl_clear`
Clears the NVL backlog.

```es
~ nvl_clear
```
