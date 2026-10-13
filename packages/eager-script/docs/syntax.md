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
| `? Option (target_id) if cond` | Conditional choice option | `? Buy sword (armory) if gold >= 50` |
| `> target_id` | Unconditional jump / goto label | `> ruins` |
| `>> target_id` | Subroutine call (pushes to call stack) | `>> inspect_artifact` |
| `<<` | Return from subroutine (pops call stack) | `<<` |
| `@default name = expr` | Declare initial variable default in preamble | `@default gold = 100` |
| `@character id "Name" ...` | Declare character metadata in preamble | `@character alice "Alice" asset_prefix=ali` |
| `$ target = expr` | Assign or update story variable | `$ gold -= 25` |
| `@if expr` | Conditional block start | `@if affinity >= 10` |
| `@elif expr` | Alternative conditional branch | `@elif affinity > 0` |
| `@else` | Fallback conditional branch | `@else` |
| `@end` | End conditional block | `@end` |
| `[var_name]` | Variable text interpolation in dialogue/narration | `Alice: You have [gold] coins left.` |
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

### 3. Variables & Assignments (`@default`, `$`)

- **Default Variable Declarations (`@default`)**:
  Placed in the script preamble (before the first scene label) to initialize story state variables when a new game starts:
  ```es
  @default gold = 100
  @default has_key = False
  @default player_name = "Robin"
  ```
- **State Mutation (`$`)**:
  Mutate or reassign variables during script execution using standard or in-place assignment operators (`=`, `+=`, `-=`, `*=`, `/=`, `%=`):
  ```es
  $ gold += 50
  $ has_key = True
  $ reputation -= 5
  ```
- **Safe Expression Evaluator**:
  Expressions on the right-hand side of assignments and conditions are evaluated using an AST whitelist evaluator (`eager_script.expr`), preventing arbitrary code execution. Supported syntax includes:
  - Numeric literals, strings, and booleans (`True`, `False`, `None`)
  - Arithmetic operators (`+`, `-`, `*`, `/`, `//`, `%`)
  - Comparison operators (`==`, `!=`, `<`, `<=`, `>`, `>=`)
  - Boolean logic (`and`, `or`, `not`)
  - Safe whitelisted identifier lookups and dictionary access

### 4. Character Declarations (`@character`)

Declare characters and presentation metadata in the script preamble:

```es
@character alice "Alice" asset_prefix=alice_uniform color="#ff77aa" default_expression=smile
@character bob "Bob" asset_prefix=bob_casual side_image=bob_side.png
```

Supported attributes:
- `"Display Name"`: Human-readable name used when rendering dialogue boxes.
- `asset_prefix`: File name prefix used by the graphics engine to locate character sprite files (e.g. `alice_uniform_smile.png`).
- `color`: Hex color used for speaker names in the UI.
- `default_expression`: Sprite expression to use if none is explicitly specified in a `~ show` hook.
- `side_image`: Side image sprite rendered next to the text box.

### 5. Conditionals & Flow Control (`@if`, `@elif`, `@else`, `@end`)

Direct script execution conditionally based on evaluated expressions:

```es
@if gold >= 100
  Alice (smile): That will be 100 gold coins, please!
  $ gold -= 100
  $ has_ticket = True
@elif gold >= 50
  Alice (thinking): You're short on funds, but I can offer a discount today.
  $ gold -= 50
  $ has_ticket = True
@else
  Alice (sad): I'm sorry, you don't have enough money.
@end
```

Conditional blocks may be nested. During scene graph construction, conditional blocks are lowered into flat, deterministic jump beats (`ParsedCondJump` and `ParsedLocalJump`), preserving compatibility with the headless virtual machine.

### 6. Choices & Branching

- **Standard Choice Options (`?`)**: Consecutive choice lines form an interactive choice menu:
  ```es
  ? Agree to help the stranger (accept_quest)
  ? Politely decline and walk away (decline_quest)
  ```
- **Conditional Choices (`if`)**: Append an `if` expression to conditionally show or hide a choice based on current game state:
  ```es
  ? Buy masterwork sword (buy_sword) if gold >= 150
  ? Pick the locked chest (unlock_chest) if has_lockpick
  ? Search for another path (detour)
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

### 7. Variable Interpolation (`[var]`)

Variables can be dynamically inserted into dialogue, narration, choices, and engine hook arguments using square brackets:

```es
Alice: Welcome back, [player_name]!
Narrator: You have [gold] coins and [reputation] reputation points.
```

- **Nested Dictionary Access**: `[player.inventory.weapon]`
- **Escaping Brackets**: Use double brackets `[[` and `]]` to output literal square brackets:
  ```es
  Narrator: Press [[Space]] or [[Enter]] to advance the story.
  ```

### 8. Engine Hooks (`~`)

Trigger runtime events, camera shakes, sound effects, or visual presentation commands:

```es
~ bg classroom_day with crossfade duration=1.0
~ show alice smile at center
~ play bgm school_theme.ogg
~ screen_shake intensity=1.5 duration=0.3
```

### 9. Comments & Escaping

- **Comments**: Lines starting with `#` are ignored by the parser. Inline comments preceded by whitespace (`text # comment`) are also stripped unless escaped.
- **Escaping**: If you need to use reserved characters (`#`, `:`, `?`, `-`, `>`, `/`, `~`, `\`, `<`, `@`, `$`) as literal text, escape them with a backslash:
  ```es
  Alice: Call \#1 cost \$5 dollars.
  ```

---

## Eager-SP Mode (`--plain`)

Designed for interactive fiction, branching gamebooks, and visual novels that read like natural literary manuscripts without engine syntax tags.

In `--plain` mode:
- **Natural scene headings only**: Must use `## Title` (e.g., `## The Hidden Room`). Explicit identifiers (`--- id`) are rejected.
- **Natural choice & jump targets**: `? Search room (The Hidden Room)` and `> The Hidden Room` target the natural title and are automatically slugified to match headings.
- **Paragraph dialogue continuation**: Lines under a character speaker continue that character's dialogue without needing `-`. A blank line ends the beat.
- **Engine markup disallowed**: Subroutines (`>>`, `<<`), engine hooks (`~`), text-box layout beats (`-`, `/`), voice tags (`{voice:...}`), preamble directives (`@default`, `@character`), variable assignments (`$`), conditional blocks (`@if`, `@elif`, `@else`, `@end`), and conditional choices (`if ...`) raise validation errors.
