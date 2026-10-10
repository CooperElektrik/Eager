# DSL Syntax Reference

`eager_script` screenplay scripts are plain UTF-8 text files (conventionally with a `.es` extension) designed to be human-readable, fast to write, and simple to parse.

---

## Quick Reference Table

| Syntax | Description | Example |
| :--- | :--- | :--- |
| `## Name --- id` | Scene/section label with explicit identifier | `## Ancient Ruins --- ruins` |
| `## Name` | Scene/section label with auto-generated slug ID | `## Great Hall` *(generates `great_hall`)* |
| `Speaker: Text` | Character dialogue beat | `Alice: Hello, traveler!` |
| `Speaker (emotion): Text` | Dialogue with character emotion/sprite tag | `Alice (happy): Welcome back!` |
| `Speaker: {voice:...} Text` | Dialogue with voice audio clip tag | `Alice: {voice:greet.ogg} Hello!` |
| `- Text` | Appends text beat to the current dialogue box | `- It has been a long journey.` |
| `/ Text` | Clears and starts a new dialogue box | `/ Look at this ancient map.` |
| `Speakerless lines` | Narration beat (consecutive lines grouped) | `A cold wind blows through the trees.` |
| `? Option (target_id)` | Choice option (consecutive choices form a menu) | `? Enter the cave (cave_entry)` |
| `> target_id` | Unconditional jump / goto label | `> ruins` |
| `>> target_id` | Subroutine call (pushes to call stack) | `>> inspect_artifact` |
| `<<` | Return from subroutine (pops call stack) | `<<` |
| `~ hook_name` | Trigger engine hook (SFX, event, camera shake) | `~ screen_shake` |
| `# Comment` | Standalone or inline comment (ignored by parser) | `# Setup sequence` |
| `\symbol` | Escapes special DSL prefixes (`\#`, `\:`, `\-`, etc.) | `Alice: Item \#1 costs \$5.` |

---

## Detailed Syntax Rules

### 1. Scene Labels (`##`)

Scenes divide your script into logical sections, acting as jump targets for navigation and branching:

- **Explicit Identifier**: `## Scene Title --- scene_id`  
  Specifies both the human-readable title and the technical target ID.
- **Auto-slugified Identifier**: `## Scene Title`  
  Automatically slugifies the title into lowercase snake_case (e.g. `## Grand Hall` becomes `grand_hall`).

### 2. Dialogue & Narration

- **Dialogue**: `Speaker: Text`  
  Identifies character speech. Can include an optional emotion tag in parentheses:
  ```es
  Alice (surprised): I didn't expect to see you here!
  ```
- **Voice Clips**: `{voice:clip_name.ogg}`  
  Can be attached immediately following the colon:
  ```es
  Bob: {voice:bob_greet.ogg} Good morning!
  ```
- **Append Beat (`-`)**: Appends text to the active dialogue box without advancing to a new box:
  ```es
  Alice: It was a dark night.
  - The stars were completely obscured.
  ```
- **Fresh Box Beat (`/`)**: Clears the current dialogue box and starts a new one under the same speaker:
  ```es
  Alice: Let me explain...
  / Here is what actually happened.
  ```
- **Narration**: Any lines without a speaker prefix are treated as narration. Consecutive narration lines are combined with spaces into a single beat until a blank line or other command is encountered.

### 3. Choices & Branching

- **Choice Options (`?`)**: Consecutive choice lines form a choice menu:
  ```es
  ? Agree to help the stranger (accept_quest)
  ? Politely decline and walk away (decline_quest)
  ```
- **Jumps (`>`)**: Directs execution to another scene label:
  ```es
  > peaceful_entry
  ```
- **Subroutine Calls (`>>`) & Returns (`<<`)**:
  Call a reusable scene and return back to the caller when done:
  ```es
  >> inventory_check
  > continue_journey

  ## Inventory Check --- inventory_check
  Narrator: Checking backpack...
  <<
  ```

### 4. Engine Hooks (`~`)

Trigger runtime events, camera shakes, sound effects, or custom logic in the game engine:

```es
~ play_bgm tavern.ogg
~ screen_shake
```

### 5. Comments & Escaping

- **Comments**: Lines starting with `#` are ignored by the parser. Inline comments preceded by whitespace (`text # comment`) are also stripped unless escaped.
- **Escaping**: If you need to use reserved characters (`#`, `:`, `?`, `-`, `>`, `/`, `~`, `\`, `<`) as literal text, escape them with a backslash:
  ```es
  Alice: Call \#1 cost \:5 dollars.
  ```

---

## Eager-SP Mode (`--plain`)

Designed for interactive fiction, branching gamebooks, and visual novels that read like natural literary manuscripts without engine syntax tags.

In `--plain` mode:
- **Natural scene headings only**: Must use `## Title` (e.g., `## The Hidden Room`). Explicit identifiers (`--- id`) are rejected.
- **Natural choice & jump targets**: `? Search room (The Hidden Room)` and `> The Hidden Room` target the natural title and are automatically slugified to match headings.
- **Paragraph dialogue continuation**: Lines under a character speaker continue that character's dialogue without needing `-`. A blank line ends the beat.
- **Engine markup disallowed**: Subroutines (`>>`, `<<`), engine hooks (`~`), text-box layout beats (`-`, `/`), and voice tags (`{voice:...}`) raise validation errors.
